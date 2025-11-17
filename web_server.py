from __future__ import annotations

import base64
import os
import re
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
import json
import traceback

import anyio
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from logger import get_logger
from ocr_client import DeepSeekOCRClient
from pdf2image import convert_from_bytes
from question_manager import QuestionManager
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from class_report import ClassReportGenerator
from config import (
    ANALYTICS_WINDOW_DAYS,
    EXAM_PARSE_ANSWER_BATCH_SIZE,
    HOMEWORK_UPLOAD_DIR,
    OCR_BASE_URL,
    OCR_MODE,
    REPORT_MAX_ITEMS,
    SECRET_KEY,
    SYSTEM_DATABASE_PATH,
    WEB_CONFIG,
)
from export_renderer import ExportRenderer
from homework_service import HomeworkBatchProcessor, HomeworkFileEntry
from student_manager import HomeworkItem, StudentManager
from system_manager import SystemManager
from utils import apply_filename_replacements, save_ocr_images


app = FastAPI(
    title="DeepSeek 教学平台",
    version="2.0.0",
    description="基于 FastAPI 的教学与 OCR 后端服务。",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    session_cookie="deepseek_session",
)

app.mount("/static", StaticFiles(directory="static"), name="static")
if not os.path.exists("uploads"):
    os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
# 添加 /images 路径别名，指向 uploads 目录，以兼容前端代码
app.mount("/images", StaticFiles(directory="uploads"), name="images")
templates = Jinja2Templates(directory="templates")

# 初始化服务对象
logger = get_logger()
system_manager = SystemManager(SYSTEM_DATABASE_PATH)
question_manager = QuestionManager(system_manager=system_manager)
ocr_client = DeepSeekOCRClient(OCR_BASE_URL)
export_renderer = ExportRenderer("uploads")
student_manager = StudentManager(
    question_manager=question_manager,
    system_manager=system_manager,
    llm_client=question_manager.llm_client,
)
os.makedirs(HOMEWORK_UPLOAD_DIR, exist_ok=True)
homework_processor = HomeworkBatchProcessor(
    ocr_client=ocr_client,
    student_manager=student_manager,
    question_manager=question_manager,
    system_manager=system_manager,
    upload_root="uploads",
    logger=logger,
)
class_report_generator = ClassReportGenerator(
    student_manager=student_manager,
    system_manager=system_manager,
    question_manager=question_manager,
)


ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "pdf"}


def allowed_file(filename: str) -> bool:
    """Return True if the uploaded filename uses an allowed extension.

    Parameters:
        filename: 用户上传的原始文件名。

    Returns:
        当扩展名满足要求时返回 True，否则返回 False。
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


async def require_login(request: Request) -> int:
    """FastAPI dependency that enforces an authenticated session.

    Parameters:
        request: 当前请求对象。

    Returns:
        已认证用户的整型 ID。

    Raises:
        HTTPException: 当用户未登录或 session 缺失时抛出 401。
    """
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    return int(user_id)


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO formatted string into a datetime object.

    Parameters:
        value: ISO 字符串或 None。

    Returns:
        转换后的 datetime；当解析失败或为空时返回 None。
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def serialize_student(student_row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert a student database row into an API friendly structure。

    Parameters:
        student_row: 原始数据库行字典。

    Returns:
        序列化后的学生字典；如果输入为空则返回 None。
    """
    if not student_row:
        return None
    avg = student_row.get("cached_average_score")
    return {
        "student_id": student_row.get("student_id"),
        "name": student_row.get("name"),
        "average_score": round(float(avg), 2) if isinstance(avg, (int, float)) else None,
        "average_updated_at": student_row.get("cached_average_updated_at"),
        "latest_history_timestamp": student_row.get("latest_history_timestamp"),
        "updated_at": student_row.get("updated_at"),
        "window_days": student_row.get("cached_average_window_days", ANALYTICS_WINDOW_DAYS),
    }


