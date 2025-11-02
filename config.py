# -*- coding: utf-8 -*-
"""
高考题目录入和自动打标系统配置文件
"""

# 数据库配置
DATABASE_PATH = "question_database.db"
SYSTEM_DATABASE_PATH = "system.db"

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

# Embedding服务配置
EMBEDDING_CONFIG = {
    "api_url": "http://192.168.31.65:11434/api/embed",
    "model": "qwen3-embedding:0.6b"
}

# Embedding缓存配置
EMBEDDING_CACHE_PATH = "data/embeddings_cache.jsonl"

# LaTeX编译服务配置
LATEX_COMPILE_CONFIG = {
    "api_url": "http://192.168.31.65:5000/compile-latex",
    "compile_recipe": [
        ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"],
        ["xelatex", "-output-directory", "{output_dir}", "-interaction=nonstopmode", "{tex_file}"]
    ]
}