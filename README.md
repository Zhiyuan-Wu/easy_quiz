# 高考题目录入和自动打标系统

一个智能的高考题目管理系统，支持题目录入、自动打标、OCR解析和查询管理功能。

## 新功能特性

### 1. 图片支持
- ✅ 题目支持多张图片上传
- ✅ 图片预览和管理
- ✅ 图片路径存储在数据库中

### 2. OCR试卷解析
- ✅ 上传试卷图片进行OCR识别
- ✅ 自动解析出多道题目
- ✅ 批量打标和生成解答
- ✅ 批量保存到数据库

### 3. 改进的题目管理
- ✅ 修复LaTeX数学公式渲染问题
- ✅ 添加题目删除功能（带确认）
- ✅ 优化布局：紧凑的一行显示
- ✅ 支持题目图片显示

### 4. Google风格搜索
- ✅ 居中搜索框设计
- ✅ 搜索按钮集成在搜索框内
- ✅ 标签筛选在下方独立区域

### 5. 浅色专业风格
- ✅ 整体采用浅色配色方案
- ✅ 简约专业的视觉设计
- ✅ 更好的用户体验

## 技术架构

### 后端
- **Flask**: Web框架
- **SQLite**: 数据库存储
- **OpenAI API**: 大语言模型集成
- **OCR服务**: 图片文字识别

### 前端
- **HTML5**: 语义化结构
- **CSS3**: 现代样式设计
- **JavaScript**: 交互功能
- **MathJax**: 数学公式渲染

### 数据库结构
```sql
CREATE TABLE questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    latex_content TEXT NOT NULL,
    tags TEXT NOT NULL,  -- JSON格式存储标签列表
    reference_answer TEXT,
    source TEXT,
    image TEXT,  -- JSON格式存储图片路径列表
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 安装和运行

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置
编辑 `config.py` 文件，设置：
- 大语言模型API配置
- 数据库路径
- Web服务器配置

### 3. 运行
```bash
python web_server.py
```

访问 `http://127.0.0.1:5001` 使用系统。

## 功能说明

### 1. 录入题目
- 支持LaTeX格式的题目内容
- 多张图片上传和预览
- 自动打标和生成解答
- 手动标签选择

### 2. 试卷解析
- 上传试卷图片
- OCR识别和格式化
- 批量题目处理
- 自动打标和保存

### 3. 查询题目
- Google风格搜索界面
- 关键词搜索
- 标签筛选
- 实时结果展示

### 4. 题目管理
- 题目列表展示
- 数学公式正确渲染
- 删除功能（带确认）
- 紧凑布局设计

## API接口

### 题目管理
- `POST /api/questions` - 添加题目
- `GET /api/questions/search` - 搜索题目
- `GET /api/questions/{id}` - 获取题目详情
- `DELETE /api/questions/{id}` - 删除题目

### 图片上传
- `POST /api/upload` - 上传图片
- `GET /uploads/{filename}` - 获取图片

### OCR解析
- `POST /api/ocr-parse` - 解析试卷

### 自动处理
- `POST /api/questions/auto-tag` - 自动打标

## 配置说明

### 大语言模型配置
```python
LLM_CONFIG = {
    "api_url": "https://api.deepseek.com",
    "api_key": "your-api-key",
    "model": "deepseek-chat",
    "max_tokens": 2000,
    "temperature": 0.7
}
```

### OCR服务配置
确保OCR服务运行在指定地址，支持图片上传和markdown格式返回。

## 注意事项

1. 确保OCR服务正常运行
2. 配置正确的大语言模型API
3. 图片文件会保存在 `uploads` 目录
4. 数据库文件为 `question_database.db`

## 更新日志

### v2.2.1
- ✅ 修复标签筛选在搜索页面不显示的问题
- ✅ 完全移除搜索框的嵌套圆角矩形
- ✅ 统一试卷解析页面宽度与其他页面一致
- ✅ 优化标签渲染逻辑，确保页面切换时正确显示

### v2.2.0
- ✅ 修复默认页签选中状态显示
- ✅ 修复标签筛选显示问题
- ✅ 优化搜索框样式（去除圆角）
- ✅ 改进题目管理页面布局对齐
- ✅ 重新设计试卷解析页面：简约美观，支持拖拽上传
- ✅ 优化页面初始化逻辑

### v2.1.0
- ✅ 改进题目管理页面：紧凑布局，单行显示
- ✅ 试卷解析功能独立页面
- ✅ 打标结果预览功能
- ✅ 默认停留在搜索页面
- ✅ OCR解析自动打标和去噪
- ✅ 选择题选项使用enumerate环境

### v2.0.0
- ✅ 添加图片支持
- ✅ OCR试卷解析功能
- ✅ 改进题目管理界面
- ✅ Google风格搜索
- ✅ 浅色专业风格设计