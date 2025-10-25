# -*- coding: utf-8 -*-
"""
高考题目录入和自动打标系统核心类
"""

import sqlite3
import json
import requests
import re
from typing import List, Dict, Optional, Tuple
from config import DATABASE_PATH, LLM_CONFIG, QUESTION_TAGS, MAX_QUESTION_LENGTH, MAX_ANSWER_LENGTH
from openai import OpenAI

class QuestionManager:
    """高考题目管理器类"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        """
        初始化题目管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.llm_client = OpenAI(api_key=LLM_CONFIG["api_key"],base_url=LLM_CONFIG["api_url"])
        self.init_database()
    
    def init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建题目表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                latex_content TEXT NOT NULL,
                tags TEXT NOT NULL,  -- JSON格式存储标签列表
                reference_answer TEXT,
                source TEXT,
                image TEXT,  -- JSON格式存储图片路径列表
                user_id INTEGER,  -- 上传用户ID
                visibility TEXT DEFAULT 'public',  -- 可见范围: public(所有人), private(仅自己)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 检查是否需要添加新字段（用于数据库升级）
        cursor.execute("PRAGMA table_info(questions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'user_id' not in columns:
            cursor.execute('ALTER TABLE questions ADD COLUMN user_id INTEGER')
        
        if 'visibility' not in columns:
            cursor.execute("ALTER TABLE questions ADD COLUMN visibility TEXT DEFAULT 'public'")
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags ON questions(tags)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON questions(source)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON questions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_visibility ON questions(visibility)')
        
        conn.commit()
        conn.close()
    
    def add_question(self, latex_content: str, tags: List[str] = None, 
                    reference_answer: str = None, source: str = None, 
                    image: List[str] = None, user_id: int = None, 
                    visibility: str = 'public') -> int:
        """
        添加题目到数据库
        
        Args:
            latex_content: LaTeX格式的题目内容
            tags: 题目标签列表
            reference_answer: 参考解答
            source: 题目来源
            image: 图片路径列表
            
        Returns:
            新插入题目的ID
        """
        if not latex_content or len(latex_content) > MAX_QUESTION_LENGTH:
            raise ValueError("题目内容不能为空且长度不能超过{}字符".format(MAX_QUESTION_LENGTH))
        
        if reference_answer and len(reference_answer) > MAX_ANSWER_LENGTH:
            raise ValueError("参考解答长度不能超过{}字符".format(MAX_ANSWER_LENGTH))
        
        tags = tags or []
        tags_json = json.dumps(tags, ensure_ascii=False)
        image = image or []
        image_json = json.dumps(image, ensure_ascii=False)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO questions (latex_content, tags, reference_answer, source, image, user_id, visibility)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (latex_content, tags_json, reference_answer, source, image_json, user_id, visibility))
            
            question_id = cursor.lastrowid
            conn.commit()
            return question_id
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_questions_by_tags(self, tags: List[str], current_user_id: int = None) -> List[Dict]:
        """
        根据标签查询题目（考虑可见性）
        
        Args:
            tags: 要查询的标签列表
            current_user_id: 当前用户ID
            
        Returns:
            匹配的题目列表
        """
        if not tags:
            return []
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 构建查询条件
        conditions = []
        params = []
        
        for tag in tags:
            conditions.append("tags LIKE ?")
            params.append(f'%"{tag}"%')
        
        # 添加可见性条件
        visibility_condition = "(visibility = 'public' OR user_id = ?)"
        params.append(current_user_id)
        
        query = f"SELECT * FROM questions WHERE ({' OR '.join(conditions)}) AND {visibility_condition} ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        # 转换为字典格式
        questions = []
        for row in rows:
            question = self._row_to_dict(row)
            questions.append(question)
        
        return questions
    
    def get_question_by_id(self, question_id: int, current_user_id: int = None) -> Optional[Dict]:
        """
        根据ID获取题目详情（考虑可见性）
        
        Args:
            question_id: 题目ID
            current_user_id: 当前用户ID
            
        Returns:
            题目信息字典，如果不存在或无权访问返回None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM questions 
            WHERE id = ? AND (visibility = 'public' OR user_id = ?)
        ''', (question_id, current_user_id))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return self._row_to_dict(row)
        return None
    
    def get_reference_answer(self, question_id: int, current_user_id: int = None) -> Optional[str]:
        """
        获取题目的参考解答（考虑可见性）
        
        Args:
            question_id: 题目ID
            current_user_id: 当前用户ID
            
        Returns:
            参考解答，如果不存在或无权访问返回None
        """
        question = self.get_question_by_id(question_id, current_user_id)
        return question['reference_answer'] if question else None
    
    def auto_tag_and_answer(self, latex_content: str, source: str = None) -> Tuple[List[str], str]:
        """
        使用大语言模型自动打标并生成参考解答
        
        Args:
            latex_content: LaTeX格式的题目内容
            source: 题目来源
            
        Returns:
            (标签列表, 参考解答)
        """
        try:
            # 构建提示词
            prompt = f"""
