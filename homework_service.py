from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from utils import (
    apply_filename_replacements,
    match_student_by_filename,
    normalize_homework_results,
    save_ocr_images,
)


@dataclass
class HomeworkFileEntry:
    """描述待解析的作业文件。"""

    original_filename: str
    stored_filename: str
    stored_path: str
    forced_student_id: Optional[str] = None
    forced_student_name: Optional[str] = None


class HomeworkBatchProcessor:
    """封装作业批量解析逻辑，支持单文件复用。"""

    def __init__(
        self,
        *,
        ocr_client,
        student_manager,
        question_manager,
        system_manager,
        upload_root: str,
        logger,
    ) -> None:
        self.ocr_client = ocr_client
        self.student_manager = student_manager
        self.question_manager = question_manager
        self.system_manager = system_manager
        self.upload_root = upload_root
        self.logger = logger

        os.makedirs(self.upload_root, exist_ok=True)

    def process_batch(
        self,
        file_entries: Sequence[HomeworkFileEntry],
        export_id: int,
        user_id: int,
        *,
        force_student_id: Optional[str] = None,
        force_student_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """批量处理上传的作业文件。"""
        export_data = self.system_manager.get_export_by_id(export_id)
        if not export_data or export_data.get("user_id") != user_id:
            raise ValueError("无法访问指定的试卷")

        question_ids = export_data.get("question_ids") or []
        questions: List[Dict[str, Any]] = []
        for qid in question_ids:
            question = self.question_manager.get_question_by_id(qid, user_id)
            if question:
                questions.append(question)
        if not questions:
            raise ValueError("所选试卷暂无题目信息")

        paper_title = export_data.get("title") or "未命名试卷"
        roster = self.student_manager.list_students(user_id)
        roster_map = {
            str(student.get("student_id")): student
            for student in roster
            if isinstance(student, dict) and student.get("student_id")
        }

        mapping: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        failures: List[Dict[str, Any]] = []
        unknown_counter = 1

        questions_meta = [
            {
                "question_number": index,
                "question_id": question.get("id"),
                "question_type": question.get("question_type"),
            }
            for index, question in enumerate(questions, start=1)
        ]

        for entry in file_entries:
            forced_id = entry.forced_student_id or force_student_id
            forced_name = entry.forced_student_name or force_student_name

            try:
                parse_result = self._parse_single_file(
                    entry,
                    questions,
                    paper_title,
                    user_id,
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.log_error(exc, f"作业批量解析失败 - 文件: {entry.original_filename}")
                failures.append(
                    {
                        "filename": entry.original_filename,
                        "message": str(exc),
                    }
                )
                continue

            detected_student_id = (parse_result.get("detected_student_id") or "").strip()
            detected_student_name = (parse_result.get("detected_student_name") or "").strip()

            matched_student = match_student_by_filename(entry.original_filename, roster)
            assigned_student_id: str
            assignment_source: str

            if forced_id:
                assigned_student_id = forced_id.strip()
                assignment_source = "manual"
            elif matched_student:
                assigned_student_id = str(matched_student.get("student_id") or "").strip()
                assignment_source = "filename"
            elif detected_student_id:
                assigned_student_id = detected_student_id
                assignment_source = "llm"
            else:
                assigned_student_id = f"unknown_id{unknown_counter}"
                assignment_source = "unknown"
                unknown_counter += 1

            if not assigned_student_id:
                assigned_student_id = f"unknown_id{unknown_counter}"
                assignment_source = "unknown"
                unknown_counter += 1

            if assigned_student_id in mapping:
                failures.append(
                    {
                        "filename": entry.original_filename,
                        "message": f"学号 {assigned_student_id} 已存在，已跳过该文件",
                    }
                )
                continue

            student_name = (
                forced_name
                or roster_map.get(assigned_student_id, {}).get("name")
                or detected_student_name
                or ""
            )

            mapping[assigned_student_id] = {
                "student_id": assigned_student_id,
                "student_name": student_name,
                "detected_student_id": detected_student_id,
                "detected_student_name": detected_student_name,
                "assignment_source": assignment_source,
                "original_filename": entry.original_filename,
                "stored_filename": entry.stored_filename,
                "results": parse_result["results"],
                "total_score": parse_result["total_score"],
                "total_raw": parse_result["total_raw"],
                "ocr_text": parse_result["ocr_text"],
            }
            order.append(assigned_student_id)

        return {
            "paper_title": paper_title,
            "questions": questions_meta,
            "mapping": mapping,
            "order": order,
            "failures": failures,
        }

    def _parse_single_file(
        self,
        entry: HomeworkFileEntry,
        questions: List[Dict[str, Any]],
        paper_title: str,
        user_id: int,
    ) -> Dict[str, Any]:
        """解析单个作业文件，返回结构化结果。"""
        ocr_response = self.ocr_client.ocr_image(entry.stored_path)
        pages = ocr_response.get("pages") or []

        markdown_segments: List[str] = []
        for page in pages:
            page_markdown = page.get("markdown") or ""
            page_images = page.get("images") or []
            page_suffix = page.get("suggested_suffix", "")
            page_mapping, replacements = save_ocr_images(
                page_images,
                self.upload_root,
                self.logger,
                suffix=page_suffix,
            )
            page_markdown = apply_filename_replacements(page_markdown, replacements)
            page["markdown"] = page_markdown
            if page_markdown.strip():
                markdown_segments.append(page_markdown.strip())

        if not markdown_segments:
            fallback_markdown = (
                ocr_response.get("markdown")
                or ocr_response.get("text")
                or ""
            )
            if fallback_markdown.strip():
                markdown_segments.append(fallback_markdown.strip())

        ocr_text = "\n\n".join(markdown_segments)

        parse_payload = self.student_manager.parse_homework_ocr(
            paper_title,
            questions,
            ocr_text,
            user_id,
        )

        llm_results = parse_payload.get("results") or []
        normalized_results = normalize_homework_results(questions, llm_results)
        total_raw = sum(item.get("score", 0.0) or 0.0 for item in normalized_results)
        total_score = total_raw / len(normalized_results) if normalized_results else 0.0

        return {
            "ocr_text": ocr_text,
            "results": normalized_results,
            "total_raw": total_raw,
            "total_score": total_score,
            "detected_student_id": parse_payload.get("detected_student_id") or "",
            "detected_student_name": parse_payload.get("detected_student_name") or "",
        }
