# -*- coding: utf-8 -*-
"""
高考题目录入和自动打标系统Web服务器
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
from functools import wraps
import base64
import json
import os
import re
import uuid
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Sequence

import requests
from werkzeug.utils import secure_filename
from question_manager import QuestionManager
from ocr_client import DeepSeekOCRClient
from system_manager import SystemManager
from export_renderer import ExportRenderer
from student_manager import StudentManager, HomeworkItem
from config import (
    WEB_CONFIG,
    OCR_BASE_URL,
    LLM_CONFIG,
    SECRET_KEY,
    SYSTEM_DATABASE_PATH,
    HOMEWORK_UPLOAD_DIR,
    ANALYTICS_WINDOW_DAYS,
    REPORT_MAX_ITEMS,
    EXAM_PARSE_ANSWER_BATCH_SIZE,
    LATEX_COMPILE_CONFIG,
)
from logger import get_logger
from pdf2image import convert_from_bytes
import traceback
from utils import (
    apply_filename_replacements,
    convert_pdf_to_images,
    save_ocr_images,
)
from class_report import (
    build_section_instances,
    build_sections_payload,
    render_sections_latex,
    latex_escape,
)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 配置上传文件夹
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# 确保上传文件夹存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 初始化日志记录器
logger = get_logger()

def log_error_with_details(e: Exception, context: str, **kwargs):
    """记录详细的错误信息，包括traceback和变量信息。
    
    参数:
        e: 异常对象。
        context: 错误上下文描述。
        **kwargs: 额外的变量信息。
    
    返回:
        None。
    """
    import sys
    exc_type, exc_value, exc_traceback = sys.exc_info()
    traceback_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    
    # 构建详细的错误信息
    error_details = {
        'context': context,
        'exception_type': type(e).__name__,
        'exception_message': str(e),
        'traceback': traceback_str,
    }
    
    # 添加额外的变量信息
    if kwargs:
        error_details['variables'] = {}
        for key, value in kwargs.items():
            try:
                # 尝试将值转换为字符串，避免序列化问题
                if isinstance(value, (str, int, float, bool, type(None))):
                    error_details['variables'][key] = value
                else:
                    error_details['variables'][key] = str(value)
            except Exception:
                error_details['variables'][key] = '<无法序列化>'
    
    # 记录到日志
    logger.log_error(e, f"{context} - 详细信息: {json.dumps(error_details, ensure_ascii=False, indent=2)}")

# 初始化系统管理器
system_manager = SystemManager(SYSTEM_DATABASE_PATH)

# 初始化题目管理器
question_manager = QuestionManager(system_manager=system_manager)

# 初始化OCR客户端
ocr_client = DeepSeekOCRClient(OCR_BASE_URL)

# 初始化导出渲染器
export_renderer = ExportRenderer(UPLOAD_FOLDER)

# 初始化学生管理器
student_manager = StudentManager(
    question_manager=question_manager,
    system_manager=system_manager,
    llm_client=question_manager.llm_client,
)

if not os.path.exists(HOMEWORK_UPLOAD_DIR):
    os.makedirs(HOMEWORK_UPLOAD_DIR, exist_ok=True)

# 登录验证装饰器
def login_required(f):
    """登录保护装饰器，未登录用户将被跳转至登录页。

    参数:
        f: 被包装的视图函数。

    返回:
        包装后的视图函数。
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        """确保会话中存在用户信息后再执行原函数。

        参数:
            *args: 传递给原函数的位置参数。
            **kwargs: 传递给原函数的关键字参数。

        返回:
            原视图函数的返回值或重定向响应。
        """
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    """判断上传文件是否具有允许的扩展名。

    参数:
        filename: 上传文件名。

    返回:
        若扩展名合法返回 True，否则返回 False。
    """
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def normalize_homework_results(
    questions: Sequence[Dict[str, Any]],
    llm_results: Sequence[Dict[str, Any]],
    fallback_student_id: str,
) -> List[Dict[str, Any]]:
    """根据题目顺序整理LLM返回的批改结果。"""
    results_by_id: Dict[int, Dict[str, Any]] = {}
    results_by_number: Dict[int, Dict[str, Any]] = {}

    for item in llm_results or []:
        if not isinstance(item, dict):
            continue
        qid_val = item.get("question_id")
        qnum_val = item.get("question_number")
        try:
            if qid_val is not None:
                results_by_id[int(qid_val)] = item
        except (TypeError, ValueError):
            pass
        try:
            if qnum_val is not None:
                results_by_number[int(qnum_val)] = item
        except (TypeError, ValueError):
            pass

    normalized: List[Dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        qid = question.get("id")
        raw_item: Optional[Dict[str, Any]] = None

        int_qid: Optional[int] = None
        try:
            if qid is not None:
                int_qid = int(qid)
        except (TypeError, ValueError):
            int_qid = None

        if int_qid is not None and int_qid in results_by_id:
            raw_item = results_by_id[int_qid]
        elif index in results_by_number:
            raw_item = results_by_number[index]

        student_answer = ""
        feedback = ""
        score_value = 0.0
        student_id = fallback_student_id or ""

        if raw_item:
            student_answer = raw_item.get("student_answer") or ""
            feedback = raw_item.get("feedback") or ""
            custom_student_id = raw_item.get("student_id")
            if isinstance(custom_student_id, str) and custom_student_id.strip():
                student_id = custom_student_id.strip()
            try:
                score_value = float(raw_item.get("score", 0))
            except (TypeError, ValueError):
                score_value = 0.0

        score_value = max(0.0, min(1.0, score_value))

        normalized.append(
            {
                "question_id": qid,
                "question_number": index,
                "original_question": question.get("latex_content"),
                "reference_answer": question.get("reference_answer"),
                "student_answer": student_answer,
                "score": round(score_value, 4),
                "feedback": feedback,
                "question_type": question.get("question_type"),
                "tags": question.get("tags", []),
                "source": question.get("source"),
                "student_id": student_id,
            }
        )

    return normalized


def perform_homework_parsing(
    file_path: str,
    questions: List[Dict[str, Any]],
    paper_title: str,
    user_id: int,
) -> Dict[str, Any]:
    """执行OCR与作业批改流程，返回整理后的结果。"""
    ocr_result = ocr_client.ocr_image(file_path)
    ocr_text = ocr_result.get("markdown") or ocr_result.get("text") or ""

    parse_payload = student_manager.parse_homework_ocr(paper_title, questions, ocr_text, user_id)
    if not isinstance(parse_payload, dict):
        raise ValueError("作业批改失败，返回格式无效")

    detected_student_id = (parse_payload.get("detected_student_id") or "").strip()
    detected_student_name = (parse_payload.get("detected_student_name") or "").strip()
    llm_results = parse_payload.get("results") if isinstance(parse_payload.get("results"), list) else []

    normalized_results = normalize_homework_results(questions, llm_results, detected_student_id)

    return {
        "ocr_text": ocr_text,
        "ocr_images": ocr_result.get("images", []),
        "detected_student_id": detected_student_id,
        "detected_student_name": detected_student_name,
        "normalized_results": normalized_results,
        "llm_results": llm_results,
    }


def match_student_by_filename(filename: str, roster: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """尝试根据文件名匹配学生信息。"""
    if not filename:
        return None
    name_body = os.path.splitext(filename)[0].lower()
    for student in roster:
        if not isinstance(student, dict):
            continue
        sid = str(student.get("student_id") or "").lower()
        name = str(student.get("name") or "").lower()
        if sid and sid in name_body:
            return student
        if name and name in name_body:
            return student
    return None


def build_class_report_context(export_id: int, user_id: int) -> Dict[str, Any]:
    """构建全班报告所需的数据上下文。"""
    export_data = system_manager.get_export_by_id(export_id)
    if not export_data or export_data.get("user_id") != user_id:
        raise ValueError("无法访问指定的试卷")

    question_ids = export_data.get("question_ids") or []
    questions: List[Dict[str, Any]] = []
    question_id_map: Dict[Any, Dict[str, Any]] = {}
    for index, qid in enumerate(question_ids, start=1):
        question = question_manager.get_question_by_id(qid, user_id)
        if not question:
            continue
        tags = question.get("tags") or []
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        meta = {
            "id": question.get("id"),
            "number": index,
            "question_type": question.get("question_type"),
            "tags": tags,
            "latex_content": question.get("latex_content"),
            "reference_answer": question.get("reference_answer"),
        }
        questions.append(meta)
        key_candidates = {qid, question.get("id"), str(question.get("id"))}
        for key in list(key_candidates):
            try:
                key_candidates.add(int(key))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        for key in key_candidates:
            question_id_map[key] = meta

    if not questions:
        raise ValueError("所选试卷暂无题目信息")

    roster = student_manager.list_students(user_id)
    roster_map = {
        str(student.get("student_id")): student
        for student in roster
        if isinstance(student, dict) and student.get("student_id")
    }

    result_rows = student_manager.get_homework_results_by_export(export_id, user_id)
    question_scores: Dict[int, List[float]] = {item["number"]: [] for item in questions}
    student_entries: Dict[str, Dict[str, Any]] = {}

    for row in result_rows:
        sid = row.get("student_id")
        if not sid:
            continue

        qnum_raw = row.get("question_number")
        qnum: Optional[int] = None
        try:
            if qnum_raw is not None:
                qnum = int(qnum_raw)
        except (TypeError, ValueError):
            qnum = None

        if qnum not in question_scores:
            qmeta = question_id_map.get(row.get("question_id"))
            if qmeta:
                qnum = qmeta.get("number")

        if qnum not in question_scores:
            continue

        try:
            score_value = float(row.get("score", 0.0))
        except (TypeError, ValueError):
            score_value = 0.0
        score_value = max(0.0, min(1.0, score_value))

        entry = student_entries.setdefault(
            sid,
            {
                "student_id": sid,
                "student_name": row.get("student_name")
                or row.get("roster_name")
                or roster_map.get(str(sid), {}).get("name", ""),
                "scores": {},
            },
        )
        entry["scores"][qnum] = score_value
        question_scores[qnum].append(score_value)

    total_questions = len(questions)
    ranking_rows: List[Dict[str, Any]] = []
    for entry in student_entries.values():
        normalized_scores = {
            question["number"]: entry["scores"].get(question["number"], 0.0) for question in questions
        }
        total_raw = sum(normalized_scores.values())
        total_score = total_raw / total_questions if total_questions else 0.0
        ranking_rows.append(
            {
                "student_id": entry["student_id"],
                "student_name": entry.get("student_name", ""),
                "scores": normalized_scores,
                "total_raw": total_raw,
                "total_score": total_score,
            }
        )

    ranking_rows.sort(key=lambda item: (-item["total_score"], str(item["student_id"])))
    last_score: Optional[float] = None
    current_rank = 0
    for index, row in enumerate(ranking_rows, start=1):
        score_value = row["total_score"]
        if last_score is None or abs(score_value - last_score) > 1e-6:
            current_rank = index
            last_score = score_value
        row["rank"] = current_rank

    average_scores = {}
    for question in questions:
        qnum = question["number"]
        scores_list = question_scores.get(qnum, [])
        average_scores[qnum] = sum(scores_list) / len(scores_list) if scores_list else 0.0

    average_total_raw = (
        sum(row["total_raw"] for row in ranking_rows) / len(ranking_rows) if ranking_rows else 0.0
    )
    average_total_score = average_total_raw / total_questions if total_questions else 0.0
    average_row = {
        "scores": average_scores,
        "total_raw": average_total_raw,
        "total_score": average_total_score,
    }

    overview_rows: List[Dict[str, Any]] = []
    for question in questions:
        qnum = question["number"]
        scores_list = question_scores.get(qnum, [])
        attempts = len(scores_list)
        average_score = sum(scores_list) / attempts if attempts else 0.0
        full_score_rate = sum(1 for score in scores_list if score >= 0.999) / attempts if attempts else 0.0
        overview_rows.append(
            {
                "question_number": qnum,
                "question_id": question.get("id"),
                "question_type": question.get("question_type"),
                "tags": question.get("tags", []),
                "average_score": average_score,
                "full_score_rate": full_score_rate,
                "attempts": attempts,
            }
        )

    mistake_candidates = [
        item for item in overview_rows if item.get("attempts", 0) > 0
    ]
    mistake_candidates.sort(key=lambda item: item.get("full_score_rate", 0.0))

    common_mistakes: List[Dict[str, Any]] = []
    for item in mistake_candidates[:3]:
        qnum = item.get("question_number")
        meta = next((q for q in questions if q.get("number") == qnum), {})
        common_mistakes.append(
            {
                "question_number": item.get("question_number"),
                "question_id": item.get("question_id"),
                "question_type": item.get("question_type"),
                "tags": item.get("tags", []),
                "average_score": item.get("average_score"),
                "full_score_rate": item.get("full_score_rate"),
                "latex_content": meta.get("latex_content", ""),
            }
        )

    roster_rows = []
    for sid, student in roster_map.items():
        if sid not in student_entries:
            roster_rows.append(
                {
                    "student_id": sid,
                    "student_name": student.get("name", ""),
                    "scores": {question["number"]: None for question in questions},
                    "total_raw": None,
                    "total_score": None,
                }
            )

    return {
        "paper_title": export_data.get("title") or "未命名试卷",
        "questions": questions,
        "ranking_rows": ranking_rows,
        "average_row": average_row,
        "overview_rows": overview_rows,
        "common_mistakes": common_mistakes,
        "roster_rows": roster_rows,
        "student_count": len(ranking_rows),
    }


def build_class_report_latex(paper_title: str, sections_latex: str) -> str:
    """生成完整的LaTeX文档内容。"""
    title_text = latex_escape(paper_title or "未命名试卷")
    return (
        "\\documentclass{exam-zh}\n"
        "\\usepackage{booktabs}\n"
        "\\begin{document}\n"
        "\\begin{center}\n"
        "\\LARGE 全班作业报告\\\\[6pt]\n"
        f"\\large {title_text}\n"
        "\\end{center}\n\n"
        f"{sections_latex}\n\n"
        "\\end{document}\n"
    )


def compile_latex_to_pdf(latex_content: str) -> str:
    """调用外部LaTeX编译服务生成PDF，并返回base64内容。"""
    api_url = LATEX_COMPILE_CONFIG.get("api_url")
    if not api_url:
        raise ValueError("未配置LaTeX编译服务地址")

    payload: Dict[str, Any] = {"latex_content": latex_content}
    compile_recipe = LATEX_COMPILE_CONFIG.get("compile_recipe")
    if compile_recipe:
        payload["compile_recipe"] = compile_recipe

    try:
        response = requests.post(api_url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise ValueError(f"PDF编译请求失败: {exc}") from exc

    if not data.get("success"):
        raise ValueError(data.get("error") or "PDF编译失败")

    pdf_base64 = data.get("pdf_base64")
    if not pdf_base64:
        raise ValueError("PDF编译服务未返回文件数据")
    return pdf_base64


def parse_iso_datetime(value):
    """将 ISO 字符串解析为 datetime 对象。

    参数:
        value: ISO 格式的时间字符串。

    返回:
        解析出的 datetime 对象；解析失败返回 None。
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def serialize_student(student_row):
    """将学生数据库记录转换为 API 可用结构。

    参数:
        student_row: 学生信息行字典。

    返回:
        序列化后的学生信息字典；若输入为 None 则返回 None。
    """
    if not student_row:
        return None

    avg = student_row.get('cached_average_score')
    return {
        'student_id': student_row.get('student_id'),
        'name': student_row.get('name'),
        'average_score': round(float(avg), 2) if isinstance(avg, (int, float)) else None,
        'average_updated_at': student_row.get('cached_average_updated_at'),
        'latest_history_timestamp': student_row.get('latest_history_timestamp'),
        'updated_at': student_row.get('updated_at'),
        'window_days': student_row.get('cached_average_window_days', ANALYTICS_WINDOW_DAYS),
    }


def serialize_history_item(row):
    """将作业历史记录转换为前端友好的结构。

    参数:
        row: 作业记录字典。

    返回:
        序列化后的历史记录字典；若输入为 None 则返回 None。
    """
    if not row:
        return None

    score = row.get('score')
    student_answer = row.get('student_answer') or ''
    return {
        'id': row.get('id'),
        'session_uid': row.get('session_uid'),
        'export_id': row.get('export_id'),
        'paper_title': row.get('paper_title'),
        'question_id': row.get('question_id'),
        'question_number': row.get('question_number'),
        'original_question': row.get('original_question'),
        'reference_answer': row.get('reference_answer'),
        'student_answer': student_answer,
        'score': round(float(score), 4) if isinstance(score, (int, float)) else None,
        'feedback': row.get('feedback') or '',
        'created_at': row.get('created_at'),
        'updated_at': row.get('updated_at'),
    }


def collect_history_for_report(student_id):
    """收集生成学习报告所需的历史数据。

    参数:
        student_id: 学生编号。

    返回:
        (全部历史列表, 截断列表, 最新时间戳) 的三元组。
    """
    history_records = student_manager.get_homework_history(
        student_id,
        window_days=ANALYTICS_WINDOW_DAYS,
        limit=None,
    )

    if not history_records:
        return [], [], None

    def score_key(item):
        """生成用于排序的键值，缺失分数视为 0。

        参数:
            item: 作业记录字典。

        返回:
            包含排序优先级与得分的元组。
        """
        score = item.get('score')
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
        ts = parse_iso_datetime(record.get('created_at'))
        if ts and (latest_ts is None or ts > latest_ts):
            latest_ts = ts

    return history_records, trimmed, latest_ts


def generate_report_for_student(student):
    """根据学生错题历史生成学习报告并更新缓存。

    参数:
        student: 学生信息字典。

    返回:
        (报告字典, 截断历史列表, 最新时间戳) 的三元组。
    """
    _, history_for_report, latest_ts = collect_history_for_report(student['student_id'])
    if not history_for_report:
        raise ValueError('暂无做题历史，无法生成报告')

    report = student_manager.generate_learning_report(student['name'], history_for_report)
    student_manager.cache_report(student['student_id'], report, latest_ts)

    return report, history_for_report, latest_ts

@app.route('/')
@login_required
def index():
    """主页"""
    user = system_manager.get_user_by_id(session['user_id'])
    return render_template('index.html', user=user)

@app.route('/profile')
@login_required
def profile():
    """用户中心页面"""
    user = system_manager.get_user_by_id(session['user_id'])
    return render_template('user_profile.html', user=user)

@app.route('/login')
def login_page():
    """登录页面"""
    return render_template('login.html')

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册API"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        
        success, message = system_manager.register_user(username, password, email)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        log_error_with_details(e, "用户注册API失败", username=username if 'username' in locals() else None, email=email if 'email' in locals() else None)
        return jsonify({'success': False, 'message': str(e)}), 500


# ------------------------------------------------------------------
# 学生管理与作业解析相关API
# ------------------------------------------------------------------

@app.route('/api/students', methods=['GET'])
@login_required
def list_students():
    """学生列表 API。

    返回:
        包含学生列表的 JSON 响应。
    """
    try:
        user_id = session['user_id']
        students = student_manager.list_students(user_id)
        payload = []
        for stu in students:
            serialized = serialize_student(stu)
            if serialized:
                payload.append(serialized)
        return jsonify({'success': True, 'students': payload})
    except Exception as e:
        log_error_with_details(e, "获取学生列表失败", user_id=session.get('user_id'))
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students', methods=['POST'])
@login_required
def add_student_api():
    """新增学生 API。

    返回:
        包含新增学生信息的 JSON 响应。
    """
    try:
        data = request.get_json() or {}
        student_id = (data.get('student_id') or '').strip()
        name = (data.get('name') or '').strip()
        user_id = session['user_id']

        if not student_id or not name:
            return jsonify({'success': False, 'message': '学号和姓名不能为空'}), 400

        student = student_manager.add_student(student_id, name, user_id)
        return jsonify({'success': True, 'student': serialize_student(student)})
    except ValueError as ve:
        log_error_with_details(ve, "新增学生失败-参数验证", student_id=student_id, name=name, user_id=user_id)
        return jsonify({'success': False, 'message': str(ve)}), 400
    except Exception as e:
        log_error_with_details(e, "新增学生失败", student_id=student_id, name=name, user_id=user_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/<student_id>/history', methods=['GET'])
@login_required
def get_student_history(student_id):
    """获取学生作业历史 API。

    参数:
        student_id: 路径中的学生编号。

    返回:
        包含历史记录的 JSON 响应。
    """
    try:
        limit = request.args.get('limit', type=int)
        window_days = request.args.get('window_days', type=int) or ANALYTICS_WINDOW_DAYS

        history_rows = student_manager.get_homework_history(student_id, window_days=window_days, limit=limit)
        history = [serialize_history_item(row) for row in history_rows if row]

        return jsonify({'success': True, 'history': history})
    except Exception as e:
        log_error_with_details(e, f"获取学生{student_id}做题历史失败", student_id=student_id, limit=limit, window_days=window_days)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/<student_id>/homework/parse', methods=['POST'])
@login_required
def parse_student_homework(student_id):
    """解析学生上传的作业图片并返回批改结果。

    参数:
        student_id: 路径中的学生编号。

    返回:
        批改结果的 JSON 响应。
    """
    file = request.files.get('file')
    if file is None or file.filename == '':
        return jsonify({'success': False, 'message': '请上传作业图片'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': '文件格式不支持'}), 400

    export_id_raw = request.form.get('export_id')
    student_name = (request.form.get('student_name') or '').strip()

    if not export_id_raw:
        return jsonify({'success': False, 'message': '请选择关联的试卷'}), 400

    try:
        export_id = int(export_id_raw)
    except ValueError:
        return jsonify({'success': False, 'message': '试卷信息无效'}), 400

    user_id = session['user_id']
    student_record = student_manager.get_student(student_id, user_id)
    if not student_record:
        if not student_name:
            return jsonify({'success': False, 'message': '请填写学生姓名'}), 400
        student_record = student_manager.add_student(student_id, student_name, user_id)
    else:
        student_name = student_record.get('name') or student_name

    filename = secure_filename(file.filename)
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    save_path = os.path.join(HOMEWORK_UPLOAD_DIR, unique_filename)

    try:
        file.save(save_path)

        export_data = system_manager.get_export_by_id(export_id)
        if not export_data or export_data.get('user_id') != session['user_id']:
            return jsonify({'success': False, 'message': '无法访问指定的试卷'}), 400

        question_ids = export_data.get('question_ids') or []
        questions = []
        for qid in question_ids:
            question = question_manager.get_question_by_id(qid, session['user_id'])
            if question:
                questions.append(question)

        if not questions:
            return jsonify({'success': False, 'message': '所选试卷暂无题目信息'}), 400

        paper_title = export_data.get('title') or '未命名试卷'

        parsing_bundle = perform_homework_parsing(
            save_path,
            questions,
            paper_title,
            session['user_id'],
        )
        normalized_results = parsing_bundle.get('normalized_results', [])
        detected_student_id = parsing_bundle.get('detected_student_id', '')
        detected_student_name = parsing_bundle.get('detected_student_name', '')

        return jsonify({
            'success': True,
            'paper_title': paper_title,
            'student': serialize_student(student_record),
            'export_id': export_id,
            'results': normalized_results,
            'detected_student_id': detected_student_id,
            'detected_student_name': detected_student_name,
        })
    except Exception as e:
        log_error_with_details(e, f"作业解析失败 - 学生: {student_id}", 
                              student_id=student_id, export_id=export_id, 
                              student_name=student_name, filename=file.filename if 'file' in locals() else None)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/homework/batch-parse', methods=['POST'])
@login_required
def batch_parse_homework():
    """批量解析作业文件的接口。"""
    user_id = session['user_id']
    files = request.files.getlist('files')
    if not files:
        files = request.files.getlist('file')
    if not files:
        return jsonify({'success': False, 'message': '请上传作业文件'}), 400

    export_id_raw = request.form.get('export_id')
    if not export_id_raw:
        return jsonify({'success': False, 'message': '请选择关联的试卷'}), 400

    try:
        export_id = int(export_id_raw)
    except ValueError:
        return jsonify({'success': False, 'message': '试卷信息无效'}), 400

    export_data = system_manager.get_export_by_id(export_id)
    if not export_data or export_data.get('user_id') != user_id:
        return jsonify({'success': False, 'message': '无法访问指定的试卷'}), 400

    question_ids = export_data.get('question_ids') or []
    questions: List[Dict[str, Any]] = []
    for qid in question_ids:
        question = question_manager.get_question_by_id(qid, user_id)
        if question:
            questions.append(question)

    if not questions:
        return jsonify({'success': False, 'message': '所选试卷暂无题目信息'}), 400

    paper_title = export_data.get('title') or '未命名试卷'
    roster = student_manager.list_students(user_id)
    roster_map = {
        str(student.get('student_id')): student for student in roster if isinstance(student, dict)
    }

    mapping: Dict[str, Dict[str, Any]] = {}
    mapping_order: List[str] = []
    failures: List[Dict[str, Any]] = []
    unknown_counter = 1

    for file in files:
        original_filename = getattr(file, 'filename', '') or ''
        if not original_filename:
            continue

        if not allowed_file(original_filename):
            failures.append({'filename': original_filename, 'message': '文件格式不支持'})
            continue

        filename = secure_filename(original_filename) or f"upload_{uuid.uuid4().hex}.dat"
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        save_path = os.path.join(HOMEWORK_UPLOAD_DIR, unique_filename)

        try:
            file.save(save_path)
        except Exception as exc:
            log_error_with_details(exc, "批量作业上传保存失败", filename=original_filename)
            failures.append({'filename': original_filename, 'message': '文件保存失败'})
            continue

        try:
            parsing_bundle = perform_homework_parsing(save_path, questions, paper_title, user_id)
        except Exception as exc:
            log_error_with_details(exc, "批量作业解析失败", filename=original_filename)
            failures.append({'filename': original_filename, 'message': str(exc)})
            continue

        matched_student = match_student_by_filename(original_filename, roster)
        assignment_source = 'filename' if matched_student else 'llm'
        assigned_student_id = ''
        assigned_student_name = ''

        if matched_student:
            assigned_student_id = str(matched_student.get('student_id', '')).strip()
            assigned_student_name = matched_student.get('name', '') or ''
        else:
            detected_id = parsing_bundle.get('detected_student_id', '').strip()
            detected_name = parsing_bundle.get('detected_student_name', '').strip()
            if detected_id:
                assigned_student_id = detected_id
                assigned_student_name = detected_name or roster_map.get(detected_id, {}).get('name', '')
            else:
                assignment_source = 'unknown'
                assigned_student_id = f"unknown_id{unknown_counter}"
                unknown_counter += 1
                assigned_student_name = ''

        if not assigned_student_id:
            assigned_student_id = f"unknown_id{unknown_counter}"
            unknown_counter += 1

        if assigned_student_id in mapping:
            failures.append({
                'filename': original_filename,
                'message': f'学号 {assigned_student_id} 已存在，已跳过该文件'
            })
            continue

        normalized_results = []
        for item in parsing_bundle.get('normalized_results', []):
            if not isinstance(item, dict):
                continue
            result_copy = dict(item)
            result_copy['student_id'] = assigned_student_id
            normalized_results.append(result_copy)

        question_count = len(questions)
        total_raw = sum(result.get('score', 0.0) for result in normalized_results)
        average_score = total_raw / question_count if question_count else 0.0

        mapping[assigned_student_id] = {
            'student_id': assigned_student_id,
            'student_name': assigned_student_name,
            'detected_student_id': parsing_bundle.get('detected_student_id', ''),
            'detected_student_name': parsing_bundle.get('detected_student_name', ''),
            'assignment_source': assignment_source,
            'original_filename': original_filename,
            'stored_filename': unique_filename,
            'results': normalized_results,
            'total_score': average_score,
            'total_raw': total_raw,
        }
        mapping_order.append(assigned_student_id)

    question_columns = [
        {
            'question_number': index,
            'question_id': question.get('id'),
            'question_type': question.get('question_type'),
        }
        for index, question in enumerate(questions, start=1)
    ]

    return jsonify({
        'success': True,
        'paper_title': paper_title,
        'export_id': export_id,
        'questions': question_columns,
        'mapping': mapping,
        'order': mapping_order,
        'failures': failures,
    })


@app.route('/api/students/homework/batch-save', methods=['POST'])
@login_required
def batch_save_homework():
    """批量保存作业批改结果的接口。"""
    user_id = session['user_id']
    data = request.get_json() or {}
    export_id_raw = data.get('export_id')
    paper_title = data.get('paper_title') or ''
    entries = data.get('students') or []

    if not export_id_raw:
        return jsonify({'success': False, 'message': '缺少试卷信息'}), 400

    try:
        export_id = int(export_id_raw)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '试卷信息无效'}), 400

    if not entries:
        return jsonify({'success': False, 'message': '没有可保存的作业结果'}), 400

    saved: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        student_id = (entry.get('student_id') or '').strip()
        if not student_id or student_id.startswith('unknown_id'):
            skipped.append({'student_id': student_id or '', 'reason': '未指定有效学生'})
            continue

        student_name = (entry.get('student_name') or '').strip()
        results = entry.get('results') or []
        if not results:
            skipped.append({'student_id': student_id, 'reason': '缺少作业结果'})
            continue

        student = student_manager.get_student(student_id, user_id)
        if not student:
            if not student_name:
                skipped.append({'student_id': student_id, 'reason': '缺少学生姓名'})
                continue
            student = student_manager.add_student(student_id, student_name, user_id)
        else:
            student_name = student.get('name') or student_name

        items: List[HomeworkItem] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            try:
                score = float(result.get('score', 0))
            except (TypeError, ValueError):
                score = 0.0
            score = max(0.0, min(1.0, score))
            item = HomeworkItem(
                question_id=result.get('question_id'),
                question_number=str(result.get('question_number')),
                original_question=result.get('original_question') or '',
                reference_answer=result.get('reference_answer') or '',
                student_answer=result.get('student_answer') or '',
                score=score,
                feedback=result.get('feedback') or '',
            )
            items.append(item)

        if not items:
            skipped.append({'student_id': student_id, 'reason': '作业结果格式无效'})
            continue

        session_uid = student_manager.record_homework_results(
            student_id=student_id,
            student_name=student_name,
            export_id=export_id,
            paper_title=paper_title,
            items=items,
            user_id=user_id,
            raw_payload=entry,
        )
        saved.append({'student_id': student_id, 'session_uid': session_uid})

    return jsonify({
        'success': True,
        'saved': saved,
        'skipped': skipped,
    })


@app.route('/api/students/class-report', methods=['POST'])
@login_required
def generate_class_report():
    """生成全班作业报告的数据。"""
    user_id = session['user_id']
    data = request.get_json() or {}
    export_id_raw = data.get('export_id')
    if not export_id_raw:
        return jsonify({'success': False, 'message': '缺少试卷信息'}), 400

    try:
        export_id = int(export_id_raw)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '试卷信息无效'}), 400

    try:
        context = build_class_report_context(export_id, user_id)
        sections = build_section_instances(context)
        sections_payload = build_sections_payload(sections)
    except Exception as exc:
        log_error_with_details(exc, "生成全班报告失败", export_id=export_id)
        return jsonify({'success': False, 'message': str(exc)}), 500

    return jsonify({
        'success': True,
        'paper_title': context.get('paper_title'),
        'section_order': sections_payload.get('order', []),
        'sections': sections_payload.get('sections', {}),
        'question_count': len(context.get('questions', [])),
        'student_count': context.get('student_count', 0),
    })


@app.route('/api/students/class-report/download', methods=['POST'])
@login_required
def download_class_report():
    """生成并下载全班作业报告PDF。"""
    user_id = session['user_id']
    data = request.get_json() or {}
    export_id_raw = data.get('export_id')
    if not export_id_raw:
        return jsonify({'success': False, 'message': '缺少试卷信息'}), 400

    try:
        export_id = int(export_id_raw)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '试卷信息无效'}), 400

    try:
        context = build_class_report_context(export_id, user_id)
        sections = build_section_instances(context)
        sections_latex = render_sections_latex(sections)
        latex_content = build_class_report_latex(context.get('paper_title'), sections_latex)
        pdf_base64 = compile_latex_to_pdf(latex_content)
    except Exception as exc:
        log_error_with_details(exc, "导出全班报告PDF失败", export_id=export_id)
        return jsonify({'success': False, 'message': str(exc)}), 500

    return jsonify({
        'success': True,
        'paper_title': context.get('paper_title'),
        'pdf_base64': pdf_base64,
    })


@app.route('/api/students/<student_id>/homework/save', methods=['POST'])
@login_required
def save_student_homework(student_id):
    """保存学生作业批改结果 API。

    参数:
        student_id: 路径中的学生编号。

    返回:
        保存结果的 JSON 响应。
    """
    try:
        data = request.get_json() or {}
        export_id_value = data.get('export_id')
        paper_title = data.get('paper_title') or ''
        student_name = (data.get('student_name') or '').strip()
        results = data.get('results') or []

        if not export_id_value:
            return jsonify({'success': False, 'message': '缺少试卷信息'}), 400

        try:
            export_id = int(export_id_value)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': '试卷信息无效'}), 400

        if not results:
            return jsonify({'success': False, 'message': '没有可保存的作业结果'}), 400

        user_id = session['user_id']
        student = student_manager.get_student(student_id, user_id)
        if not student:
            if not student_name:
                return jsonify({'success': False, 'message': '请提供学生姓名'}), 400
            student = student_manager.add_student(student_id, student_name, user_id)
        else:
            student_name = student.get('name') or student_name

        items = []
        for result in results:
            if not isinstance(result, dict):
                continue
            try:
                score = float(result.get('score', 0))
            except (TypeError, ValueError):
                score = 0.0
            score = max(0.0, min(1.0, score))

            item = HomeworkItem(
                question_id=result.get('question_id'),
                question_number=str(result.get('question_number')),
                original_question=result.get('original_question') or '',
                reference_answer=result.get('reference_answer') or '',
                student_answer=result.get('student_answer') or '',
                score=score,
                feedback=result.get('feedback') or '',
            )
            items.append(item)

        if not items:
            return jsonify({'success': False, 'message': '作业结果格式无效'}), 400

        user_id = session['user_id']
        session_uid = student_manager.record_homework_results(
            student_id=student_id,
            student_name=student_name,
            export_id=export_id,
            paper_title=paper_title,
            items=items,
            user_id=user_id,
            raw_payload=data,
        )

        refreshed_student = student_manager.get_student(student_id, user_id)

        return jsonify({
            'success': True,
            'session_uid': session_uid,
            'student': serialize_student(refreshed_student),
        })
    except ValueError as ve:
        log_error_with_details(ve, f"保存作业解析结果失败-参数验证 - 学生: {student_id}", 
                              student_id=student_id, export_id=export_id_value)
        return jsonify({'success': False, 'message': str(ve)}), 400
    except Exception as e:
        log_error_with_details(e, f"保存作业解析结果失败 - 学生: {student_id}", 
                              student_id=student_id, export_id=export_id_value, 
                              paper_title=paper_title, results_count=len(results) if 'results' in locals() else 0)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/students/<student_id>/report', methods=['GET'])
@login_required
def get_student_report(student_id):
    """获取或生成学生学习报告 API。

    参数:
        student_id: 路径中的学生编号。

    返回:
        学习报告或错误信息的 JSON 响应。
    """
    try:
        user_id = session['user_id']
        student = student_manager.get_student(student_id, user_id)
        if not student:
            return jsonify({'success': False, 'message': '学生不存在'}), 404

        force_refresh = request.args.get('refresh', 'false').lower() == 'true'

        if force_refresh or student_manager.needs_report_refresh(student_id):
            report, history_for_report, _ = generate_report_for_student(student)
            return jsonify({
                'success': True,
                'report': report,
                'cached': False,
                'history_preview': [serialize_history_item(item) for item in history_for_report],
                'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            })

        cached = student_manager.get_cached_report(student_id) or {}
        _, history_for_report, _ = collect_history_for_report(student_id)

        return jsonify({
            'success': True,
            'report': cached,
            'cached': True,
            'history_preview': [serialize_history_item(item) for item in history_for_report],
            'generated_at': student.get('cached_report_generated_at'),
        })
    except ValueError as ve:
        log_error_with_details(ve, f"生成学习报告失败-参数验证 - 学生: {student_id}", 
                              student_id=student_id, force_refresh=force_refresh)
        return jsonify({'success': False, 'message': str(ve)}), 400
    except Exception as e:
        log_error_with_details(e, f"生成学习报告失败 - 学生: {student_id}", 
                              student_id=student_id, force_refresh=force_refresh, user_id=user_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/students/<student_id>/recommendations', methods=['GET'])
@login_required
def get_student_recommendations(student_id):
    """获取学生题目推荐 API。

    参数:
        student_id: 路径中的学生编号。

    返回:
        推荐题目的 JSON 响应。
    """
    try:
        user_id = session['user_id']
        student = student_manager.get_student(student_id, user_id)
        if not student:
            return jsonify({'success': False, 'message': '学生不存在'}), 404

        recommendations = student_manager.build_recommendations(
            student_id,
            current_user_id=user_id
        )

        return jsonify({
            'success': True,
            'questions': recommendations,
        })
    except ValueError as ve:
        log_error_with_details(ve, f"生成AI题目推荐失败-参数验证 - 学生: {student_id}", student_id=student_id)
        return jsonify({'success': False, 'message': str(ve)}), 400
    except Exception as e:
        log_error_with_details(e, f"生成AI题目推荐失败 - 学生: {student_id}", 
                              student_id=student_id, user_id=user_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录API"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = system_manager.authenticate_user(username, password)
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return jsonify({
                'success': True,
                'message': '登录成功',
                'user': user
            })
        else:
            return jsonify({
                'success': False,
                'message': '用户名或密码错误'
            })
    except Exception as e:
        log_error_with_details(e, "用户登录API失败", username=username if 'username' in locals() else None)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出API"""
    session.clear()
    return jsonify({'success': True, 'message': '已登出'})

@app.route('/api/auth/current', methods=['GET'])
@login_required
def get_current_user():
    """获取当前登录用户信息API"""
    user = system_manager.get_user_by_id(session['user_id'])
    if user:
        return jsonify({
            'success': True,
            'user': user
        })
    return jsonify({'success': False, 'message': '未登录'}), 401

@app.route('/static/<path:filename>')
def static_files(filename):
    """静态文件服务"""
    return send_from_directory('static', filename)

@app.route('/api/questions', methods=['POST'])
@login_required
def add_question():
    """添加题目API"""
    try:
        data = request.get_json()
        
        # 验证必需字段
        if not data or 'latex_content' not in data:
            return jsonify({'success': False, 'message': '题目内容不能为空'}), 400
        
        latex_content = data['latex_content']
        tags = data.get('tags', [])
        reference_answer = data.get('reference_answer', '')
        source = data.get('source', '')
        image = data.get('image', [])
        visibility = data.get('visibility', 'public')  # 新增：可见范围，默认所有人
        question_type = data.get('question_type', '解答题')
        
        # 添加题目
        question_id = question_manager.add_question(
            latex_content=latex_content,
            tags=tags,
            reference_answer=reference_answer,
            source=source,
            image=image,
            user_id=session['user_id'],
            visibility=visibility,
            question_type=question_type
        )
        
        return jsonify({
            'success': True, 
            'message': '题目添加成功',
            'question_id': question_id
        })
        
    except Exception as e:
        log_error_with_details(e, "添加题目API失败", 
                              user_id=session.get('user_id'), 
                              latex_content_length=len(latex_content) if 'latex_content' in locals() else 0,
                              tags=tags if 'tags' in locals() else None)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/questions/<int:question_id>', methods=['PUT'])
@login_required
def update_question(question_id):
    """更新题目API"""
    try:
        data = request.get_json() or {}
        latex_content = (data.get('latex_content') or '').strip()
        reference_answer = data.get('reference_answer', '')
        question_type = data.get('question_type')

        if not latex_content:
            return jsonify({'success': False, 'message': '题目内容不能为空'}), 400

        current_user_id = session['user_id']
        question = question_manager.get_question_by_id(question_id, current_user_id)
        if not question:
            return jsonify({'success': False, 'message': '题目不存在或无权访问'}), 404

        if question.get('user_id') != current_user_id:
            return jsonify({'success': False, 'message': '无权修改该题目'}), 403

        updated_question = question_manager.update_question(
            question_id=question_id,
            latex_content=latex_content,
            reference_answer=reference_answer,
            current_user_id=current_user_id,
            question_type=question_type
        )

        return jsonify({
            'success': True,
            'question': updated_question
        })

    except PermissionError as e:
        log_error_with_details(e, f"更新题目失败-权限错误 - question_id: {question_id}", 
                              question_id=question_id, current_user_id=current_user_id)
        return jsonify({'success': False, 'message': str(e)}), 403
    except ValueError as e:
        log_error_with_details(e, f"更新题目失败-参数验证 - question_id: {question_id}", 
                              question_id=question_id, latex_content_length=len(latex_content) if 'latex_content' in locals() else 0)
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        log_error_with_details(e, f"更新题目失败 - question_id: {question_id}", 
                              question_id=question_id, current_user_id=current_user_id)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/auto-tag', methods=['POST'])
@login_required
def auto_tag_question():
    """自动打标、生成解答和LaTeX格式化API"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({'success': False, 'message': '题目内容不能为空'}), 400
        
        content = data['content']
        source = data.get('source', '')
        user_id = session.get('user_id')
        
        logger.log_user_action(user_id, "自动打标和LaTeX格式化", f"内容长度: {len(content)}")
        
        # 自动打标、生成解答和LaTeX格式化
        tags, answer, latex_content, question_type = question_manager.auto_tag_and_answer(content, source)
        
        duration = time.time() - start_time
        logger.log_performance("自动打标API", duration, f"用户ID: {user_id}")
        
        return jsonify({
            'success': True,
            'tags': tags,
            'answer': answer,
            'latex_content': latex_content,
            'question_type': question_type
        })
        
    except Exception as e:
        log_error_with_details(e, f"自动打标API失败 - 用户ID: {session.get('user_id')}", 
                              user_id=session.get('user_id'), 
                              content_length=len(content) if 'content' in locals() else 0,
                              source=source if 'source' in locals() else None)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/search', methods=['GET'])
@login_required
def search_questions():
    """搜索题目API"""
    try:
        # 获取查询参数
        tags = request.args.getlist('tags')
        keyword = request.args.get('keyword', '')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        # 获取当前用户ID
        current_user_id = session['user_id']
        
        questions = []
        
        if tags:
            # 按标签查询
            questions = question_manager.get_questions_by_tags(tags, current_user_id)
        elif keyword:
            # 关键词搜索
            questions = question_manager.search_questions(keyword, current_user_id)
        else:
            # 获取所有题目
            questions = question_manager.get_all_questions(limit, offset, current_user_id)
        
        return jsonify({
            'success': True,
            'questions': questions,
            'total': len(questions)
        })
        
    except Exception as e:
        log_error_with_details(e, "搜索题目API失败", 
                              user_id=session.get('user_id'), 
                              tags=tags if 'tags' in locals() else None,
                              keyword=keyword if 'keyword' in locals() else None,
                              page=page if 'page' in locals() else None)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/questions/<int:question_id>', methods=['GET'])
@login_required
def get_question(question_id):
    """获取单个题目详情API"""
    try:
        current_user_id = session['user_id']
        question = question_manager.get_question_by_id(question_id, current_user_id)
        
        if question:
            return jsonify({
                'success': True,
                'question': question
            })
        else:
            return jsonify({
                'success': False,
                'message': '题目不存在或无权访问'
            }), 404
            
    except Exception as e:
        log_error_with_details(e, f"获取单个题目详情API失败 - question_id: {question_id}", 
                              question_id=question_id, current_user_id=current_user_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/questions/<int:question_id>/ai-variant', methods=['POST'])
@login_required
def generate_question_variant(question_id):
    """AI生成题目变体API"""
    try:
        current_user_id = session['user_id']
        base_question = question_manager.get_question_by_id(question_id, current_user_id)

        if not base_question:
            return jsonify({'success': False, 'message': '题目不存在或无权访问'}), 404

        if base_question.get('user_id') != current_user_id:
            return jsonify({'success': False, 'message': '无权对此题目生成变体'}), 403

        data = request.get_json() or {}
        working_question = dict(base_question)
        override_content = data.get('latex_content')
        override_answer = data.get('reference_answer')

        if override_content:
            working_question['latex_content'] = override_content
        if override_answer is not None:
            working_question['reference_answer'] = override_answer

        variant = question_manager.generate_question_variant(working_question)

        return jsonify({
            'success': True,
            'variant': variant
        })
    except ValueError as e:
        log_error_with_details(e, f"AI变题失败-参数验证 - question_id: {question_id}", 
                              question_id=question_id, current_user_id=current_user_id)
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        log_error_with_details(e, f"AI变题失败 - question_id: {question_id}", 
                              question_id=question_id, current_user_id=current_user_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/questions/stats', methods=['GET'])
@login_required
def get_question_stats():
    """获取题目统计信息API"""
    try:
        current_user_id = session['user_id']
        stats = question_manager.get_question_stats(current_user_id)
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        log_error_with_details(e, "获取题目统计信息API失败", 
                              current_user_id=current_user_id)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """上传图片API"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        if file and allowed_file(file.filename):
            # 生成唯一文件名
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            unique_filename = f"{uuid.uuid4()}{ext}"
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            
            return jsonify({
                'success': True,
                'filename': unique_filename,
                'url': f'/uploads/{unique_filename}'
            })
        else:
            return jsonify({'success': False, 'message': '不支持的文件类型'}), 400
            
    except Exception as e:
        log_error_with_details(e, "上传图片API失败", 
                              filename=file.filename if 'file' in locals() else None,
                              user_id=session.get('user_id'))
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """提供上传的图片文件"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/images/<path:path>')
def serve_image(path):
    """
    提供图片文件服务，支持 uploads 目录下的所有图片
    例如：/uploads/ocr_images/ocr_463c588a_0.jpg
    """
    try:
        # 构建完整文件路径
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], path)
        
        # 安全检查：确保路径在 uploads 目录内
        upload_folder = os.path.abspath(app.config['UPLOAD_FOLDER'])
        abs_file_path = os.path.abspath(file_path)
        
        if not abs_file_path.startswith(upload_folder):
            return jsonify({'error': 'Invalid path'}), 403
        
        # 检查文件是否存在
        if os.path.exists(abs_file_path) and os.path.isfile(abs_file_path):
            return send_from_directory(upload_folder, path)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        log_error_with_details(e, f"图片服务错误 - path: {path}", path=path)
        return jsonify({'error': str(e)}), 500

@app.route('/api/questions/<int:question_id>', methods=['DELETE'])
@login_required
def delete_question(question_id):
    """删除题目API"""
    try:
        current_user_id = session['user_id']
        success = question_manager.delete_question(question_id, current_user_id)

        if success:
            return jsonify({
                'success': True,
                'message': '题目删除成功'
            })
        else:
            return jsonify({
                'success': False,
                'message': '题目不存在或无权删除'
            }), 404

    except Exception as e:
        log_error_with_details(e, f"删除题目API失败 - question_id: {question_id}", 
                              question_id=question_id, current_user_id=current_user_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/pdf-preview', methods=['POST'])
@login_required
def pdf_preview():
    """生成PDF文件第一页的预览图"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '没有选择文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '没有选择文件'}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'message': '仅支持PDF文件预览'}), 400

    try:
        pdf_content = file.read()
        if not pdf_content:
            return jsonify({'success': False, 'message': '文件内容为空'}), 400

        images = convert_from_bytes(pdf_content, first_page=1, last_page=1)
        if not images:
            return jsonify({'success': False, 'message': '无法生成PDF预览'}), 500

        preview_image = images[0]
        buffer = BytesIO()
        preview_image.save(buffer, format='PNG')
        preview_data = base64.b64encode(buffer.getvalue()).decode('ascii')

        return jsonify({
            'success': True,
            'preview': f'data:image/png;base64,{preview_data}'
        })
    except Exception as e:
        log_error_with_details(e, f"生成PDF预览失败 - 文件名: {file.filename}", 
                              filename=file.filename if 'file' in locals() else None,
                              user_id=session.get('user_id'))
        return jsonify({'success': False, 'message': f'无法生成PDF预览: {str(e)}'}), 500


@app.route('/api/ocr-parse', methods=['POST'])
@login_required
def ocr_parse():
    """OCR解析试卷API"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        if file and allowed_file(file.filename):
            upload_images_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'upload_images')
            os.makedirs(upload_images_dir, exist_ok=True)

            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            ext = (ext or '').lower()
            unique_filename = f"{uuid.uuid4()}{ext}"
            file_path = os.path.join(upload_images_dir, unique_filename)
            file.save(file_path)

            file_extension = ext.lstrip('.')
            is_pdf = file_extension == 'pdf'

            try:
                markdown_segments = []
                image_filename_mapping = {}

                if is_pdf:
                    logger.log_system_info(f"开始处理PDF试卷 - 文件: {file_path}")
                    page_image_paths = convert_pdf_to_images(file_path, upload_images_dir)
                    for page_index, image_path in page_image_paths:
                        logger.log_system_info(f"开始OCR处理 - PDF第{page_index}页: {image_path}")
                        ocr_result = ocr_client.ocr_image(image_path)
                        page_markdown = ocr_result.get('markdown', '')
                        ocr_images = ocr_result.get('images', [])
                        logger.log_ocr_result(ocr_result.get('request_id', 'unknown'), page_markdown, len(ocr_images))

                        page_mapping, replacements = save_ocr_images(
                            ocr_images,
                            app.config['UPLOAD_FOLDER'],
                            logger,
                            suffix=f"_p{page_index}",
                        )
                        image_filename_mapping.update(page_mapping)
                        page_markdown = apply_filename_replacements(page_markdown, replacements)
                        markdown_segments.append(page_markdown)
                else:
                    logger.log_system_info(f"开始OCR处理 - 文件: {file_path}")
                    ocr_result = ocr_client.ocr_image(file_path)
                    markdown_content = ocr_result.get('markdown', '')
                    ocr_images = ocr_result.get('images', [])
                    logger.log_ocr_result(ocr_result.get('request_id', 'unknown'), markdown_content, len(ocr_images))

                    page_mapping, replacements = save_ocr_images(
                        ocr_images,
                        app.config['UPLOAD_FOLDER'],
                        logger,
                    )
                    image_filename_mapping.update(page_mapping)
                    markdown_segments.append(apply_filename_replacements(markdown_content, replacements))

                markdown_content = '\n\n'.join(segment for segment in markdown_segments if segment)
                logger.log_system_info(
                    f"开始解析试卷，markdown内容长度: {len(markdown_content)}, 可用图片数量: {len(image_filename_mapping)}"
                )

                parsed_questions = question_manager.parse_exam_paper(
                    markdown_content,
                    image_filename_mapping,
                    get_answer_batch_size=EXAM_PARSE_ANSWER_BATCH_SIZE if is_pdf else None,
                )
                logger.log_question_parsing(len(parsed_questions), "试卷解析")

                if not parsed_questions:
                    return jsonify({
                        'success': False,
                        'message': '试卷解析完成，但没有识别出任何题目。请检查试卷图片质量或内容格式。'
                    })

                return jsonify({
                    'success': True,
                    'questions': parsed_questions
                })

            except Exception as e:
                log_error_with_details(e, "OCR解析试卷失败", 
                                      filename=file.filename if 'file' in locals() else None,
                                      file_path=file_path if 'file_path' in locals() else None,
                                      user_id=session.get('user_id'))
                return jsonify({'success': False, 'message': f'OCR解析失败: {str(e)}'}), 500
        else:
            return jsonify({'success': False, 'message': '不支持的文件类型'}), 400
            
    except Exception as e:
        log_error_with_details(e, "OCR解析API失败", 
                              filename=file.filename if 'file' in locals() else None,
                              user_id=session.get('user_id'))
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tags', methods=['GET'])
def get_tags():
    """获取所有可用标签API"""
    try:
        tags = system_manager.get_all_tags(limit=20)
        tag_names = [tag['name'] for tag in tags]
        return jsonify({
            'success': True,
            'tags': tag_names
        })
    except Exception as e:
        log_error_with_details(e, "获取所有可用标签API失败")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/export-paper', methods=['POST'])
@login_required
def export_paper():
    """导出试卷API"""
    try:
        data = request.get_json()
        questions = data.get('questions', [])
        title = data.get('title', '数学试卷')
        mode = data.get('mode', 'questions')  # questions 或 with-answers
        format_type = data.get('format', 'latex')  # latex, docx, 或 pdf
        
        if not questions:
            return jsonify({'success': False, 'message': '没有题目可导出'}), 400
        
        # 保存导出历史
        question_ids = [q.get('id') for q in questions if q.get('id')]
        if question_ids:
            system_manager.save_export_history(
                user_id=session['user_id'],
                title=title,
                question_ids=question_ids,
                export_format=format_type,
                export_mode=mode
            )
        
        # 生成文件内容
        if format_type == 'latex':
            content = export_renderer.render_latex(questions, mode, title)
            mimetype = 'text/plain'
            filename = f'{title}_{uuid.uuid4().hex[:8]}.tex'
        elif format_type == 'docx':
            file_path = export_renderer.render_docx(questions, mode, title)
            return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), 
                                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        elif format_type == 'pdf':
            file_path = export_renderer.render_pdf(questions, mode, title)
            return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path), 
                                     as_attachment=True, mimetype='application/pdf')
        else:
            return jsonify({'success': False, 'message': '不支持的格式'}), 400
        
        # 对于LaTeX，直接返回内容
        from flask import Response
        return Response(
            content,
            mimetype=mimetype,
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        log_error_with_details(e, "导出试卷API失败", 
                              user_id=session.get('user_id'),
                              title=title if 'title' in locals() else None,
                              format_type=format_type if 'format_type' in locals() else None,
                              mode=mode if 'mode' in locals() else None,
                              questions_count=len(questions) if 'questions' in locals() else 0)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/user/exports', methods=['GET'])
@login_required
def get_user_exports():
    """获取用户导出记录API"""
    try:
        user_id = session['user_id']
        exports = system_manager.get_export_history(user_id, limit=50)
        return jsonify({
            'success': True,
            'exports': exports
        })
    except Exception as e:
        log_error_with_details(e, "获取用户导出记录API失败", user_id=user_id)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/user/reset-password', methods=['POST'])
@login_required
def reset_password():
    """重置密码API"""
    try:
        data = request.get_json()
        user_id = session['user_id']
        old_password = data.get('old_password')
        new_password = data.get('new_password')
        
        success, message = system_manager.update_password(user_id, old_password, new_password)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        log_error_with_details(e, "重置密码API失败", user_id=user_id)
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/user/re-export/<int:export_id>', methods=['GET'])
@login_required
def get_re_export_data(export_id):
    """获取重新导出数据API"""
    try:
        user_id = session['user_id']
        export_data = system_manager.get_export_by_id(export_id)
        
        if not export_data or export_data['user_id'] != user_id:
            return jsonify({'success': False, 'message': '导出记录不存在或无权访问'}), 404
        
        # 根据题目ID获取题目详情
        questions = []
        for question_id in export_data['question_ids']:
            question = question_manager.get_question_by_id(question_id, user_id)
            if question:
                questions.append(question)
        
        return jsonify({
            'success': True,
            'export': export_data,
            'questions': questions
        })
    except Exception as e:
        log_error_with_details(e, f"获取重新导出数据API失败 - export_id: {export_id}", 
                              export_id=export_id, user_id=user_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return jsonify({'success': False, 'message': '页面不存在'}), 404

@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    return jsonify({'success': False, 'message': '服务器内部错误'}), 500

if __name__ == '__main__':
    # 确保templates目录存在
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    print(f"启动Web服务器: http://{WEB_CONFIG['host']}:{WEB_CONFIG['port']}")
    app.run(
        host=WEB_CONFIG['host'],
        port=WEB_CONFIG['port'],
        debug=WEB_CONFIG['debug']
    )
