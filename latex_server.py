from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import anyio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    from config import LATEX_CLASS_PATH
except ImportError:  # pragma: no cover - fallback for partially configured envs
    LATEX_CLASS_PATH = "resources/exam-zh.cls"


class CompileRequest(BaseModel):
    latex_content: str = Field(..., description="完整的 LaTeX 源文档内容")
    dependencies: Dict[str, Dict[str, str]] = Field(
        default_factory=dict,
        description="附带的依赖文件，例如图片等",
    )
    compile_recipe: Optional[List[List[str]]] = Field(
        default=None,
        description="自定义编译指令序列",
    )


app = FastAPI(
    title="DeepSeek LaTeX Service",
    description="独立的 LaTeX 编译服务，将 LaTeX 内容转换为 PDF。",
    version="1.0.0",
)


async def _compile_latex(payload: CompileRequest) -> Dict[str, Any]:
    """Compile LaTeX content on a worker thread.

    Parameters:
        payload: Validated request body describing the LaTeX source,
            optional dependencies and compilation recipe.

    Returns:
        包含 `success` 字段和可选 `pdf_base64` 字段的结果字典。
    """
    return await anyio.to_thread.run_sync(_compile_latex_sync, payload, limiter=None)


def _compile_latex_sync(payload: CompileRequest) -> Dict[str, Any]:
    """Compile LaTeX synchronously inside a temporary directory.

    Parameters:
        payload: Validated compile request数据对象。

    Returns:
        包含成功标志和 PDF Base64 内容的响应字典。

    Raises:
        HTTPException: 当输入非法或编译失败时抛出。
    """
    if not payload.latex_content.strip():
        raise HTTPException(status_code=400, detail="latex_content is required")

    recipe = payload.compile_recipe or [
        ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"],
        ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"],
    ]

    temp_dir_path = Path(tempfile.mkdtemp(prefix="latex_compile_"))
    tex_file = temp_dir_path / "paper.tex"
    pdf_file = temp_dir_path / "paper.pdf"

    try:
        tex_file.write_text(payload.latex_content, encoding="utf-8")

        if LATEX_CLASS_PATH and os.path.exists(LATEX_CLASS_PATH):
            cls_target = temp_dir_path / os.path.basename(LATEX_CLASS_PATH)
            shutil.copy2(LATEX_CLASS_PATH, cls_target)
        else:
            raise HTTPException(
                status_code=500,
                detail=f"cls file not found at path: {LATEX_CLASS_PATH}",
            )

        image_files = payload.dependencies.get("image_files", {})
        for filename, base64_content in image_files.items():
            target = temp_dir_path / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_bytes(base64.b64decode(base64_content))
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to decode image {filename}: {exc}",
                ) from exc

        tex_filename = tex_file.name
        for command_template in recipe:
            command = [
                arg.replace("{output_dir}", str(temp_dir_path)).replace("{tex_file}", tex_filename)
                for arg in command_template
            ]

            result = subprocess.run(
                command,
                cwd=str(temp_dir_path),
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )

            if result.returncode != 0 and not pdf_file.exists():
                raise HTTPException(
                    status_code=500,
                    detail=f"PDF compilation failed: {result.stderr or result.stdout}",
                )

        if not pdf_file.exists():
            raise HTTPException(
                status_code=500,
                detail="PDF compilation finished without creating a PDF file",
            )

        pdf_data = pdf_file.read_bytes()
        pdf_base64 = base64.b64encode(pdf_data).decode("utf-8")
        return {"success": True, "pdf_base64": pdf_base64}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Compilation timeout")
    finally:
        shutil.rmtree(temp_dir_path, ignore_errors=True)


@app.post("/compile-latex")
async def compile_latex_endpoint(payload: CompileRequest) -> Dict[str, Any]:
    """
    将 LaTeX 内容编译成 PDF。

    Parameters:
        payload: 包含 LaTeX 源文件、依赖及可选编译流程的请求体。

    Returns:
        编译结果的 JSON 字典，其中成功时包含 `pdf_base64`。
    """
    return await _compile_latex(payload)


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    """健康检查端点。

    Returns:
        字典形式的健康状态信息。
    """
    return {"status": "ok"}


if __name__ == "__main__":  # pragma: no cover - manual launch helper
    import uvicorn

    uvicorn.run("latex_server:app", host="0.0.0.0", port=5000, reload=False)