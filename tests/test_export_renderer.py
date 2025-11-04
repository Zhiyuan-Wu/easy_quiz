import base64
from pathlib import Path

import docx
import pytest

import export_renderer as renderer_module
from export_renderer import ExportRenderer


@pytest.fixture()
def renderer(tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return ExportRenderer(upload_folder=str(upload_dir))


@pytest.fixture()
def renderer_with_template(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    template_path = tmp_path / "template.tex"
    template_path.write_text("""
\\documentclass{article}
\\begin{document}
{{TITLE}}
{{QUESTION_SECTIONS}}
\\end{document}
""".strip(), encoding="utf-8")

    cls_path = tmp_path / "exam.cls"
    cls_path.write_text("% dummy class", encoding="utf-8")

    output_dir = tmp_path / "latex_output"

    monkeypatch.setattr(renderer_module, "LATEX_TEMPLATE_PATH", str(template_path))
    monkeypatch.setattr(renderer_module, "LATEX_CLASS_PATH", str(cls_path))
    monkeypatch.setattr(renderer_module, "LATEX_OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(
        renderer_module,
        "LATEX_COMPILE_CONFIG",
        {"api_url": "http://localhost:9999/compile", "compile_recipe": [["xelatex", "{tex_file}"]]}
    )

    return ExportRenderer(upload_folder=str(upload_dir)), upload_dir


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


def test_render_latex_metadata_includes_images(renderer_with_template):
    renderer, upload_dir = renderer_with_template

    image_path = upload_dir / "example.png"
    image_path.write_bytes(b"png")

    questions = [
        {
            "id": 1,
            "latex_content": r"\\begin{enumerate}\\item A\\end{enumerate}",
            "reference_answer": "答案",
            "tags": ["选择题"],
            "question_type": "选择题",
            "image": [f"/uploads/{image_path.name}"],
        }
    ]

    latex_content, metadata = renderer.render_latex(questions, mode='with-answers', title='测试', return_metadata=True)

    assert "\\begin{choices}" in latex_content
    assert Path(metadata['tex_file']).exists()
    assert metadata['image_files']


def test_render_pdf_uses_compile_service(renderer_with_template, monkeypatch):
    renderer, upload_dir = renderer_with_template

    image_path = upload_dir / "diagram.png"
    image_path.write_bytes(b"pngdata")

    payload_holder = {}

    def fake_post(url, json=None, timeout=None):
        payload_holder['url'] = url
        payload_holder['payload'] = json

        class _Response:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "success": True,
                    "pdf_base64": base64.b64encode(b"PDF").decode('ascii')
                }

        return _Response()

    monkeypatch.setattr(renderer_module.requests, "post", fake_post)

    questions = [
        {
            "id": 1,
            "latex_content": "题目",
            "reference_answer": "答案",
            "tags": [],
            "question_type": "解答题",
            "image": [f"/uploads/{image_path.name}"],
        }
    ]

    pdf_path = renderer.render_pdf(questions, mode='questions', title='测试PDF')

    assert Path(pdf_path).exists()
    assert payload_holder['url'] == "http://localhost:9999/compile"
    dependencies = payload_holder['payload']['dependencies']
    assert dependencies['image_files']
    assert payload_holder['payload']['compile_recipe'] == [["xelatex", "{tex_file}"]]
