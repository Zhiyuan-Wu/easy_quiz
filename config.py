# -*- coding: utf-8 -*-
"""
高考题目录入和自动打标系统配置文件
"""

# 数据库配置
DATABASE_PATH = "question_database.db"
USER_DATABASE_PATH = "users.db"

# Session配置
SECRET_KEY = "your-secret-key-change-this-in-production"

# 大语言模型配置
LLM_CONFIG = {
    "api_url": "https://api.deepseek.com",  # 替换为实际的API地址
    "api_key": "sk-7027575dc0a64e3e9c726fe39195cc31",  # 替换为实际的API密钥
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
    "host": "127.0.0.1",
    "port": 5001,
    "debug": False
}

# 其他配置
MAX_QUESTION_LENGTH = 10000  # 题目最大长度
MAX_ANSWER_LENGTH = 5000     # 答案最大长度

# OCR服务配置
OCR_BASE_URL = "http://192.168.31.65:5000"