def serialize_history_item(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Convert a homework history row into JSON serializable data。

    Parameters:
        row: 作业历史记录行。

    Returns:
        标准化的历史记录字典；若输入为空返回 None。
    """
    if not row:
        return None
    score = row.get("score")
    student_answer = row.get("student_answer") or ""
    return {
        "id": row.get("id"),
        "session_uid": row.get("session_uid"),
        "export_id": row.get("export_id"),
        "paper_title": row.get("paper_title"),
        "question_id": row.get("question_id"),
        "question_number": row.get("question_number"),
        "original_question": row.get("original_question"),
        "reference_answer": row.get("reference_answer"),
        "student_answer": student_answer,
        "score": round(float(score), 4) if isinstance(score, (int, float)) else None,
        "feedback": row.get("feedback") or "",
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def collect_history_for_report(student_id: str):
    """Collect homework records needed for building a learning report。

    Parameters:
        student_id: 学生编号。

    Returns:
        包含全部记录、截断列表以及最新时间戳的三元组。
    """
    history_records = student_manager.get_homework_history(
        student_id,
        window_days=ANALYTICS_WINDOW_DAYS,
        limit=None,
    )

    if not history_records:
        return [], [], None

    def score_key(item: Dict[str, Any]):
        score = item.get("score")
        if score is None:
            return (0, 0.0)
        try:
            return (0, float(score))
        except (TypeError, ValueError):
            return (0, 0.0)

    sorted_history = sorted(history_records, key=score_key)
    trimmed = sorted_history[:REPORT_MAX_ITEMS]

    latest_ts = None
    for record in history_records:
        ts = parse_iso_datetime(record.get("created_at"))
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    return history_records, trimmed, latest_ts


def generate_report_for_student(student: Dict[str, Any]):
    """Generate a learning report for the specified student。

    Parameters:
        student: 学生信息字典。

    Returns:
        由报告、用于展示的历史记录和最新时间戳组成的三元组。

    Raises:
        ValueError: 在缺少历史记录时抛出。
    """
    _, history_for_report, latest_ts = collect_history_for_report(student["student_id"])
    if not history_for_report:
        raise ValueError("暂无做题历史，无法生成报告")

    report = student_manager.generate_learning_report(student["name"], history_for_report)
    student_manager.cache_report(student["student_id"], report, latest_ts)
    return report, history_for_report, latest_ts


def log_error_with_details(exc: Exception, context: str, request: Optional[Request] = None, **kwargs) -> None:
    """Log detailed error information with contextual metadata。

    Parameters:
        exc: 捕获的异常。
        context: 错误发生的上下文描述。
        request: 可选的请求对象，用于记录请求详细信息。
        **kwargs: 额外的调试信息。
    """
    traceback_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    error_details = {
        "context": context,
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
        "traceback": traceback_str,
    }
    
    # 添加请求信息
    if request:
        try:
            error_details["request"] = {
                "method": request.method,
                "url": str(request.url),
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "path_params": dict(request.path_params),
                "headers": dict(request.headers),
                "client": {
                    "host": request.client.host if request.client else None,
                    "port": request.client.port if request.client else None,
                },
            }
            # 注意：读取请求体会消耗掉请求体，可能导致后续无法读取
            # 这里只记录请求体是否存在，不实际读取
            if request.method in ("POST", "PUT", "PATCH"):
                error_details["request"]["has_body"] = True
                error_details["request"]["body_note"] = "请求体存在但未读取（避免消耗请求流）"
            # 尝试获取 session 信息
            try:
                session_data = dict(request.session) if hasattr(request, "session") else {}
                # 隐藏敏感信息
                if "user_id" in session_data:
                    error_details["request"]["session"] = {"user_id": session_data.get("user_id")}
            except Exception:  # noqa: BLE001
                pass
        except Exception as e:  # noqa: BLE001
            error_details["request"] = f"<无法获取请求信息: {str(e)}>"
    
    # 添加额外的变量信息
    if kwargs:
        error_details["variables"] = {}
        for key, value in kwargs.items():
            try:
                # 限制字符串长度，避免日志过大
                if isinstance(value, str) and len(value) > 1000:
                    error_details["variables"][key] = value[:1000] + "...(截断)"
                elif isinstance(value, (str, int, float, bool, type(None))):
                    error_details["variables"][key] = value
                else:
                    error_details["variables"][key] = str(value)[:1000] + ("..." if len(str(value)) > 1000 else "")
            except Exception:  # noqa: BLE001
                error_details["variables"][key] = "<无法序列化>"
    
    logger.log_error(exc, f"{context} - 详细信息: {json.dumps(error_details, ensure_ascii=False, indent=2)}")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main dashboard page for authenticated users.
    Redirects to login page if user is not authenticated.

    Parameters:
        request: 当前请求对象。

    Returns:
        渲染后的首页模板响应，或重定向到登录页面。
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    
    user = await run_in_threadpool(system_manager.get_user_by_id, user_id)
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, user_id: int = Depends(require_login)):
    """Render the personal profile page.

    Parameters:
        request: 当前请求对象。
        user_id: 已登录用户 ID。

    Returns:
        用户中心模板响应。
    """
    user = await run_in_threadpool(system_manager.get_user_by_id, user_id)
    return templates.TemplateResponse("user_profile.html", {"request": request, "user": user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/favicon.ico")
async def favicon():
    """Handle favicon requests to avoid 404 errors."""
    return Response(status_code=204)


@app.post("/api/auth/register")
async def register(payload: Dict[str, Any]):
    """Register a new user account.

    Parameters:
        payload: 包含用户名、密码、邮箱的请求体。

    Returns:
        注册结果字典。
    """
    try:
        username = payload.get("username")
        password = payload.get("password")
        email = payload.get("email")
        success, message = await run_in_threadpool(system_manager.register_user, username, password, email)
        return {"success": success, "message": message}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "用户注册API失败", username=username, email=email)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/auth/login")
async def login(request: Request, payload: Dict[str, Any]):
    """Authenticate a user and persist the session.

    Parameters:
        request: 当前请求对象（用于写入 session）。
        payload: 包含用户名与密码的 JSON。

    Returns:
        登录成功/失败信息以及用户数据。
    """
    try:
        username = payload.get("username")
        password = payload.get("password")
        user = await run_in_threadpool(system_manager.authenticate_user, username, password)
        if not user:
            return {"success": False, "message": "用户名或密码错误"}
        request.session["user_id"] = user["id"]
        request.session["username"] = user["username"]
        return {"success": True, "message": "登录成功", "user": user}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "用户登录API失败", username=username)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/auth/logout")
async def logout(request: Request):
    """Clear the current user session."""
    request.session.clear()
    # 仅返回成功标记
    return {"success": True, "message": "已登出"}


@app.get("/api/auth/current")
async def get_current_user(request: Request, user_id: int = Depends(require_login)):
    """Retrieve the active user's information.

    Parameters:
        request: 当前请求对象，用于处理失效 session。
        user_id: 经过验证的用户 ID。

    Returns:
        包含用户信息的字典。
    """
    user = await run_in_threadpool(system_manager.get_user_by_id, user_id)
    if user:
        return {"success": True, "user": user}
    request.session.clear()
    raise HTTPException(status_code=401, detail="未登录")


@app.get("/api/students")
async def list_students(user_id: int = Depends(require_login)):
    """List students belonging to the current user.

    Parameters:
        user_id: 当前登录用户 ID。

    Returns:
        包含学生列表的响应字典。
    """
    try:
        students = await run_in_threadpool(student_manager.list_students, user_id)
        payload = [serialized for stu in students if (serialized := serialize_student(stu))]
        return {"success": True, "students": payload}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "获取学生列表失败", user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/students")
async def add_student_api(
    payload: Dict[str, Any],
    user_id: int = Depends(require_login),
):
    """Create a new student record for the current user.

    Parameters:
        payload: 提供学号与姓名的 JSON。
        user_id: 当前用户 ID。

    Returns:
        新增学生信息的响应字典。
    """
    student_id = (payload.get("student_id") or "").strip()
    name = (payload.get("name") or "").strip()
    if not student_id or not name:
        raise HTTPException(status_code=400, detail="学号和姓名不能为空")
    try:
        student = await run_in_threadpool(student_manager.add_student, student_id, name, user_id)
        return {"success": True, "student": serialize_student(student)}
    except ValueError as exc:
        log_error_with_details(exc, "新增学生失败-参数验证", student_id=student_id, name=name, user_id=user_id)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "新增学生失败", student_id=student_id, name=name, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/students/{student_id}/history")
async def get_student_history(
    student_id: str,
    user_id: int = Depends(require_login),
    limit: Optional[int] = Query(None),
    window_days: int = Query(ANALYTICS_WINDOW_DAYS),
):
    """Return homework history for a specific student.

    Parameters:
        student_id: 学生编号。
        user_id: 所属用户 ID。
        limit: 返回条数上限。
        window_days: 时间窗口。

    Returns:
        包含历史数组的响应字典。
    """
    try:
        history_rows = await run_in_threadpool(
            student_manager.get_homework_history,
            student_id,
            window_days,
            limit,
        )
        history = [serialize_history_item(row) for row in history_rows if row]
        return {"success": True, "history": history}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(
            exc,
            "获取学生做题历史失败",
            student_id=student_id,
            user_id=user_id,
            limit=limit,
            window_days=window_days,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/students/{student_id}/homework/parse")
async def parse_student_homework(
    request: Request,
    student_id: str,
    file: UploadFile = File(...),
    export_id: int = Form(...),
    student_name: str = Form(""),
    user_id: int = Depends(require_login),
):
    """Parse a single homework submission and return grading results.

    Parameters:
        request: 当前请求对象。
        student_id: 学生编号。
        file: 上传的作业图片或 PDF。
        export_id: 关联的试卷 ID。
        student_name: 学生姓名，必要时补全。
        user_id: 当前用户 ID。

    Returns:
        包含解析结果和学生信息的响应字典。
    """
    if not allowed_file(file.filename or ""):
        raise HTTPException(status_code=400, detail="文件格式不支持")

    student_record = await run_in_threadpool(student_manager.get_student, student_id, user_id)
    if not student_record:
        if not student_name.strip():
            raise HTTPException(status_code=400, detail="请填写学生姓名")
        student_record = await run_in_threadpool(student_manager.add_student, student_id, student_name.strip(), user_id)
    else:
        student_name = student_record.get("name") or student_name

    unique_filename = f"{uuid.uuid4().hex}_{file.filename}"
    save_path = os.path.join(HOMEWORK_UPLOAD_DIR, unique_filename)
    os.makedirs(HOMEWORK_UPLOAD_DIR, exist_ok=True)
    content = await file.read()
    await anyio.Path(save_path).write_bytes(content)

    try:
        entry = HomeworkFileEntry(
            original_filename=file.filename,
            stored_filename=unique_filename,
            stored_path=save_path,
        )
        batch_result = await run_in_threadpool(
            lambda: homework_processor.process_batch(
                [entry],
                export_id,
                user_id,
                force_student_id=student_id,
                force_student_name=student_name,
            )
        )
        mapping: Dict[str, Dict[str, Any]] = batch_result.get("mapping", {})
        mapping_entry = mapping.get(student_id) or (mapping.get(batch_result["order"][0]) if batch_result.get("order") else None)
        if not mapping_entry:
            raise ValueError("作业解析失败，未生成有效结果")

        return {
            "success": True,
            "paper_title": batch_result.get("paper_title"),
            "student": serialize_student(student_record),
            "export_id": export_id,
            "results": mapping_entry.get("results", []),
            "detected_student_id": mapping_entry.get("detected_student_id", ""),
            "detected_student_name": mapping_entry.get("detected_student_name", ""),
        }
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(
            exc,
            "作业解析失败",
            student_id=student_id,
            export_id=export_id,
            student_name=student_name,
            filename=file.filename,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/students/homework/batch-parse")
async def batch_parse_homework(
    request: Request,
    export_id: int = Form(...),
    force_student_id: Optional[str] = Form(None),
    force_student_name: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    user_id: int = Depends(require_login),
):
    """Batch parse multiple homework files in a single request.

    Parameters:
        request: 当前请求对象。
        export_id: 试卷 ID。
        force_student_id: 强制指定的学生编号。
        force_student_name: 强制指定的学生姓名。
        files: 上传的文件列表。
        user_id: 用户 ID。

    Returns:
        包含解析映射与失败列表的响应字典。
    """
    entries: List[HomeworkFileEntry] = []
    pre_failures: List[Dict[str, Any]] = []
    os.makedirs(HOMEWORK_UPLOAD_DIR, exist_ok=True)

    for uploaded in files:
        original_filename = uploaded.filename or ""
        if not original_filename:
            continue
        if not allowed_file(original_filename):
            pre_failures.append({"filename": original_filename, "message": "文件格式不支持"})
            continue

        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
        save_path = os.path.join(HOMEWORK_UPLOAD_DIR, unique_filename)
        try:
            content = await uploaded.read()
            await anyio.Path(save_path).write_bytes(content)
            entries.append(
                HomeworkFileEntry(
                    original_filename=original_filename,
                    stored_filename=unique_filename,
                    stored_path=save_path,
                )
            )
        except Exception as exc:  # noqa: BLE001
            log_error_with_details(exc, "批量作业上传保存失败", filename=original_filename)
            pre_failures.append({"filename": original_filename, "message": "文件保存失败"})

    if not entries and pre_failures:
        return {
            "success": False,
            "paper_title": "",
            "export_id": export_id,
            "questions": [],
            "mapping": {},
            "order": [],
            "failures": pre_failures,
        }

    try:
        batch_result = await run_in_threadpool(
            lambda: homework_processor.process_batch(
                entries,
                export_id,
                user_id,
                force_student_id=force_student_id,
                force_student_name=force_student_name,
            )
        )
        failures = batch_result.get("failures", [])
        if pre_failures:
            failures.extend(pre_failures)
        return {
            "success": True,
            "paper_title": batch_result.get("paper_title"),
            "export_id": export_id,
            "questions": batch_result.get("questions", []),
            "mapping": batch_result.get("mapping", {}),
            "order": batch_result.get("order", []),
            "failures": failures,
        }
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "批量作业解析失败", export_id=export_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/students/homework/batch-save")
async def batch_save_homework(payload: Dict[str, Any], user_id: int = Depends(require_login)):
    """Persist multiple homework grading results in one call.

    Parameters:
        payload: 包含批量成绩的 JSON。
        user_id: 当前用户 ID。

    Returns:
        成功与跳过列表。
    """
    export_id_raw = payload.get("export_id")
    entries = payload.get("students") or []
    paper_title = payload.get("paper_title") or ""

    if not export_id_raw:
        raise HTTPException(status_code=400, detail="缺少试卷信息")
    try:
        export_id = int(export_id_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="试卷信息无效") from exc

    if not entries:
        raise HTTPException(status_code=400, detail="没有可保存的作业结果")

    saved: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        student_id = (entry.get("student_id") or "").strip()
        if not student_id or student_id.startswith("unknown_id"):
            skipped.append({"student_id": student_id or "", "reason": "未指定有效学生"})
            continue
        student_name = (entry.get("student_name") or "").strip()
        results = entry.get("results") or []
        if not results:
            skipped.append({"student_id": student_id, "reason": "缺少作业结果"})
            continue
        student = await run_in_threadpool(student_manager.get_student, student_id, user_id)
        if not student:
            if not student_name:
                skipped.append({"student_id": student_id, "reason": "缺少学生姓名"})
                continue
            student = await run_in_threadpool(student_manager.add_student, student_id, student_name, user_id)
        else:
            student_name = student.get("name") or student_name

        items: List[HomeworkItem] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            try:
                score = float(result.get("score", 0))
            except (TypeError, ValueError):
                score = 0.0
            score = max(0.0, min(1.0, score))
            items.append(
                HomeworkItem(
                    question_id=result.get("question_id"),
                    question_number=str(result.get("question_number")),
                    original_question=result.get("original_question") or "",
                    reference_answer=result.get("reference_answer") or "",
                    student_answer=result.get("student_answer") or "",
                    score=score,
                    feedback=result.get("feedback") or "",
                )
            )

        if not items:
            skipped.append({"student_id": student_id, "reason": "作业结果格式无效"})
            continue

        session_uid = await run_in_threadpool(
            student_manager.record_homework_results,
            student_id,
            student_name,
            export_id,
            paper_title,
            items,
            user_id,
            entry,
        )
        saved.append({"student_id": student_id, "session_uid": session_uid})

    return {"success": True, "saved": saved, "skipped": skipped}


@app.post("/api/students/class-report")
async def generate_class_report(payload: Dict[str, Any], user_id: int = Depends(require_login)):
    """Generate aggregate analytics for a class report.

    Parameters:
        payload: 请求体包含导出 ID。
        user_id: 当前用户 ID。

    Returns:
        报告统计数据的响应字典。
    """
    export_id_raw = payload.get("export_id")
    if not export_id_raw:
        raise HTTPException(status_code=400, detail="缺少试卷信息")
    try:
        export_id = int(export_id_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="试卷信息无效") from exc

    try:
        report_payload = await run_in_threadpool(class_report_generator.generate_payload, export_id, user_id)
        return {
            "success": True,
            "paper_title": report_payload.get("paper_title"),
            "section_order": report_payload.get("section_order", []),
            "sections": report_payload.get("sections", {}),
            "question_count": report_payload.get("question_count", 0),
            "student_count": report_payload.get("student_count", 0),
        }
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "生成全班报告失败", export_id=export_id, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/students/class-report/download")
async def download_class_report(payload: Dict[str, Any], user_id: int = Depends(require_login)):
    """Generate a PDF version of the class report for download.

    Parameters:
        payload: 请求体包含导出 ID。
        user_id: 当前用户 ID。

    Returns:
        包含 PDF Base64 数据的字典。
    """
    export_id_raw = payload.get("export_id")
    if not export_id_raw:
        raise HTTPException(status_code=400, detail="缺少试卷信息")
    try:
        export_id = int(export_id_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="试卷信息无效") from exc

    try:
        pdf_payload = await run_in_threadpool(class_report_generator.generate_pdf, export_id, user_id)
        return {"success": True, "paper_title": pdf_payload.get("paper_title"), "pdf_base64": pdf_payload.get("pdf_base64")}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "导出全班报告PDF失败", export_id=export_id, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/students/{student_id}/homework/save")
async def save_student_homework(
    student_id: str,
    payload: Dict[str, Any],
    user_id: int = Depends(require_login),
):
    """Persist grading results for a single student.

    Parameters:
        student_id: 学生编号。
        payload: 请求体含题目结果信息。
        user_id: 当前用户 ID。

    Returns:
        包含 session UID 与更新后学生信息的字典。
    """
    export_id_value = payload.get("export_id")
    student_name = (payload.get("student_name") or "").strip()
    results = payload.get("results") or []
    paper_title = payload.get("paper_title") or ""

    if not export_id_value:
        raise HTTPException(status_code=400, detail="缺少试卷信息")
    try:
        export_id = int(export_id_value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="试卷信息无效") from exc
    if not results:
        raise HTTPException(status_code=400, detail="没有可保存的作业结果")

    student = await run_in_threadpool(student_manager.get_student, student_id, user_id)
    if not student:
        if not student_name:
            raise HTTPException(status_code=400, detail="请提供学生姓名")
        student = await run_in_threadpool(student_manager.add_student, student_id, student_name, user_id)
    else:
        student_name = student.get("name") or student_name

    items: List[HomeworkItem] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        try:
            score = float(result.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))
        items.append(
            HomeworkItem(
                question_id=result.get("question_id"),
                question_number=str(result.get("question_number")),
                original_question=result.get("original_question") or "",
                reference_answer=result.get("reference_answer") or "",
                student_answer=result.get("student_answer") or "",
                score=score,
                feedback=result.get("feedback") or "",
            )
        )

    if not items:
        raise HTTPException(status_code=400, detail="作业结果格式无效")

    session_uid = await run_in_threadpool(
        student_manager.record_homework_results,
        student_id,
        student_name,
        export_id,
        paper_title,
        items,
        user_id,
        payload,
    )
    refreshed_student = await run_in_threadpool(student_manager.get_student, student_id, user_id)
    return {"success": True, "session_uid": session_uid, "student": serialize_student(refreshed_student)}


@app.get("/api/students/{student_id}/report")
async def get_student_report(
    student_id: str,
    refresh: bool = Query(False),
    user_id: int = Depends(require_login),
):
    """Retrieve or regenerate a student's learning report.

    Parameters:
        student_id: 学生编号。
        refresh: 是否强制刷新。
        user_id: 当前用户 ID。

    Returns:
        包含报告内容及历史预览的响应字典。
    """
    try:
        student = await run_in_threadpool(student_manager.get_student, student_id, user_id)
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")

        if refresh or student_manager.needs_report_refresh(student_id):
            report, history_for_report, _ = await run_in_threadpool(generate_report_for_student, student)
            return {
                "success": True,
                "report": report,
                "cached": False,
                "history_preview": [serialize_history_item(item) for item in history_for_report],
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }

        cached = await run_in_threadpool(student_manager.get_cached_report, student_id) or {}
        _, history_for_report, _ = collect_history_for_report(student_id)
        return {
            "success": True,
            "report": cached,
            "cached": True,
            "history_preview": [serialize_history_item(item) for item in history_for_report],
            "generated_at": student.get("cached_report_generated_at"),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        log_error_with_details(exc, "生成学习报告失败-参数验证", student_id=student_id, refresh=refresh)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "生成学习报告失败", student_id=student_id, refresh=refresh, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/students/{student_id}/recommendations")
async def get_student_recommendations(
    student_id: str,
    user_id: int = Depends(require_login),
):
    """Generate question recommendations for a student.

    Parameters:
        student_id: 学生编号。
        user_id: 当前登录用户 ID。

    Returns:
        推荐题目列表。
    """
    try:
        student = await run_in_threadpool(student_manager.get_student, student_id, user_id)
        if not student:
            raise HTTPException(status_code=404, detail="学生不存在")
        recommendations = await run_in_threadpool(student_manager.build_recommendations, student_id, user_id)
        return {"success": True, "questions": recommendations}
    except HTTPException:
        raise
    except ValueError as exc:
        log_error_with_details(exc, "生成AI题目推荐失败-参数验证", student_id=student_id)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "生成AI题目推荐失败", student_id=student_id, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/questions")
async def add_question(
    payload: Dict[str, Any],
    user_id: int = Depends(require_login),
):
    """Insert a new question into the database.

    Parameters:
        payload: 包含题目内容、标签等信息的 JSON。
        user_id: 当前用户 ID。

    Returns:
        包含新增题目 ID 的响应字典。
    """
    if not payload or "latex_content" not in payload:
        raise HTTPException(status_code=400, detail="题目内容不能为空")
    latex_content = payload["latex_content"]
    tags = payload.get("tags", [])
    reference_answer = payload.get("reference_answer", "")
    source = payload.get("source", "")
    image = payload.get("image", [])
    visibility = payload.get("visibility", "public")
    question_type = payload.get("question_type", "解答题")
    try:
        question_id = await run_in_threadpool(
            question_manager.add_question,
            latex_content,
            tags,
            reference_answer,
            source,
            image,
            user_id,
            visibility,
            question_type,
        )
        return {"success": True, "message": "题目添加成功", "question_id": question_id}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(
            exc,
            "添加题目API失败",
            user_id=user_id,
            latex_content_length=len(latex_content),
            tags=tags,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.put("/api/questions/{question_id}")
async def update_question(
    question_id: int,
    payload: Dict[str, Any],
    user_id: int = Depends(require_login),
):
    """Update question content, answer, or type.

    Parameters:
        question_id: 题目 ID。
        payload: 更新数据 JSON。
        user_id: 当前用户 ID。

    Returns:
        更新后的题目信息。
    """
    latex_content = (payload.get("latex_content") or "").strip()
    reference_answer = payload.get("reference_answer", "")
    question_type = payload.get("question_type")
    if not latex_content:
        raise HTTPException(status_code=400, detail="题目内容不能为空")
    try:
        question = await run_in_threadpool(question_manager.get_question_by_id, question_id, user_id)
        if not question:
            raise HTTPException(status_code=404, detail="题目不存在或无权访问")
        if question.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权修改该题目")
        updated_question = await run_in_threadpool(
            question_manager.update_question,
            question_id,
            latex_content,
            reference_answer,
            user_id,
            question_type,
        )
        return {"success": True, "question": updated_question}
    except HTTPException:
        raise
    except ValueError as exc:
        log_error_with_details(exc, "更新题目失败-参数验证", question_id=question_id, latex_content_length=len(latex_content))
        raise HTTPException(status_code=400, detail=str(exc))
    except PermissionError as exc:
        log_error_with_details(exc, "更新题目失败-权限错误", question_id=question_id, user_id=user_id)
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "更新题目失败", question_id=question_id, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/questions/auto-tag")
async def auto_tag_question(
    payload: Dict[str, Any],
    user_id: int = Depends(require_login),
):
    """Automatically tag and answer a question using the LLM.

    Parameters:
        payload: 请求体包含题目原文。
        user_id: 当前用户 ID。

    Returns:
        由标签、答案和 LaTeX 文本组成的字典。
    """
    if not payload or "content" not in payload:
        raise HTTPException(status_code=400, detail="题目内容不能为空")
    content = payload["content"]
    source = payload.get("source", "")
    start_time = time.time()
    try:
        logger.log_user_action(user_id, "自动打标和LaTeX格式化", f"内容长度: {len(content)}")
        tags, answer, latex_content, question_type = await run_in_threadpool(
            question_manager.auto_tag_and_answer,
            content,
            source,
        )
        duration = time.time() - start_time
        logger.log_performance("自动打标API", duration, f"用户ID: {user_id}")
        return {
            "success": True,
            "tags": tags,
            "answer": answer,
            "latex_content": latex_content,
            "question_type": question_type,
        }
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(
            exc,
            "自动打标API失败",
            user_id=user_id,
            content_length=len(content),
            source=source,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/questions/search")
async def search_questions(
    tags: List[str] = Query(default=[]),
    keyword: str = Query(default=""),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    user_id: int = Depends(require_login),
):
    """Search or list questions with optional filtering.

    Parameters:
        tags: 按标签过滤。
        keyword: 关键词搜索。
        page: 页码。
        limit: 每页数量。
        user_id: 当前用户 ID。

    Returns:
        题目列表以及数量。
    """
    try:
        offset = (page - 1) * limit
        if tags:
            questions = await run_in_threadpool(question_manager.get_questions_by_tags, tags, user_id)
        elif keyword:
            questions = await run_in_threadpool(question_manager.search_questions, keyword, user_id)
        else:
            questions = await run_in_threadpool(question_manager.get_all_questions, limit, offset, user_id)
        return {"success": True, "questions": questions, "total": len(questions)}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(
            exc,
            "搜索题目API失败",
            user_id=user_id,
            tags=tags,
            keyword=keyword,
            page=page,
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/questions/stats")
async def get_question_stats(request: Request, user_id: int = Depends(require_login)):
    """Return question statistics for the current user."""
    try:
        stats = await run_in_threadpool(question_manager.get_question_stats, user_id)
        return {"success": True, "stats": stats}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "获取题目统计信息失败", request=request, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/questions/{question_id}")
async def get_question(
    question_id: int,
    user_id: int = Depends(require_login),
):
    """Fetch a single question by ID with permission checks.

    Parameters:
        question_id: 题目 ID。
        user_id: 当前用户 ID。

    Returns:
        包含题目详情的字典。
    """
    try:
        question = await run_in_threadpool(question_manager.get_question_by_id, question_id, user_id)
        if question:
            return {"success": True, "question": question}
        raise HTTPException(status_code=404, detail="题目不存在或无权访问")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "获取题目详情失败", question_id=question_id, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/questions/{question_id}/ai-variant")
async def generate_question_variant(
    question_id: int,
    payload: Dict[str, Any],
    user_id: int = Depends(require_login),
):
    """Ask the LLM to generate a variant based on an existing question.

    Parameters:
        question_id: 原题 ID。
        payload: 可选的覆盖内容。
        user_id: 当前用户 ID。

    Returns:
        变体题目的字段。
    """
    try:
        base_question = await run_in_threadpool(question_manager.get_question_by_id, question_id, user_id)
        if not base_question:
            raise HTTPException(status_code=404, detail="题目不存在或无权访问")
        if base_question.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="无权对此题目生成变体")

        working_question = dict(base_question)
        if payload.get("latex_content"):
            working_question["latex_content"] = payload["latex_content"]
        if payload.get("reference_answer") is not None:
            working_question["reference_answer"] = payload["reference_answer"]

        variant = await run_in_threadpool(question_manager.generate_question_variant, working_question)
        return {"success": True, "variant": variant}
    except HTTPException:
        raise
    except ValueError as exc:
        log_error_with_details(exc, "AI变题失败-参数验证", question_id=question_id, user_id=user_id)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "AI变题失败", question_id=question_id, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: int = Depends(require_login),
):
    """Handle generic media upload and return a public URL."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="没有选择文件")
    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="不支持的文件类型")

    unique_filename = f"{uuid.uuid4()}{os.path.splitext(file.filename)[1]}"
    save_path = os.path.join("uploads", unique_filename)
    content = await file.read()
    await anyio.Path(save_path).write_bytes(content)
    return {"success": True, "filename": unique_filename, "url": f"/uploads/{unique_filename}"}


