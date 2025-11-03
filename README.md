# 智能题库管理与试卷生成平台

## 项目概览

系统面向一线教师与教研团队，提供题目采集、自动解析、题型识别与多格式试卷导出的一体化工作流。平台内置题型分类、标签体系和高质量排版模版，可在本地完成题库构建与试卷生产，全流程可追踪、可回溯。

## 核心能力

- **题目结构化管理**：支持文本、LaTeX 与多图混排，题目类型自动识别并可人工校正。
- **AI 辅助录入**：调用大模型完成标签建议、参考解答生成以及题面 LaTeX 格式化。
- **试卷解析**：OCR 上传整张试卷，自动拆题、还原图片并写回题库。
- **多格式导出**：一键生成 PDF / DOCX / LaTeX，排版遵循教考规范，解答区自动加框强调。
- **语义检索**：关键词 + Embedding 双通道搜索，支持标签过滤与可见性控制。

## 技术栈

- **后端**：Flask · SQLite · OpenAI Chat Completions · 自建 OCR 服务
- **前端**：原生 HTML/CSS/JavaScript · MathJax 公式渲染
- **文档渲染**：LaTeX（exam-zh 模板）· python-docx
- **向量检索**：本地 SQLite 索引 + FAISS 临时向量搜索

## 目录结构

```text
workspace/
├─ web_server.py        # Flask 入口与 API 层
├─ question_manager.py  # 题目增删改查、AI 与检索逻辑
├─ export_renderer.py   # 试卷导出（LaTeX / PDF / DOCX）
├─ templates/           # 前端模版（Jinja2）
├─ static/              # 样式、脚本与前端配置
├─ resources/           # LaTeX 模板与类文件
├─ config.py            # 系统配置（数据库、API、OCR 等）
└─ requirements.txt     # Python 依赖
```

## 快速上手

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **配置参数**（`config.py`）
   - LLM 与 OCR 服务地址 / 密钥
   - Web 服务端口、密钥
   - 题库与系统数据库路径

3. **启动服务**
   ```bash
   python web_server.py
   ```
   登录后即可通过浏览器访问 `http://127.0.0.1:5001`。

## 常用工作流

- **录入单题**：填写题面 → 上传配图 → 调用 AI 自动排版/打标 → 选择题型与标签 → 保存。
- **批量解析试卷**：上传整页图像 → 等待 OCR+LLM 拆题 → 勾选保留题目 → 批量写入题库。
- **组卷导出**：将题目加入“试卷购物车” → 选择导出模式与格式 → 获得本地 PDF / DOCX / LaTeX 文件。
- **题库检索**：关键词搜索或标签过滤，支持私有题可见性与 Embedding 召回补全。

## 运维提示

- 向量索引采用 SQLite 存储，位于 `data/embeddings_cache.db`，首次运行会自动从旧版 JSONL 缓存迁移。
- 导出文件与上传图片默认保存在 `uploads/` 目录，注意定期备份与清理。
- 日志输出至根目录 `log.txt`，可用于排查 OCR / LLM / 导出过程中的异常。

欢迎根据实际教研场景扩展题型、模板或接入自定义模型。
