# -*- coding: utf-8 -*-
"""
高考题目录入和自动打标系统核心类
"""

import sqlite3
import json
import requests
import re
import time
import os
import threading
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from typing import List, Dict, Optional, Tuple
from config import (
    DATABASE_PATH,
    LLM_CONFIG,
    MAX_QUESTION_LENGTH,
    MAX_ANSWER_LENGTH,
    EMBEDDING_CACHE_DB_PATH,
)
from openai import OpenAI
from logger import get_logger
from json_repair import repair_json
from ocr_client import DeepSeekOCRClient

import faiss

QUESTION_TYPE_CHOICES = {"选择题", "填空题", "解答题"}
DEFAULT_QUESTION_TYPE = "解答题"


def _sanitize_question_type(value: Optional[str]) -> str:
    """标准化题目类型值为受支持的选项之一。

    参数:
        value: 原始题目类型字符串，可能为 None。

    返回:
        合法的题目类型字符串。
    """
    if isinstance(value, str):
        question_type = value.strip() or DEFAULT_QUESTION_TYPE
    else:
        question_type = DEFAULT_QUESTION_TYPE
    if question_type not in QUESTION_TYPE_CHOICES:
        question_type = DEFAULT_QUESTION_TYPE
    return question_type

class QuestionManager:
    """高考题目管理器类。"""
    
    def __init__(self, db_path: str = DATABASE_PATH, system_manager=None):
        """初始化题目管理器。

        参数:
            db_path: 题目数据库文件路径。
            system_manager: 系统管理器实例，可为 None。

        返回:
            None。
        """
        self.db_path = db_path
        self.system_manager = system_manager
        self.llm_client = OpenAI(api_key=LLM_CONFIG["api_key"],base_url=LLM_CONFIG["api_url"])
        self.logger = get_logger()
        self.ocr_client = DeepSeekOCRClient()
        self.init_database()
        
        # Embedding缓存文件路径（使用配置）
        cache_dir = os.path.dirname(EMBEDDING_CACHE_DB_PATH)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        self.embedding_cache_path = EMBEDDING_CACHE_DB_PATH
        self._ensure_embedding_store()
        self.embedding_cache = self._load_embedding_cache()  # question_id -> embedding vector
        
        # 异步任务锁和正在处理的question_id集合
        self._async_task_lock = threading.Lock()
        self._processing_question_ids = set()  # 正在计算embedding的question_id集合
    
    def init_database(self):
        """初始化题目数据库表结构。

        返回:
            None。
        """
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
                question_type TEXT DEFAULT '解答题',
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
        if 'question_type' not in columns:
            cursor.execute("ALTER TABLE questions ADD COLUMN question_type TEXT DEFAULT '解答题'")
        
        # 创建索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags ON questions(tags)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source ON questions(source)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON questions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_visibility ON questions(visibility)')
        
        conn.commit()
        conn.close()
    
    def _ensure_embedding_store(self):
        """确保 embedding 缓存存储结构存在。

        返回:
            None。
        """
        conn = sqlite3.connect(self.embedding_cache_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''
                CREATE TABLE IF NOT EXISTS embeddings (
                    question_id INTEGER PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
            conn.commit()
        finally:
            conn.close()

    def _load_embedding_cache(self):
        """加载 embedding 缓存内容。

        返回:
            question_id 到 embedding 向量的映射字典。
        """
        cache = {}
        try:
            conn = sqlite3.connect(self.embedding_cache_path)
            cursor = conn.cursor()
            cursor.execute('SELECT question_id, embedding FROM embeddings')
            rows = cursor.fetchall()
            for question_id, embedding_text in rows:
                try:
                    cache[question_id] = json.loads(embedding_text)
                except Exception as parse_error:
                    self.logger.log_error(parse_error, f"解析embedding失败 - question_id: {question_id}")
            conn.close()
        except Exception as e:
            self.logger.log_error(e, "加载embedding缓存失败")
        return cache
    
    def _save_embedding_to_cache(self, question_id: int, embedding: List[float]):
        """保存或更新 embedding 数据。

        参数:
            question_id: 题目 ID。
            embedding: 题目对应的向量列表。

        返回:
            None。
        """
        try:
            conn = sqlite3.connect(self.embedding_cache_path)
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO embeddings (question_id, embedding, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(question_id) DO UPDATE SET
                    embedding = excluded.embedding,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                (question_id, json.dumps(embedding, ensure_ascii=False))
            )
            conn.commit()
            conn.close()

            self.embedding_cache[question_id] = embedding
        except Exception as e:
            self.logger.log_error(e, f"保存embedding缓存失败 - question_id: {question_id}")

    def _get_detailed_instruct(self, task_description: str, query: str) -> str:
        """构造包含任务描述的查询文本。

        参数:
            task_description: 任务描述文本。
            query: 用户查询内容。

        返回:
            带指令的查询字符串。
        """
        return f'Instruct: {task_description}\nQuery:{query}'
    
    def _get_question_text(self, question: Dict) -> str:
        """拼接题目的完整文本内容。

        参数:
            question: 题目信息字典。

        返回:
            包含来源、标签、题面和参考答案的文本。
        """
        parts = []
        if question.get('source'):
            parts.append(question['source'])
        if question.get('tags'):
            parts.extend(question['tags'])
        if question.get('latex_content'):
            parts.append(question['latex_content'])
        if question.get('reference_answer'):
            parts.append(question['reference_answer'])
        return ' '.join(parts)
    
    def _compute_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算两个向量的余弦相似度。

        参数:
            vec1: 向量 1。
            vec2: 向量 2。

        返回:
            余弦相似度数值。
        """
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))
    
    def _compute_missing_embeddings_async(self, question_ids: List[int], current_user_id: int = None):
        """异步计算缺失的 embedding 向量。

        参数:
            question_ids: 待补齐 embedding 的题目 ID 列表。
            current_user_id: 当前用户 ID，可为 None。

        返回:
            None。
        """
        def compute_task():
            """后台线程任务：加载题目、计算 embedding 并更新缓存。

            返回:
                None。
            """
            processed_ids = set()  # 记录成功处理的question_id
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                for question_id in question_ids:
                    # 再次检查是否已有embedding（防止并发情况）
                    if question_id in self.embedding_cache:
                        processed_ids.add(question_id)
                        continue
                    
                    # 获取题目信息
                    cursor.execute('''
                        SELECT * FROM questions 
                        WHERE id = ? AND (visibility = 'public' OR user_id = ?)
                    ''', (question_id, current_user_id))
                    
                    row = cursor.fetchone()
                    if not row:
                        processed_ids.add(question_id)  # 题目不存在，也标记为已处理，避免重复尝试
                        continue
                    
                    question = self._row_to_dict(row)
                    question_text = self._get_question_text(question)
                    
                    # 计算embedding（不需要prompt）
                    try:
                        embeddings = self.ocr_client.get_embeddings([question_text])
                        if embeddings and len(embeddings) > 0:
                            # 再次检查是否已有embedding（防止在计算过程中被其他线程写入）
                            if question_id not in self.embedding_cache:
                                self._save_embedding_to_cache(question_id, embeddings[0])
                            processed_ids.add(question_id)
                    except Exception as e:
                        self.logger.log_error(e, f"计算embedding失败 - question_id: {question_id}")
                        processed_ids.add(question_id)  # 即使失败也标记为已处理，避免重复尝试
                
                conn.close()
            except Exception as e:
                self.logger.log_error(e, "异步计算embedding任务失败")
            finally:
                # 从正在处理的集合中移除本次任务处理的question_id
                with self._async_task_lock:
                    # 移除已处理的ID（包括成功和失败的）
                    self._processing_question_ids.difference_update(question_ids)
        
        # 在后台线程中执行
        thread = threading.Thread(target=compute_task)
        thread.daemon = True
        thread.start()
    
    def add_question(self, latex_content: str, tags: List[str] = None, 
                    reference_answer: str = None, source: str = None, 
                    image: List[str] = None, user_id: int = None, 
                    visibility: str = 'public', question_type: str = '解答题') -> int:
        """将题目写入数据库。

        参数:
            latex_content: LaTeX 格式的题目内容。
            tags: 题目标签列表，可选。
            reference_answer: 参考解答文本，可选。
            source: 题目来源说明，可选。
            image: 图片路径列表，可选。
            user_id: 上传题目的用户 ID，可选。
            visibility: 可见范围，默认 public。
            question_type: 题目类型，默认“解答题”。

        返回:
            新插入题目的 ID。
        """
        start_time = time.time()
        
        if not latex_content or len(latex_content) > MAX_QUESTION_LENGTH:
            self.logger.log_error(ValueError("题目内容不能为空且长度不能超过{}字符".format(MAX_QUESTION_LENGTH)), "添加题目验证")
            raise ValueError("题目内容不能为空且长度不能超过{}字符".format(MAX_QUESTION_LENGTH))
        
        if reference_answer and len(reference_answer) > MAX_ANSWER_LENGTH:
            self.logger.log_error(ValueError("参考解答长度不能超过{}字符".format(MAX_ANSWER_LENGTH)), "添加题目验证")
            raise ValueError("参考解答长度不能超过{}字符".format(MAX_ANSWER_LENGTH))
        
        tags = tags or []
        tags_json = json.dumps(tags, ensure_ascii=False)
        image = image or []
        image_json = json.dumps(image, ensure_ascii=False)
        
        question_type = _sanitize_question_type(question_type)

        self.logger.log_database_operation(
            "INSERT",
            "questions",
            details=f"用户ID: {user_id}, 标签: {tags}, 来源: {source}, 题目类型: {question_type}"
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO questions (latex_content, tags, reference_answer, source, image, user_id, visibility, question_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (latex_content, tags_json, reference_answer, source, image_json, user_id, visibility, question_type))
            
            question_id = cursor.lastrowid
            conn.commit()
            
            duration = time.time() - start_time
            self.logger.log_performance("添加题目", duration, f"题目ID: {question_id}")
            self.logger.log_database_operation("INSERT_SUCCESS", "questions", question_id, f"内容长度: {len(latex_content)}")
            
            return question_id
            
        except Exception as e:
            conn.rollback()
            self.logger.log_error(e, f"添加题目失败 - 用户ID: {user_id}")
            raise e
        finally:
            conn.close()
    
    def update_question(self, question_id: int, latex_content: str,
                        reference_answer: Optional[str], current_user_id: int,
                        question_type: Optional[str] = None) -> Optional[Dict]:
        """更新题目内容并刷新对应的 embedding。

        参数:
            question_id: 题目 ID。
            latex_content: 更新后的题目内容。
            reference_answer: 更新后的参考答案，可为 None。
            current_user_id: 当前用户 ID。
            question_type: 更新后的题目类型，可为 None。

        返回:
            更新后的题目字典；若题目不存在则返回 None。
        """
        if not latex_content or not latex_content.strip():
            raise ValueError("题目内容不能为空")

        reference_answer = reference_answer if reference_answer is not None else ''

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT user_id FROM questions WHERE id = ?', (question_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError('题目不存在')
            owner_id = row[0]
            if owner_id != current_user_id:
                raise PermissionError('无权修改该题目')

            normalized_type = None
            if question_type is not None:
                normalized_type = _sanitize_question_type(question_type)

            set_clauses = ["latex_content = ?", "reference_answer = ?", "updated_at = CURRENT_TIMESTAMP"]
            params = [latex_content, reference_answer]
            if normalized_type is not None:
                set_clauses.insert(2, "question_type = ?")
                params.append(normalized_type)

            set_clause_sql = ', '.join(set_clauses)
            params.extend([question_id, current_user_id])

            cursor.execute(
                f'''
                UPDATE questions
                SET {set_clause_sql}
                WHERE id = ? AND user_id = ?
                ''', params
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

        updated_question = self.get_question_by_id(question_id, current_user_id)
        if updated_question:
            try:
                question_text = self._get_question_text(updated_question)
                embeddings = self.ocr_client.get_embeddings([question_text])
                if embeddings and len(embeddings) > 0:
                    self._save_embedding_to_cache(question_id, embeddings[0])
            except Exception as e:
                self.logger.log_error(e, f"更新题目embedding失败 - question_id: {question_id}")

        return updated_question

    def get_questions_by_tags(self, tags: List[str], current_user_id: int = None) -> List[Dict]:
        """按标签查询题目（包含可见性过滤）。

        参数:
            tags: 需要匹配的标签列表。
            current_user_id: 当前用户 ID，可为 None。

        返回:
            匹配的题目字典列表。
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
        """根据 ID 获取题目详情（含可见性判断）。

        参数:
            question_id: 题目 ID。
            current_user_id: 当前用户 ID，可为 None。

        返回:
            题目信息字典；若不存在或无权访问则返回 None。
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
    
    
    def auto_tag_and_answer(self, content: str, source: str = None) -> Tuple[List[str], str, str, str]:
        """使用大模型为题目自动打标并生成解答与 LaTeX。

        参数:
            content: 原始题目内容。
            source: 题目来源，可为 None。

        返回:
            (标签列表, 参考解答, LaTeX 内容, 题目类型) 四元组。
        """
        start_time = time.time()
        
        try:
            # 获取当前可用的标签
            available_tags = []
            if self.system_manager:
                tags = self.system_manager.get_all_tags(limit=50)
                available_tags = [tag['name'] for tag in tags]
            
            # 构建提示词
            prompt = f"""
请分析以下高考数学题目，并完成以下任务：

1. 将题目内容格式化为标准的LaTeX格式，确保数学公式、符号、格式都正确
2. 请给这个题目所涉及的知识点打上几个标签，可以参考以下标签：{', '.join(available_tags) if available_tags else '立体几何, 导数题, 极值点偏移, 三角函数, 数列, 概率统计, 解析几何, 函数与方程, 不等式, 向量, 复数, 算法与程序框图'}
3. 生成详细的参考解答
4. 判断题目类型并返回 question_type 字段，可选值仅限 "选择题"、"填空题"、"解答题"，若无法确定请返回 "解答题"

题目内容：
{content}

请按以下JSON格式回复：
{{
    "latex_content": "LaTeX格式的题目内容",
    "tags": ["标签1", "标签2"],
    "answer": "详细的参考解答，包含解题步骤和最终答案",
    "question_type": "解答题"
}}
"""
            
            self.logger.log_llm_prompt(prompt, "自动打标和LaTeX格式化")
            
            # 调用大语言模型API
            response = self.llm_client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[{"role": "user", "content": prompt}]
            )
            response = response.choices[0].message.content
            
            self.logger.log_llm_response(response, "自动打标和LaTeX格式化")
            
            # 解析响应
            try:
                match = re.search(r'\{.*\}', response, re.DOTALL).group(0)
                match = repair_json(match)
                result = json.loads(match)
                latex_content = result.get('latex_content', content)
                tags = result.get('tags', [])
                answer = result.get('answer', '')
                question_type = result.get('question_type', '解答题')
                if not isinstance(question_type, str):
                    question_type = '解答题'
                question_type = question_type.strip() or '解答题'
                if question_type not in QUESTION_TYPE_CHOICES:
                    question_type = '解答题'
                
                # 验证标签并添加到数据库
                valid_tags = []
                for tag in tags:
                    if self.system_manager:
                        # 添加标签到数据库（如果不存在则创建，存在则增加使用计数）
                        self.system_manager.add_tag(tag)
                        valid_tags.append(tag)
                    else:
                        # 如果没有系统管理器，直接使用标签
                        valid_tags.append(tag)
                
                duration = time.time() - start_time
                self.logger.log_performance("自动打标和LaTeX格式化", duration, f"标签数量: {len(valid_tags)}")
                
                return valid_tags, answer, latex_content, question_type
                
            except json.JSONDecodeError as e:
                self.logger.log_error(e, "JSON解析失败 - 自动打标")
                raise e
                
        except Exception as e:
            self.logger.log_error(e, "自动打标失败")
            return [], "自动生成解答失败，请手动输入", content, '解答题'

    def generate_question_variant(self, question: Dict) -> Dict:
        """基于原题生成微调后的题目变体。

        参数:
            question: 原始题目信息字典。

        返回:
            新生成的题目信息字典。
        """
        if not question:
            raise ValueError('题目信息缺失，无法生成变体')

        latex_content = question.get('latex_content', '').strip()
        reference_answer = question.get('reference_answer', '').strip()
        tags = question.get('tags', [])
        images = question.get('image', [])

        if not latex_content:
            raise ValueError('题目内容为空，无法生成变体')

        image_instruction = ''
        if images:
            image_instruction = f"题目包含图片引用（{', '.join(images)}），请保持图片数量与引用一致，不要修改图片内容。"

        tag_instruction = ''
        if tags:
            tag_instruction = f"题目的核心知识点标签包括：{', '.join(tags)}。"

        prompt = f"""
你是一名资深命题教师，请基于给定的题目生成一个经过微调的新题。请遵循以下原则：

1. 保留题目的核心考察点和大致难度，但可以通过替换数据、调整已知条件、引入边界或特殊情形等方式实现变化。
2. 确保题目叙述清晰、逻辑自洽，所有符号、单位、条件和结论互相匹配。
3. {image_instruction}
4. {tag_instruction}
5. 如果原题包含参考解答，请为新题给出更新后的参考解答；若原题无解答，可补充一个清晰的解答步骤。
6. 输出请使用有效的LaTeX语法，保持题面与解答格式规范。

请直接按照以下JSON格式回复，不要提供额外说明：
{{
  "latex_content": "新的题目内容",
  "reference_answer": "新的参考解答，可为空字符串",
  "tags": ["可选的新标签数组"]
}}

原题内容：
{latex_content}

原题参考解答：
{reference_answer or '暂无参考解答'}
"""

        self.logger.log_llm_prompt(prompt, "AI变题")

        response = self.llm_client.chat.completions.create(
            model=LLM_CONFIG["model"],
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content

        self.logger.log_llm_response(content, "AI变题")

        try:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if not match:
                raise ValueError('模型输出格式不符合JSON要求')
            payload = repair_json(match.group(0))
            variant = json.loads(payload)
        except Exception as e:
            self.logger.log_error(e, "解析AI变题结果失败")
            raise ValueError('AI生成的内容解析失败，请稍后重试')

        new_content = variant.get('latex_content', '').strip() or latex_content
        new_answer = variant.get('reference_answer', variant.get('answer', '')).strip()
        new_tags = variant.get('tags', tags)

        return {
            'latex_content': new_content,
            'reference_answer': new_answer,
            'tags': new_tags
        }
    
    def parse_exam_paper(
        self,
        markdown_content: str,
        image_filename_mapping: Dict[str, str] = None,
        get_answer_batch_size: Optional[int] = None,
    ) -> List[Dict]:
        """解析试卷内容并提取题目结构。

        参数:
            markdown_content: OCR 识别得到的 Markdown 内容。
            image_filename_mapping: 图片文件名到本地路径的映射，可为 None。
            get_answer_batch_size: 控制答案生成批次的大小，为 None 时保持单次解析。

        返回:
            解析出的题目字典列表。
        """
        start_time = time.time()
        
        try:
            # 构建提示词
            images_info = ""
            if image_filename_mapping:
                available_filenames = list(image_filename_mapping.keys())
                images_info = f"\n可用的图片文件：{', '.join(available_filenames)}"
            
            # 获取当前可用的标签
            available_tags = []
            if self.system_manager:
                tags = self.system_manager.get_all_tags(limit=50)
                available_tags = [tag['name'] for tag in tags]
            
            instruction_items = [
                r"去除OCR识别中的明显噪声和不合理内容，去除与题目内容无关的内容。",
                r"识别并分离每道题目。移除原有题目编号，分值信息。重复的题目不要重复返回。",
                r"将题目内容转换为LaTeX格式，数学公式和变量务必使用公式环境。选择题选项使用enumerate环境，选择题的选项之间使用\\item命令，选项内部不需要再添加ABCD标签。表格使用table环境。除此之外不要使用其他环境，如\\centering等。空行直接插入空行，而不要使用\\par命令或\\\\来强制换行",
                r"识别题目中引用的图片（如果有），从可用图片列表中选择合适的图片，严格返回可用的图片文件列表中的文件名，不要新增前缀或移除后缀。只能在image字段中声明所需要的图片，不要重复在question字段的原始题目中使用包含图片的\includegraphics命令。",
                r"识别OCR文本中的表格结构（使用<table>、<tr>、<td>、<br>标签），移除这些标签并转换为标准的LaTeX table/tabular 环境，保持单元格内容。",
                r"对于选择题，在合适的位置插入一对括号()来表明需要解答内容的位置，对于填空题，在合适的位置插入\underline{\hspace{1cm}}来表明需要解答内容的位置。",
            ]

            tag_instruction_prefix = "为每道题目生成三个以上的其所考察的知识点标签，包括知识领域、解题技巧、用到的公式等，标签可以参考："

            instruction_items.append(
                f"{tag_instruction_prefix}{', '.join(available_tags) if available_tags else '立体几何, 导数题, 极值点偏移, 三角函数, 数列, 概率统计, 解析几何, 函数与方程, 不等式, 向量, 复数, 算法与程序框图'}"
            )
            instruction_items.append(
                '判断每道题目的类型并返回 question_type 字段，可选值仅限 "选择题"、"填空题"、"解答题"，若无法确定请返回 "解答题"'
            )
            if get_answer_batch_size is None:
                instruction_items.append("给每道题目生成详细的参考解答，包括解题步骤和最终答案")
            instruction_items.append("返回JSON格式，包含题目列表。务必注意json格式中斜杠等符号的正确转义。")


            instruction_text = "\n".join(
                f"{idx}. {item}" for idx, item in enumerate(instruction_items, start=1)
            )

            json_lines = [
                "{",
                '    "questions": [',
                "        {",
                '            "question": "LaTeX格式的题目内容",',
                '            "image": ["图片路径1", "图片路径2"],',
                '            "question_type": "解答题",',
            ]
            if get_answer_batch_size is None:
                json_lines.append('            "answer": "详细的参考解答",')
            json_lines.append('            "tags": ["标签1", "标签2"]')
            json_lines.extend([
                "        }",
                "    ]",
                "}",
            ])
            json_template = textwrap.dedent("\n".join(json_lines)).strip()

            examples = r"""
{
    "questions": [
    {
        "question": "已知三棱柱 $ABC-A_1B_1C_1$ 的侧棱与底面边长都相等，$A_1$ 在底面 $ABC$ 内的射影为 $\\triangle ABC$ 的中心，则 $AB_1$ 与底面 $ABC$ 所成角的正弦值等于( )\n\\begin{enumerate}\n\\item $\\frac{1}{3}$\n\\item $\\frac{\\sqrt{2}}{3}$\n\\item $\\frac{\\sqrt{3}}{3}$\n\\item $\\frac{2}{3}$\n\\end{enumerate}",
        "image": ["0_p2.jpg"],
        "tags": ["立体几何", "线面角", "空间几何"],
        "question_type": "选择题"
    },
    {
        "question": "已知抛物线 $y = ax^{2} - 1$ 的焦点是坐标原点，则以抛物线与两坐标轴的三个交点为顶点的三角形面积为$\\underline{\\hspace{1cm}}$。",
        "image": [],
        "tags": ["解析几何", "抛物线", "三角形面积"],
        "question_type": "填空题"
    },
    {
        "question": "四棱锥 $A-BCDE$ 中，底面 $BCDE$ 为矩形，侧面 $ABC\\perp$ 底面 $BCDE$，$BC=2$，$CD=\\sqrt{2}$，$AB=AC$。\n\n(I) 证明：$AD\\perp CE$；\n\n(II) 设 $CE$ 与平面 $ABE$ 所成的角为 $45^{\\circ}$，求二面角 $C-AD-E$ 的大小。",
        "image": ["0_p3.jpg"],
        "tags": ["立体几何", "空间向量", "线面垂直", "二面角"],
        "question_type": "解答题"
    }
    ]
}
"""

            prompt = textwrap.dedent(
                f"""请分析以下试卷内容，提取所有题目并格式化为LaTeX格式。

试卷内容：
{markdown_content}{images_info}

请按以下要求处理：
{instruction_text}

请按以下JSON格式回复：
{json_template}

请参考以下示例：
{examples}

你的解析结果（JSON格式）：
"""
            ).strip()

            self.logger.log_llm_prompt(prompt, "试卷解析")
            
            # 调用大语言模型API
            response = self.llm_client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[{"role": "user", "content": prompt}]
            )
            response = response.choices[0].message.content
            
            self.logger.log_llm_response(response, "试卷解析")
            
            # 解析响应
            try:
                match = re.search(r'\{.*\}', response, re.DOTALL).group(0)
                match = repair_json(match)
                result = json.loads(match)
                questions = result.get('questions', [])
                
                # 验证解析结果
                if not questions:
                    self.logger.log_warning("大模型没有解析出任何题目", "试卷解析")
                    return []

                self.logger.log_question_parsing(len(questions), "试卷解析（原始大模型返回）")
                
                # 确保每个题目都有必要的字段
                validated_questions = []
                for i, question in enumerate(questions):
                    if not isinstance(question, dict):
                        self.logger.log_warning(f"题目 {i+1} 不是有效的字典格式", "试卷解析")
                        continue
                    
                    # 处理图片路径映射
                    question_images = question.get('image', [])
                    mapped_images = []
                    if question_images and image_filename_mapping:
                        for img_filename in question_images:
                            img_filename = img_filename.strip().replace("images/", "")
                            if img_filename in image_filename_mapping:
                                mapped_images.append(image_filename_mapping[img_filename])
                                self.logger.log_image_processing(img_filename, image_filename_mapping[img_filename], "映射")
                            else:
                                self.logger.log_warning(f"图片文件 {img_filename} 在映射中未找到", "试卷解析")
                    
                    # 确保必要字段存在
                    normalized_question_type = _sanitize_question_type(question.get('question_type'))

                    validated_question = {
                        'question': question.get('question', ''),
                        'image': mapped_images,  # 使用映射后的本地路径
                        'tags': question.get('tags', []),
                        'answer': question.get('answer', ''),
                        'question_type': normalized_question_type
                    }
                    
                    if not validated_question['question']:
                        self.logger.log_warning(f"题目 {i+1} 没有题目内容", "试卷解析")
                        continue
                    
                    validated_questions.append(validated_question)

                if (
                    get_answer_batch_size is not None
                    and isinstance(get_answer_batch_size, int)
                    and get_answer_batch_size != 0
                    and validated_questions
                ):
                    batch_size = max(1, abs(get_answer_batch_size))

                    def _build_answer_prompt(batch_indices):
                        lines = []
                        for idx in batch_indices:
                            question_payload = validated_questions[idx]
                            display_index = idx + 1
                            tags_text = ', '.join(question_payload.get('tags', [])) or '无'
                            images_text = ', '.join(question_payload.get('image', [])) or '无'
                            lines.append(
                                textwrap.dedent(
                                    f"""题目 {display_index}:
题型: {question_payload.get('question_type', '解答题')}
标签: {tags_text}
图片: {images_text}
LaTeX题面:
{question_payload.get('question', '')}
"""
                                ).strip()
                            )
                        question_block = '\n\n'.join(lines)
                        return textwrap.dedent(
                            f"""你是一名资深的数学教师，请为以下题目生成严格、条理清晰的参考解答。请保持与提供的题目序号一致，不要输出额外说明或重复题面。

请按照下述JSON格式回复：
{{
    "answers": [
        {{
            "question_index": 1,
            "answer": "在此填写详细解答"
        }}
    ]
}}

注意：
1. 请使用latex写数学公式。
1. 如果信息不足以回答问题，请直接回答参考答案略。
2. 选择题的答案请明确使用ABCD的标签（按照\\item命令的顺序），而不是第一个选项等模糊说法。
3. 使用json返回你的结果，务必注意json格式中斜杠等符号的正确转义。

题目列表：
{question_block}
"""
                        ).strip()

                    def _request_answers_for_batch(batch_indices, batch_number):
                        batch_prompt = _build_answer_prompt(batch_indices)
                        context_name = f"试卷答案生成-批次{batch_number}"
                        self.logger.log_llm_prompt(batch_prompt, context_name)
                        response = self.llm_client.chat.completions.create(
                            model=LLM_CONFIG["model"],
                            messages=[{"role": "user", "content": batch_prompt}]
                        )
                        content = response.choices[0].message.content
                        self.logger.log_llm_response(content, context_name)

                        try:
                            match = re.search(r'\{.*\}', content, re.DOTALL)
                            if not match:
                                raise ValueError("未找到JSON结构")
                            payload_text = repair_json(match.group(0))
                            payload = json.loads(payload_text)
                        except Exception as exc:
                            self.logger.log_error(exc, f"解析批次 {batch_number} 答案失败")
                            return {}

                        answers_data = payload.get('answers', [])
                        mapping = {}
                        for item in answers_data:
                            if not isinstance(item, dict):
                                continue
                            try:
                                question_index = int(item.get('question_index')) - 1
                            except (TypeError, ValueError):
                                continue
                            answer_text = item.get('answer')
                            if not isinstance(answer_text, str):
                                continue
                            mapping[question_index] = answer_text.strip()
                        return mapping

                    batches = [
                        list(range(start, min(start + batch_size, len(validated_questions))))
                        for start in range(0, len(validated_questions), batch_size)
                    ]

                    answers_collected = {}
                    max_workers = min(len(batches), 4) or 1
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        future_to_meta = {
                            executor.submit(_request_answers_for_batch, batch_indices, batch_number): (batch_number, batch_indices)
                            for batch_number, batch_indices in enumerate(batches, start=1)
                        }
                        for future in as_completed(future_to_meta):
                            batch_number, batch_indices = future_to_meta[future]
                            try:
                                batch_answers = future.result()
                                answers_collected.update(batch_answers)
                            except Exception as exc:
                                self.logger.log_error(exc, f"批次 {batch_number} 答案生成任务异常")

                    for idx, answer_text in answers_collected.items():
                        if 0 <= idx < len(validated_questions) and answer_text:
                            validated_questions[idx]['answer'] = answer_text

                duration = time.time() - start_time
                self.logger.log_performance("试卷解析", duration, f"解析出 {len(validated_questions)} 道题目")
                self.logger.log_question_parsing(len(validated_questions), "试卷解析（解析后）")
                
                return validated_questions
                
            except json.JSONDecodeError as e:
                self.logger.log_error(e, "JSON解析失败 - 试卷解析")
                return []
                
        except Exception as e:
            self.logger.log_error(e, "解析试卷失败")
            return []
    
    def delete_question(self, question_id: int, current_user_id: int = None) -> bool:
        """删除题目，仅允许删除自己的题目。

        参数:
            question_id: 题目 ID。
            current_user_id: 当前用户 ID。

        返回:
            删除成功返回 True，否则返回 False。
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
        """分页获取题目列表（含可见性过滤）。

        参数:
            limit: 每页条目数量。
            offset: 偏移量。
            current_user_id: 当前用户 ID，可为 None。

        返回:
            题目字典列表。
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
    
    def search_questions(self, keyword: str, current_user_id: int = None, k: int = 10) -> List[Dict]:
        """结合关键词与 embedding 召回搜索题目。

        参数:
            keyword: 搜索关键词。
            current_user_id: 当前用户 ID，可为 None。
            k: embedding 搜索返回的数量上限。

        返回:
            匹配题目的字典列表，包含排序得分。
        """
        # 1. 关键词搜索
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        keyword_questions = []
        if keyword:
            cursor.execute('''
                SELECT * FROM questions 
                WHERE (latex_content LIKE ? OR source LIKE ?)
                AND (visibility = 'public' OR user_id = ?)
                ORDER BY created_at DESC
            ''', (f'%{keyword}%', f'%{keyword}%', current_user_id))
            
            rows = cursor.fetchall()
            for row in rows:
                question = self._row_to_dict(row)
                question['ranking_score'] = 0.0
                keyword_questions.append(question)
        
        # 2. 获取所有可见题目
        cursor.execute('''
            SELECT * FROM questions 
            WHERE visibility = 'public' OR user_id = ?
        ''', (current_user_id,))
        
        all_visible_questions = []
        all_question_ids = []
        rows = cursor.fetchall()
        for row in rows:
            question = self._row_to_dict(row)
            all_visible_questions.append(question)
            all_question_ids.append(question['id'])
        
        conn.close()
        
        # 3. Embedding搜索（如果有关键词）
        embedding_questions = []
        embedding_similarity_map = {}  # question_id -> similarity
        missing_embedding_ids = []
        
        if keyword:
            try:
                # 构建带指令的查询文本
                task = 'Given a web search query, retrieve relevant passages that answer the query'
                query_text = self._get_detailed_instruct(task, keyword)
                
                # 获取查询的embedding
                query_embeddings = self.ocr_client.get_embeddings([query_text])
                if query_embeddings and len(query_embeddings) > 0:
                    query_embedding = query_embeddings[0]
                    query_embedding_array = np.array([query_embedding], dtype='float32')
                    
                    # 动态构建faiss索引（仅包含可见题目且有embedding的）
                    visible_question_ids = [q['id'] for q in all_visible_questions]
                    visible_embeddings = []
                    visible_question_id_list = []
                    
                    for question_id in visible_question_ids:
                        if question_id in self.embedding_cache:
                            visible_embeddings.append(self.embedding_cache[question_id])
                            visible_question_id_list.append(question_id)
                        else:
                            missing_embedding_ids.append(question_id)
                    
                    if len(visible_embeddings) > 0:
                        try:
                            # 构建临时faiss索引
                            embeddings_array = np.array(visible_embeddings, dtype='float32')
                            dimension = embeddings_array.shape[1]
                            temp_index = faiss.IndexFlatL2(dimension)
                            temp_index.add(embeddings_array)
                            
                            # 使用faiss搜索top k个最相似的embedding
                            k_search = min(k * 2, len(visible_embeddings))
                            distances, indices = temp_index.search(query_embedding_array, k_search)

                            embedding_candidates: List[Dict] = []
                            visible_question_dict = {q['id']: q for q in all_visible_questions}

                            for idx, dist in zip(indices[0], distances[0]):
                                if idx < len(visible_question_id_list):
                                    question_id = visible_question_id_list[idx]
                                    if question_id in visible_question_dict:
                                        similarity = -float(dist)
                                        question = visible_question_dict[question_id]
                                        question_with_score = dict(question)
                                        question_with_score['ranking_score'] = similarity
                                        embedding_candidates.append(question_with_score)
                                        embedding_similarity_map[question_id] = similarity

                            embedding_candidates.sort(
                                key=lambda item: item.get('ranking_score', 0.0), reverse=True
                            )
                            embedding_questions = embedding_candidates[:k]
                        except Exception as e:
                            self.logger.log_error(e, "Faiss搜索失败")
                            embedding_questions = []
                            embedding_similarity_map = {}
            except Exception as e:
                self.logger.log_error(e, "Embedding搜索失败")
        
        # 4. 合并结果（去重）
        result_dict = {}
        for question in keyword_questions:
            result_dict[question['id']] = question
        
        for question in embedding_questions:
            existing = result_dict.get(question['id'])
            if existing:
                existing_score = existing.get('ranking_score', 0.0)
                new_score = question.get('ranking_score', 0.0)
                existing['ranking_score'] = max(existing_score, new_score)
            else:
                result_dict[question['id']] = question
        
        # 5. 如果有缺失的embedding，启动异步任务计算
        if missing_embedding_ids:
            # 只计算可见题目的embedding
            visible_missing_ids = [qid for qid in missing_embedding_ids if qid in all_question_ids]
            if visible_missing_ids:
                # 过滤掉正在处理的question_id，避免重复任务
                with self._async_task_lock:
                    new_missing_ids = [qid for qid in visible_missing_ids 
                                     if qid not in self._processing_question_ids 
                                     and qid not in self.embedding_cache]
                    # 标记这些question_id为正在处理
                    self._processing_question_ids.update(new_missing_ids)
                
                if new_missing_ids:
                    self._compute_missing_embeddings_async(new_missing_ids, current_user_id)
        
        # 6. 返回合并后的结果列表
        results = list(result_dict.values())
        
        # 优先显示关键词匹配的题目，然后是embedding匹配的（按相似度排序）
        keyword_question_ids = {q['id'] for q in keyword_questions}
        embedding_question_ids = {q['id'] for q in embedding_questions}
        
        def sort_key(q):
            """根据命中来源与相似度对题目排序。

            参数:
                q: 题目信息字典。

            返回:
                用于排序的元组。
            """
            q_id = q['id']
            in_keyword = q_id in keyword_question_ids
            in_embedding = q_id in embedding_question_ids
            
            if in_keyword and in_embedding:
                return (0, 0)  # 两种都匹配，优先级最高
            elif in_keyword:
                return (1, 0)  # 只关键词匹配
            elif in_embedding:
                # 使用similarity排序，相似度越高（值越大）越靠前，所以使用负值
                similarity = embedding_similarity_map.get(q_id, 0)
                return (2, -similarity)  # 只embedding匹配，按相似度排序
            else:
                return (3, 0)
        
        results.sort(key=sort_key)
        
        return results
    
    def get_question_stats(self, current_user_id: int = None) -> Dict:
        """获取题目统计信息。

        参数:
            current_user_id: 当前用户 ID，可为 None。

        返回:
            包含总题量与个人题量的字典。
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
        """将数据库行转换为题目字典。

        参数:
            row: sqlite 行数据。

        返回:
            题目信息字典，若行为空则返回 None。
        """
        if not row:
            return None
        
        # 获取列信息以正确处理ALTER TABLE后的列顺序
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(questions)")
        columns_info = cursor.fetchall()
        conn.close()
        
        # 创建列名到索引的映射
        column_map = {col[1]: idx for idx, col in enumerate(columns_info)}
        
        # 安全地获取列值，处理可能不存在的列
        def get_column_value(column_name, default=None):
            """安全获取指定列的值。

            参数:
                column_name: 列名。
                default: 获取失败时使用的默认值。

            返回:
                目标列的值或默认值。
            """
            if column_name in column_map:
                idx = column_map[column_name]
                if idx < len(row):
                    return row[idx]
            return default
        
        return {
            'id': get_column_value('id'),
            'latex_content': get_column_value('latex_content'),
            'tags': json.loads(get_column_value('tags', '[]')),
            'reference_answer': get_column_value('reference_answer'),
            'source': get_column_value('source'),
            'image': json.loads(get_column_value('image', '[]')) if get_column_value('image') else [],
            'user_id': get_column_value('user_id'),
            'visibility': get_column_value('visibility', 'public'),
            'question_type': get_column_value('question_type', '解答题'),
            'created_at': get_column_value('created_at'),
            'updated_at': get_column_value('updated_at')
        }
