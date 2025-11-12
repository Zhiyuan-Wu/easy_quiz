from __future__ import annotations

from typing import Any, Dict, List, Sequence


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
