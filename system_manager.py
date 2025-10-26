# -*- coding: utf-8 -*-
"""
系统管理模块 - 用户管理和标签管理
"""

import sqlite3
import hashlib
import json
from typing import Optional, Dict, List
from config import SYSTEM_DATABASE_PATH, QUESTION_TAGS

class SystemManager:
    """系统管理器类 - 管理用户和标签"""
    
    def __init__(self, db_path: str = SYSTEM_DATABASE_PATH):
        """
        初始化系统管理器
        
        Args:
            db_path: 系统数据库文件路径
        """
        self.db_path = db_path
        self.init_database()
        self.seed_initial_tags()
    
    def init_database(self):
        """初始化系统数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建标签表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建导出历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS export_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT,
                question_ids TEXT, -- JSON array
                export_format TEXT,
                export_mode TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON users(username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tag_name ON tags(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tag_usage ON tags(usage_count)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_export_user ON export_history(user_id)')
        
        conn.commit()
        conn.close()
    
    def seed_initial_tags(self):
        """将初始标签种子数据添加到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            for tag_name in QUESTION_TAGS:
                cursor.execute('''
                    INSERT OR IGNORE INTO tags (name, usage_count)
                    VALUES (?, 0)
                ''', (tag_name,))
            
            conn.commit()
        finally:
            conn.close()
    
    def hash_password(self, password: str) -> str:
        """
        对密码进行哈希
        
        Args:
            password: 明文密码
            
        Returns:
            哈希后的密码
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()
    
    def register_user(self, username: str, password: str, email: str = None) -> tuple:
        """
        注册新用户
        
        Args:
            username: 用户名
            password: 密码
            email: 邮箱（可选）
            
        Returns:
            (success, message)
        """
        if not username or len(username) < 3:
            return False, "用户名至少需要3个字符"
        
        if not password or len(password) < 6:
            return False, "密码至少需要6个字符"
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 检查用户名是否已存在
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            if cursor.fetchone():
                return False, "用户名已存在"
            
            # 插入新用户
            password_hash = self.hash_password(password)
            cursor.execute('''
                INSERT INTO users (username, password_hash, email)
                VALUES (?, ?, ?)
            ''', (username, password_hash, email))
            
            conn.commit()
            return True, "注册成功"
            
        except Exception as e:
            conn.rollback()
            return False, f"注册失败: {str(e)}"
        finally:
            conn.close()
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict]:
        """
        验证用户登录
        
        Args:
            username: 用户名
            password: 密码
            
        Returns:
            用户信息字典，如果验证失败返回None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            password_hash = self.hash_password(password)
            cursor.execute('''
                SELECT id, username, email, created_at 
                FROM users 
                WHERE username = ? AND password_hash = ?
            ''', (username, password_hash))
            
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'created_at': row[3]
                }
            return None
            
        finally:
            conn.close()
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """
        根据ID获取用户信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            用户信息字典，如果不存在返回None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, username, email, created_at 
                FROM users 
                WHERE id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'created_at': row[3]
                }
            return None
            
        finally:
            conn.close()
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        根据用户名获取用户信息
        
        Args:
            username: 用户名
            
        Returns:
            用户信息字典，如果不存在返回None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, username, email, created_at 
                FROM users 
                WHERE username = ?
            ''', (username,))
            
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'created_at': row[3]
                }
            return None
            
        finally:
            conn.close()
    
    def update_password(self, user_id: int, old_password: str, new_password: str) -> tuple:
        """
        更新用户密码
        
        Args:
            user_id: 用户ID
            old_password: 旧密码
            new_password: 新密码
            
        Returns:
            (success, message)
        """
        if not new_password or len(new_password) < 6:
            return False, "新密码至少需要6个字符"
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 验证旧密码
            old_password_hash = self.hash_password(old_password)
            cursor.execute('''
                SELECT id FROM users 
                WHERE id = ? AND password_hash = ?
            ''', (user_id, old_password_hash))
            
            if not cursor.fetchone():
                return False, "旧密码错误"
            
            # 更新密码
            new_password_hash = self.hash_password(new_password)
            cursor.execute('''
                UPDATE users 
                SET password_hash = ? 
                WHERE id = ?
            ''', (new_password_hash, user_id))
            
            conn.commit()
            return True, "密码更新成功"
            
        except Exception as e:
            conn.rollback()
            return False, f"密码更新失败: {str(e)}"
        finally:
            conn.close()
    
    # 标签管理方法
    def get_all_tags(self, limit: int = 20) -> List[Dict]:
        """
        获取所有标签，按使用频率排序
        
        Args:
            limit: 返回标签数量限制
            
        Returns:
            标签列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT name, usage_count, created_at 
                FROM tags 
                ORDER BY usage_count DESC, name ASC 
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            tags = []
            for row in rows:
                tags.append({
                    'name': row[0],
                    'usage_count': row[1],
                    'created_at': row[2]
                })
            
            return tags
            
        finally:
            conn.close()
    
    def add_tag(self, tag_name: str) -> bool:
        """
        添加标签或增加使用计数
        
        Args:
            tag_name: 标签名称
            
        Returns:
            是否成功
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 尝试插入新标签，如果已存在则增加使用计数
            cursor.execute('''
                INSERT INTO tags (name, usage_count)
                VALUES (?, 1)
                ON CONFLICT(name) DO UPDATE SET
                usage_count = usage_count + 1
            ''', (tag_name,))
            
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_tag_by_name(self, name: str) -> Optional[Dict]:
        """
        根据名称获取标签
        
        Args:
            name: 标签名称
            
        Returns:
            标签信息字典，如果不存在返回None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT name, usage_count, created_at 
                FROM tags 
                WHERE name = ?
            ''', (name,))
            
            row = cursor.fetchone()
            
            if row:
                return {
                    'name': row[0],
                    'usage_count': row[1],
                    'created_at': row[2]
                }
            return None
            
        finally:
            conn.close()
    
    # 导出历史管理方法
    def save_export_history(self, user_id: int, title: str, question_ids: List[int], 
                          export_format: str, export_mode: str) -> int:
        """
        保存导出历史
        
        Args:
            user_id: 用户ID
            title: 导出标题
            question_ids: 题目ID列表
            export_format: 导出格式
            export_mode: 导出模式
            
        Returns:
            导出历史ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            question_ids_json = json.dumps(question_ids, ensure_ascii=False)
            cursor.execute('''
                INSERT INTO export_history (user_id, title, question_ids, export_format, export_mode)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, title, question_ids_json, export_format, export_mode))
            
            export_id = cursor.lastrowid
            conn.commit()
            return export_id
            
        finally:
            conn.close()
    
    def get_export_history(self, user_id: int, limit: int = 50) -> List[Dict]:
        """
        获取用户的导出历史
        
        Args:
            user_id: 用户ID
            limit: 返回数量限制
            
        Returns:
            导出历史列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, title, question_ids, export_format, export_mode, created_at
                FROM export_history 
                WHERE user_id = ?
                ORDER BY created_at DESC 
                LIMIT ?
            ''', (user_id, limit))
            
            rows = cursor.fetchall()
            history = []
            for row in rows:
                history.append({
                    'id': row[0],
                    'title': row[1],
                    'question_ids': json.loads(row[2]),
                    'export_format': row[3],
                    'export_mode': row[4],
                    'created_at': row[5]
                })
            
            return history
            
        finally:
            conn.close()
    
    def get_export_by_id(self, export_id: int) -> Optional[Dict]:
        """
        根据ID获取导出历史详情
        
        Args:
            export_id: 导出历史ID
            
        Returns:
            导出历史详情，如果不存在返回None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT id, user_id, title, question_ids, export_format, export_mode, created_at
                FROM export_history 
                WHERE id = ?
            ''', (export_id,))
            
            row = cursor.fetchone()
            
            if row:
                return {
                    'id': row[0],
                    'user_id': row[1],
                    'title': row[2],
                    'question_ids': json.loads(row[3]),
                    'export_format': row[4],
                    'export_mode': row[5],
                    'created_at': row[6]
                }
            return None
            
        finally:
            conn.close()
