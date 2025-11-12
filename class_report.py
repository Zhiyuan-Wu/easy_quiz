from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import requests

from config import LATEX_COMPILE_CONFIG


def latex_escape(text: str) -> str:
    """Escape special LaTeX characters in plain text."""
    if text is None:
        return ""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    escaped = str(text)
    for target, replacement in replacements.items():
        escaped = escaped.replace(target, replacement)
    return escaped


def format_percent(value: Any, decimals: int = 1) -> str:
    """Format a ratio value (0~1) as percentage text for LaTeX."""
    try:
        numeric = float(value)
        return f"{numeric * 100:.{decimals}f}\\%"
    except (TypeError, ValueError):
        return "--"


def format_percent_plain(value: Any, decimals: int = 1) -> str:
    """Format a ratio value (0~1) as percentage plain text."""
    try:
        numeric = float(value)
        return f"{numeric * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "--"


class BaseSection:
    """Base class for class report sections."""

    identifier: str = ""
    title: str = ""

    def __init__(self, context: Dict[str, Any]) -> None:
        self.context = context

    def to_payload(self) -> Dict[str, Any]:
        raise NotImplementedError

    def to_latex(self) -> str:
        raise NotImplementedError


class ClassRankingSection(BaseSection):
    identifier = "class_ranking"
    title = "全班排名"

    def to_payload(self) -> Dict[str, Any]:
        questions = self.context.get("questions", [])
        average_row = self.context.get("average_row", {})
        ranking_rows = self.context.get("ranking_rows", [])
        roster_rows = self.context.get("roster_rows", [])

        rows: List[Dict[str, Any]] = [
            {
                "row_type": "average",
                "student_id": "",
                "student_name": "全班平均",
                "scores": average_row.get("scores", {}),
                "total_score": average_row.get("total_score"),
                "total_raw": average_row.get("total_raw"),
                "rank": "-",
            }
        ]

        for row in ranking_rows:
            rows.append(
                {
                    "row_type": "student",
                    "student_id": row.get("student_id", ""),
                    "student_name": row.get("student_name", ""),
                    "scores": row.get("scores", {}),
                    "total_score": row.get("total_score"),
                    "total_raw": row.get("total_raw"),
                    "rank": row.get("rank") if row.get("rank") is not None else "-",
                }
            )

        for row in roster_rows:
            rows.append(
                {
                    "row_type": "roster_only",
                    "student_id": row.get("student_id", ""),
                    "student_name": row.get("student_name", ""),
                    "scores": row.get("scores", {}),
                    "total_score": row.get("total_score"),
                    "total_raw": row.get("total_raw"),
                    "rank": "-",
                }
            )

        return {
            "title": self.title,
            "questions": [
                {
                    "question_number": item.get("number"),
                    "question_id": item.get("id"),
                    "question_type": item.get("question_type"),
                }
                for item in questions
            ],
            "rows": rows,
        }

    def to_latex(self) -> str:
        questions: Sequence[Dict[str, Any]] = self.context.get("questions", [])
        average_row: Dict[str, Any] = self.context.get("average_row", {})
        ranking_rows: Sequence[Dict[str, Any]] = self.context.get("ranking_rows", [])
        roster_rows: Sequence[Dict[str, Any]] = self.context.get("roster_rows", [])

        headers = ["学号", "姓名"] + [f"题{q.get('number')}" for q in questions] + ["总分", "排名"]
        column_spec = "ll" + "c" * (len(headers) - 2)

        lines = [f"\\section*{{{self.title}}}", f"\\begin{{tabular}}{{{column_spec}}}", "\\hline"]
        lines.append(" & ".join(headers) + " \\\\")
        lines.append("\\hline")

        def render_row(student_id: str, student_name: str, scores: Dict[int, Any], total: Any, rank_value: Any) -> str:
            cells = [
                latex_escape(student_id or "--"),
                latex_escape(student_name or "--"),
            ]
            for question in questions:
                qnum = question.get("number")
                cells.append(format_percent(scores.get(qnum)))
            cells.append(format_percent(total))
            cells.append(latex_escape(str(rank_value) if rank_value not in (None, "-", "") else "--"))
            return " & ".join(cells) + " \\\\"

        lines.append(
            render_row(
                "",
                "全班平均",
                average_row.get("scores", {}),
                average_row.get("total_score"),
                "-",
            )
        )
        lines.append("\\hline")

        for row in ranking_rows:
            lines.append(
                render_row(
                    row.get("student_id", ""),
                    row.get("student_name", ""),
                    row.get("scores", {}),
                    row.get("total_score"),
                    row.get("rank"),
                )
            )
        for row in roster_rows:
            lines.append(
                render_row(
                    row.get("student_id", ""),
                    row.get("student_name", ""),
                    row.get("scores", {}),
                    row.get("total_score"),
                    "-",
                )
            )

        lines.append("\\hline")
        lines.append("\\end{tabular}")
        lines.append("\\medskip")
        return "\n".join(lines)


