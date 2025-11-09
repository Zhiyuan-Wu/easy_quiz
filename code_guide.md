# Easy Quiz 项目代码说明文档

## 目录

1. [整体功能架构](#整体功能架构)
2. [代码目录结构](#代码目录结构)
3. [主要功能的实现原理](#主要功能的实现原理)
4. [其他值得关注的信息](#其他值得关注的信息)

---

## 整体功能架构

### 系统概述

Easy Quiz 是一个基于AI的高考题目管理工具，旨在利用AI优化学习中的信息效率。系统采用前后端分离的Web架构，后端使用Flask框架，前端使用原生JavaScript和MathJax进行数学公式渲染。

### 核心功能模块

#### 1. 题目管理模块 (`question_manager.py`)
- **题目存储**：支持LaTeX格式的题目内容、标签、参考答案、图片等
- **自动打标**：使用LLM自动识别知识点并生成标签
- **语义搜索**：结合关键词搜索和Embedding向量搜索
- **题目变体生成**：基于原题生成AI变体

#### 2. 学生管理模块 (`student_manager.py`)
- **学生信息管理**：学生基本信息、平均分缓存
- **作业批改**：OCR识别学生作业，LLM自动批改
- **学习报告生成**：基于错题历史生成个性化学习报告
- **题目推荐**：根据薄弱知识点推荐练习题

#### 3. OCR解析模块 (`ocr_client.py`, `web_server.py`)
- **试卷识别**：支持图片和PDF格式的试卷OCR识别
- **题目提取**：使用LLM从OCR文本中提取结构化题目
- **图片处理**：自动提取和保存题目中的图片

#### 4. 试卷导出模块 (`export_renderer.py`)
- **多格式支持**：LaTeX、Word (DOCX)、PDF
- **专业排版**：按题型分组、自动编号、答案可选
- **公式渲染**：LaTeX公式转换为Word格式的Office Math

#### 5. 系统管理模块 (`system_manager.py`)
- **用户管理**：注册、登录、密码管理
- **标签管理**：标签的创建、使用计数
- **导出历史**：记录用户的试卷导出记录

### 技术架构

```
┌─────────────────────────────────────────┐
│          Web前端 (HTML/JS)              │
│    - 题目查询界面                        │
│    - OCR上传界面                         │
│    - 学生管理界面                        │
│    - 试卷导出界面                        │
└─────────────────┬───────────────────────┘
                  │ HTTP/JSON
┌─────────────────▼───────────────────────┐
│      Flask Web服务器 (web_server.py)     │
│    - 路由处理                            │
│    - 会话管理                            │
│    - 文件上传                            │
└─────┬───────────┬───────────┬──────────┘
      │           │           │
┌─────▼───┐  ┌────▼────┐  ┌───▼────────┐
│题目管理 │  │学生管理 │  │系统管理    │
│Manager  │  │Manager  │  │Manager    │
└────┬────┘  └────┬────┘  └───┬────────┘
     │            │           │
┌────▼────────────▼───────────▼──────┐
│          SQLite 数据库              │
│  - questions.db (题目)              │
│  - students.db (学生)               │
│  - homework_results.db (作业)       │
│  - system.db (用户/标签)            │
│  - embeddings_cache.db (向量缓存)   │
└────────────────────────────────────┘
     │            │           │
┌────▼────────────▼───────────▼──────┐
│      外部服务                        │
│  - LLM API (DeepSeek)               │
│  - OCR服务 (DeepSeek OCR)           │
│  - Embedding服务 (Qwen)             │
│  - LaTeX编译服务                    │
└────────────────────────────────────┘
```

---

## 代码目录结构

### 主要Python模块

```
question_tagging/
├── web_server.py              # Flask Web服务器主入口
├── question_manager.py        # 题目管理核心类
├── student_manager.py         # 学生与学情管理
├── system_manager.py          # 系统管理（用户、标签）
├── export_renderer.py         # 试卷导出渲染器
├── ocr_client.py              # OCR服务客户端
├── utils.py                   # 工具函数（PDF转换、图片处理等）
├── logger.py                  # 日志记录器
└── config.py                  # 配置文件
```

### 前端文件

```
templates/
├── index.html                 # 主页面
├── login.html                 # 登录页面
└── user_profile.html          # 用户中心

static/
├── app-core.js                # 核心应用逻辑
├── questions.js               # 题目管理相关
├── ocr.js                     # OCR上传相关
├── students.js                # 学生管理相关
├── cart.js                    # 试卷生成购物车
├── profile.js                 # 用户资料
├── help.js                    # 帮助系统
├── config.js                  # 前端配置
└── style.css                  # 样式文件
```

### 数据存储

```
data/
├── students.db                # 学生信息数据库
├── homework_results.db        # 作业批改结果数据库
└── embeddings_cache.db        # Embedding向量缓存

question_database.db           # 题目数据库
system.db                      # 系统数据库（用户、标签）
```

### 资源文件

```
resources/
├── exam_template.tex          # LaTeX试卷模板
└── exam-zh.cls                # LaTeX文档类

uploads/
├── upload_images/             # 用户上传的图片
├── ocr_images/                # OCR识别的图片
└── homework_submissions/      # 学生作业上传

latex_results/                 # LaTeX编译输出目录
exports/                       # 导出的试卷文件
```

---

## 主要功能的实现原理

### 1. 题目管理功能

#### 1.1 题目存储结构

题目数据存储在SQLite数据库中，主要字段包括：
- `latex_content`: LaTeX格式的题目内容
- `tags`: JSON格式的标签列表
- `reference_answer`: 参考答案
- `image`: JSON格式的图片路径列表
- `user_id`: 上传用户ID
- `visibility`: 可见范围（public/private）
- `question_type`: 题目类型（选择题/填空题/解答题）

#### 1.2 自动打标机制

**实现位置**: `question_manager.py::auto_tag_and_answer()`

**流程**:
1. 获取系统中已有的标签列表作为参考
2. 构建包含任务描述的提示词，要求LLM：
   - 将题目格式化为LaTeX格式
   - 识别知识点并生成标签
   - 生成详细参考解答
   - 判断题目类型
3. 调用LLM API获取结构化JSON响应
4. 解析响应并验证标签，自动添加到标签库

**关键代码片段**:
```python
prompt = f"""
请分析以下高考数学题目，并完成以下任务：
1. 将题目内容格式化为标准的LaTeX格式
2. 请给这个题目所涉及的知识点打上几个标签
3. 生成详细的参考解答
4. 判断题目类型并返回 question_type 字段
...
"""
response = self.llm_client.chat.completions.create(
    model=LLM_CONFIG["model"],
    messages=[{"role": "user", "content": prompt}]
)
```

#### 1.3 语义搜索机制

**实现位置**: `question_manager.py::search_questions()`

**搜索策略**:
1. **关键词搜索**：在题目内容和来源中搜索关键词（SQL LIKE查询）
2. **Embedding搜索**：
   - 将查询关键词转换为Embedding向量
   - 使用FAISS构建临时索引，搜索最相似的题目
   - 计算余弦相似度作为排序依据
3. **结果合并**：合并两种搜索结果，去重并按相关性排序
4. **异步Embedding计算**：对于缺失Embedding的题目，后台异步计算并缓存

**Embedding缓存机制**:
- 使用独立的SQLite数据库存储Embedding向量
- 题目更新时自动刷新对应的Embedding
- 异步计算避免阻塞搜索请求

**关键代码片段**:
```python
# 构建查询向量
query_text = self._get_detailed_instruct(task, keyword)
query_embeddings = self.ocr_client.get_embeddings([query_text])
query_embedding_array = np.array([query_embeddings[0]], dtype='float32')

# 构建FAISS索引
embeddings_array = np.array(visible_embeddings, dtype='float32')
temp_index = faiss.IndexFlatL2(dimension)
temp_index.add(embeddings_array)

# 搜索最相似的题目
distances, indices = temp_index.search(query_embedding_array, k_search)
```

### 2. 学生管理与作业批改

#### 2.1 作业批改流程

**实现位置**: `web_server.py::parse_student_homework()`, `student_manager.py::parse_homework_ocr()`

**流程**:
1. **文件上传**：接收学生上传的作业图片或PDF
2. **OCR识别**：
   - PDF文件先转换为图片（每页一张）
   - 调用OCR服务识别每页内容
   - 合并多页Markdown文本
3. **题目匹配**：根据关联的试卷ID获取原始题目列表
4. **LLM批改**：
   - 构建包含原题和学生答案的提示词
   - LLM匹配学生答案与原题，给出得分和反馈
   - 返回结构化的批改结果
5. **结果保存**：将批改结果保存到数据库

**提示词设计**:
```python
prompt = f"""
你是一名严格的数学阅卷教师。请根据以下原始试卷题目，与学生手写作业的OCR识别文本进行匹配和批改。

评分要求：
1. 请匹配学生答案与原题号，忽略OCR文本中与本试卷无关的内容
2. 得分区间为0到1，可保留两位小数
3. feedback字段用于指出学生不理解的知识点或建议
...
"""
```

#### 2.2 学习报告生成

**实现位置**: `student_manager.py::generate_learning_report()`

**流程**:
1. **数据收集**：获取指定时间窗口内的作业历史记录
2. **数据筛选**：按得分从低到高排序，取前N条错题
3. **LLM分析**：
   - 构建包含错题记录的提示词
   - LLM分析错题分布、薄弱知识点
   - 生成学习计划建议
4. **结果缓存**：将报告缓存到学生记录中，避免重复生成

**报告结构**:
```json
{
    "mistake_distribution": "错题分布概述",
    "knowledge_points": ["知识点1", "知识点2"],
    "study_plan": [
        {"step": 1, "topic": "主题", "action": "建议"}
    ]
}
```

#### 2.3 题目推荐算法

**实现位置**: `student_manager.py::build_recommendations()`

**流程**:
1. **获取薄弱点**：从学习报告中提取需要补强的知识点
2. **搜索题目**：对每个知识点进行语义搜索，找到相关题目
3. **结果聚合**：
   - 合并多个知识点的搜索结果
   - 按相似度得分排序
   - 记录推荐理由（来自哪些知识点）
4. **返回Top N**：返回最相关的N道题目

### 3. OCR试卷解析

#### 3.1 试卷识别流程

**实现位置**: `web_server.py::ocr_parse()`

**流程**:
1. **文件处理**：
   - 支持图片（PNG/JPG）和PDF格式
   - PDF转换为多张图片（每页一张）
2. **OCR识别**：
   - 逐页调用OCR服务
   - OCR返回Markdown格式的文本和提取的图片
3. **图片保存**：
   - 将OCR返回的图片保存到本地
   - 建立文件名映射关系
   - 更新Markdown中的图片引用路径
4. **题目提取**：
   - 调用LLM解析Markdown内容
   - 提取结构化题目（题面、图片、标签、类型、答案）
   - 批量生成参考答案（可选）

#### 3.2 题目提取提示词设计

**关键要求**:
- 去除OCR噪声
- 识别并分离每道题目
- 转换为标准LaTeX格式
- 识别并映射图片引用
- 生成知识点标签
- 判断题目类型
- 生成参考解答（可选）

**批量答案生成**:
- 对于PDF多页试卷，支持批量生成答案以提高效率
- 使用线程池并发处理多个题目批次
- 每个批次包含N道题目（可配置）

### 4. 试卷导出功能

#### 4.1 LaTeX导出

**实现位置**: `export_renderer.py::render_latex()`

**流程**:
1. **题目分组**：按题目类型（选择题、填空题、解答题）分组
2. **模板填充**：
   - 读取LaTeX模板文件
   - 按题型生成分组标题（包含分值信息）
   - 构建题目块（题面、图片、答案）
3. **图片处理**：
   - 复制题目图片到输出目录
   - 更新LaTeX中的图片路径
4. **文件生成**：生成.tex文件和依赖的.cls文件

#### 4.2 Word导出

**实现位置**: `export_renderer.py::render_docx()`

**关键技术**:
1. **LaTeX公式转换**：
   - 使用`latex2mathml`库将LaTeX转换为MathML
   - 将MathML转换为Word的Office Math XML格式
   - 支持内联公式和块级公式
2. **内容解析**：
   - 解析LaTeX内容，分离文本和公式
   - 处理enumerate环境（选择题选项）
   - 处理table环境（表格）
3. **格式处理**：
   - 替换`\underline{\hspace{1cm}}`为下划线
   - 处理图片插入和布局
   - 设置段落格式和缩进

#### 4.3 PDF导出

**实现位置**: `export_renderer.py::render_pdf()`

**流程**:
1. 生成LaTeX内容（带元数据）
2. 将图片转换为base64编码
3. 调用LaTeX编译服务API
4. 接收编译后的PDF（base64编码）
5. 解码并保存PDF文件

### 5. 数据库设计

#### 5.1 题目表 (questions)

```sql
CREATE TABLE questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latex_content TEXT NOT NULL,
    tags TEXT NOT NULL,  -- JSON格式
    reference_answer TEXT,
    source TEXT,
    image TEXT,  -- JSON格式
    user_id INTEGER,
    visibility TEXT DEFAULT 'public',
    question_type TEXT DEFAULT '解答题',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

#### 5.2 学生表 (students)

```sql
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    name TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    cached_average_score REAL,
    cached_average_window_days INTEGER,
    cached_average_updated_at TEXT,
    cached_report_json TEXT,
    cached_report_generated_at TEXT,
    cached_report_history_timestamp TEXT,
    latest_history_timestamp TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(student_id, user_id)
)
```

#### 5.3 作业结果表 (homework_results)

```sql
CREATE TABLE homework_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uid TEXT NOT NULL,
    student_id TEXT NOT NULL,
    student_name TEXT NOT NULL,
    export_id INTEGER NOT NULL,
    paper_title TEXT,
    question_id INTEGER,
    question_number TEXT,
    original_question TEXT,
    reference_answer TEXT,
    student_answer TEXT,
    score REAL,
    feedback TEXT,
    raw_payload TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

#### 5.4 Embedding缓存表 (embeddings)

```sql
CREATE TABLE embeddings (
    question_id INTEGER PRIMARY KEY,
    embedding TEXT NOT NULL,  -- JSON格式的向量
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

---

## 其他值得关注的信息

### 1. 缓存机制

#### 1.1 Embedding缓存
- **目的**：避免重复计算题目的Embedding向量
- **存储**：独立的SQLite数据库
- **更新策略**：题目更新时自动刷新
- **异步计算**：缺失的Embedding在后台线程中计算，不阻塞主流程

#### 1.2 平均分缓存
- **目的**：避免频繁计算学生平均分
- **缓存字段**：`cached_average_score`, `cached_average_updated_at`
- **失效条件**：
  - 有新的作业记录时
  - 缓存超过TTL时间（默认6小时）

#### 1.3 学习报告缓存
- **目的**：避免重复生成学习报告
- **缓存字段**：`cached_report_json`, `cached_report_generated_at`
- **失效条件**：有新的作业记录时

### 2. 异步任务处理

#### 2.1 Embedding异步计算
**实现位置**: `question_manager.py::_compute_missing_embeddings_async()`

**机制**:
- 使用线程锁防止重复计算
- 维护正在处理的question_id集合
- 后台线程批量计算缺失的Embedding
- 计算完成后更新缓存

**关键代码**:
```python
self._async_task_lock = threading.Lock()
self._processing_question_ids = set()

def compute_task():
    # 后台计算任务
    for question_id in question_ids:
        if question_id not in self.embedding_cache:
            embeddings = self.ocr_client.get_embeddings([question_text])
            self._save_embedding_to_cache(question_id, embeddings[0])

thread = threading.Thread(target=compute_task)
thread.daemon = True
thread.start()
```

### 3. 错误处理与日志

#### 3.1 日志系统
**实现位置**: `logger.py`

**日志类型**:
- OCR结果日志
- LLM请求/响应日志
- 数据库操作日志
- 图片处理日志
- 题目解析日志
- 用户操作日志
- 错误和警告日志
- 性能统计日志

#### 3.2 错误处理策略
- **详细错误记录**：`log_error_with_details()`函数记录完整的错误信息，包括traceback和变量值
- **优雅降级**：OCR失败、LLM失败时返回友好的错误信息
- **数据验证**：在关键操作前验证输入数据

### 4. 安全性考虑

#### 4.1 用户认证
- 使用Flask Session管理用户登录状态
- 密码使用SHA256哈希存储
- 登录保护装饰器`@login_required`

#### 4.2 权限控制
- 题目可见性控制：`public`（所有人可见）或`private`（仅创建者可见）
- 题目修改/删除权限检查
- 学生数据隔离（按user_id过滤）

#### 4.3 文件安全
- 使用`secure_filename()`防止路径遍历
- 文件类型白名单验证
- 文件大小限制（16MB）

### 5. 性能优化

#### 5.1 数据库索引
- 题目表：tags、source、user_id、visibility索引
- 学生表：updated_at、latest_history_timestamp、user_id索引
- 作业结果表：student_id、session_uid、created_at索引

#### 5.2 批量处理
- PDF试卷解析时批量生成答案（可配置批次大小）
- 使用线程池并发处理多个答案生成任务

#### 5.3 向量搜索优化
- 使用FAISS进行高效的向量相似度搜索
- 仅对可见题目构建索引，减少计算量

### 6. 配置管理

**配置文件**: `config.py`

**主要配置项**:
- **数据库路径**：各数据库文件路径
- **LLM配置**：API地址、密钥、模型名称
- **OCR配置**：OCR服务地址
- **Embedding配置**：向量服务地址和模型
- **LaTeX编译配置**：编译服务地址和命令
- **分析窗口配置**：学习报告的时间窗口、题目数量限制等

### 7. 依赖服务

#### 7.1 LLM服务
- **用途**：自动打标、解答生成、作业批改、学习报告生成、题目变体生成
- **接口**：OpenAI兼容的Chat API
- **配置**：DeepSeek Chat模型

#### 7.2 OCR服务
- **用途**：识别试卷图片和PDF中的文字和公式
- **接口**：HTTP POST，返回Markdown格式文本和提取的图片
- **配置**：DeepSeek OCR服务

#### 7.3 Embedding服务
- **用途**：生成文本的向量表示，用于语义搜索
- **接口**：HTTP POST，接收文本列表，返回向量列表
- **配置**：Qwen3 Embedding模型

#### 7.4 LaTeX编译服务
- **用途**：将LaTeX源码编译为PDF
- **接口**：HTTP POST，接收LaTeX内容和依赖文件，返回PDF（base64编码）
- **配置**：自定义编译服务

### 8. 前端技术栈

- **MathJax**：数学公式渲染
- **原生JavaScript**：无框架依赖，轻量级
- **Font Awesome**：图标库
- **响应式设计**：适配不同屏幕尺寸

### 9. 数据流转示例

#### 9.1 题目录入流程
```
用户输入题目文本
    ↓
调用自动打标API
    ↓
LLM分析并返回：标签、LaTeX、答案、类型
    ↓
保存到数据库
    ↓
异步计算Embedding（后台）
    ↓
保存Embedding到缓存
```

#### 9.2 作业批改流程
```
上传作业图片/PDF
    ↓
OCR识别 → Markdown文本
    ↓
获取关联试卷的题目列表
    ↓
LLM匹配和批改
    ↓
保存批改结果到数据库
    ↓
更新学生平均分缓存（异步）
    ↓
返回批改结果给前端
```

#### 9.3 试卷导出流程
```
选择题目列表
    ↓
按题型分组
    ↓
生成LaTeX/Word/PDF内容
    ↓
处理图片和公式
    ↓
保存导出历史
    ↓
返回文件给用户下载
```

---

## 总结

Easy Quiz 项目是一个功能完整、架构清晰的AI辅助教育系统。主要特点包括：

1. **模块化设计**：各功能模块职责清晰，易于维护和扩展
2. **AI能力集成**：充分利用LLM、OCR、Embedding等AI技术
3. **性能优化**：缓存机制、异步任务、批量处理等优化策略
4. **用户体验**：支持多种格式导出、语义搜索、个性化推荐
5. **可扩展性**：配置化设计，易于适配不同的AI服务

项目代码质量较高，注释详细，错误处理完善，适合作为AI教育应用的参考实现。

