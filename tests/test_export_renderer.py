from pathlib import Path

import docx
import pytest

from export_renderer import ExportRenderer


@pytest.fixture()
def renderer(tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return ExportRenderer(upload_folder=str(upload_dir))


def sample_questions():
    return [
        {
            "id": 1,
            "latex_content": "已知 $1+1=2$，求 $1+2$。",
            "reference_answer": "3",
            "tags": ["基础代数"],
            "question_type": "选择题",
            "image": [],
        },
        {
            "id": 2,
            "latex_content": "求解 $x$，使得 $x^2=9$。",
            "reference_answer": "x=\\pm 3",
            "tags": ["方程"],
            "question_type": "解答题",
            "image": [],
        },
        {
            "id": 3,
            "latex_content": "若 $a+b=5$，则 $a$ 的值为?",
            "reference_answer": "5-b",
            "tags": ["填空"],
            "question_type": "填空题",
            "image": [],
        },
    ]


def test_render_latex_sections_order(renderer, tmp_path):
    questions = sample_questions()
    latex_content = renderer.render_latex(questions, mode='questions', title='测试试卷')

    # 确认按照题型排序生成 section
    section_sequence = [
        "选择题",
        "填空题",
        "解答题",
    ]
    indices = [latex_content.find(title) for title in section_sequence]
    assert all(idx != -1 for idx in indices)
    assert indices == sorted(indices)


def test_render_docx_generates_group_headings(renderer, tmp_path):
    questions = sample_questions()
    docx_path = renderer.render_docx(questions, mode='with-answers', title='测试试卷')
    assert Path(docx_path).exists()

    document = docx.Document(docx_path)
    headings = [p.text for p in document.paragraphs if p.style.name.startswith('Heading')]

    assert any("选择题" in heading for heading in headings)
    assert any("填空题" in heading for heading in headings)
    assert any("解答题" in heading for heading in headings)
