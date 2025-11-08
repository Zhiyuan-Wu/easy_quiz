"""学生与学情管理模块"""

from __future__ import annotations

import os
import json
import re
import uuid
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from config import (
    STUDENT_DATABASE_PATH,
    HOMEWORK_DATABASE_PATH,
    ANALYTICS_WINDOW_DAYS,
    REPORT_MAX_ITEMS,
    AI_RECOMMENDATION_LIMIT,
    AVERAGE_CACHE_TTL_SECONDS,
    LLM_CONFIG,
)
from logger import get_logger
from json_repair import repair_json


def _ensure_parent_dir(path: str) -> None:
    """确保目标路径的父目录存在。

    参数:
        path: 需要验证的文件路径。

    返回:
        None。
    """
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _utc_now() -> datetime:
    """获取当前的 UTC 时间。

    返回:
        当前 UTC 时间的 datetime 对象。
    """
    return datetime.now(datetime.timezone.utc)


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """将 ISO 格式字符串转换为 datetime 对象。

    参数:
        value: ISO 格式的时间字符串，可能为 None。

    返回:
        转换后的 datetime 对象，若无法转换则返回 None。
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _format_timestamp(dt: Optional[datetime]) -> Optional[str]:
    """将 datetime 对象格式化为秒级精度的 ISO 字符串。

    参数:
        dt: 需要格式化的 datetime 对象，可能为 None。

    返回:
        格式化后的字符串；如果输入为 None 则返回 None。
    """
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds")


def _extract_outermost_json_block(raw_text: str) -> str:
    """从 LLM 输出中提取最外层的 JSON 文本。

    参数:
        raw_text: 原始的模型输出文本。

    返回:
        匹配到的最外层 JSON 字符串。
    """
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        raise ValueError("未在模型输出中找到JSON对象")
    return match.group(0)


@dataclass
class HomeworkItem:
    """单道作业批改记录的数据结构。

    属性:
        question_id: 题目在题库中的 ID，可能为 None。
        question_number: 题目编号字符串。
        original_question: 原题 LaTeX 内容。
        reference_answer: 参考答案内容。
        student_answer: 学生作答文本。
        score: 批改得分，范围 0~1。
        feedback: 针对该题的反馈。
    """

    question_id: Optional[int]
    question_number: str
    original_question: str
    reference_answer: str
    student_answer: str
    score: float
    feedback: str


class StudentManager:
    """封装学生信息与作业结果的持久化与缓存逻辑"""

    def __init__(
        self,
        question_manager,
        system_manager,
        llm_client: OpenAI,
    ) -> None:
        """初始化学生管理器并完成数据库准备。

        参数:
            question_manager: 题目管理器实例。
            system_manager: 系统管理器实例。
            llm_client: LLM 客户端对象。

        返回:
            None。
        """
        self.logger = get_logger()
        self.question_manager = question_manager
        self.system_manager = system_manager
        self.llm_client = llm_client
        self.model_name = LLM_CONFIG.get("model") or "deepseek-chat"

        _ensure_parent_dir(STUDENT_DATABASE_PATH)
        _ensure_parent_dir(HOMEWORK_DATABASE_PATH)

        self._init_student_db()
        self._init_homework_db()

    # ------------------------------------------------------------------
    # 数据库初始化与连接
    # ------------------------------------------------------------------
    def _student_conn(self) -> sqlite3.Connection:
        """创建学生信息数据库的连接。

        返回:
            sqlite3.Connection 对象，用于访问学生数据表。
        """
        conn = sqlite3.connect(STUDENT_DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _homework_conn(self) -> sqlite3.Connection:
        """创建作业批改结果数据库的连接。

        返回:
            sqlite3.Connection 对象，用于访问作业结果数据表。
        """
        conn = sqlite3.connect(HOMEWORK_DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_student_db(self) -> None:
        """初始化学生信息表并创建必要索引。

        返回:
            None。
        """
        conn = self._student_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    cached_average_score REAL,
                    cached_average_window_days INTEGER,
                    cached_average_updated_at TEXT,
                    cached_report_json TEXT,
                    cached_report_generated_at TEXT,
                    cached_report_history_timestamp TEXT,
                    latest_history_timestamp TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(student_id, user_id)
                )
                """
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_students_updated_at ON students(updated_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_students_latest_history ON students(latest_history_timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_students_user_id ON students(user_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def _init_homework_db(self) -> None:
        """初始化作业结果表并创建必要索引。

        返回:
            None。
        """
        conn = self._homework_conn()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS homework_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_uid TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    student_name TEXT NOT NULL,
                    export_id INTEGER NOT NULL,
                    paper_title TEXT,
                    question_id INTEGER,
                    question_number TEXT,
                    original_question TEXT,
                    reference_answer TEXT,
                    student_answer TEXT,
                    score REAL,
                    feedback TEXT,
                    raw_payload TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_homework_student ON homework_results(student_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_homework_session ON homework_results(session_uid)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_homework_created ON homework_results(created_at)"
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 学生基本信息
    # ------------------------------------------------------------------
    def add_student(self, student_id: str, name: str, user_id: int) -> Dict:
        """创建新学生记录并返回数据库中的存储结果。

        参数:
            student_id: 学生编号。
            name: 学生姓名。
            user_id: 当前用户的 ID。

        返回:
            包含学生信息的字典。
        """
        student_id = student_id.strip()
        name = name.strip()
        if not student_id or not name:
            raise ValueError("学号和姓名不能为空")
        if user_id is None:
            raise ValueError("用户ID不能为空")

        now = _format_timestamp(_utc_now())
        conn = self._student_conn()
        try:
            conn.execute(
                """
                INSERT INTO students (
                    student_id, name, user_id, cached_average_window_days, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (student_id, name, user_id, ANALYTICS_WINDOW_DAYS, now, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("学号已存在，请勿重复添加")
        finally:
            conn.close()

        return self.get_student(student_id, user_id)

    def get_student(self, student_id: str, user_id: int) -> Optional[Dict]:
        """根据学号查询学生信息，并在必要时刷新缓存数据。

        参数:
            student_id: 学生编号。
            user_id: 当前用户的 ID。

        返回:
            学生信息字典，若不存在则为 None。
        """
        conn = self._student_conn()
        try:
            row = conn.execute(
                "SELECT * FROM students WHERE student_id = ? AND user_id = ?",
                (student_id, user_id),
            ).fetchone()
            if not row:
                return None
            student = dict(row)
            return self._ensure_average_cache(student)
        finally:
            conn.close()

    def list_students(self, user_id: int) -> List[Dict]:
        """获取指定用户下的学生列表，并返回缓存已刷新后的数据。

        参数:
            user_id: 当前用户的 ID。

        返回:
            学生信息字典的列表。
        """
        conn = self._student_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM students WHERE user_id = ? ORDER BY updated_at DESC, student_id ASC",
                (user_id,),
            ).fetchall()
        finally:
            conn.close()

        students: List[Dict] = []
        for row in rows:
            student = dict(row)
            students.append(self._ensure_average_cache(student))
        return students

    # ------------------------------------------------------------------
    # 平均分缓存
    # ------------------------------------------------------------------
    def _ensure_average_cache(self, student_row: Dict) -> Dict:
        """确保学生的平均分缓存有效，并返回更新后的记录。

        参数:
            student_row: 学生数据行字典。

        返回:
            经过缓存刷新后的学生信息字典。
        """
        student_id = student_row.get("student_id")
        if not student_id:
            return student_row

        user_id = student_row.get("user_id")

        cached_updated_at = _parse_timestamp(student_row.get("cached_average_updated_at"))
        latest_history = _parse_timestamp(student_row.get("latest_history_timestamp"))

        needs_refresh = False
        if latest_history and (not cached_updated_at or latest_history > cached_updated_at):
            needs_refresh = True
        elif cached_updated_at:
            ttl = timedelta(seconds=AVERAGE_CACHE_TTL_SECONDS)
            if _utc_now() - cached_updated_at > ttl:
                needs_refresh = True
        else:
            needs_refresh = True

        if not needs_refresh:
            return student_row

        avg_score, latest_ts = self._compute_average(student_id, ANALYTICS_WINDOW_DAYS)
        now_iso = _format_timestamp(_utc_now())
        params = [
            avg_score,
            now_iso,
            ANALYTICS_WINDOW_DAYS,
            _format_timestamp(latest_ts) if latest_ts else None,
            now_iso,
            student_id,
        ]

        where_clause = "student_id = ?"
        if user_id is not None:
            where_clause += " AND user_id = ?"
            params.append(user_id)

        conn = self._student_conn()
        try:
            conn.execute(
                f"""
                UPDATE students
                SET cached_average_score = ?,
                    cached_average_updated_at = ?,
                    cached_average_window_days = ?,
                    latest_history_timestamp = COALESCE(?, latest_history_timestamp),
                    updated_at = ?
                WHERE {where_clause}
                """,
                tuple(params),
            )
            conn.commit()
            if user_id is not None:
                refreshed = conn.execute(
                    "SELECT * FROM students WHERE student_id = ? AND user_id = ?",
                    (student_id, user_id),
                ).fetchone()
            else:
                refreshed = conn.execute(
                    "SELECT * FROM students WHERE student_id = ?",
                    (student_id,),
                ).fetchone()
            if refreshed:
                return dict(refreshed)
        finally:
            conn.close()

        # Fallback when no refreshed row was fetched (e.g. missing user_id constraint)
        student_row["cached_average_score"] = avg_score
        student_row["cached_average_updated_at"] = now_iso
        student_row["cached_average_window_days"] = ANALYTICS_WINDOW_DAYS
        if latest_ts:
            student_row["latest_history_timestamp"] = _format_timestamp(latest_ts)
        student_row["updated_at"] = now_iso
        return student_row

    def _compute_average(self, student_id: str, window_days: int) -> Tuple[Optional[float], Optional[datetime]]:
        """在指定时间窗口内计算学生的平均得分。

        参数:
            student_id: 学生编号。
            window_days: 统计时间窗口的天数。

        返回:
            (平均分, 最新作业时间) 的二元组，若无数据则对应元素为 None。
        """
        conn = self._homework_conn()
        try:
            cutoff = _format_timestamp(_utc_now() - timedelta(days=window_days))
            rows = conn.execute(
                """
                SELECT score, created_at
                FROM homework_results
                WHERE student_id = ? AND created_at >= ?
                ORDER BY created_at DESC
                """,
                (student_id, cutoff),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return None, None

        scores = [row["score"] for row in rows if row["score"] is not None]
        if not scores:
            return None, _parse_timestamp(rows[0]["created_at"])

        avg_score = round(sum(scores) / len(scores), 4)
        latest_ts = _parse_timestamp(rows[0]["created_at"])
        return avg_score, latest_ts

    # ------------------------------------------------------------------
    # 作业记录
    # ------------------------------------------------------------------
    def record_homework_results(
        self,
        student_id: str,
        student_name: str,
        export_id: int,
        paper_title: str,
        items: List[HomeworkItem],
        user_id: int,
        raw_payload: Optional[Dict] = None,
    ) -> str:
        """保存一批作业批改结果并返回会话 ID。

        参数:
            student_id: 学生编号。
            student_name: 学生姓名。
            export_id: 关联的导出记录 ID。
            paper_title: 试卷标题。
            items: 作业批改结果列表。
            user_id: 当前用户 ID。
            raw_payload: 原始请求载荷，可选。

        返回:
            新生成的作业记录会话 ID。
        """
        if not self.get_student(student_id, user_id):
            self.add_student(student_id, student_name, user_id)

        session_uid = uuid.uuid4().hex
        now_iso = _format_timestamp(_utc_now())

        conn = self._homework_conn()
        try:
            for item in items:
                conn.execute(
                    """
                    INSERT INTO homework_results (
                        session_uid, student_id, student_name, export_id, paper_title,
                        question_id, question_number, original_question, reference_answer,
                        student_answer, score, feedback, raw_payload, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_uid,
                        student_id,
                        student_name,
                        export_id,
                        paper_title,
                        item.question_id,
                        item.question_number,
                        item.original_question,
                        item.reference_answer,
                        item.student_answer,
                        item.score,
                        item.feedback,
                        json.dumps(raw_payload, ensure_ascii=False) if raw_payload else None,
                        now_iso,
                        now_iso,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

        latest_ts = self._get_latest_history_timestamp(student_id)
        conn = self._student_conn()
        try:
            conn.execute(
                """
                UPDATE students
                SET latest_history_timestamp = ?,
                    cached_average_updated_at = NULL,
                    cached_average_score = NULL,
                    cached_report_history_timestamp = NULL,
                    cached_report_generated_at = NULL,
                    cached_report_json = NULL,
                    name = ?,
                    updated_at = ?
                WHERE student_id = ?
                """,
                (
                    _format_timestamp(latest_ts) if latest_ts else now_iso,
                    student_name,
                    now_iso,
                    student_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return session_uid

    def _get_latest_history_timestamp(self, student_id: str) -> Optional[datetime]:
        """获取学生最近一次作业记录的时间戳。

        参数:
            student_id: 学生编号。

        返回:
            最近一次记录的 datetime 对象，若不存在则为 None。
        """
        conn = self._homework_conn()
        try:
            row = conn.execute(
                """
                SELECT created_at
                FROM homework_results
                WHERE student_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (student_id,),
            ).fetchone()
            if row:
                return _parse_timestamp(row["created_at"])
            return None
        finally:
            conn.close()

    def get_homework_history(
        self,
        student_id: str,
        window_days: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """获取学生的历史作业记录，可按时间窗口与数量限制过滤。

        参数:
            student_id: 学生编号。
            window_days: 时间窗口天数，None 表示不限制。
            limit: 返回条目数量上限，None 表示不限制。

        返回:
            作业记录字典列表。
        """
        conn = self._homework_conn()
        try:
            params: List = [student_id]
            conditions = ["student_id = ?"]
            if window_days:
                cutoff = _format_timestamp(_utc_now() - timedelta(days=window_days))
                conditions.append("created_at >= ?")
                params.append(cutoff)

            where_clause = " AND ".join(conditions)
            order_clause = "ORDER BY created_at DESC"
            limit_clause = f"LIMIT {int(limit)}" if limit else ""

            query = f"SELECT * FROM homework_results WHERE {where_clause} {order_clause} {limit_clause}"
            rows = conn.execute(query, tuple(params)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 报告缓存
    # ------------------------------------------------------------------
    def get_cached_report(self, student_id: str) -> Optional[Dict]:
        """获取学生的缓存学习报告。

        参数:
            student_id: 学生编号。

        返回:
            报告数据字典，若无缓存则为 None。
        """
        conn = self._student_conn()
        try:
            row = conn.execute(
                "SELECT cached_report_json, cached_report_history_timestamp FROM students WHERE student_id = ?",
                (student_id,),
            ).fetchone()
            if not row or not row["cached_report_json"]:
                return None

            report = json.loads(row["cached_report_json"])
            report["history_timestamp"] = row["cached_report_history_timestamp"]
            return report
        finally:
            conn.close()

    def needs_report_refresh(self, student_id: str, cached_report: Optional[Dict] = None) -> bool:
        """判断学生的学习报告是否需要重新生成。

        参数:
            student_id: 学生编号。
            cached_report: 已获取的缓存报告，可选。

        返回:
            若需要刷新返回 True，否则返回 False。
        """
        cached = cached_report if cached_report is not None else self.get_cached_report(student_id)
        if not cached:
            return True

        cached_history_ts = _parse_timestamp(cached.get("history_timestamp"))
        latest_history = self._get_latest_history_timestamp(student_id)
        if latest_history and (not cached_history_ts or latest_history > cached_history_ts):
            return True
        return False

    def cache_report(self, student_id: str, report: Dict, history_timestamp: Optional[datetime]) -> None:
        """将生成的学习报告写入学生缓存。

        参数:
            student_id: 学生编号。
            report: 报告数据字典。
            history_timestamp: 报告对应的历史时间戳，可为 None。

        返回:
            None。
        """
        conn = self._student_conn()
        try:
            now_iso = _format_timestamp(_utc_now())
            conn.execute(
                """
                UPDATE students
                SET cached_report_json = ?,
                    cached_report_generated_at = ?,
                    cached_report_history_timestamp = ?,
                    updated_at = ?
                WHERE student_id = ?
                """,
                (
                    json.dumps(report, ensure_ascii=False),
                    now_iso,
                    _format_timestamp(history_timestamp) if history_timestamp else None,
                    now_iso,
                    student_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # AI 相关能力
    # ------------------------------------------------------------------
    def build_homework_prompt(
        self,
        paper_title: str,
        questions: List[Dict],
        ocr_text: str,
    ) -> str:
        """生成用于作业批改的提示词。

        参数:
            paper_title: 试卷标题。
            questions: 试卷题目列表。
            ocr_text: 学生作业的 OCR 文本。

        返回:
            构造好的提示词字符串。
        """
        question_block = json.dumps(
            [
                {
                    "question_id": q.get("id"),
                    "question_number": idx + 1,
                    "question": q.get("latex_content", ""),
                    "reference_answer": q.get("reference_answer", ""),
                }
                for idx, q in enumerate(questions)
            ],
            ensure_ascii=False,
        )

        prompt = f"""
你是一名严格的数学阅卷教师。请根据以下原始试卷题目，与学生手写作业的OCR识别文本进行匹配和批改。

试卷标题：{paper_title}
原始试卷题目与编号（JSON数组）：
{question_block}

学生作业OCR文本：
{ocr_text}

评分要求：
1. 请匹配学生答案与原题号，忽略OCR文本中与本试卷无关的内容。
2. 对于未匹配到的题目，请将学生解答设为""空字符串，并将得分设为0。
3. 得分区间为0到1，可保留两位小数；0表示完全错误，1表示完全正确，可给出介于0到1之间的分值。
4. feedback字段用于指出学生不理解的知识点或建议，若完全正确可为空字符串。
5. 返回格式必须是JSON，结构如下：
{{
    "results": [
        {{
            "question_id": 原题数据库ID,
            "question_number": 原始题号（数字），
            "student_answer": "学生的作答文本",
            "score": 浮点数0~1,
            "feedback": "针对该题的点评，可为空"
        }}
    ]
}}

请仅返回JSON，不要添加额外解释。
"""
        return prompt

    def parse_homework_ocr(
        self,
        paper_title: str,
        questions: List[Dict],
        ocr_text: str,
    ) -> List[Dict]:
        """调用大模型批改作业并返回结构化结果。

        参数:
            paper_title: 试卷标题。
            questions: 试卷题目列表。
            ocr_text: OCR 识别出的学生作业文本。

        返回:
            批改结果字典列表。
        """
        prompt = self.build_homework_prompt(paper_title, questions, ocr_text)
        self.logger.log_llm_prompt(prompt, "作业批改")

        response = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        self.logger.log_llm_response(content, "作业批改")

        try:
            outer_json = _extract_outermost_json_block(content)
            payload = repair_json(outer_json)
            data = json.loads(payload)
            if not isinstance(data, dict) or "results" not in data:
                raise ValueError("LLM返回格式不正确")
            return data["results"]
        except Exception as exc:
            self.logger.log_error(exc, "解析作业批改结果失败")
            raise ValueError("作业批改失败，请稍后重试") from exc

    def build_report_prompt(self, student_name: str, history: List[Dict]) -> str:
        """生成学习报告的提示词文本。

        参数:
            student_name: 学生姓名。
            history: 学生历史错题记录列表。

        返回:
            拼接后的提示词字符串。
        """
        history_payload = json.dumps(
            [
                {
                    "question_number": item.get("question_number"),
                    "score": item.get("score"),
                    "feedback": item.get("feedback"),
                    "question_id": item.get("question_id"),
                    "original_question": item.get("original_question"),
                }
                for item in history
            ],
            ensure_ascii=False,
        )

        prompt = f"""
你是一位资深的数学教研员。请基于以下学生在最近{ANALYTICS_WINDOW_DAYS}天内的错题记录，为学生生成学习报告。

学生姓名：{student_name}
错题记录（JSON数组，按照得分从低到高排序，长度<= {REPORT_MAX_ITEMS}）：
{history_payload}

请输出JSON，格式如下：
{{
    "mistake_distribution": "概述错题主要分布，字数80-120字",
    "knowledge_points": ["需要重点补强的知识点（短语）"],
    "study_plan": [
        {{
            "step": 1,
            "topic": "学习主题",
            "action": "具体练习或复习建议"
        }}
    ]
}}
请确保knowledge_points为字符串数组，study_plan为按顺序排列的对象数组。
只返回JSON。
"""
        return prompt

    def generate_learning_report(self, student_name: str, history: List[Dict]) -> Dict:
        """调用大模型生成学习报告并解析结果。

        参数:
            student_name: 学生姓名。
            history: 错题记录列表。

        返回:
            结构化的学习报告字典。
        """
        if not history:
            raise ValueError("缺少做题历史，无法生成报告")

        prompt = self.build_report_prompt(student_name, history)
        self.logger.log_llm_prompt(prompt, "学习报告生成")

        response = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        self.logger.log_llm_response(content, "学习报告生成")

        try:
            outer_json = _extract_outermost_json_block(content)
            payload = repair_json(outer_json)
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("报告结构无效")
            if "knowledge_points" in data and not isinstance(data["knowledge_points"], list):
                raise ValueError("knowledge_points 必须是数组")
            return data
        except Exception as exc:
            self.logger.log_error(exc, "解析学习报告失败")
            raise ValueError("学习报告生成失败，请稍后重试") from exc

    def _collect_report_history(
        self, student_id: str
    ) -> Tuple[List[Dict], List[Dict], Optional[datetime]]:
        """收集报告及推荐所需的历史数据。

        参数:
            student_id: 学生编号。

        返回:
            (全部历史列表, 截断后的列表, 最新时间戳) 的三元组。
        """
        history_records = self.get_homework_history(
            student_id,
            window_days=ANALYTICS_WINDOW_DAYS,
            limit=None,
        )

        if not history_records:
            return [], [], None

        def score_key(item: Dict) -> Tuple[int, float]:
            """为排序提供稳定的得分键值。

            参数:
                item: 单条作业记录字典。

            返回:
                由优先级和得分组成的排序键元组。
            """
            score = item.get("score")
            try:
                return (0, float(score))
            except (TypeError, ValueError):
                return (0, 0.0)

        sorted_history = sorted(history_records, key=score_key)
        trimmed_history = sorted_history[:REPORT_MAX_ITEMS]

        latest_ts = None
        for record in history_records:
            ts = _parse_timestamp(record.get("created_at"))
            if ts and (latest_ts is None or ts > latest_ts):
                latest_ts = ts

        return history_records, trimmed_history, latest_ts

    def _resolve_recommendation_reasons(self, student: Dict) -> List[str]:
        """基于学生数据确定推荐所需的知识点列表。

        参数:
            student: 学生信息字典。

        返回:
            经过筛选的知识点列表。
        """
        student_id = student.get("student_id")
        if not student_id:
            return []

        cached_report = self.get_cached_report(student_id)
        refresh_needed = self.needs_report_refresh(student_id, cached_report)

        report: Optional[Dict] = cached_report
        if refresh_needed:
            _, history_for_report, latest_ts = self._collect_report_history(student_id)
            if not history_for_report:
                return []
            report = self.generate_learning_report(student.get("name") or student_id, history_for_report)
            self.cache_report(student_id, report, latest_ts)

        if not report:
            return []

        knowledge_points = report.get("knowledge_points") or []
        normalized_points = [kp.strip() for kp in knowledge_points if isinstance(kp, str) and kp.strip()]
        return normalized_points[:5]

    def build_recommendations(
        self,
        student_id: str,
        current_user_id: Optional[int] = None,
    ) -> List[Dict]:
        """汇总学生薄弱知识点并生成题目推荐。

        参数:
            student_id: 学生编号。
            current_user_id: 当前用户 ID，必须提供。

        返回:
            推荐题目的列表，每项包含题目信息与推荐理由。
        """

        if current_user_id is None:
            raise ValueError("生成推荐需要提供用户ID")

        student = self.get_student(student_id, current_user_id)
        if not student:
            raise ValueError("学生不存在或无权访问")

        reasons = self._resolve_recommendation_reasons(student)
        if not reasons:
            return []

        aggregated: Dict[int, Dict] = {}
        for reason in reasons:
            try:
                results = self.question_manager.search_questions(
                    reason,
                    current_user_id=current_user_id,
                )
            except TypeError:
                results = self.question_manager.search_questions(reason, current_user_id=current_user_id)

            for question in results:
                qid = question.get("id")
                if qid is None:
                    continue

                score_value = question.get("ranking_score")
                try:
                    numeric_score = float(score_value)
                except (TypeError, ValueError):
                    numeric_score = 0.0

                existing = aggregated.get(qid)
                if not existing:
                    question_payload = dict(question)
                    question_payload["ranking_score"] = numeric_score
                    question_payload["recommended_reasons"] = {reason}
                    aggregated[qid] = question_payload
                else:
                    existing["ranking_score"] = max(existing.get("ranking_score", 0.0), numeric_score)
                    reasons_set = existing.get("recommended_reasons")
                    if isinstance(reasons_set, set):
                        reasons_set.add(reason)
                    else:
                        existing["recommended_reasons"] = {reason}

        compiled: List[Dict] = []
        for payload in aggregated.values():
            reasons_set = payload.get("recommended_reasons", set())
            if isinstance(reasons_set, set):
                payload["recommended_reasons"] = sorted(reasons_set)
            compiled.append(payload)

        compiled.sort(key=lambda item: item.get("ranking_score", 0.0), reverse=True)
        return compiled[:AI_RECOMMENDATION_LIMIT]

