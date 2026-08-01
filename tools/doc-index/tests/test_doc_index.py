"""doc_index 引擎单元测试（对齐《代码规范》第 6 节：核心方法需单测）。

运行：在 tools/doc-index 目录执行 ``pytest``。
"""
import json
from pathlib import Path

import pytest

from doc_index import DocIndex, DocIndexError, tokenize

INDEX_PATH = Path(__file__).resolve().parent.parent / "doc_index.json"


# --------------------------------------------------------------------------- #
# 分词器
# --------------------------------------------------------------------------- #
def test_tokenize_ascii_lowercases_and_filters_short() -> None:
    terms = tokenize("RAG Pipeline")
    assert "rag" in terms
    assert "pipeline" in terms
    # 长度 < 2 的 ASCII 片段应被丢弃
    assert "a" not in terms


def test_tokenize_cjk_keeps_full_phrase_and_bigrams() -> None:
    terms = tokenize("检索")
    assert "检索" in terms  # 整句短语
    assert "检索" in terms  # 二元文法（此处整句长度 2，与短语重合）
    terms2 = tokenize("向量化")
    assert "向量化" in terms2
    assert "向量" in terms2
    assert "量化" in terms2


def test_tokenize_empty_returns_empty() -> None:
    assert tokenize("") == set()
    assert tokenize("   ") == set()


# --------------------------------------------------------------------------- #
# 加载
# --------------------------------------------------------------------------- #
def test_load_real_index() -> None:
    idx = DocIndex.load(INDEX_PATH)
    assert idx.project
    assert len(idx.entries) == 47


def test_load_missing_file_raises() -> None:
    with pytest.raises(DocIndexError):
        DocIndex.load("nonexistent_index.json")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(DocIndexError):
        DocIndex.load(bad)


def test_load_resolves_relative_paths_to_absolute() -> None:
    idx = DocIndex.load(INDEX_PATH)
    assert all(Path(e.path).is_absolute() for e in idx.entries)


# --------------------------------------------------------------------------- #
# 查询
# --------------------------------------------------------------------------- #
def test_query_returns_relevant_files_for_auth_task() -> None:
    idx = DocIndex.load(INDEX_PATH)
    hits = idx.query("修复登录密码校验", top_k=5)
    assert hits
    paths = [h.path for h in hits]
    # 认证服务必须出现在相关文件前列
    assert any("auth_service.py" in p for p in paths)


def test_query_multi_turn_rag_recalls_full_pipeline() -> None:
    idx = DocIndex.load(INDEX_PATH)
    hits = idx.query("实现 RAG 检索与多轮问答", top_k=8)
    categories = {h.category for h in hits}
    # 广义 RAG 任务应召回核心链路（rag 类）
    assert "rag" in categories


def test_query_threshold_filters_low_relevance() -> None:
    idx = DocIndex.load(INDEX_PATH)
    low = idx.query("实现 RAG 检索", top_k=10, threshold=0.15)
    high = idx.query("实现 RAG 检索", top_k=10, threshold=0.60)
    assert len(high) <= len(low)


def test_query_results_sorted_by_score_desc() -> None:
    idx = DocIndex.load(INDEX_PATH)
    hits = idx.query("聊天流式输出 SSE 处理", top_k=5)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_query_empty_task_returns_empty() -> None:
    idx = DocIndex.load(INDEX_PATH)
    assert idx.query("   ") == []


def test_hit_is_serializable() -> None:
    idx = DocIndex.load(INDEX_PATH)
    hits = idx.query("知识库文档上传与向量化", top_k=3)
    assert hits
    data = hits[0].to_dict()
    assert set(data.keys()) >= {"path", "score", "reason", "category"}


def test_stats_breakdown() -> None:
    idx = DocIndex.load(INDEX_PATH)
    stat = idx.stats()
    assert stat["total"] == 47
    assert "rag" in stat["by_category"]


# --------------------------------------------------------------------------- #
# 索引数据完整性（防止索引与代码脱节）
# --------------------------------------------------------------------------- #
def test_index_entries_have_required_fields() -> None:
    raw = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    for f in raw["files"]:
        assert f.get("path") and f.get("category")
        assert isinstance(f.get("keywords", []), list)
