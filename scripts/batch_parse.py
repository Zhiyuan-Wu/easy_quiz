#!/usr/bin/env python3
"""Batch parse exam files from a directory and persist questions."""

import argparse
import shutil
import uuid
from pathlib import Path
from typing import Iterable, Tuple
import sys
sys.path.append("../easy_quiz")

from config import EXAM_PARSE_ANSWER_BATCH_SIZE, SYSTEM_DATABASE_PATH
from logger import get_logger
from ocr_client import DeepSeekOCRClient
from question_manager import QuestionManager
from system_manager import SystemManager
from utils import apply_filename_replacements, convert_pdf_to_images, save_ocr_images

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "pdf"}
UPLOAD_ROOT = Path("uploads")

def iter_input_files(root: Path) -> Iterable[Path]:
    """Yield all supported files under the given directory recursively."""
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower().lstrip(".") in ALLOWED_EXTENSIONS:
            yield path


def ensure_upload_dirs() -> Tuple[Path, Path]:
    """Ensure the upload directory structure exists."""
    UPLOAD_ROOT.mkdir(exist_ok=True)
    upload_images_dir = UPLOAD_ROOT / "upload_images"
    upload_images_dir.mkdir(exist_ok=True)
    (UPLOAD_ROOT / "ocr_images").mkdir(exist_ok=True)
    return UPLOAD_ROOT, upload_images_dir


def process_file(
    source_path: Path,
    question_manager: QuestionManager,
    ocr_client: DeepSeekOCRClient,
    logger,
) -> int:
    """Parse a single file and persist questions.

    Args:
        source_path: 原始试卷文件路径。
        question_manager: QuestionManager 实例，用于写入数据库。
        ocr_client: OCR 客户端实例。
        logger: 日志记录器。

    Returns:
        int: 成功入库的题目数量。
    """
    upload_root, upload_images_dir = ensure_upload_dirs()

    ext = source_path.suffix.lower()
    unique_filename = f"{uuid.uuid4()}{ext}"
    stored_path = upload_images_dir / unique_filename
    shutil.copy2(source_path, stored_path)

    markdown_segments = []
    image_filename_mapping = {}

    if ext == ".pdf":
        logger.log_system_info(f"批量解析 - 处理PDF试卷: {stored_path}")
        page_image_paths = convert_pdf_to_images(str(stored_path), str(upload_images_dir))
        for page_index, image_path in page_image_paths:
            logger.log_system_info(f"批量解析 - OCR PDF第{page_index}页: {image_path}")
            ocr_result = ocr_client.ocr_image(image_path)
            page_markdown = ocr_result.get("markdown", "")
            ocr_images = ocr_result.get("images", [])
            logger.log_ocr_result(ocr_result.get("request_id", "unknown"), page_markdown, len(ocr_images))

            page_mapping, replacements = save_ocr_images(
                ocr_images,
                str(upload_root),
                logger,
                suffix=f"_p{page_index}",
            )
            image_filename_mapping.update(page_mapping)
            page_markdown = apply_filename_replacements(page_markdown, replacements)
            if page_markdown:
                markdown_segments.append(page_markdown)

        markdown_content = "\n\n".join(markdown_segments)
        batch_size = EXAM_PARSE_ANSWER_BATCH_SIZE
    else:
        logger.log_system_info(f"批量解析 - OCR文件: {stored_path}")
        ocr_result = ocr_client.ocr_image(str(stored_path))
        markdown_content = ocr_result.get("markdown", "")
        ocr_images = ocr_result.get("images", [])
        logger.log_ocr_result(ocr_result.get("request_id", "unknown"), markdown_content, len(ocr_images))

        page_mapping, replacements = save_ocr_images(
            ocr_images,
            str(upload_root),
            logger,
        )
        image_filename_mapping.update(page_mapping)
        markdown_content = apply_filename_replacements(markdown_content, replacements)
        batch_size = None

    if not markdown_content.strip():
        logger.log_warning(f"批量解析 - OCR内容为空，跳过文件: {source_path}", "批量解析")
        return 0

    parsed_questions = question_manager.parse_exam_paper(
        markdown_content,
        image_filename_mapping,
        get_answer_batch_size=batch_size,
    )

    if not parsed_questions:
        logger.log_warning(f"批量解析 - 未解析出题目: {source_path}", "批量解析")
        return 0

    created = 0
    # 提取文件名（不含路径和扩展名）作为来源
    source_name = source_path.stem  # stem属性自动去除扩展名
    
    for question in parsed_questions:
        question_type = question.get("question_type", "解答题") or "解答题"
        add_id = question_manager.add_question(
            latex_content=question.get("question", ""),
            tags=question.get("tags", []),
            reference_answer=question.get("answer", ""),
            source=source_name,
            image=question.get("image", []),
            question_type=question_type,
        )
        logger.log_database_operation("INSERT_BATCH", "questions", add_id, f"来源文件: {source_path}")
        created += 1

    return created


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="递归批量解析试卷图片/PDF并写入数据库。")
    parser.add_argument("input_dir", type=Path, help="待解析的根目录")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多解析的文件数量（默认不限制）",
    )
    parser.add_argument(
        "--blackwords",
        type=str,
        default="",
        help="跳过文件名中包含blackword的文件，逗号分隔",
    )
    args = parser.parse_args()
    blackwords = args.blackwords.split(",") if args.blackwords else []
    input_dir: Path = args.input_dir
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"输入目录不存在或不是有效目录: {input_dir}")

    logger = get_logger()
    system_manager = SystemManager(SYSTEM_DATABASE_PATH)
    question_manager = QuestionManager(system_manager=system_manager)
    ocr_client = DeepSeekOCRClient()

    processed_files = 0
    created_questions = 0

    for file_path in iter_input_files(input_dir):
        if args.limit is not None and processed_files >= args.limit:
            break

        if any(blackword in file_path.name for blackword in blackwords):
            continue

        try:
            created = process_file(file_path, question_manager, ocr_client, logger)
            created_questions += created
            processed_files += 1
            logger.log_system_info(f"批量解析完成: {file_path}，新增题目 {created} 道")
        except Exception as exc:
            logger.log_error(exc, f"批量解析失败 - 文件: {file_path}")

    logger.log_system_info(
        f"批量解析任务完成，共处理文件 {processed_files} 个，新增题目 {created_questions} 道"
    )


if __name__ == "__main__":
    main()
