# -*- coding: utf-8 -*-
"""
高考题目录入和自动打标系统配置文件
"""

import os

# 数据库配置
DATABASE_PATH = "question_database.db"
SYSTEM_DATABASE_PATH = "system.db"
STUDENT_DATABASE_PATH = "data/students.db"
HOMEWORK_DATABASE_PATH = "data/homework_results.db"

# Session配置
SECRET_KEY = "your-secret-key-change-this-in-production"

# 大语言模型配置
LLM_CONFIG = {
    "api_url": "https://api.deepseek.com",  # 替换为实际的API地址
    "api_key": "your-api-key",  # 替换为实际的API密钥
    "model": "deepseek-chat",  # 或使用其他模型
    "temperature": 0.7,
    "max_tokens": 4000
}

# 题目标签配置
QUESTION_TAGS = [
    "立体几何",
    "导数题", 
    "极值点偏移",
    "三角函数",
    "数列",
    "概率统计",
    "解析几何",
    "函数与方程",
    "不等式",
    "向量",
    "复数",
    "算法与程序框图"
]

# Web服务器配置

# 试卷解析配置
EXAM_PARSE_ANSWER_BATCH_SIZE = 6

WEB_CONFIG = {
    "host": "0.0.0.0",
    "port": 5001,
    "debug": False
}

# 其他配置
MAX_QUESTION_LENGTH = 10000  # 题目最大长度
MAX_ANSWER_LENGTH = 5000     # 答案最大长度

# OCR服务配置
OCR_BASE_URL = "http://192.168.31.65:5000"

# OCR模式配置
# - "processed": 使用 ocr_server 的 /ocr 接口（默认）
# - "raw": 使用 generate 接口直接调用模型
OCR_MODE = os.environ.get("OCR_MODE", "processed")

# Raw OCR服务配置（用于raw mode，直接调用generate接口）
RAW_OCR_CONFIG = {
    "api_url": "http://192.168.31.101:8000/generate",
    "model": "/Users/imac/dev/DeepSeek-OCR-8bit",
    "prompt": "<|grounding|>Convert the document to markdown."
}

# Embedding服务配置
EMBEDDING_CONFIG = {
    "api_url": "http://192.168.31.65:11434/api/embed",
    "model": "qwen3-embedding:0.6b"
}

# Embedding缓存配置
EMBEDDING_CACHE_DB_PATH = "data/embeddings_cache.db"

# LaTeX编译服务配置
LATEX_COMPILE_CONFIG = {
    "api_url": "http://192.168.31.65:5000/compile-latex",
    "compile_recipe": [
        ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"],
        ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"]
    ]
}

# LaTeX模板配置
LATEX_TEMPLATE_PATH = "resources/exam_template.tex"
LATEX_CLASS_PATH = "resources/exam-zh.cls"
LATEX_OUTPUT_DIR = "latex_results"

# 学生学情分析配置
ANALYTICS_WINDOW_DAYS = 30  # 最近一个月窗口，可调整
REPORT_MAX_ITEMS = 20  # 生成报告时的题目上限
AI_RECOMMENDATION_LIMIT = 6  # 推荐题目数量
AVERAGE_CACHE_TTL_SECONDS = 6 * 3600  # 平均分缓存有效期，防止频繁计算（可选）
HOMEWORK_UPLOAD_DIR = "uploads/homework_submissions"

# LaTeX后处理配置
LATEX_POST_PROCESSING = {
    "enabled": True,  # 是否启用LaTeX后处理
    "remove_center_env": True,  # 移除center环境
    "remove_includegraphics": True,  # 移除includegraphics命令
}