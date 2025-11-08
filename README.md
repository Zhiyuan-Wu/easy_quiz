# Easy Quiz

Easy Quiz 是一个基于AI的高考题目管理工具，旨在利用AI优化学习中的信息效率。核心能力包括：

- 便捷的试题格式化存储、语义检索、排版导出。
- 作业自动批改、错题本管理、报告。
- 推荐算法基于学习路径定制能最快提升成绩的练习题。

## 快速上手

1. 安装环境依赖。
   ```bash
   pip install -r requirements.txt
   ```

2. 填写LLM、VLM、Embedding、推荐算法模型有关的配置信息。
   ```bash
   vim config.py
   ```

3. 启动服务后通过浏览器使用。
   ```bash
   python web_server.py
   ```

## 问题反馈

如有任何问题，欢迎通过Issues反馈。