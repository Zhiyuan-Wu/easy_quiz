"""学生与学情管理模块"""

from __future__ import annotations

import os
import json
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
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _utc_now() -> datetime:
    return datetime.utcnow()


def _parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _format_timestamp(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.isoformat(timespec="seconds")


@dataclass
class HomeworkItem:
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
        conn = sqlite3.connect(STUDENT_DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _homework_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(HOMEWORK_DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_student_db(self) -> None:
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
        conn = self._student_conn()
        try:
            row = conn.execute(
                "SELECT * FROM students WHERE student_id = ? AND user_id = ?",
                (student_id, user_id),
            ).fetchone()
            if not row:
                return None
            student = dict(row)
            self._ensure_average_cache(student)
            refreshed = conn.execute(
                "SELECT * FROM students WHERE student_id = ? AND user_id = ?",
                (student_id, user_id),
            ).fetchone()
            return dict(refreshed) if refreshed else student
        finally:
            conn.close()

    def list_students(self, user_id: int) -> List[Dict]:
        conn = self._student_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM students WHERE user_id = ? ORDER BY updated_at DESC, student_id ASC",
                (user_id,),
            ).fetchall()
        finally:
            conn.close()

        students: List[Dict] = [dict(row) for row in rows]
        # 补充平均分缓存
        for student in students:
            self._ensure_average_cache(student)

        # 重新读取以反映可能更新的缓存值
        if students:
            refreshed_ids = [(stu["student_id"], user_id) for stu in students]
            refreshed = self._fetch_students_by_ids(refreshed_ids)
            return refreshed
        return students

    def _fetch_students_by_ids(self, student_id_user_pairs: List[Tuple[str, int]]) -> List[Dict]:
        if not student_id_user_pairs:
            return []
        placeholders = ",".join(["(?, ?)"] * len(student_id_user_pairs))
        params = []
        for student_id, user_id in student_id_user_pairs:
            params.extend([student_id, user_id])
        conn = self._student_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM students WHERE (student_id, user_id) IN ({placeholders})",
                tuple(params),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 平均分缓存
    # ------------------------------------------------------------------
    def _ensure_average_cache(self, student_row: Dict) -> None:
        student_id = student_row.get("student_id")
        if not student_id:
            return

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
            return

        avg_score, latest_ts = self._compute_average(student_id, ANALYTICS_WINDOW_DAYS)
        conn = self._student_conn()
        try:
            conn.execute(
                """
                UPDATE students
                SET cached_average_score = ?,
                    cached_average_updated_at = ?,
                    cached_average_window_days = ?,
                    latest_history_timestamp = COALESCE(?, latest_history_timestamp),
                    updated_at = ?
                WHERE student_id = ?
                """,
                (
                    avg_score,
                    _format_timestamp(_utc_now()),
                    ANALYTICS_WINDOW_DAYS,
                    _format_timestamp(latest_ts) if latest_ts else None,
                    _format_timestamp(_utc_now()),
                    student_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _compute_average(self, student_id: str, window_days: int) -> Tuple[Optional[float], Optional[datetime]]:
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

    def needs_report_refresh(self, student_id: str) -> bool:
        cached = self.get_cached_report(student_id)
        if not cached:
            return True

        cached_history_ts = _parse_timestamp(cached.get("history_timestamp"))
        latest_history = self._get_latest_history_timestamp(student_id)
        if latest_history and (not cached_history_ts or latest_history > cached_history_ts):
            return True
        return False

    def cache_report(self, student_id: str, report: Dict, history_timestamp: Optional[datetime]) -> None:
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
        prompt = self.build_homework_prompt(paper_title, questions, ocr_text)
        self.logger.log_llm_prompt(prompt, "作业批改")

        response = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.2,
        )
        content = response.choices[0].message.content
        self.logger.log_llm_response(content, "作业批改")

        try:
            payload = repair_json(content)
            data = json.loads(payload)
            if not isinstance(data, dict) or "results" not in data:
                raise ValueError("LLM返回格式不正确")
            return data["results"]
        except Exception as exc:
            self.logger.log_error(exc, "解析作业批改结果失败")
            raise ValueError("作业批改失败，请稍后重试") from exc

    def build_report_prompt(self, student_name: str, history: List[Dict]) -> str:
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
        if not history:
            raise ValueError("缺少做题历史，无法生成报告")

        prompt = self.build_report_prompt(student_name, history)
        self.logger.log_llm_prompt(prompt, "学习报告生成")

        response = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.3,
        )
        content = response.choices[0].message.content
        self.logger.log_llm_response(content, "学习报告生成")

        try:
            payload = repair_json(content)
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError("报告结构无效")
            if "knowledge_points" in data and not isinstance(data["knowledge_points"], list):
                raise ValueError("knowledge_points 必须是数组")
            return data
        except Exception as exc:
            self.logger.log_error(exc, "解析学习报告失败")
            raise ValueError("学习报告生成失败，请稍后重试") from exc

    def build_recommendations(
        self,
        student_id: str,
        knowledge_points: List[str],
        current_user_id: Optional[int] = None,
    ) -> Dict[str, List[Dict]]:
        unique_questions: Dict[int, Dict] = {}
        reasons = [kp for kp in knowledge_points if isinstance(kp, str) and kp.strip()]
        reasons = reasons[:5]

        if not reasons:
            return {"reasons": [], "questions": []}

        for reason in reasons:
            try:
                results = self.question_manager.search_questions(
                    reason,
                    current_user_id=current_user_id,
                    k=AI_RECOMMENDATION_LIMIT,
                )
            except TypeError:
                # 旧版本函数签名不包含k，退化处理
                results = self.question_manager.search_questions(reason, current_user_id=current_user_id)

            for question in results:
                qid = question.get("id")
                if qid is None or qid in unique_questions:
                    continue
                unique_questions[qid] = {
                    "id": qid,
                    "latex_content": question.get("latex_content"),
                    "question_type": question.get("question_type"),
                    "tags": question.get("tags", []),
                    "source": question.get("source"),
                    "created_at": question.get("created_at"),
                }
                if len(unique_questions) >= AI_RECOMMENDATION_LIMIT:
                    break
            if len(unique_questions) >= AI_RECOMMENDATION_LIMIT:
                break

        return {
            "reasons": reasons,
            "questions": list(unique_questions.values()),
        }

