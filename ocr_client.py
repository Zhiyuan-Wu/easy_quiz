import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List

import requests

from config import EMBEDDING_CONFIG
from utils import convert_pdf_to_images

class DeepSeekOCRClient:
    """DeepSeek OCR 与向量服务的轻量级客户端。"""
    def __init__(self, base_url: str = "http://localhost:5000"):
        """初始化 OCR 客户端。

        参数:
            base_url: OCR 服务的根地址，例如 "http://localhost:5000"。

        返回:
            None。
        """
        self.base_url = base_url.rstrip('/')
        self.ocr_endpoint = f"{self.base_url}/ocr"

    def ocr_image(self, image_path: str) -> Dict[str, Any]:
        """上传本地图片或 PDF 并获取 OCR 结果（Markdown 格式）。

        参数:
            image_path: 本地图片 / PDF 路径，支持 PNG、JPG、PDF（多页）。

        返回:
            包含 `request_id`、`markdown` 与 `images` 的字典。

        异常:
            requests.HTTPError, FileNotFoundError, ValueError。
        """
        path_obj = Path(image_path)
        if not path_obj.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        suffix = path_obj.suffix.lower()
        if suffix == ".pdf":
            return self._ocr_pdf(path_obj)
        if suffix not in {".png", ".jpg", ".jpeg"}:
            raise ValueError("Only PNG/JPG images or PDF documents are supported")

        return self._ocr_single_image(path_obj)

    def _ocr_single_image(self, image_path: Path) -> Dict[str, Any]:
        """对单张图片执行 OCR 请求。"""
        with open(image_path, "rb") as file_obj:
            files = {"file": (image_path.name, file_obj, "image/png")}
            response = requests.post(self.ocr_endpoint, files=files)

        response.raise_for_status()
        return response.json()

    def _ocr_pdf(self, pdf_path: Path) -> Dict[str, Any]:
        """将 PDF 拆分为页面并合并 OCR 结果。"""
        pdf_hash = self._hash_file(pdf_path)
        markdown_segments: List[str] = []
        all_images: List[Dict[str, Any]] = []
        page_details: List[Dict[str, Any]] = []

        with TemporaryDirectory(prefix="ocr_pdf_") as temp_dir:
            page_images = convert_pdf_to_images(str(pdf_path), temp_dir)
            if not page_images:
                return {
                    "request_id": f"{pdf_hash}_pdf",
                    "markdown": "",
                    "text": "",
                    "images": [],
                    "pages": [],
                }

            for page_index, image_path in page_images:
                page_result = self._ocr_single_image(Path(image_path))
                page_markdown = page_result.get("markdown") or page_result.get("text") or ""
                page_images_data = page_result.get("images") or []

                if page_markdown.strip():
                    markdown_segments.append(page_markdown.strip())
                if page_images_data:
                    all_images.extend(page_images_data)

                page_details.append(
                    {
                        "page": page_index,
                        "request_id": page_result.get("request_id"),
                        "markdown": page_markdown,
                        "images": page_images_data,
                    }
                )

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
        """计算文件内容的短哈希值。"""
        hasher = hashlib.sha256()
        with open(path, "rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:32]
    
    def get_embeddings(self, texts: list) -> list:
        """获取文本的 embedding 向量。

        参数:
            texts: 文本列表，例如 ["First sentence", "Second sentence"]。

        返回:
            embedding 向量列表，每个元素为浮点数组。

        异常:
            requests.HTTPError, ValueError。
        """
        url = EMBEDDING_CONFIG["api_url"]
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "model": EMBEDDING_CONFIG["model"],
            "input": texts
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        result = response.json()
        if "embeddings" in result:
            return result["embeddings"]
        else:
            raise ValueError("Invalid response format from embedding API")


# ----------------------------
# 使用示例
# ----------------------------
if __name__ == "__main__":
    client = DeepSeekOCRClient("http://192.168.31.65:5000")
    try:
        result = client.ocr_image("test.png")
        print("Request ID:", result["request_id"])
        print("Markdown Result:\n")
        print(result["markdown"])
    except Exception as e:
        print("Error:", e)