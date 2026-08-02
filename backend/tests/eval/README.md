# 问答评测集（25 条）

本目录是 `docs/开发流程规范.md` §5/§6 要求的**质量门禁评测集**：维护 25 条问答用例，用于回归与交付前验收。

## 文件

- `qa_set.json`：25 条用例，每条含 `id` / `category` / `question` / `expected_keywords`（用于关键词命中率代理指标）。
- `run_eval.py`：评测脚本。对每条问题调用 `POST /api/chat/send`（或直连 `ChatService`），记录回答并统计指标。
- `results.json`：实跑后生成的评分结果（当前尚未生成，见下方「待办」）。

## 质量门禁（来自开发流程规范）

| 指标 | 门禁阈值 |
|------|---------|
| 检索准确率（retrieval） | > 80% |
| 回答准确率（answer） | > 75% |
| 引用准确率（citation） | > 90% |

## 如何运行

```bash
# 1) 启动服务（真实库 + 已向量化的知识库）
cd backend && python main.py

# 2) 在另一个终端跑评测（默认 http://localhost:8000）
cd backend/tests/eval
python run_eval.py --base-url http://localhost:8000 --token <你的JWT> --out results.json
```

> 评测依赖：① 服务已启动；② 知识库已上传并向量化（`auto_init_kb=true` 或手动上传 seed 文档）；③ 有效的 JWT（免登录模式可去掉 `--token`）。`run_eval.py` 通过 `expected_keywords` 的命中率给出**回答准确率**代理值，检索/引用准确率需在脚本中结合 `sources` 字段进一步计算。

## 待办（当前状态）

- [ ] 实跑服务 + 向量库后执行 `run_eval.py`，生成 `results.json`。
- [ ] 填写真实三项指标，确认是否达到门禁（检索>80% / 回答>75% / 引用>90%）。
- [ ] 当前 `qa_set.json` 为用例初版，可按业务知识库内容持续扩充。
