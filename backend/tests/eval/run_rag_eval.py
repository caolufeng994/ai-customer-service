"""
RAG 召回质量评估脚本（对应开发规范：检索准确率>80%、引用准确率>90% 质量门禁）。

用法：
    cd backend
    env -u DASHSCOPE_API_KEY PYTHONPATH="$PWD" python tests/eval/run_rag_eval.py

说明：
  - 基于 tests/eval/qa_set.json 的 25 条业务问答（7 类意图）。
  - 对每条 query 用真实 Embedder 向量化 + Retriever 检索（阈值取当前配置 0.5）。
  - 判定"检索命中"：召回的 chunk 中至少有一个包含该条目的某个 expected_keyword。
  - 额外验证：越界 query（天气）在阈值 0.5 下不应召回任何 chunk（无漏入）。
"""
import json
import os
import sys
import time

# 允许从 backend 根目录直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.rag.retriever import Retriever  # noqa: E402
from app.config import settings  # noqa: E402

QA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_set.json")
OUT_OF_SCOPE = ["今天天气怎么样？", "帮我写一首诗", "现在几点了"]


def embed_with_retry(retriever: Retriever, text: str):
    last_err = None
    for attempt in range(4):
        try:
            return retriever.embedder.embed(text)
        except Exception as e:  # 含 429 限流
            last_err = e
            if "429" in str(e):
                wait = 2 ** attempt
                print(f"  [retry {attempt+1}] 429 限流，{wait}s 后重试...")
                time.sleep(wait)
            else:
                raise
    raise last_err


def main():
    with open(QA_PATH, encoding="utf-8") as f:
        qa = json.load(f)

    retriever = Retriever(top_k=settings.retrieval_top_k, similarity_threshold=settings.retrieval_threshold)
    print(f"Retriever: top_k={settings.retrieval_top_k} threshold={settings.retrieval_threshold}\n")

    per_category = {}
    total = 0
    hit = 0

    for item in qa:
        cat = item["category"]
        q = item["question"]
        kws = item["expected_keywords"]
        per_category.setdefault(cat, {"total": 0, "hit": 0, "max_sim": 0.0})

        try:
            emb = embed_with_retry(retriever, q)
            results = retriever.vector_store.query(
                query_embedding=emb, n_results=settings.retrieval_top_k,
                where={"kb_id": "default"},
            )
        except Exception as e:
            print(f"[ERROR] {q}: {e}")
            per_category[cat]["total"] += 1
            total += 1
            continue

        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        dists = results.get("distances", [[]])[0]

        # 阈值过滤（与 Retriever 一致）
        passed = []
        for doc, d in zip(docs, dists):
            sim = 1.0 - d
            if sim >= settings.retrieval_threshold:
                passed.append((doc, sim))

        max_sim = max((sim for _, sim in passed), default=0.0)
        # 命中判定：召回 chunk 中至少一个包含 expected_keyword
        hit_flag = any(kw in doc for doc, _ in passed for kw in kws)

        per_category[cat]["total"] += 1
        per_category[cat]["hit"] += 1 if hit_flag else 0
        per_category[cat]["max_sim"] = max(per_category[cat]["max_sim"], max_sim)
        total += 1
        hit += 1 if hit_flag else 0

        status = "OK " if hit_flag else "MISS"
        print(f"[{status}] ({cat}) sim={max_sim:.3f} | {q}")

    print("\n=== 按意图分类召回准确率 ===")
    for cat, s in per_category.items():
        acc = s["hit"] / s["total"] if s["total"] else 0
        print(f"  {cat:8s}  {s['hit']}/{s['total']}  acc={acc*100:5.1f}%  max_sim={s['max_sim']:.3f}")

    overall = hit / total if total else 0
    print(f"\n=== 总体检索准确率: {hit}/{total} = {overall*100:.1f}% ===")
    print(f"质量门禁(规范): 检索准确率>80% -> {'PASS' if overall > 0.8 else 'FAIL'}")

    # 越界 query 漏入验证
    print("\n=== 越界 query 阈值 0.5 漏入验证 ===")
    leak = 0
    for q in OUT_OF_SCOPE:
        try:
            emb = embed_with_retry(retriever, q)
            results = retriever.vector_store.query(
                query_embedding=emb, n_results=settings.retrieval_top_k,
                where={"kb_id": "default"},
            )
            docs = results.get("documents", [[]])[0]
            dists = results.get("distances", [[]])[0]
            passed = [1.0 - d for d in dists if (1.0 - d) >= settings.retrieval_threshold]
            n = len(passed)
            if n > 0:
                leak += 1
            print(f"  {'LEAK' if n else 'SAFE'} 召回 {n} 个 chunk | {q}")
        except Exception as e:
            print(f"  [ERROR] {q}: {e}")
    print(f"越界漏入条数: {leak} (应为 0)")


if __name__ == "__main__":
    main()