请分析以下高考数学题目，并完成以下任务：

1. 从以下标签中选择1-3个最符合的标签：{', '.join(QUESTION_TAGS)}
2. 生成详细的参考解答

题目内容：
{latex_content}

请按以下JSON格式回复：
{{
    "tags": ["标签1", "标签2"],
    "answer": "详细的参考解答，包含解题步骤和最终答案"
}}
"""
            
            # 调用大语言模型API
            response = self.llm_client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=LLM_CONFIG["max_tokens"],
                temperature=LLM_CONFIG["temperature"]
            )
            response = response.choices[0].message.content
            
            # 解析响应
            try:
                result = json.loads(response)
                tags = result.get('tags', [])
                answer = result.get('answer', '')
                
                # 验证标签是否在允许的标签列表中
                valid_tags = [tag for tag in tags if tag in QUESTION_TAGS]
                
                return valid_tags, answer
                
            except json.JSONDecodeError:
                # 如果JSON解析失败，尝试从文本中提取信息
                tags = self._extract_tags_from_text(response)
                answer = self._extract_answer_from_text(response)
                return tags, answer
                
        except Exception as e:
            print(f"自动打标失败: {e}")
            return [], "自动生成解答失败，请手动输入"
    
    def _call_llm_api(self, prompt: str) -> str:
        """
        调用大语言模型API
        
        Args:
            prompt: 提示词
            
        Returns:
            API响应内容
        """
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {LLM_CONFIG["api_key"]}'
        }
        
        data = {
            'model': LLM_CONFIG['model'],
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': LLM_CONFIG['max_tokens'],
            'temperature': LLM_CONFIG['temperature']
        }
        
        response = requests.post(
            LLM_CONFIG['api_url'],
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"API调用失败: {response.status_code} - {response.text}")
    
    def _extract_tags_from_text(self, text: str) -> List[str]:
        """从文本中提取标签"""
        tags = []
        for tag in QUESTION_TAGS:
            if tag in text:
                tags.append(tag)
        return tags
    
    def _extract_answer_from_text(self, text: str) -> str:
        """从文本中提取答案"""
        # 简单的文本提取逻辑，可以根据需要优化
        lines = text.split('\n')
        answer_lines = []
        in_answer = False
        
        for line in lines:
            if '解答' in line or '答案' in line or '解：' in line:
                in_answer = True
            if in_answer and line.strip():
                answer_lines.append(line.strip())
        
        return '\n'.join(answer_lines) if answer_lines else text
    
    def parse_exam_paper(self, markdown_content: str) -> List[Dict]:
        """
        解析试卷内容，提取题目
        
        Args:
            markdown_content: OCR识别的markdown内容
            
        Returns:
            解析出的题目列表
        """
        try:
            # 构建提示词
            prompt = f"""
请分析以下试卷内容，提取所有题目并格式化为LaTeX格式。

试卷内容：
{markdown_content}

