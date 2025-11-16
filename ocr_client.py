from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

import aiohttp
import anyio
from PIL import Image

from config import EMBEDDING_CONFIG, RAW_OCR_CONFIG
from utils import convert_pdf_to_images

RAW_MATCH_PATTERN = re.compile(
    r"(<\|ref\|>(?P<label>.*?)<\|/ref\|><\|det\|>(?P<det>.*?)<\|/det\|>)",
    re.DOTALL,
)
RAW_STOP_TOKEN = "<｜end▁of▁sentence｜>"


def _clean_raw_text(raw_text: str) -> str:
    """Normalize raw model output by trimming control tokens and whitespace.

    Parameters:
        raw_text: 原始的模型响应文本。

    Returns:
        去除停用符号并裁剪后的文本内容。
    """
    if not raw_text:
        return ""
    text = raw_text.strip()
    if text.endswith(RAW_STOP_TOKEN):
        text = text[: -len(RAW_STOP_TOKEN)]
    return text.strip()


def _parse_detection(det_text: str) -> List[Tuple[float, float, float, float]]:
    """Parse detection tokens into bounding box tuples.

    Parameters:
        det_text: 包含坐标信息的 JSON 或列表字符串。

    Returns:
        归一化坐标的列表，格式为 (x1, y1, x2, y2)。
    """
    try:
        parsed = json.loads(det_text)
    except json.JSONDecodeError:
        parsed = eval(det_text, {"__builtins__": {}})  # noqa: S307

    boxes: List[Tuple[float, float, float, float]] = []
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, (list, tuple)) and len(item) == 4:
                try:
                    boxes.append(tuple(float(v) for v in item))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
    return boxes


