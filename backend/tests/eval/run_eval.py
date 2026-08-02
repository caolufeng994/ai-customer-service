"""
问答评测脚本（25 条用例）

对 qa_set.json 中的每条问题调用后端 `POST /api/chat/send`，记录回答并基于
`expected_keywords` 计算关键词命中率，作为「回答准确率」的代理指标，最终汇总
检索 / 回答 / 引用三项门禁是否达标。

运行前请确保：
  1) 后端已启动（默认 http://localhost:8000）
  2) 知识库已上传并向量化
  3) 提供有效的 JWT（--token）；若服务开启免登录模式可省略

用法：
  python run_eval.py --base-url http://localhost:8000 --token <JWT> --out results.json
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_cases(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def call_chat(base_url: str, token: str | None, question: str, session_id: int | None = None):
    """Call POST /api/chat/send and return (content, sources). Requires httpx."""
    import httpx

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"message": question}
    if session_id is not None:
        payload["session_id"] = session_id

    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{base_url}/api/chat/send", json=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        data = body.get("data", {})
        return data.get("content", ""), data.get("sources", [])


def evaluate(cases: list, base_url: str, token: str | None) -> dict:
    results = []
    hit_total = 0
    hit_cases = 0

    for case in cases:
        q = case["question"]
        keywords = case.get("expected_keywords", [])
        try:
            content, sources = call_chat(base_url, token, q)
        except Exception as e:  # noqa: BLE001 - 评测脚本需容忍单条失败
            content, sources = f"<error: {e}>", []

        # 关键词命中率（回答准确率代理）
        if keywords:
            hits = sum(1 for kw in keywords if kw.lower() in content.lower())
            ratio = hits / len(keywords)
        else:
            hits, ratio = 0, 0.0
        hit_total += ratio
        if ratio >= 0.5:  # 半数关键词命中视为该条通过
            hit_cases += 1

        results.append({
            "id": case["id"],
            "category": case.get("category"),
            "question": q,
            "answer": content,
            "sources": sources,
            "keyword_hit_ratio": round(ratio, 2),
        })

    n = len(cases)
    answer_acc = hit_total / n if n else 0.0
    answer_pass_rate = hit_cases / n if n else 0.0

    summary = {
        "total": n,
        "answer_accuracy_proxy": round(answer_acc, 3),   # 平均关键词命中率
        "answer_pass_rate": round(answer_pass_rate, 3),  # 单条过半命中占比
        "gates": {
            "retrieval_accuracy": "> 0.80 (需结合 sources 人工/脚本判定)",
            "answer_accuracy_gate": 0.75,
            "citation_accuracy": "> 0.90 (需结合 sources 人工/脚本判定)",
        },
        "answer_meets_gate": answer_acc > 0.75,
    }
    return {"summary": summary, "cases": results}


def main():
    parser = argparse.ArgumentParser(description="Run 25-question eval set against the chat API")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", default=None, help="JWT bearer token (omit if no-auth mode)")
    parser.add_argument("--cases", default=os.path.join(HERE, "qa_set.json"))
    parser.add_argument("--out", default=os.path.join(HERE, "results.json"))
    args = parser.parse_args()

    try:
        import httpx  # noqa: F401
    except ImportError:
        print("ERROR: httpx is required. Install with: pip install httpx", file=sys.stderr)
        sys.exit(2)

    cases = load_cases(args.cases)
    print(f"Loaded {len(cases)} cases. Calling {args.base_url} ...")
    report = evaluate(cases, args.base_url, args.token)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    s = report["summary"]
    print(f"Answer accuracy (proxy): {s['answer_accuracy_proxy']}  | meets >0.75 gate: {s['answer_meets_gate']}")
    print(f"Per-case pass rate:       {s['answer_pass_rate']}")
    print(f"Report written to: {args.out}")


if __name__ == "__main__":
    main()