@app.delete("/api/questions/{question_id}")
async def delete_question(
    question_id: int,
    user_id: int = Depends(require_login),
):
    """Delete a question if the current user is the owner."""
    try:
        success = await run_in_threadpool(question_manager.delete_question, question_id, user_id)
        if success:
            return {"success": True, "message": "题目删除成功"}
        raise HTTPException(status_code=404, detail="题目不存在或无权删除")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "删除题目失败", question_id=question_id, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/pdf-preview")
async def pdf_preview(
    file: UploadFile = File(...),
    user_id: int = Depends(require_login),
):
    """Generate a preview image for the first page of a PDF."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="没有选择文件")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持PDF文件预览")
    try:
        pdf_content = await file.read()
        if not pdf_content:
            raise HTTPException(status_code=400, detail="文件内容为空")
        images = await run_in_threadpool(convert_from_bytes, pdf_content, 1, 1)
        if not images:
            raise HTTPException(status_code=500, detail="无法生成PDF预览")
        preview_image = images[0]
        buffer = BytesIO()
        preview_image.save(buffer, format="PNG")
        preview_data = base64.b64encode(buffer.getvalue()).decode("ascii")
        return {"success": True, "preview": f"data:image/png;base64,{preview_data}"}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "生成PDF预览失败", filename=file.filename, user_id=user_id)
        raise HTTPException(status_code=500, detail=f"无法生成PDF预览: {exc}")


@app.post("/api/ocr-parse")
async def ocr_parse(
    file: UploadFile = File(...),
    mode: Optional[str] = Form(None),
    user_id: int = Depends(require_login),
):
    """Run OCR on an uploaded exam and parse questions."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="没有选择文件")
    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="不支持的文件类型")

    # 如果没有指定 mode，使用全局配置
    ocr_mode = mode if mode else OCR_MODE

    upload_images_dir = os.path.join("uploads", "upload_images")
    os.makedirs(upload_images_dir, exist_ok=True)
    unique_filename = f"{uuid.uuid4()}{os.path.splitext(file.filename)[1]}"
    file_path = os.path.join(upload_images_dir, unique_filename)
    content = await file.read()
    await anyio.Path(file_path).write_bytes(content)
    is_pdf = file.filename.lower().endswith(".pdf")

    try:
        logger.log_system_info(f"开始OCR处理 - 文件: {file_path}, 模式: {ocr_mode}")
        ocr_result = await ocr_client.ocr_image_async(file_path, mode=ocr_mode)
        pages = ocr_result.get("pages") or []

        markdown_segments: List[str] = []
        image_filename_mapping: Dict[str, str] = {}

        for page in pages:
            page_number = page.get("page")
            page_markdown = page.get("markdown") or ""
            page_images = page.get("images") or []
            request_id = page.get("request_id", "unknown")
            logger.log_system_info(f"OCR页面完成 - 文件: {file_path}, 页码: {page_number}, 请求ID: {request_id}")
            logger.log_ocr_result(request_id, page_markdown, len(page_images))
            page_mapping, replacements = save_ocr_images(
                page_images,
                "uploads",
                logger,
                suffix=page.get("suggested_suffix", ""),
            )
            image_filename_mapping.update(page_mapping)
            page_text = apply_filename_replacements(page_markdown, replacements)
            if page_text:
                markdown_segments.append(page_text)

        if not markdown_segments:
            fallback_markdown = ocr_result.get("markdown") or ocr_result.get("text") or ""
            if fallback_markdown:
                markdown_segments.append(fallback_markdown)

        markdown_content = "\n\n".join(segment for segment in markdown_segments if segment)
        logger.log_system_info(
            f"开始解析试卷，markdown内容长度: {len(markdown_content)}, 可用图片数量: {len(image_filename_mapping)}"
        )

        parsed_questions = await run_in_threadpool(
            question_manager.parse_exam_paper,
            markdown_content,
            image_filename_mapping,
            EXAM_PARSE_ANSWER_BATCH_SIZE if is_pdf else None,
        )
        logger.log_question_parsing(len(parsed_questions), "试卷解析")

        if not parsed_questions:
            return {
                "success": False,
                "message": "试卷解析完成，但没有识别出任何题目。请检查试卷图片质量或内容格式。",
            }
        return {"success": True, "questions": parsed_questions}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(
            exc,
            "OCR解析试卷失败",
            filename=file.filename,
            file_path=file_path,
            user_id=user_id,
        )
        raise HTTPException(status_code=500, detail=f"OCR解析失败: {exc}")