class QuestionOverviewSection(BaseSection):
    identifier = "question_overview"
    title = "题目总览"

    def to_payload(self) -> Dict[str, Any]:
        rows = self.context.get("overview_rows", [])
        return {
            "title": self.title,
            "rows": [
                {
                    "question_number": item.get("question_number"),
                    "question_id": item.get("question_id"),
                    "question_type": item.get("question_type"),
                    "tags": item.get("tags", []),
                    "average_score": item.get("average_score"),
                    "full_score_rate": item.get("full_score_rate"),
                }
                for item in rows
            ],
        }

    def to_latex(self) -> str:
        rows: Sequence[Dict[str, Any]] = self.context.get("overview_rows", [])
        lines = [
            f"\\section*{{{self.title}}}",
            "\\begin{tabular}{l l l l}",
            "\\hline",
            "题号 & 标签 & 平均得分 & 满分率 \\\\",
            "\\hline",
        ]
        for item in rows:
            tag_text = "、".join(item.get("tags") or []) or "--"
            lines.append(
                f"{latex_escape(str(item.get('question_number')))} & "
                f"{latex_escape(tag_text)} & "
                f"{format_percent(item.get('average_score'))} & "
                f"{format_percent(item.get('full_score_rate'))} \\\\"
            )
        lines.append("\\hline")
        lines.append("\\end{tabular}")
        lines.append("\\medskip")
        return "\n".join(lines)


class CommonMistakesSection(BaseSection):
    identifier = "common_mistakes"
    title = "高频错题"

    def to_payload(self) -> Dict[str, Any]:
        cards = self.context.get("common_mistakes", [])
        return {
            "title": self.title,
            "cards": [
                {
                    "question_number": item.get("question_number"),
                    "question_id": item.get("question_id"),
                    "question_type": item.get("question_type"),
                    "tags": item.get("tags", []),
                    "average_score": item.get("average_score"),
                    "full_score_rate": item.get("full_score_rate"),
                    "latex_content": item.get("latex_content", ""),
                }
                for item in cards
            ],
        }

    def to_latex(self) -> str:
        cards: Sequence[Dict[str, Any]] = self.context.get("common_mistakes", [])
        lines = [f"\\section*{{{self.title}}}"]
        if not cards:
            lines.append("本次作业暂无高频错题。")
            return "\n".join(lines)

        for item in cards:
            tags = "、".join(item.get("tags") or []) or "--"
            lines.append(f"\\subsection*{{题目 {latex_escape(str(item.get('question_number')))}}}")
            lines.append(
                f"标签：{latex_escape(tags)}；平均得分：{format_percent(item.get('average_score'))}；"
                f"满分率：{format_percent(item.get('full_score_rate'))}"
            )
            question_content = item.get("latex_content")
            if question_content:
                lines.append("\\begin{quote}")
                lines.append(question_content)
                lines.append("\\end{quote}")
            lines.append("\\medskip")
        return "\n".join(lines)


SECTION_FACTORIES = [
    ClassRankingSection,
    QuestionOverviewSection,
    CommonMistakesSection,
]


def build_section_instances(context: Dict[str, Any]) -> List[BaseSection]:
    """Instantiate report sections from context."""
    return [factory(context) for factory in SECTION_FACTORIES]


def build_sections_payload(sections: Sequence[BaseSection]) -> Dict[str, Any]:
    """Convert section instances to payload and order metadata."""
    section_order: List[str] = []
    section_mapping: Dict[str, Dict[str, Any]] = {}
    for section in sections:
        section_order.append(section.identifier)
        section_mapping[section.identifier] = section.to_payload()
    return {"order": section_order, "sections": section_mapping}


def render_sections_latex(sections: Sequence[BaseSection]) -> str:
    """Render all sections to LaTeX snippet."""
    return "\n\n".join(section.to_latex() for section in sections)


