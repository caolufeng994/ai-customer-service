# 文档索引系统（agent-doc-index）

面向 AI Agent 的**机器可读**文档索引工具：让 agent 按「任务描述 / 关键词」从索引中
精准筛选出*需要读取*的文件，避免盲目把整个代码库塞进上下文。与 `docs/文档索引.md`
（人工可读的文档导航）互补——本工具是结构化的、可被程序匹配检索的版本。

> 本工具是独立于 FastAPI 运行时的 **agent 辅助工具**，不进入 `backend/app` 分层，
> 放在 `tools/` 下，遵循《代码规范》的模块化与目录划分约定。

## 目录结构

```
tools/doc-index/
├── doc_index.py        # 引擎（纯标准库，CLI + 库两用）
├── doc_index.json      # 索引数据：5day 全部 47 个源文件 + 关键文档
├── ruff.toml           # 对齐《代码规范》的 lint 配置
├── README.md
└── tests/
    ├── conftest.py
    └── test_doc_index.py   # pytest 单测
```

## 索引条目字段

| 字段 | 含义 |
|------|------|
| `path` | 文件相对仓库根的路径（引擎加载时解析为绝对路径） |
| `category` | 分类（config / core / model / rag / service / api / schema / utils / doc） |
| `description` | 一句话功能概述 |
| `use_cases` | 适用场景（自然语言短语），用于相关性匹配 |
| `keywords` | 关键词（精确匹配词），用于相关性匹配 |

相关性得分：`0.40*关键词 + 0.30*场景 + 0.20*概述 + 0.10*路径`，仅返回 `score ≥ threshold` 的文件。

## 用法

```bash
# 在仓库根目录执行（默认 base-dir 自动解析为仓库根，输出绝对路径）
cd 5day
python tools/doc-index/doc_index.py query "实现 RAG 检索与多轮问答" --topk 5
python tools/doc-index/doc_index.py query "修复登录密码校验" --threshold 0.15 --json
python tools/doc-index/doc_index.py paths "聊天流式输出 SSE"        # 仅打印路径，便于管道
python tools/doc-index/doc_index.py stats

# 库用法
from doc_index import DocIndex
idx = DocIndex.load("tools/doc-index/doc_index.json")
for hit in idx.query("实现 RAG 检索", top_k=5):
    print(hit.path, hit.score, hit.reason)   # agent 仅 read(hit.path)
```

## 规范遵循（对齐《代码规范》《开发流程规范》）

- **命名/类型/注释**：函数 `snake_case`、类 `PascalCase`；全函数类型注解；公开类/方法
  与模块首行均有 docstring。
- **日志**：统一 `logging.getLogger(__name__)`，无 `print()` 调试输出。
- **异常处理**：自定义 `DocIndexError` 替代裸 `Exception`，CLI 层优雅退出（退出码 2）。
- **静态检查**：`ruff.toml` 与后端一致（行宽 100，E/F/I/N/W/UP）；`black` 兼容（双引号）。
- **测试**：`tests/test_doc_index.py` 覆盖分词、加载、查询排序/阈值/相关性、错误路径、
  索引完整性，符合「核心方法需单测」要求。

```bash
cd tools/doc-index
python -m ruff check .      # 0 错误
python -m pytest -q         # 全部通过
```

## 维护

- 项目新增/重构文件时，在 `doc_index.json` 的 `files` 中追加一条（path/category/description/
  use_cases/keywords）。
- 换项目服务：替换 `doc_index.json` 即可，引擎无需改动。