def _scale_box(
    box: Tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> Tuple[int, int, int, int]:
    """Scale normalized coordinates to pixel positions.

    Parameters:
        box: 归一化的左上角和右下角坐标。
        image_width: 图像宽度（像素）。
        image_height: 图像高度（像素）。

    Returns:
        对应的整数像素坐标 (x1, y1, x2, y2)。
    """
    x1, y1, x2, y2 = box
    x1 = int(max(0, min(image_width, round(x1 / 999 * image_width))))
    y1 = int(max(0, min(image_height, round(y1 / 999 * image_height))))
    x2 = int(max(0, min(image_width, round(x2 / 999 * image_width))))
    y2 = int(max(0, min(image_height, round(y2 / 999 * image_height))))

    if x2 <= x1:
        x2 = min(image_width, x1 + 1)
    if y2 <= y1:
        y2 = min(image_height, y1 + 1)
    return x1, y1, x2, y2


def _collect_annotations(raw_text: str) -> List[Dict[str, Any]]:
    """Collect control annotations from raw text output.

    Parameters:
        raw_text: 包含控制标记的模型输出。

    Returns:
        解析后的注释列表，每项包含标签、坐标和原始文本。
    """
    annotations: List[Dict[str, Any]] = []
    for match in RAW_MATCH_PATTERN.finditer(raw_text):
        label = match.group("label").strip()
        det_text = match.group("det").strip()
        boxes = _parse_detection(det_text)
        annotations.append(
            {
                "label": label,
                "boxes": boxes,
                "raw": match.group(0),
            }
        )
    return annotations


def _crop_images_from_annotations(
    image_path: Path,
    annotations: Iterable[Dict[str, Any]],
    *,
    output_dir: Optional[Path] = None,
) -> Tuple[List[Dict[str, str]], Dict[str, str]]:
    """Crop image regions referenced by annotations.

    Parameters:
        image_path: 原始图像路径。
        annotations: 控制标签解析结果。
        output_dir: 可选的输出目录，用于保存裁剪图像。

    Returns:
        Tuple，其中包含编码后的裁剪图像列表以及替换引用的映射字典。
    """
    with Image.open(image_path) as image:
        image = image.convert("RGB")
        width, height = image.size

        output_images_dir: Optional[Path] = None
        if output_dir:
            output_images_dir = output_dir / "images"
            output_images_dir.mkdir(parents=True, exist_ok=True)

        cropped_images: List[Dict[str, str]] = []
        replacements: Dict[str, str] = {}

        for annotation in annotations:
            if annotation["label"].lower() != "image" or not annotation["boxes"]:
                continue

            first_image_index = len(cropped_images)
            for box in annotation["boxes"]:
                x1, y1, x2, y2 = _scale_box(box, width, height)
                cropped = image.crop((x1, y1, x2, y2))

                buffer = BytesIO()
                cropped.save(buffer, format="JPEG", quality=90)
                buffer.seek(0)

                filename = f"{len(cropped_images)}.jpg"
                base64_data = base64.b64encode(buffer.read()).decode("utf-8")
                cropped_images.append(
                    {
                        "filename": filename,
                        "data": base64_data,
                    }
                )

                if output_images_dir:
                    (output_images_dir / filename).write_bytes(base64.b64decode(base64_data))

            replacements[annotation["raw"]] = f"![](images/{first_image_index}.jpg)\n"

        return cropped_images, replacements


def _purge_control_tokens(raw_text: str, annotations: List[Dict[str, Any]], replacements: Dict[str, str]) -> str:
    """Remove control tokens and apply replacements to produce Markdown text.

    Parameters:
        raw_text: 原始模型输出。
        annotations: 解析的注释列表。
        replacements: 需要替换的文本映射。

    Returns:
        清理并替换后的 Markdown 文本。
    """
    processed = raw_text
    for annotation in annotations:
        if annotation["raw"] in replacements:
            processed = processed.replace(annotation["raw"], replacements[annotation["raw"]])
        else:
            processed = processed.replace(annotation["raw"], "")

    processed = processed.replace("\\coloneqq", ":=").replace("\\eqqcolon", "=:")
    processed = re.sub(r"\n{3,}", "\n\n", processed)
    return processed.strip()


class DeepSeekOCRClient:
    """DeepSeek OCR 与向量服务的异步客户端。"""

    def __init__(self, base_url: str = "http://localhost:5000") -> None:
        """初始化 OCR 客户端实例。

        Parameters:
            base_url: OCR 服务基础 URL。
        """
        self.base_url = base_url.rstrip("/")
        self.ocr_endpoint = f"{self.base_url}/ocr"

    async def ocr_image_async(
        self,
        image_path: str,
        *,
        mode: Literal["processed", "raw"] = "processed",
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        """Execute OCR on a single image or PDF page asynchronously.

        Parameters:
            image_path: 输入图像或 PDF 文件路径。
            mode: 输出模式，`processed` 或 `raw`。
            output_dir: 可选的输出目录，用于保存裁剪图像。

        Returns:
            OCR 结果字典，包括 markdown、images 以及分页详情。

        Raises:
            FileNotFoundError: 当路径不存在时抛出。
            ValueError: 当文件类型不受支持时抛出。
        """
        path_obj = Path(image_path)
        if not path_obj.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        suffix = path_obj.suffix.lower()
        if suffix == ".pdf":
            return await self._ocr_pdf_async(path_obj, mode=mode, output_dir=output_dir)
        if suffix not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("Only PNG/JPG images or PDF documents are supported")

        page = await self._ocr_single_image_async(
            path_obj,
            page_number=1,
            suggested_suffix="",
            mode=mode,
            output_dir=output_dir,
        )
        return {
            "request_id": page["request_id"],
            "markdown": page["markdown"],
            "text": page["markdown"],
            "images": page["images"],
            "pages": [page],
        }

    async def _ocr_single_image_async(
        self,
        image_path: Path,
        *,
        page_number: Optional[int],
        suggested_suffix: str,
        mode: Literal["processed", "raw"],
        output_dir: Optional[str | Path],
    ) -> Dict[str, Any]:
        """Submit a single image for OCR and format the response.

        Parameters:
            image_path: 输入图像路径。
            page_number: 页码信息，可选。
            suggested_suffix: 推荐的文件名后缀。
            mode: 输出模式。
            output_dir: 可选的裁剪图像输出目录。

        Returns:
            单页 OCR 结果字典。
        """
        if mode == "raw":
            # Raw mode: 使用 generate 接口
            image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
            payload = {
                "model": RAW_OCR_CONFIG["model"],
                "image": [f"data:image/jpeg;base64,{image_data}"],
                "prompt": RAW_OCR_CONFIG["prompt"]
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    RAW_OCR_CONFIG["api_url"],
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    response.raise_for_status()
                    raw_payload = await response.json()
            
            # 从 raw_payload 中提取 text 字段作为 raw_text
            raw_text = _clean_raw_text(raw_payload.get("text", ""))
            # 生成一个 request_id（基于文件内容哈希）
            request_id = self._hash_file(image_path)
            
            annotations = _collect_annotations(raw_text)
            output_dir_path = Path(output_dir) if output_dir else None

            cropped_images, image_replacements = await anyio.to_thread.run_sync(
                _crop_images_from_annotations,
                image_path,
                annotations,
                output_dir=output_dir_path,
                limiter=None,
            )

            processed_markdown = _purge_control_tokens(raw_text, annotations, image_replacements)

            return {
                "page": page_number,
                "request_id": request_id,
                "markdown": processed_markdown,
                "images": cropped_images,
                "suggested_suffix": suggested_suffix,
                "raw": raw_payload,
            }
        else:
            # Processed mode: 使用 ocr server 的 /ocr 接口（不带 mode 参数）
            form = aiohttp.FormData()
            form.add_field("file", image_path.read_bytes(), filename=image_path.name, content_type="image/png")

            async with aiohttp.ClientSession() as session:
                async with session.post(self.ocr_endpoint, data=form) as response:
                    response.raise_for_status()
                    payload = await response.json()

            request_id = payload.get("request_id")
            if not request_id:
                raise ValueError("OCR service did not return request_id")

            markdown = payload.get("markdown") or payload.get("text") or ""
            images = payload.get("images") or []
            return {
                "page": page_number,
                "request_id": request_id,
                "markdown": markdown,
                "images": images,
                "suggested_suffix": suggested_suffix,
                "raw": payload,
            }

    async def _ocr_pdf_async(
        self,
        pdf_path: Path,
        *,
        mode: Literal["processed", "raw"],
        output_dir: Optional[str | Path],
    ) -> Dict[str, Any]:
        """Perform OCR on each page of a PDF and merge the outputs.

        Parameters:
            pdf_path: PDF 文件路径。
            mode: 输出模式。
            output_dir: 可选的输出目录。

        Returns:
            聚合后的 OCR 结果字典。
        """
        pdf_hash = await anyio.to_thread.run_sync(self._hash_file, pdf_path, limiter=None)

        markdown_segments: List[str] = []
        all_images: List[Dict[str, Any]] = []
        page_details: List[Dict[str, Any]] = []

        with TemporaryDirectory(prefix="ocr_pdf_") as temp_dir:
            page_images = await anyio.to_thread.run_sync(
                convert_pdf_to_images,
                str(pdf_path),
                temp_dir,
                limiter=None,
            )
            if not page_images:
                return {
                    "request_id": f"{pdf_hash}_pdf",
                    "markdown": "",
                    "text": "",
                    "images": [],
                    "pages": [],
                }

            for page_index, image_path in page_images:
                suggested_suffix = f"_p{page_index}"
                page_result = await self._ocr_single_image_async(
                    Path(image_path),
                    page_number=page_index,
                    suggested_suffix=suggested_suffix,
                    mode=mode,
                    output_dir=output_dir,
                )
                page_markdown = page_result.get("markdown") or ""
                page_images_data = page_result.get("images") or []

                if page_markdown.strip():
                    markdown_segments.append(page_markdown.strip())
                if page_images_data:
                    all_images.extend(page_images_data)

                page_details.append(page_result)

        combined_markdown = "\n\n".join(markdown_segments)
        return {
            "request_id": f"{pdf_hash}_pdf",
            "markdown": combined_markdown,
            "text": combined_markdown,
            "images": all_images,
            "pages": page_details,
        }

    @staticmethod
    def _hash_file(path: Path) -> str:
        """Return a short hash identifier for the given file.

        Parameters:
            path: 文件路径。

        Returns:
            32 位十六进制哈希前缀。
        """
        hasher = hashlib.sha256()
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:32]

    async def get_embeddings_async(self, texts: List[str]) -> List[List[float]]:
        """Request embedding vectors for a batch of texts。

        Parameters:
            texts: 待编码文本列表。

        Returns:
            浮点向量列表。
        """
        if not texts:
            return []

        payload = {
            "model": EMBEDDING_CONFIG["model"],
            "input": texts,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                EMBEDDING_CONFIG["api_url"],
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                response.raise_for_status()
                data = await response.json()

        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list):
            raise ValueError("Invalid response format from embedding API")
        return embeddings

    def ocr_image(
        self,
        image_path: str,
        *,
        mode: Literal["processed", "raw"] = "processed",
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        """同步包装，以便在非异步环境中复用。

        Parameters:
            image_path: 输入图像或 PDF 的路径。
            mode: OCR 输出模式，默认为 `processed`。
            output_dir: 可选的输出目录，保存裁剪图像。

        Returns:
            与 `ocr_image_async` 相同结构的 OCR 结果字典。
        """
        return asyncio.run(
            self.ocr_image_async(image_path, mode=mode, output_dir=output_dir)
        )

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """同步包装，以兼容旧的调用路径。

        Parameters:
            texts: 待编码的文本列表。

        Returns:
            对应的嵌入向量列表。
        """
        return asyncio.run(self.get_embeddings_async(texts))


async def _demo() -> None:  # pragma: no cover - manual test helper
    """Minimal interactive demo for the OCR client."""
    client = DeepSeekOCRClient("http://127.0.0.1:5000")
    try:
        result = await client.ocr_image("test.png", mode="raw")
        print("Request ID:", result["request_id"])
        print("Markdown Result:\n", result["markdown"])
    finally:
        pass


if __name__ == "__main__":  # pragma: no cover - manual test helper
    asyncio.run(_demo())