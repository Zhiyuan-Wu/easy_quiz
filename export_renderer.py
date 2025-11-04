# -*- coding: utf-8 -*-
"""
导出渲染器 - 专业试卷导出功能
"""

import os
import uuid
import shutil
import base64
import requests
from datetime import datetime
from typing import List, Dict, Optional
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.shared import OxmlElement, qn
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
import re
from config import LATEX_COMPILE_CONFIG, LATEX_TEMPLATE_PATH, LATEX_CLASS_PATH, LATEX_OUTPUT_DIR

TYPE_SEQUENCE = ["选择题", "填空题", "解答题"]
DEFAULT_QUESTION_TYPE = "解答题"
TYPE_SETTINGS = {
    "选择题": {
        "display": "选择题",
        "score": 5,
        "summary": "{display}，每题{score}分，共{total}分。每个题目的多个选项中只有一个是正确的。"
    },
    "填空题": {
        "display": "填空题",
        "score": 5,
        "summary": "{display}，每题{score}分，共{total}分。请将答案填写在指定位置，不要写出推导过程。"
    },
    "解答题": {
        "display": "解答题",
        "score": 10,
        "summary": "{display}，每题{score}分，共{total}分。请写出完整的解题思路和必要的理由。"
    }
}
try:
    from latex2mathml.converter import convert as latex_to_mathml
    LATEX2MATHML_AVAILABLE = True
except ImportError:
    LATEX2MATHML_AVAILABLE = False

