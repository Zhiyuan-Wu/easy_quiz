# -*- coding: utf-8 -*-
"""
日志工具模块
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


class SystemLogger:
    """系统日志记录器"""
    
    def __init__(self, log_file: str = "log.txt"):
        """
        初始化日志记录器
        
        Args:
            log_file: 日志文件路径
        """
        self.log_file = log_file
        self._setup_logger()
    
    def _setup_logger(self):
        """设置日志记录器"""
        # 创建日志目录
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 配置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 创建文件处理器
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.WARNING)
        
        # 配置根日志记录器
        self.logger = logging.getLogger('question_tagging')
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def log_ocr_result(self, request_id: str, markdown_content: str, images_count: int):
        """记录OCR结果"""
        self.logger.info(f"OCR处理完成 - 请求ID: {request_id}, 内容长度: {len(markdown_content)}, 图片数量: {images_count}")
        self.logger.info(f"OCR Markdown内容: {markdown_content}...")
    
    def log_llm_prompt(self, prompt: str, context: str = ""):
        """记录大模型提示词"""
        self.logger.info(f"发送大模型请求 - 上下文: {context}")
        self.logger.info(f"提示词: {prompt}...")
    
    def log_llm_response(self, response: str, context: str = ""):
        """记录大模型返回结果"""
        self.logger.info(f"大模型响应 - 上下文: {context}, 响应长度: {len(response)}")
        self.logger.info(f"大模型响应内容: {response}...")
    
    def log_database_operation(self, operation: str, table: str, record_id: Optional[int] = None, details: str = ""):
        """记录数据库操作"""
        self.logger.info(f"数据库操作 - {operation} - 表: {table}, ID: {record_id}, 详情: {details}")
    
    def log_image_processing(self, original_filename: str, local_path: str, operation: str = "保存"):
        """记录图片处理"""
        self.logger.info(f"图片处理 - {operation} - 原始文件: {original_filename}, 本地路径: {local_path}")
    
    def log_question_parsing(self, questions_count: int, parsing_type: str = "试卷解析"):
        """记录题目解析"""
        self.logger.info(f"{parsing_type}完成 - 解析出 {questions_count} 道题目")
    
    def log_user_action(self, user_id: int, action: str, details: str = ""):
        """记录用户操作"""
        self.logger.info(f"用户操作 - 用户ID: {user_id}, 操作: {action}, 详情: {details}")
    
    def log_error(self, error: Exception, context: str = ""):
        """记录错误"""
        self.logger.error(f"系统错误 - 上下文: {context}, 错误: {str(error)}", exc_info=True)
    
    def log_warning(self, message: str, context: str = ""):
        """记录警告"""
        self.logger.warning(f"系统警告 - 上下文: {context}, 消息: {message}")
    
    def log_system_info(self, message: str):
        """记录系统信息"""
        self.logger.info(f"系统信息 - {message}")
    
    def log_performance(self, operation: str, duration: float, details: str = ""):
        """记录性能信息"""
        self.logger.info(f"性能统计 - 操作: {operation}, 耗时: {duration:.2f}秒, 详情: {details}")


# 创建全局日志记录器实例
system_logger = SystemLogger()


def get_logger() -> SystemLogger:
    """获取日志记录器实例"""
    return system_logger