请按以下要求处理：
1. 去除OCR识别中的明显噪声和不合理内容
2. 识别并分离每道题目
3. 将题目内容转换为LaTeX格式，选择题选项优先使用enumerate环境
4. 识别题目中引用的图片（如果有）
5. 为每道题目自动打标并生成解答
6. 返回JSON格式，包含题目列表

请按以下JSON格式回复：
{{
    "questions": [
        {{
            "question": "LaTeX格式的题目内容",
            "image": ["图片路径1", "图片路径2"],
            "tags": ["标签1", "标签2"],
            "answer": "详细的参考解答"
        }}
    ]
}}
"""
            
            # 调用大语言模型API
            response = self.llm_client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=LLM_CONFIG["max_tokens"],
                temperature=LLM_CONFIG["temperature"]
            )
            response = response.choices[0].message.content
            
            # 解析响应
            try:
                result = json.loads(response)
                return result.get('questions', [])
            except json.JSONDecodeError:
                # 如果JSON解析失败，返回空列表
                return []
                
        except Exception as e:
            print(f"解析试卷失败: {e}")
            return []
    
    def delete_question(self, question_id: int, current_user_id: int = None) -> bool:
        """
        删除题目（只能删除自己的题目）
        
        Args:
            question_id: 题目ID
            current_user_id: 当前用户ID
            
        Returns:
            是否删除成功
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('DELETE FROM questions WHERE id = ? AND user_id = ?', (question_id, current_user_id))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_all_questions(self, limit: int = 100, offset: int = 0, current_user_id: int = None) -> List[Dict]:
        """
        获取所有题目（分页，考虑可见性）
        
        Args:
            limit: 每页数量
            offset: 偏移量
            current_user_id: 当前用户ID
            
        Returns:
            题目列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM questions 
            WHERE visibility = 'public' OR user_id = ?
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        ''', (current_user_id, limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        questions = []
        for row in rows:
            question = self._row_to_dict(row)
            questions.append(question)
        
        return questions
    
    def search_questions(self, keyword: str, current_user_id: int = None) -> List[Dict]:
        """
        根据关键词搜索题目（考虑可见性）
        
        Args:
            keyword: 搜索关键词
            current_user_id: 当前用户ID
            
        Returns:
            匹配的题目列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM questions 
            WHERE (latex_content LIKE ? OR source LIKE ?)
            AND (visibility = 'public' OR user_id = ?)
            ORDER BY created_at DESC
        ''', (f'%{keyword}%', f'%{keyword}%', current_user_id))
        
        rows = cursor.fetchall()
        conn.close()
        
        questions = []
        for row in rows:
            question = self._row_to_dict(row)
            questions.append(question)
        
        return questions
    
    def get_question_stats(self, current_user_id: int = None) -> Dict:
        """
        获取题目统计信息
        
        Args:
            current_user_id: 当前用户ID
            
        Returns:
            统计信息字典
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总题目数（可见的）
        cursor.execute('''
            SELECT COUNT(*) FROM questions 
            WHERE visibility = 'public' OR user_id = ?
        ''', (current_user_id,))
        total = cursor.fetchone()[0]
        
        # 我的题目数
        cursor.execute('SELECT COUNT(*) FROM questions WHERE user_id = ?', (current_user_id,))
        my_questions = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total': total,
            'my_questions': my_questions
        }
    
    def _row_to_dict(self, row) -> Dict:
        """将数据库行转换为字典"""
        if not row:
            return None
        
        # 处理不同长度的行（用于数据库升级兼容）
        return {
            'id': row[0],
            'latex_content': row[1],
            'tags': json.loads(row[2]),
            'reference_answer': row[3],
            'source': row[4],
            'image': json.loads(row[5]) if row[5] else [],
            'user_id': row[6] if len(row) > 6 else None,
            'visibility': row[7] if len(row) > 7 else 'public',
            'created_at': row[8] if len(row) > 8 else row[6],
            'updated_at': row[9] if len(row) > 9 else row[7]
        }