def build_class_report_latex(paper_title: str, sections_latex: str) -> str:
    """构建完整的 LaTeX 文档内容。"""
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
    """调用外部 LaTeX 服务生成 PDF，返回 base64 字符串。"""
    api_url = LATEX_COMPILE_CONFIG.get("api_url")
    if not api_url:
        raise ValueError("未配置 LaTeX 编译服务地址")

    payload: Dict[str, Any] = {"latex_content": latex_content}
    compile_recipe = LATEX_COMPILE_CONFIG.get("compile_recipe")
    if compile_recipe:
        payload["compile_recipe"] = compile_recipe

    try:
        response = requests.post(api_url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:  # noqa: BLE001
        raise ValueError(f"PDF 编译请求失败: {exc}") from exc

    if not data.get("success"):
        raise ValueError(data.get("error") or "PDF 编译失败")

    pdf_base64 = data.get("pdf_base64")
    if not pdf_base64:
        raise ValueError("PDF 编译服务未返回文件数据")
    return pdf_base64


class ClassReportGenerator:
    """封装全班报告生成与导出的服务。"""

    def __init__(self, student_manager, system_manager, question_manager) -> None:
        self.student_manager = student_manager
        self.system_manager = system_manager
        self.question_manager = question_manager

    def build_context(self, export_id: int, user_id: int) -> Dict[str, Any]:
        """构建报告上下文数据。"""
        export_data = self.system_manager.get_export_by_id(export_id)
        if not export_data or export_data.get("user_id") != user_id:
            raise ValueError("无法访问指定的试卷")

        question_ids = export_data.get("question_ids") or []
        questions: List[Dict[str, Any]] = []
        question_id_map: Dict[Any, Dict[str, Any]] = {}
        for index, qid in enumerate(question_ids, start=1):
            question = self.question_manager.get_question_by_id(qid, user_id)
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

        roster = self.student_manager.list_students(user_id)
        roster_map = {
            str(student.get("student_id")): student
            for student in roster
            if isinstance(student, dict) and student.get("student_id")
        }

        result_rows = self.student_manager.get_homework_results_by_export(export_id, user_id)
        question_scores: Dict[int, List[float]] = {item["number"]: [] for item in questions}
        student_entries: Dict[str, Dict[str, Any]] = {}

        for row in result_rows:
            sid = row.get("student_id")
            if not sid:
                continue

            qnum_raw = row.get("question_number")
            try:
                qnum = int(qnum_raw) if qnum_raw is not None else None
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
                question["number"]: entry["scores"].get(question["number"], 0.0)
                for question in questions
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
            average_scores[qnum] = (
                sum(scores_list) / len(scores_list) if scores_list else 0.0
            )

        average_total_raw = (
            sum(row["total_raw"] for row in ranking_rows) / len(ranking_rows)
            if ranking_rows
            else 0.0
        )
        average_total_score = (
            average_total_raw / total_questions if total_questions else 0.0
        )
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
            full_score_rate = (
                sum(1 for score in scores_list if score >= 0.999) / attempts
                if attempts
                else 0.0
            )
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

    def build_sections_payload(
        self,
        export_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """生成章节载荷与上下文。"""
        context = self.build_context(export_id, user_id)
        sections = build_section_instances(context)
        payload = build_sections_payload(sections)
        return {
            "context": context,
            "sections": sections,
            "payload": payload,
        }

    def generate_payload(
        self,
        export_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """获取前端渲染所需的章节顺序与内容。"""
        data = self.build_sections_payload(export_id, user_id)
        return {
            "paper_title": data["context"].get("paper_title"),
            "section_order": data["payload"]["order"],
            "sections": data["payload"]["sections"],
            "student_count": data["context"].get("student_count", 0),
            "question_count": len(data["context"].get("questions") or []),
        }

    def generate_pdf(
        self,
        export_id: int,
        user_id: int,
    ) -> Dict[str, Any]:
        """生成报告 PDF，并返回元数据。"""
        data = self.build_sections_payload(export_id, user_id)
        sections_latex = render_sections_latex(data["sections"])
        latex_document = build_class_report_latex(
            data["context"].get("paper_title") or "未命名试卷",
            sections_latex,
        )
        pdf_base64 = compile_latex_to_pdf(latex_document)
        return {
            "paper_title": data["context"].get("paper_title"),
            "pdf_base64": pdf_base64,
        }
