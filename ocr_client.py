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

from config import EMBEDDING_CONFIG
from utils import convert_pdf_to_images

RAW_MATCH_PATTERN = re.compile(
    r"(<\|ref\|>(?P<label>.*?)<\|/ref\|><\|det\|>(?P<det>.*?)<\|/det\|>)",
    re.DOTALL,
)
RAW_STOP_TOKEN = "<｜end▁of▁sentence｜>"


def _clean_raw_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    text = raw_text.strip()
    if text.endswith(RAW_STOP_TOKEN):
        text = text[: -len(RAW_STOP_TOKEN)]
    return text.strip()


def _parse_detection(det_text: str) -> List[Tuple[float, float, float, float]]:
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
        self.base_url = base_url.rstrip("/")
        self.ocr_endpoint = f"{self.base_url}/ocr"

    async def ocr_image_async(
        self,
        image_path: str,
        *,
        mode: Literal["processed", "raw"] = "processed",
        output_dir: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
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
        form = aiohttp.FormData()
        form.add_field("file", image_path.read_bytes(), filename=image_path.name, content_type="image/png")

        endpoint = f"{self.ocr_endpoint}?mode={mode}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
            async with session.post(endpoint, data=form) as response:
                response.raise_for_status()
                payload = await response.json()

        request_id = payload.get("request_id")
        if not request_id:
            raise ValueError("OCR service did not return request_id")

        if mode == "processed":
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

        raw_text = _clean_raw_text(payload.get("raw_text", ""))
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
            "raw": payload,
        }

    async def _ocr_pdf_async(
        self,
        pdf_path: Path,
        *,
        mode: Literal["processed", "raw"],
        output_dir: Optional[str | Path],
    ) -> Dict[str, Any]:
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
        hasher = hashlib.sha256()
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:32]

    async def get_embeddings_async(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        payload = {
            "model": EMBEDDING_CONFIG["model"],
            "input": texts,
        }

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
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
        """同步包装，以便在非异步环境中复用。"""
        return asyncio.run(
            self.ocr_image_async(image_path, mode=mode, output_dir=output_dir)
        )

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """同步包装，以兼容旧的调用路径。"""
        return asyncio.run(self.get_embeddings_async(texts))


async def _demo() -> None:  # pragma: no cover - manual test helper
    client = DeepSeekOCRClient("http://127.0.0.1:5000")
    try:
        result = await client.ocr_image("test.png", mode="raw")
        print("Request ID:", result["request_id"])
        print("Markdown Result:\n", result["markdown"])
    finally:
        pass


if __name__ == "__main__":  # pragma: no cover - manual test helper
    asyncio.run(_demo())