class ExportRenderer:
    """导出渲染器类"""
    
    def __init__(self, upload_folder: str = "uploads"):
        """
        初始化导出渲染器
        
        Args:
            upload_folder: 上传文件夹路径
        """
        self.upload_folder = upload_folder
    
    def render_latex(self, questions: List[Dict], mode: str, title: str, return_metadata: bool = False):
        """
        生成LaTeX格式试卷
        
        Args:
            questions: 题目列表
            mode: 导出模式 (questions/with-answers)
            title: 试卷标题
            return_metadata: 是否返回元数据（输出目录、依赖文件等）
            
        Returns:
            LaTeX内容字符串，或者如果return_metadata=True，返回(latex_content, metadata)元组
            metadata包含: {
                'output_dir': 输出目录路径,
                'cls_file': cls文件路径,
                'tex_file': tex文件路径,
                'image_files': 图片文件列表（文件名到完整路径的映射）
            }
        """
        if not os.path.exists(LATEX_TEMPLATE_PATH):
            raise FileNotFoundError(f"未找到LaTeX模板文件: {LATEX_TEMPLATE_PATH}")

        if not os.path.exists(LATEX_CLASS_PATH):
            raise FileNotFoundError(f"未找到exam-zh.cls文件: {LATEX_CLASS_PATH}")

        os.makedirs(LATEX_OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir_name = f"paper_{timestamp}_{uuid.uuid4().hex[:6]}"
        output_dir = os.path.join(LATEX_OUTPUT_DIR, output_dir_name)
        os.makedirs(output_dir, exist_ok=True)

        class_target = os.path.join(output_dir, os.path.basename(LATEX_CLASS_PATH))
        shutil.copy2(LATEX_CLASS_PATH, class_target)

        with open(LATEX_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            template = f.read()

        copied_images: Dict[str, str] = {}
        grouped_questions = self._group_questions_by_type(questions)
        question_sections: List[str] = []
        subject = "数学试卷"
        current_index = 1

        for question_type, type_questions in grouped_questions:
            if not type_questions:
                continue

            section_title = self._format_section_title(question_type, len(type_questions))
            blocks: List[str] = []

            for question in type_questions:
                block = self._build_question_block(
                    question=question,
                    index=current_index,
                    mode=mode,
                    output_dir=output_dir,
                    copied_images=copied_images
                )
                if block:
                    blocks.append(block)
                    current_index += 1

            if blocks:
                section_content = "\n\n".join(blocks)
                question_sections.append(f"\\section{{{section_title}}}\n\n{section_content}")

        if not question_sections:
            question_sections.append("\\section{题目}\\textit{（暂无题目）}")

        question_sections_str = "\n\n".join(question_sections)

        latex_content = (template
                         .replace('{{TITLE}}', title or '数学试卷')
                         .replace('{{SUBJECT}}', subject)
                         .replace('{{QUESTION_SECTIONS}}', question_sections_str))

        safe_title = re.sub(r'[^0-9A-Za-z\u4e00-\u9fa5_-]+', '_', title or 'exam')
        output_tex_path = os.path.join(output_dir, f"{safe_title}.tex")
        with open(output_tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)

        if return_metadata:
            # 构建图片文件映射（文件名 -> 完整路径）
            image_files = {}
            for orig_path, filename in copied_images.items():
                image_full_path = os.path.join(output_dir, filename)
                if os.path.exists(image_full_path):
                    image_files[filename] = image_full_path
            
            metadata = {
                'output_dir': output_dir,
                'cls_file': class_target,
                'tex_file': output_tex_path,
                'image_files': image_files
            }
            return latex_content, metadata
        
        return latex_content
    
    def render_docx(self, questions: List[Dict], mode: str, title: str) -> str:
        """
        生成Word格式试卷

        Args:
            questions: 题目列表
            mode: 导出模式 (questions/with-answers)
            title: 试卷标题

        Returns:
            文件路径
        """
        doc = Document()

        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.9)
            section.right_margin = Inches(0.9)

        title_text = title or '数学试卷'
        title_para = doc.add_heading(title_text, level=0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        current_date = datetime.now().strftime("%Y年%m月%d日")
        date_para = doc.add_paragraph(f"日期：{current_date}")
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph()

        info_para = doc.add_paragraph()
        info_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        info_run = info_para.add_run("姓名：__________    学号：__________    班级：__________")
        info_run.font.size = Pt(11)
        info_para.paragraph_format.space_after = Pt(12)

        notice_heading = doc.add_paragraph("注意事项")
        notice_heading.style = 'Heading 2'
        notice_items = [
            "答卷前，考生务必将自己的姓名、考生号、考场号和座位号填写答题卡上，用2B铅笔将试卷类型（B）填涂在答题卡相应位置上，将条形码横贴在答题卡右上角“条形码粘贴处”。",
            "作答选择题时，选出每小题答案后，用2B铅笔在答题卡上对应题目选项的答案信息点涂黑；如需改动，用橡皮擦干净后，再选涂其他答案。答案不能答在试卷上。写在试卷、草稿纸和答题卡上的非答题区域均无效。",
            "非选择题必须用黑色字迹的钢笔或签字笔作答，答案必须写在答题卡各题目指定区域内相应位置上；如需改动，先划掉原来的答案，然后再写上新答案；不准使用铅笔和涂改液。不按以上要求作答无效。",
            "考生必须保持答题卡的整洁。考试结束后，将试卷和答题卡一并交回。"
        ]
        for item in notice_items:
            notice_para = doc.add_paragraph(item, style='List Number')
            notice_para.paragraph_format.space_after = Pt(4)

        doc.add_paragraph()

        grouped_questions = self._group_questions_by_type(questions)
        current_index = 1

        for question_type, type_questions in grouped_questions:
            if not type_questions:
                continue

            summary_text = self._format_section_title(question_type, len(type_questions))
            section_heading = doc.add_heading(summary_text, level=1)
            section_heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
            section_heading.paragraph_format.space_before = Pt(12)
            section_heading.paragraph_format.space_after = Pt(6)

            for question in type_questions:
                question_heading = doc.add_paragraph(f"第 {current_index} 题")
                question_heading.style = 'Heading 3'
                question_heading.paragraph_format.space_after = Pt(2)

                latex_content = question.get('latex_content', '') or ''
                readable_content = self._latex_to_readable(latex_content)
                normalized_content = (readable_content or '').replace('• ', '\n• ')
                content_lines = [line.strip() for line in normalized_content.split('\n') if line.strip()]
                if not content_lines:
                    content_lines = ['（本题内容暂缺）']

                resolved_images = []
                for img_path in question.get('image') or []:
                    resolved = self._resolve_docx_image_path(img_path)
                    if resolved:
                        resolved_images.append(resolved)

                if resolved_images:
                    table = doc.add_table(rows=1, cols=2)
                    table.alignment = WD_TABLE_ALIGNMENT.CENTER
                    table.autofit = False
                    table.columns[0].width = Inches(5.0)
                    table.columns[1].width = Inches(2.5)
                    self._remove_table_borders(table)

                    left_cell = table.cell(0, 0)
                    right_cell = table.cell(0, 1)
                    left_cell.text = ''
                    right_cell.text = ''
                    left_cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                    right_cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP

                    self._append_text_lines(left_cell, content_lines)
                    self._add_images_to_cell(right_cell, resolved_images)
                else:
                    self._append_text_lines(doc, content_lines)

                reference_answer = question.get('reference_answer', '') or ''
                if mode == 'with-answers' and reference_answer.strip():
                    answer_heading = doc.add_paragraph("参考解答")
                    if answer_heading.runs:
                        answer_heading.runs[0].bold = True
                    answer_heading.paragraph_format.space_before = Pt(6)
                    answer_heading.paragraph_format.space_after = Pt(3)

                    answer_table = doc.add_table(rows=1, cols=1)
                    answer_table.style = 'Table Grid'
                    answer_table.alignment = WD_TABLE_ALIGNMENT.CENTER
                    answer_cell = answer_table.cell(0, 0)
                    answer_cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                    answer_cell.text = ''

                    readable_answer = self._latex_to_readable(reference_answer)
                    normalized_answer = (readable_answer or '').replace('• ', '\n• ')
                    answer_lines = [line.strip() for line in normalized_answer.split('\n') if line.strip()]
                    if not answer_lines:
                        answer_lines = ['（本题内容暂缺）']
                    self._append_text_lines(answer_cell, answer_lines)

                doc.add_paragraph()
                current_index += 1

        filename = f'paper_{uuid.uuid4().hex[:8]}.docx'
        file_path = os.path.join(self.upload_folder, filename)
        doc.save(file_path)

        return file_path

    def render_pdf(self, questions: List[Dict], mode: str, title: str) -> str:
        """
        生成PDF格式试卷（通过LaTeX编译API）
        
        Args:
            questions: 题目列表
            mode: 导出模式 (questions/with-answers)
            title: 试卷标题
            
        Returns:
            文件路径
        """
        # 首先生成LaTeX内容和元数据
        latex_content, metadata = self.render_latex(questions, mode, title, return_metadata=True)
        
        # 调用LaTeX编译API
        api_url = LATEX_COMPILE_CONFIG["api_url"]
        compile_recipe = LATEX_COMPILE_CONFIG.get("compile_recipe")
        
        # 读取图像文件内容并转换为base64编码
        image_data = {}
        for filename, image_path in metadata['image_files'].items():
            if os.path.exists(image_path):
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    image_data[filename] = image_base64
        
        # 构建依赖文件信息（只传递图像数据，不传递路径）
        dependencies = {
            'image_files': image_data  # 文件名 -> base64编码的数据
        }
        
        payload = {
            "latex_content": latex_content,
            "dependencies": dependencies
        }
        if compile_recipe:
            payload["compile_recipe"] = compile_recipe
        
        response = requests.post(api_url, json=payload, timeout=120)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success") and result.get("pdf_base64"):
                # 解码PDF并保存
                pdf_filename = f'paper_{uuid.uuid4().hex[:8]}.pdf'
                pdf_path = os.path.join(self.upload_folder, pdf_filename)
                
                pdf_data = base64.b64decode(result["pdf_base64"])
                with open(pdf_path, 'wb') as f:
                    f.write(pdf_data)
                
                return pdf_path
            else:
                raise Exception(result.get("error", "Unknown error"))
        else:
            raise Exception(f"API request failed: {response.status_code}")

    def _build_question_block(self, question: Dict, index: int, mode: str, output_dir: str,
                              copied_images: Dict[str, str]) -> str:
        latex_body = question.get('latex_content', '') or ''
        latex_body = self._convert_enumerate_to_choices(latex_body)

        question_body = latex_body.strip()

        images = question.get('image') or []
        image_filenames = []
        for img_path in images:
            filename = self._copy_image_to_output(img_path, output_dir, copied_images, index)
            if filename:
                image_filenames.append(filename)

        if image_filenames:
            image_block = "\\par\n".join(
                f"\\includegraphics[width=0.32\\textwidth]{{{name}}}" for name in image_filenames
            )
            question_text = question_body or '\\textit{（本题内容暂缺）}'
            latex_body = (
                "\\textfigure[text-width=\\columnwidth,fig-pos=bottom-flushright]{%\n"
                f"{question_text}\n"
                "}{%\n"
                f"{image_block}\n"
                "}"
            )

        if not latex_body.strip():
            latex_body = question_body or '\\textit{（本题内容暂缺）}'


        parts = [
            f"% Question {index}",
            "\\begin{question}",
            latex_body.strip(),
            "\\end{question}"
        ]

        reference_answer = question.get('reference_answer', '') or ''
        if mode == 'with-answers' and reference_answer.strip():
            parts.extend([
                "\\begin{tcolorbox}[colback=white,colframe=black,boxrule=0.8pt]",
                "\\begin{solution}",
                reference_answer.strip(),
                "\\end{solution}",
                "\\end{tcolorbox}"
            ])

        return "\n".join(part for part in parts if part)

    def _normalize_question_type(self, question: Dict) -> str:
        q_type = (question.get('question_type') or '').strip()
        if q_type not in TYPE_SETTINGS:
            q_type = DEFAULT_QUESTION_TYPE
        return q_type

    def _group_questions_by_type(self, questions: List[Dict]) -> List[tuple]:
        grouped = {question_type: [] for question_type in TYPE_SEQUENCE}
        for question in questions:
            normalized = self._normalize_question_type(question)
            grouped.setdefault(normalized, [])
            grouped[normalized].append(question)
        return [(question_type, grouped.get(question_type, [])) for question_type in TYPE_SEQUENCE]

    def _format_section_title(self, question_type: str, count: int) -> str:
        settings = TYPE_SETTINGS.get(question_type, TYPE_SETTINGS[DEFAULT_QUESTION_TYPE])
        score = settings.get('score', 0)
        total = score * count if score else count
        return settings['summary'].format(
            display=settings.get('display', question_type),
            score=score,
            total=total,
            count=count
        )

    def _convert_enumerate_to_choices(self, content: str) -> str:
        if not content:
            return ''
        processed = re.sub(r'\\begin\{enumerate\}(\[[^\]]*\])?', r'\\begin{choices}\1', content)
        processed = re.sub(r'\\end\{enumerate\}', r'\\end{choices}', processed)
        processed = re.sub(r'\\begin\{Enumerate\}(\[[^\]]*\])?', r'\\begin{choices}\1', processed)
        processed = re.sub(r'\\end\{Enumerate\}', r'\\end{choices}', processed)
        return processed

    def _copy_image_to_output(self, image_path: str, output_dir: str,
                               copied_images: Dict[str, str], index: int) -> str:
        if not image_path:
            return ''

        if image_path in copied_images:
            return copied_images[image_path]

        clean_path = image_path.lstrip('/')
        if clean_path.startswith('uploads/'):
            clean_path = clean_path[len('uploads/'):]

        absolute_path = os.path.join(self.upload_folder, clean_path)
        if not os.path.exists(absolute_path):
            print(f"图片文件不存在: {absolute_path}")
            return ''

        base_name = os.path.basename(clean_path)
        name, ext = os.path.splitext(base_name)
        dest_filename = f"q{index}_{name}{ext}"
        dest_path = os.path.join(output_dir, dest_filename)
        counter = 1
        while os.path.exists(dest_path):
            dest_filename = f"q{index}_{name}_{counter}{ext}"
            dest_path = os.path.join(output_dir, dest_filename)
            counter += 1

        shutil.copy2(absolute_path, dest_path)
        copied_name = dest_filename.replace('\\', '/')
        copied_images[image_path] = copied_name
        return copied_name
    
    def _clean_latex_content(self, content: str) -> str:
        """
        清理LaTeX内容，确保格式正确
        
        Args:
            content: 原始内容
            
        Returns:
            清理后的LaTeX内容
        """
        if not content:
            return ""
        
        # 移除多余的空白行
        content = re.sub(r'\n\s*\n\s*\n', '\n\n', content)
        
        # 确保数学公式正确
        content = re.sub(r'\$([^$]+)\$', r'$\1$', content)
        
        # 处理enumerate环境
        content = re.sub(r'\\begin\{enumerate\}', r'\\begin{enumerate}', content)
        content = re.sub(r'\\end\{enumerate\}', r'\\end{enumerate}', content)
        
        # 处理itemize环境
        content = re.sub(r'\\begin\{itemize\}', r'\\begin{itemize}', content)
        content = re.sub(r'\\end\{itemize\}', r'\\end{itemize}', content)
        
        return content.strip()
    
    def _latex_to_readable(self, latex_content: str) -> str:
        """
        将LaTeX内容转换为可读文本（用于Word文档）
        
        Args:
            latex_content: LaTeX内容
            
        Returns:
            可读文本
        """
        if not latex_content:
            return ""
        
        # 移除LaTeX命令，保留基本文本
        content = latex_content
        
        # 移除数学公式标记
        content = re.sub(r'\$([^$]+)\$', r'\1', content)
        content = re.sub(r'\\\[([^\]]+)\\\]', r'\1', content)
        content = re.sub(r'\\\(([^)]+)\\\)', r'\1', content)
        
        # 移除常见的LaTeX命令
        content = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', content)
        content = re.sub(r'\\[a-zA-Z]+', '', content)
        
        # 处理列表
        content = re.sub(r'\\begin\{enumerate\}', '', content)
        content = re.sub(r'\\end\{enumerate\}', '', content)
        content = re.sub(r'\\begin\{itemize\}', '', content)
        content = re.sub(r'\\end\{itemize\}', '', content)
        content = re.sub(r'\\item\s*', '• ', content)
        
        # 清理多余空白
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\n\s*\n', '\n\n', content)
        
        return content.strip()

    def _resolve_docx_image_path(self, image_path: str) -> Optional[str]:
        if not image_path:
            return None

        clean_path = image_path.strip()
        if not clean_path:
            return None

        if clean_path.startswith('http://') or clean_path.startswith('https://'):
            return None  # 当前不支持远程图片

        if clean_path.startswith('/'):
            clean_path = clean_path.lstrip('/')

        if clean_path.startswith('uploads/'):
            candidate = os.path.join(self.upload_folder, clean_path[len('uploads/'):])
        else:
            candidate = clean_path if os.path.isabs(clean_path) else os.path.join(self.upload_folder, clean_path)

        if os.path.exists(candidate):
            return candidate
        return None

    def _append_text_lines(self, container, lines: List[str], bullet_style: str = 'List Bullet') -> None:
        is_table_cell = hasattr(container, '_tc')
        existing_paragraphs = list(getattr(container, 'paragraphs', [])) if is_table_cell else []
        first_paragraph = existing_paragraphs[0] if existing_paragraphs else None

        if not lines:
            lines = ['']

        for idx, raw_line in enumerate(lines):
            line = raw_line or ''
            is_bullet = line.startswith('•')
            text = line[1:].strip() if is_bullet else line.strip()

            if idx == 0 and first_paragraph is not None:
                paragraph = first_paragraph
                paragraph.text = ''
            else:
                paragraph = container.add_paragraph()

            if is_bullet and bullet_style:
                paragraph.style = bullet_style
            run = paragraph.add_run(text or ' ')
            paragraph.paragraph_format.space_after = Pt(6)

    def _add_images_to_cell(self, cell, image_paths: List[str]) -> None:
        existing_paragraphs = list(getattr(cell, 'paragraphs', []))
        first_paragraph = existing_paragraphs[0] if existing_paragraphs else None

        for idx, image_path in enumerate(image_paths):
            if not os.path.exists(image_path):
                continue

            if idx == 0 and first_paragraph is not None:
                paragraph = first_paragraph
                paragraph.text = ''
            else:
                paragraph = cell.add_paragraph()

            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = paragraph.add_run()
            try:
                run.add_picture(image_path, width=Inches(2.2))
            except Exception as exc:
                print(f"无法添加图片 {image_path}: {exc}")
            paragraph.paragraph_format.space_after = Pt(6)

    def _remove_table_borders(self, table) -> None:
        tbl = table._tbl
        tbl_pr = tbl.get_or_add_tblPr()
        tbl_borders = tbl_pr.find(qn('w:tblBorders'))
        if tbl_borders is not None:
            tbl_pr.remove(tbl_borders)

        tbl_borders = OxmlElement('w:tblBorders')
        for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
            edge_element = OxmlElement(f'w:{edge}')
            edge_element.set(qn('w:val'), 'nil')
            tbl_borders.append(edge_element)
        tbl_pr.append(tbl_borders)
    
    def _add_mathml_to_paragraph(self, paragraph, latex_math: str):
        """
        将LaTeX数学公式转换为MathML并添加到段落中
        
        Args:
            paragraph: Word段落对象
            latex_math: LaTeX数学公式
        """
        if not LATEX2MATHML_AVAILABLE or not latex_math:
            return
        
        try:
            # 转换LaTeX为MathML
            mathml = latex_to_mathml(latex_math)
            
            # 创建MathML元素
            math_element = OxmlElement('m:oMath')
            math_element.set(qn('xmlns:m'), 'http://schemas.openxmlformats.org/officeDocument/2006/math')
            
            # 解析MathML并添加到元素中
            mathml_xml = parse_xml(f'<math xmlns="http://www.w3.org/1998/Math/MathML">{mathml}</math>')
            math_element.append(mathml_xml)
            
            # 添加到段落
            paragraph._element.append(math_element)
            
        except Exception as e:
            print(f"MathML转换失败: {e}")
            # 如果转换失败，添加原始文本
            paragraph.add_run(latex_math)
