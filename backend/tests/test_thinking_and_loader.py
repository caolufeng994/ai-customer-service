"""
回归测试:编码健壮性 + Agent 思维链(CoT)事件流。

不依赖数据库,纯单元级验证:
1. loader 文本读取在 utf-8 / gbk / 损坏混合编码 三种情况下都不应抛出
   UnicodeDecodeError(即修复启动期 'gbk' codec 崩溃)。
2. ChatService._stream_thinking 产出符合约定的 SSE 事件序列,且思考流异常时
   能优雅降级(thinking_end 仍发出,不向外抛异常)。
"""
import os
import tempfile

import pytest

from app.rag.loader import DocumentLoader
from app.services.chat_service import ChatService


# ---------------------------------------------------------------------------
# 1) loader 编码回退链
# ---------------------------------------------------------------------------

def _write_bytes(data: bytes) -> str:
    p = tempfile.mktemp(suffix=".txt")
    with open(p, "wb") as f:
        f.write(data)
    return p


def test_loader_reads_utf8():
    p = _write_bytes("产品介绍：客户服务须知。".encode("utf-8"))
    try:
        assert DocumentLoader.load_txt(p) == "产品介绍：客户服务须知。"
    finally:
        os.remove(p)


def test_loader_reads_gbk():
    # Windows 记事本另存的 ANSI/GBK 文档
    p = _write_bytes("产品介绍：客户服务须知。".encode("gbk"))
    try:
        assert DocumentLoader.load_txt(p) == "产品介绍：客户服务须知。"
    finally:
        os.remove(p)


def test_loader_does_not_crash_on_garbled_encoding():
    """曾经:损坏/混合编码文件会让 gbk 回退抛出 UnicodeDecodeError 并导致启动崩溃。
    修复后:utf-8 -> gbk -> latin-1 兜底,latin-1 永不抛编码错误。"""
    # 0xAC 作为裸字节:既不是合法 utf-8 续字节,也无法在 gbk 中配对尾字节。
    p = _write_bytes(b"hello \xac\x00 world \xad\xff end")
    try:
        # 不应抛出 UnicodeDecodeError
        text = DocumentLoader.load_txt(p)
        assert isinstance(text, str)
        assert len(text) > 0
    finally:
        os.remove(p)


# ---------------------------------------------------------------------------
# 2) CoT 思维链事件流
# ---------------------------------------------------------------------------

class _FakeLLM:
    def chat_stream(self, messages, temperature=0.7, max_tokens=1000):
        for chunk in ["我", "在理解", "用户的问题", "并检索知识库。"]:
            yield chunk


class _BrokenLLM:
    def chat_stream(self, messages, temperature=0.7, max_tokens=1000):
        raise RuntimeError("llm down")


def test_stream_thinking_event_sequence():
    events = list(ChatService._stream_thinking(_FakeLLM(), "如何退货?", "知识库内容", None))
    types = [e["type"] for e in events]
    assert types[0] == "thinking_start"
    assert types[-1] == "thinking_end"
    # 中间应为若干 thought 块
    thought_chunks = [e for e in events if e["type"] == "thought"]
    assert len(thought_chunks) == 4
    assert thought_chunks[0]["data"] == "我"
    assert events[0]["data"] == {"status": "thinking"}
    assert events[-1]["data"] == {"status": "answering"}


def test_stream_thinking_degrades_gracefully():
    """思考流异常时仍发出 thinking_end,且不向外抛异常。"""
    events = list(ChatService._stream_thinking(_BrokenLLM(), "hi", "", None))
    assert events[0]["type"] == "thinking_start"
    assert events[-1]["type"] == "thinking_end"
    # 没有 thought 块(调用立即失败),但流程完整不会崩。
    assert all(e["type"] != "thought" for e in events)