@app.get("/api/tags")
async def get_tags():
    """Return a list of system tags."""
    try:
        tags = await run_in_threadpool(system_manager.get_all_tags, 20)
        tag_names = [tag["name"] for tag in tags]
        return {"success": True, "tags": tag_names}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "获取所有可用标签失败")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/export-paper")
async def export_paper(
    payload: Dict[str, Any],
    user_id: int = Depends(require_login),
):
    """Export selected questions into LaTeX, DOCX, or PDF."""
    questions = payload.get("questions", [])
    title = payload.get("title", "数学试卷")
    mode = payload.get("mode", "questions")
    format_type = payload.get("format", "latex")

    if not questions:
        raise HTTPException(status_code=400, detail="没有题目可导出")

    question_ids = [q.get("id") for q in questions if q.get("id")]
    if question_ids:
        await run_in_threadpool(
            system_manager.save_export_history,
            user_id,
            title,
            question_ids,
            format_type,
            mode,
        )

    try:
        if format_type == "latex":
            content = await run_in_threadpool(export_renderer.render_latex, questions, mode, title)
            filename = f"{title}_{uuid.uuid4().hex[:8]}.tex"
            return StreamingResponse(
                iter([content]),
                media_type="text/plain",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        if format_type == "docx":
            file_path = await run_in_threadpool(export_renderer.render_docx, questions, mode, title)
            return FileResponse(file_path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=os.path.basename(file_path))
        if format_type == "pdf":
            file_path = await run_in_threadpool(export_renderer.render_pdf, questions, mode, title)
            return FileResponse(file_path, media_type="application/pdf", filename=os.path.basename(file_path))
        raise HTTPException(status_code=400, detail="不支持的格式")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(
            exc,
            "导出试卷失败",
            user_id=user_id,
            title=title,
            format_type=format_type,
            mode=mode,
            questions_count=len(questions),
        )
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/user/exports")
async def get_user_exports(user_id: int = Depends(require_login)):
    """Return recent export history for the current user."""
    try:
        exports = await run_in_threadpool(system_manager.get_export_history, user_id, 50)
        return {"success": True, "exports": exports}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "获取用户导出记录失败", user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/user/reset-password")
async def reset_password(
    payload: Dict[str, Any],
    user_id: int = Depends(require_login),
):
    """Allow a user to update their password."""
    old_password = payload.get("old_password")
    new_password = payload.get("new_password")
    try:
        success, message = await run_in_threadpool(system_manager.update_password, user_id, old_password, new_password)
        return {"success": success, "message": message}
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "重置密码失败", user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/user/re-export/{export_id}")
async def get_re_export_data(
    export_id: int,
    user_id: int = Depends(require_login),
):
    """Fetch metadata required to re-export a previous paper."""
    try:
        export_data = await run_in_threadpool(system_manager.get_export_by_id, export_id)
        if not export_data or export_data["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="导出记录不存在或无权访问")
        questions = []
        for question_id in export_data["question_ids"]:
            question = await run_in_threadpool(question_manager.get_question_by_id, question_id, user_id)
            if question:
                questions.append(question)
        return {"success": True, "export": export_data, "questions": questions}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log_error_with_details(exc, "获取重新导出数据失败", export_id=export_id, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle 422 validation errors with detailed logging."""
    error_details = {
        "error_type": "RequestValidationError",
        "errors": exc.errors(),
        "body": exc.body if hasattr(exc, "body") else None,
    }
    log_error_with_details(
        exc,
        "请求验证失败 (422)",
        request=request,
        validation_errors=error_details["errors"],
        request_body=error_details.get("body"),
    )
    return JSONResponse(
        {
            "success": False,
            "message": "请求参数验证失败",
            "errors": error_details["errors"],
        },
        status_code=422,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with detailed logging."""
    log_error_with_details(
        exc,
        f"HTTP异常 ({exc.status_code})",
        request=request,
        status_code=exc.status_code,
        detail=exc.detail if hasattr(exc, "detail") else str(exc),
    )
    return JSONResponse(
        {"success": False, "message": exc.detail if hasattr(exc, "detail") else str(exc)},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with detailed logging."""
    log_error_with_details(
        exc,
        "未处理的异常",
        request=request,
    )
    return JSONResponse(
        {"success": False, "message": "服务器内部错误"},
        status_code=500,
    )


@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):  # pragma: no cover - fallback
    """Handle 404 errors with a consistent JSON payload."""
    log_error_with_details(
        exc,
        "404 页面不存在",
        request=request,
    )
    return JSONResponse({"success": False, "message": "页面不存在"}, status_code=404)


@app.exception_handler(500)
async def internal_error(request: Request, exc: HTTPException):  # pragma: no cover - fallback
    """Handle uncaught server errors."""
    log_error_with_details(
        exc,
        "500 服务器内部错误",
        request=request,
    )
    return JSONResponse({"success": False, "message": "服务器内部错误"}, status_code=500)


if __name__ == "__main__":  # pragma: no cover - manual launch
    import uvicorn

    uvicorn.run(
        "web_server:app",
        host=WEB_CONFIG["host"],
        port=WEB_CONFIG["port"],
        reload=False,
    )
