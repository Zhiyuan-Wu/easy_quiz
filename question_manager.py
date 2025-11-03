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
import numpy as np
from typing import List, Dict, Optional, Tuple
from config import DATABASE_PATH, LLM_CONFIG, MAX_QUESTION_LENGTH, MAX_ANSWER_LENGTH, EMBEDDING_CACHE_PATH
from openai import OpenAI
from logger import get_logger
from json_repair import repair_json
from ocr_client import DeepSeekOCRClient

import faiss

class QuestionManager:
    """高考题目管理器类"""
    
    def __init__(self, db_path: str = DATABASE_PATH, system_manager=None):
        """
        初始化题目管理器
        
        Args:
            db_path: 数据库文件路径
            system_manager: 系统管理器实例
        """
        self.db_path = db_path
        self.system_manager = system_manager
        self.llm_client = OpenAI(api_key=LLM_CONFIG["api_key"],base_url=LLM_CONFIG["api_url"])
        self.logger = get_logger()
        self.ocr_client = DeepSeekOCRClient()
        self.init_database()
        
        # Embedding缓存文件路径（使用配置）
        cache_dir = os.path.dirname(EMBEDDING_CACHE_PATH)
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir, exist_ok=True)
        self.embedding_cache_path = EMBEDDING_CACHE_PATH
        self.embedding_cache = {}  # question_id -> embedding vector
        self._load_embedding_cache()
        
        # 异步任务锁和正在处理的question_id集合
        self._async_task_lock = threading.Lock()
        self._processing_question_ids = set()  # 正在计算embedding的question_id集合
    
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
    
    def _load_embedding_cache(self):
        """加载embedding缓存"""
        if os.path.exists(self.embedding_cache_path):
            try:
                with open(self.embedding_cache_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            item = json.loads(line.strip())
                            question_id = item['question_id']
                            embedding = item['embedding']
                            self.embedding_cache[question_id] = embedding
            except Exception as e:
                self.logger.log_error(e, "加载embedding缓存失败")
                self.embedding_cache = {}
    
    def _save_embedding_to_cache(self, question_id: int, embedding: List[float]):
        """追加保存embedding到缓存文件"""
        try:
            with open(self.embedding_cache_path, 'a', encoding='utf-8') as f:
                item = {
                    'question_id': question_id,
                    'embedding': embedding
                }
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
            
            # 更新内存缓存
            self.embedding_cache[question_id] = embedding
        except Exception as e:
            self.logger.log_error(e, f"保存embedding缓存失败 - question_id: {question_id}")

    def _rewrite_embedding_cache(self):
        """将当前内存中的embedding缓存写回文件"""
        try:
            with open(self.embedding_cache_path, 'w', encoding='utf-8') as f:
                for question_id, embedding in self.embedding_cache.items():
                    f.write(json.dumps({
                        'question_id': question_id,
                        'embedding': embedding
                    }, ensure_ascii=False) + '\n')
        except Exception as e:
            self.logger.log_error(e, "重写embedding缓存失败")

    def _update_embedding_cache(self, question_id: int, embedding: List[float]):
        """更新指定题目的embedding缓存"""
        self.embedding_cache[question_id] = embedding
        self._rewrite_embedding_cache()
    
    def _get_detailed_instruct(self, task_description: str, query: str) -> str:
        """获取带指令的查询文本"""
        return f'Instruct: {task_description}\nQuery:{query}'
    
    def _get_question_text(self, question: Dict) -> str:
        """获取题目的完整文本（来源+标签+题目+解答）"""
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
        """计算余弦相似度"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))
    
    def _compute_missing_embeddings_async(self, question_ids: List[int], current_user_id: int = None):
        """异步计算缺失的embedding"""
        def compute_task():
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
        
        self.logger.log_database_operation("INSERT", "questions", details=f"用户ID: {user_id}, 标签: {tags}, 来源: {source}")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO questions (latex_content, tags, reference_answer, source, image, user_id, visibility)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (latex_content, tags_json, reference_answer, source, image_json, user_id, visibility))
            
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
                        reference_answer: Optional[str], current_user_id: int) -> Optional[Dict]:
        """更新题目信息并刷新对应的embedding"""
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

            cursor.execute('''
                UPDATE questions
                SET latex_content = ?, reference_answer = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
            ''', (latex_content, reference_answer, question_id, current_user_id))
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
                    self._update_embedding_cache(question_id, embeddings[0])
            except Exception as e:
                self.logger.log_error(e, f"更新题目embedding失败 - question_id: {question_id}")

        return updated_question

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
    
    
    def auto_tag_and_answer(self, content: str, source: str = None) -> Tuple[List[str], str, str]:
        """
        使用大语言模型自动打标、生成参考解答并格式化为LaTeX
        
        Args:
            content: 题目内容（可能是普通文本或LaTeX格式）
            source: 题目来源
            
        Returns:
            (标签列表, 参考解答, LaTeX格式的题目内容)
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

题目内容：
{content}

请按以下JSON格式回复：
{{
    "latex_content": "LaTeX格式的题目内容",
    "tags": ["标签1", "标签2"],
    "answer": "详细的参考解答，包含解题步骤和最终答案"
}}
"""
            
            self.logger.log_llm_prompt(prompt, "自动打标和LaTeX格式化")
            
            # 调用大语言模型API
            response = self.llm_client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=LLM_CONFIG["max_tokens"],
                temperature=LLM_CONFIG["temperature"]
            )
            response = response.choices[0].message.content
            
            self.logger.log_llm_response(response, "自动打标和LaTeX格式化")
            
            # 解析响应
            try:
                match = re.search(r'\{.*?\}', response, re.DOTALL).group(0)
                match = repair_json(match)
                result = json.loads(match)
                latex_content = result.get('latex_content', content)
                tags = result.get('tags', [])
                answer = result.get('answer', '')
                
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
                
                return valid_tags, answer, latex_content
                
            except json.JSONDecodeError as e:
                self.logger.log_error(e, "JSON解析失败 - 自动打标")
                raise e
                
        except Exception as e:
            self.logger.log_error(e, "自动打标失败")
            return [], "自动生成解答失败，请手动输入", content

    def generate_question_variant(self, question: Dict) -> Dict:
        """基于原题生成微调后的题目变体"""
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
            messages=[{"role": "user", "content": prompt}],
            max_tokens=LLM_CONFIG["max_tokens"],
            temperature=LLM_CONFIG["temperature"]
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
    
    def parse_exam_paper(self, markdown_content: str, image_filename_mapping: Dict[str, str] = None) -> List[Dict]:
        """
        解析试卷内容，提取题目
        
        Args:
            markdown_content: OCR识别的markdown内容
            image_filename_mapping: 图片文件名映射关系 {原始文件名: 本地路径}
            
        Returns:
            解析出的题目列表
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
            
            prompt = f"""
请分析以下试卷内容，提取所有题目并格式化为LaTeX格式。

试卷内容：
{markdown_content}{images_info}

请按以下要求处理：
1. 去除OCR识别中的明显噪声和不合理内容
2. 识别并分离每道题目。移除原有题目编号，分值信息。
3. 将题目内容转换为LaTeX格式，选择题选项优先使用enumerate环境。
4. 识别题目中引用的图片（如果有），从可用图片列表中选择合适的图片，严格返回可用的图片文件列表中的文件名，不要新增前缀或移除后缀。
5. 为每道题目生成其所考察的知识点标签并生成解答，标签可以参考：{', '.join(available_tags) if available_tags else '立体几何, 导数题, 极值点偏移, 三角函数, 数列, 概率统计, 解析几何, 函数与方程, 不等式, 向量, 复数, 算法与程序框图'}
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
            
            self.logger.log_llm_prompt(prompt, "试卷解析")
            
            # 调用大语言模型API
            response = self.llm_client.chat.completions.create(
                model=LLM_CONFIG["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=LLM_CONFIG["max_tokens"],
                temperature=LLM_CONFIG["temperature"]
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
                    validated_question = {
                        'question': question.get('question', ''),
                        'image': mapped_images,  # 使用映射后的本地路径
                        'tags': question.get('tags', []),
                        'answer': question.get('answer', '')
                    }
                    
                    if not validated_question['question']:
                        self.logger.log_warning(f"题目 {i+1} 没有题目内容", "试卷解析")
                        continue
                    
                    validated_questions.append(validated_question)
                
                duration = time.time() - start_time
                self.logger.log_performance("试卷解析", duration, f"解析出 {len(validated_questions)} 道题目")
                self.logger.log_question_parsing(len(validated_questions), "试卷解析")
                
                return validated_questions
                
            except json.JSONDecodeError as e:
                self.logger.log_error(e, "JSON解析失败 - 试卷解析")
                return []
                
        except Exception as e:
            self.logger.log_error(e, "解析试卷失败")
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
    
    def search_questions(self, keyword: str, current_user_id: int = None, k: int = 10) -> List[Dict]:
        """
        根据关键词搜索题目（考虑可见性），结合关键词搜索和embedding召回
        
        Args:
            keyword: 搜索关键词
            current_user_id: 当前用户ID
            k: embedding搜索返回的最相似题目数量
            
        Returns:
            匹配的题目列表（合并了关键词搜索和embedding搜索的结果）
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
                            
                            # 将L2距离转换为相似度分数
                            similarities = []
                            similarity_map = {}  # question_id -> similarity，用于后续排序
                            visible_question_dict = {q['id']: q for q in all_visible_questions}
                            
                            for idx, dist in zip(indices[0], distances[0]):
                                if idx < len(visible_question_id_list):
                                    question_id = visible_question_id_list[idx]
                                    if question_id in visible_question_dict:
                                        # L2距离转换为相似度（使用负距离，越小越好）
                                        similarity = -float(dist)
                                        question = visible_question_dict[question_id]
                                        similarities.append((similarity, question))
                                        similarity_map[question_id] = similarity
                            
                            # 按相似度排序，取top k
                            similarities.sort(key=lambda x: x[0], reverse=True)
                            embedding_questions = [q for _, q in similarities[:k]]
                            embedding_similarity_map = similarity_map  # 保存similarity映射
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
            if question['id'] not in result_dict:
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
            'created_at': get_column_value('created_at'),
            'updated_at': get_column_value('updated_at')
        }
