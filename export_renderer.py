# -*- coding: utf-8 -*-
"""
导出渲染器 - 专业试卷导出功能
"""

import os
import uuid
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
        # 获取当前日期
        current_date = datetime.now().strftime("%Y年%m月%d日")
        
        content = f"""\\documentclass[12pt,a4paper]{{article}}
\\usepackage[UTF8]{{ctex}}
\\usepackage{{amsmath}}
\\usepackage{{amssymb}}
\\usepackage{{geometry}}
\\usepackage{{graphicx}}
\\usepackage{{enumerate}}
\\usepackage{{itemize}}
\\geometry{{left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm}}

\\title{{{title}}}
\\author{{}}
\\date{{{current_date}}}

\\begin{{document}}
\\maketitle

\\vspace{{1cm}}
\\hrule
\\vspace{{0.5cm}}

"""
        
        # 添加题目
        for i, question in enumerate(questions, 1):
            content += f"\\section*{{题目 {i}}}\n\n"
            
            # 处理题目内容，确保LaTeX格式正确
            latex_content = self._clean_latex_content(question.get('latex_content', ''))
            content += latex_content + "\n\n"
            
            # 处理图片
            images = question.get('image', [])
            for img_path in images:
                if img_path and os.path.exists(img_path.replace('/uploads/', self.upload_folder + '/')):
                    content += f"\\begin{{center}}\n"
                    content += f"\\includegraphics[width=0.8\\textwidth]{{{img_path}}}\n"
                    content += f"\\end{{center}}\n\n"
            
            # 如果包含答案模式，添加参考解答
            if mode == 'with-answers' and question.get('reference_answer'):
                content += "\\subsection*{参考解答}\n\n"
                answer_content = self._clean_latex_content(question['reference_answer'])
                content += answer_content + "\n\n"
            
            # 添加分隔线
            if i < len(questions):
                content += "\\vspace{0.5cm}\n\\hrule\n\\vspace{0.5cm}\n\n"
        
        content += "\\end{document}"
        return content
    
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
                if img_path and os.path.exists(img_path.replace('/uploads/', self.upload_folder + '/')):
                    try:
                        full_path = img_path.replace('/uploads/', self.upload_folder + '/')
                        doc.add_picture(full_path, width=Inches(4))
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
        生成PDF格式试卷（通过LaTeX编译）
        
        Args:
            questions: 题目列表
            mode: 导出模式 (questions/with-answers)
            title: 试卷标题
            
        Returns:
            文件路径
        """
        # 首先生成LaTeX内容
        latex_content = self.render_latex(questions, mode, title)
        
        # 保存LaTeX文件
        tex_filename = f'paper_{uuid.uuid4().hex[:8]}.tex'
        tex_path = os.path.join(self.upload_folder, tex_filename)
        
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        # 尝试编译为PDF
        try:
            import subprocess
            pdf_filename = tex_filename.replace('.tex', '.pdf')
            pdf_path = os.path.join(self.upload_folder, pdf_filename)
            
            # 使用xelatex编译（支持中文）
            result = subprocess.run([
                'xelatex', 
                '-output-directory', self.upload_folder,
                '-interaction=nonstopmode',
                tex_path
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and os.path.exists(pdf_path):
                # 清理临时文件
                try:
                    os.remove(tex_path)
                    # 清理其他LaTeX生成的文件
                    for ext in ['.aux', '.log', '.out']:
                        temp_file = tex_path.replace('.tex', ext)
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                except:
                    pass
                
                return pdf_path
            else:
                # 如果编译失败，返回LaTeX文件
                return tex_path
                
        except Exception as e:
            print(f"PDF编译失败: {e}")
            # 如果编译失败，返回LaTeX文件
            return tex_path
    
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
