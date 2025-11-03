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
from typing import List, Dict
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.shared import OxmlElement, qn
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
import re
from config import LATEX_COMPILE_CONFIG, LATEX_TEMPLATE_PATH, LATEX_CLASS_PATH, LATEX_OUTPUT_DIR
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
    
    def render_latex(self, questions: List[Dict], mode: str, title: str) -> str:
        """
        生成LaTeX格式试卷
        
        Args:
            questions: 题目列表
            mode: 导出模式 (questions/with-answers)
            title: 试卷标题
            
        Returns:
            LaTeX内容字符串
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
        question_blocks: List[str] = []

        for index, question in enumerate(questions, 1):
            block = self._build_question_block(
                question=question,
                index=index,
                mode=mode,
                output_dir=output_dir,
                copied_images=copied_images
            )
            if block:
                question_blocks.append(block)

        question_block_str = "\n\n".join(question_blocks)

        subject = "数学试卷"
        section_summary = f"题目：共 {len(questions)} 小题。"

        latex_content = (template
                         .replace('{{TITLE}}', title or '数学试卷')
                         .replace('{{SUBJECT}}', subject)
                         .replace('{{SECTION_SUMMARY}}', section_summary)
                         .replace('{{QUESTION_BLOCK}}', question_block_str))

        safe_title = re.sub(r'[^0-9A-Za-z\u4e00-\u9fa5_-]+', '_', title or 'exam')
        output_tex_path = os.path.join(output_dir, f"{safe_title}.tex")
        with open(output_tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)

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
        
        # 设置页面边距
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1)
            section.right_margin = Inches(1)
        
        # 标题
        title_para = doc.add_heading(title, 0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 日期
        current_date = datetime.now().strftime("%Y年%m月%d日")
        date_para = doc.add_paragraph(f"日期：{current_date}")
        date_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 添加分隔线
        doc.add_paragraph("_" * 50)
        
        # 添加题目
        for i, question in enumerate(questions, 1):
            # 题目标题
            question_heading = doc.add_heading(f'题目 {i}', level=1)
            
            # 题目内容
            latex_content = question.get('latex_content', '')
            if latex_content:
                # 将LaTeX转换为可读文本
                readable_content = self._latex_to_readable(latex_content)
                doc.add_paragraph(readable_content)
            
            # 处理图片
            images = question.get('image', [])
            for img_path in images:
                if img_path:
                    try:
                        # 处理图片路径
                        if img_path.startswith('/uploads/'):
                            full_path = img_path.replace('/uploads/', self.upload_folder + '/')
                        else:
                            full_path = img_path
                        
                        # 检查文件是否存在
                        if os.path.exists(full_path):
                            doc.add_picture(full_path, width=Inches(4))
                        else:
                            print(f"图片文件不存在: {full_path}")
                    except Exception as e:
                        print(f"无法添加图片 {img_path}: {e}")
            
            # 如果包含答案模式，添加参考解答
            if mode == 'with-answers' and question.get('reference_answer'):
                answer_heading = doc.add_heading('参考解答', level=2)
                answer_content = question['reference_answer']
                readable_answer = self._latex_to_readable(answer_content)
                doc.add_paragraph(readable_answer)
            
            # 添加分隔
            if i < len(questions):
                doc.add_paragraph()
                # 添加分隔线
                doc.add_paragraph("_" * 30)
                doc.add_paragraph()
        
        # 保存文件
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
        # 首先生成LaTeX内容
        latex_content = self.render_latex(questions, mode, title)
        
        # 调用LaTeX编译API
        try:
            api_url = LATEX_COMPILE_CONFIG["api_url"]
            compile_recipe = LATEX_COMPILE_CONFIG.get("compile_recipe")
            
            payload = {
                "latex_content": latex_content
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
                
        except Exception as e:
            print(f"PDF编译失败: {e}")
            # 如果编译失败，保存LaTeX文件作为备用
            tex_filename = f'paper_{uuid.uuid4().hex[:8]}.tex'
            tex_path = os.path.join(self.upload_folder, tex_filename)
            with open(tex_path, 'w', encoding='utf-8') as f:
                f.write(latex_content)
            return tex_path

    def _build_question_block(self, question: Dict, index: int, mode: str, output_dir: str,
                              copied_images: Dict[str, str]) -> str:
        latex_body = question.get('latex_content', '') or ''
        latex_body = self._convert_enumerate_to_choices(latex_body)

        images = question.get('image') or []
        image_snippets = []
        for img_path in images:
            filename = self._copy_image_to_output(img_path, output_dir, copied_images, index)
            if filename:
                image_snippets.append(
                    f"\\textfigure{{\\centering}}{{\\includegraphics[width=0.45\\textwidth]{{{filename}}}}}"
                )

        if image_snippets:
            latex_body = latex_body.rstrip() + "\n" + "\n".join(image_snippets)

        if not latex_body.strip():
            latex_body = '\textit{（本题内容暂缺）}'

        parts = [
            f"% Question {index}",
            "\\begin{question}",
            latex_body.strip(),
            "\\end{question}"
        ]

        reference_answer = question.get('reference_answer', '') or ''
        if mode == 'with-answers' and reference_answer.strip():
            parts.extend([
                "\\begin{solution}",
                reference_answer.strip(),
                "\\end{solution}"
            ])

        return "\n".join(part for part in parts if part)

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
