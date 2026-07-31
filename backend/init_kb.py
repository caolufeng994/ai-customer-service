#!/usr/bin/env python
"""
Seed the RAG knowledge base with the pre-packaged documents in ../seed_docs.

Run it from the backend/ directory (the same working directory as the API
server) so the database connection, ./uploads and ./data/chroma paths line up:

    cd backend
    python init_kb.py            # idempotent: skips docs already ingested
    python init_kb.py --force    # re-ingest all seed docs (clears old vectors)

Prerequisites (same as running the server):
  * MySQL reachable and initialized (see backend/init_db.sql)
  * backend/.env populated (DASHSCOPE_API_KEY, DB_*, EMBEDDING_PROVIDER, ...)

After it finishes, starting the server gives you a knowledge base that already
contains the seed documents, so the retrieval-augmented answer chain can be
tested immediately (no manual upload needed).
"""
import argparse
import os
import sys
from pathlib import Path

# Always operate relative to backend/ so ./uploads and ./data/chroma match the
# API server, regardless of where the command is launched from.
BACKEND_DIR = Path(__file__).resolve().parent
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

from app.core.logging import setup_logging  # noqa: E402
from app.services.init_service import seed_knowledge_base  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize / seed the RAG knowledge base from seed_docs/",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-ingest every seed doc (delete existing vectors first)",
    )
    args = parser.parse_args()

    setup_logging()

    print("=" * 60)
    print("  知识库初始化  seed_docs -> 向量库 (Chroma) + MySQL")
    print("=" * 60)

    result = seed_knowledge_base(force=args.force)

    if result.get("error"):
        print(f"\n[ERROR] {result['error']}")
        print("请确认：1) 已在 backend/ 目录下运行；2) MySQL 已启动并执行过 init_db.sql；"
              "3) backend/.env 已配置 DASHSCOPE_API_KEY。")
        return 1

    seeded = result["seeded"]
    skipped = result["skipped"]
    failed = result["failed"]

    print(f"\n种子目录 : {result['seed_dir']}")
    print(f"新入库   : {len(seeded)} 篇")
    for item in seeded:
        print(f"   + {item['name']}  ({item['chunks']} chunks, {item['chars']} chars)")
    print(f"已跳过   : {len(skipped)} 篇 (已是 ready) -> {', '.join(skipped) if skipped else '无'}")
    if failed:
        print(f"失败     : {len(failed)} 篇")
        for item in failed:
            print(f"   ! {item['name']}: {item.get('error')}")
    if "vector_count" in result:
        print(f"向量总数 : {result['vector_count']}")

    print("\n完成。现在启动服务即可直接测试 RAG 检索问答主链路。")
    if not seeded and not skipped:
        return 1
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
