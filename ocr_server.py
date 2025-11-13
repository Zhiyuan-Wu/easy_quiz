from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional

import anyio
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from transformers import AutoModel, AutoTokenizer

# ----------------------------
# 配置
# ----------------------------
MODEL_PATH = os.getenv("OCR_MODEL_PATH", r"C:\dev\DeepSeek-OCR")
DEVICE = os.getenv("OCR_DEVICE", "cpu")

print("Loading OCR model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
model = AutoModel.from_pretrained(
    MODEL_PATH,
    _attn_implementation="eager",
    trust_remote_code=True,
    use_safetensors=True,
)
model = model.eval().to(DEVICE)
print("Model loaded.")

app = FastAPI(
    title="DeepSeek OCR Service",
    description="文档 OCR 识别服务，支持处理模式切换。",
    version="2.0.0",
)

RESULT_BASE = Path("results")
RESULT_BASE.mkdir(exist_ok=True)


def _load_cached_result(request_dir: Path, raw_mode: bool) -> Optional[Dict[str, object]]:
    mmd_file = request_dir / "result.mmd"
    if not mmd_file.exists():
        return None

    content = mmd_file.read_text(encoding="utf-8")

    if raw_mode:
        return {
            "request_id": request_dir.name,
            "raw_text": content,
        }

    images_dir = request_dir / "images"
    image_data: List[Dict[str, str]] = []
    if images_dir.exists():
        for ext in ("*.jpg", "*.png"):
            for img_file in sorted(images_dir.glob(ext)):
                image_data.append(
                    {
                        "filename": img_file.name,
                        "data": base64.b64encode(img_file.read_bytes()).decode("utf-8"),
                    }
                )

    return {
        "request_id": request_dir.name,
        "markdown": content,
        "images": image_data,
    }


def _run_inference(input_image_path: Path, request_dir: Path) -> str:
    prompt = "<image>\n<|grounding|>Convert the document to markdown."

    model.infer(
        tokenizer=tokenizer,
        prompt=prompt,
        image_file=str(input_image_path),
        output_path=str(request_dir),
        base_size=1024,
        image_size=640,
        crop_mode=True,
        test_compress=True,
        save_results=True,
    )

    mmd_file = request_dir / "result.mmd"
    if not mmd_file.exists():
        raise RuntimeError("OCR inference finished without generating result.mmd")

    return mmd_file.read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    """服务状态页面。"""
    return """
    <h2>✅ DeepSeek-OCR Service is Running!</h2>
    <p>Use <code>POST /ocr</code> with a PNG/JPG file to perform OCR.</p>
    <p>Example: <code>curl -F "file=@image.png" http://localhost:5000/ocr</code></p>
    """


@app.post("/ocr")
async def ocr_endpoint(
    file: UploadFile = File(...),
    mode: str = "processed",
) -> Dict[str, object]:
    """
    处理图片上传，执行 OCR 并返回结果。

    mode:
        - processed: 返回 markdown + image patches（旧模式）
        - raw: 返回原始模型输出，由客户端处理
    """
    filename = file.filename or ""
    if not filename.lower().endswith((".png", ".jpg", ".jpeg")):
        raise HTTPException(status_code=400, detail="Only PNG/JPG images are allowed")

    file_content = await file.read()
    if not file_content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    image_hash = hashlib.sha256(file_content).hexdigest()[:32]
    request_dir = RESULT_BASE / image_hash
    request_dir.mkdir(parents=True, exist_ok=True)
    input_image_path = request_dir / "input.png"
    input_image_path.write_bytes(file_content)

    raw_mode = mode.lower() == "raw"

    cached = _load_cached_result(request_dir, raw_mode)
    if cached:
        return cached

    try:
        await anyio.to_thread.run_sync(_run_inference, input_image_path, request_dir, limiter=None)
    except Exception as exc:  # noqa: BLE001
        # 清理失败的缓存目录
        for child in request_dir.glob("*"):
            if child.is_file():
                child.unlink(missing_ok=True)
            else:
                for sub in child.glob("**/*"):
                    if sub.is_file():
                        sub.unlink(missing_ok=True)
                child.rmdir()
        request_dir.rmdir()
        raise HTTPException(status_code=500, detail=f"OCR inference failed: {exc}") from exc

    result = _load_cached_result(request_dir, raw_mode)
    if result is None:
        raise HTTPException(status_code=500, detail="OCR inference produced no result")

    return result


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    """健康检查端点。"""
    return {"status": "ok"}


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    import uvicorn

    uvicorn.run("ocr_server:app", host="0.0.0.0", port=5000, reload=False)