import base64
import os
import re
import uuid
from typing import Any, Dict, List, Tuple

from pdf2image import convert_from_path
from config import LATEX_POST_PROCESSING


def save_ocr_images(
    ocr_images: List[Dict[str, Any]],
    upload_root: str,
    logger: Any,
    suffix: str = "",
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Persist OCR returned images and build filename mappings.

    Args:
        ocr_images: OCR服务返回的图片列表，每个元素包含filename和data等字段。
        upload_root: 上传目录的根路径（例如“uploads”）。
        logger: 日志记录器实例，用于记录图片处理的日志。
        suffix: 可选的文件名后缀，在扩展名前追加（用于区分页码等）。

    Returns:
        Tuple[Dict[str, str], Dict[str, str]]: 第一个字典为新文件名到静态URL的映射，
        第二个字典为原始占位符到新文件名的替换映射，用于处理Markdown中的引用。
    """
    image_mapping: Dict[str, str] = {}
    replacements: Dict[str, str] = {}
    if not ocr_images:
        return image_mapping, replacements

    images_dir = os.path.join(upload_root, "ocr_images")
    os.makedirs(images_dir, exist_ok=True)

    for img_data in ocr_images:
        if not isinstance(img_data, dict):
            continue

        original_filename = (img_data.get("filename") or "").strip()
        image_data = img_data.get("data")
        if not original_filename or image_data is None:
            continue

        name, ext = os.path.splitext(original_filename)
        ext = ext if ext else ".png"
        if not ext.startswith("."):
            ext = f".{ext}"
        new_filename = f"{name}{suffix}{ext}"
        unique_filename = f"ocr_{uuid.uuid4().hex[:8]}_{new_filename}"
        dest_path = os.path.join(images_dir, unique_filename)

        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data

        with open(dest_path, "wb") as file_obj:
            file_obj.write(image_bytes)

        relative_path = f"/uploads/ocr_images/{unique_filename}"
        image_mapping[new_filename] = relative_path
        replacements[f"images/{original_filename}"] = f"images/{new_filename}"
        replacements[original_filename] = new_filename

        if logger and hasattr(logger, "log_image_processing"):
            logger.log_image_processing(original_filename, relative_path, "保存")

    return image_mapping, replacements


def apply_filename_replacements(text: str, replacements: Dict[str, str]) -> str:
    """Apply filename replacements within OCR markdown content.

    Args:
        text: 原始的Markdown字符串。
        replacements: 替换映射，key为原始占位符，value为替换后的内容。

    Returns:
        str: 替换后的Markdown字符串。
    """
    if not text or not replacements:
        return text

    for target, new_value in sorted(replacements.items(), key=lambda item: -len(item[0])):
        text = text.replace(target, new_value)
    return text


def convert_pdf_to_images(pdf_path: str, output_dir: str) -> List[Tuple[int, str]]:
    """Convert a PDF file to page-wise PNG images.

    Args:
        pdf_path: 待转换的PDF文件路径。
        output_dir: 输出图片的目标目录。

    Returns:
        List[Tuple[int, str]]: (页码, 图片文件路径)组成的列表，页码从1开始。
    """
    os.makedirs(output_dir, exist_ok=True)
    pages = convert_from_path(pdf_path)
    results: List[Tuple[int, str]] = []

    for index, image in enumerate(pages, start=1):
        filename = f"pdf_{uuid.uuid4().hex[:8]}_page{index}.png"
        dest_path = os.path.join(output_dir, filename)
        image.save(dest_path, "PNG")
        results.append((index, dest_path))

    return results


def post_process_latex_content(latex_content: str) -> str:
    """对LaTeX内容进行后处理，移除不需要的环境和命令。
    
    参数:
        latex_content: 原始LaTeX内容字符串。
        
    返回:
        处理后的LaTeX内容字符串。
    """
    if not latex_content:
        return ''
    
    if not LATEX_POST_PROCESSING.get('enabled', True):
        return latex_content
    
    processed = latex_content
    
    # 移除 \begin{center}...\end{center} 环境（包括内容）
    if LATEX_POST_PROCESSING.get('remove_center_env', True):
        processed = re.sub(r'\\begin\{center\}[\s\S]*?\\end\{center\}', '', processed)
    
    # 移除 \includegraphics[]{} 命令（支持可选参数）
    if LATEX_POST_PROCESSING.get('remove_includegraphics', True):
        processed = re.sub(r'\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}', '', processed)
    
    return processed


def normalize_homework_results(
    questions: List[Dict[str, Any]],
    llm_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """将 LLM 返回的批改结果按照题目顺序补齐并标准化。"""
    results_by_id: Dict[int, Dict[str, Any]] = {}
    results_by_number: Dict[int, Dict[str, Any]] = {}

    for item in llm_results or []:
        if not isinstance(item, dict):
            continue
        qid_val = item.get("question_id")
        qnum_val = item.get("question_number")
        try:
            if qid_val is not None:
                results_by_id[int(qid_val)] = item
        except (TypeError, ValueError):
            pass
        try:
            if qnum_val is not None:
                results_by_number[int(qnum_val)] = item
        except (TypeError, ValueError):
            pass

    normalized: List[Dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        qid = question.get("id")
        raw_item: Dict[str, Any] | None = None

        int_qid: int | None = None
        try:
            if qid is not None:
                int_qid = int(qid)
        except (TypeError, ValueError):
            int_qid = None

        if int_qid is not None and int_qid in results_by_id:
            raw_item = results_by_id[int_qid]
        elif index in results_by_number:
            raw_item = results_by_number[index]

        student_answer = ""
        feedback = ""
        score_value = 0.0

        if raw_item:
            student_answer = raw_item.get("student_answer") or ""
            feedback = raw_item.get("feedback") or ""
            try:
                score_value = float(raw_item.get("score", 0))
            except (TypeError, ValueError):
                score_value = 0.0

        score_value = max(0.0, min(1.0, score_value))

        normalized.append(
            {
                "question_id": qid,
                "question_number": index,
                "original_question": question.get("latex_content"),
                "reference_answer": question.get("reference_answer"),
                "student_answer": student_answer,
                "score": round(score_value, 4),
                "feedback": feedback,
                "question_type": question.get("question_type"),
                "tags": question.get("tags", []),
                "source": question.get("source"),
            }
        )

    return normalized


def match_student_by_filename(filename: str, roster: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """尝试根据文件名匹配学生信息。"""
    if not filename:
        return None
    name_body = os.path.splitext(filename)[0].lower()
    for student in roster or []:
        if not isinstance(student, dict):
            continue
        sid = str(student.get("student_id") or "").lower()
        name = str(student.get("name") or "").lower()
        if sid and sid in name_body:
            return student
        if name and name in name_body:
            return student
    return None
