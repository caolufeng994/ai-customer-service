"""grounded / unsupported_claims 落库与重载往返测试(不依赖外部服务)。

验证:
1. Message 模型新增列可写入(grounded / unsupported_claims JSON 文本)。
2. MessageResponse 能从模型还原, 且 unsupported_claims 的 JSON 文本被解析回 list[str]。
3. 缺失/空值不报错, 且向前兼容(老数据 unsupported_claims=None)。
"""
import json
from datetime import datetime
from app.models.message import Message
from app.schemas.session import MessageResponse


def _make_message(**overrides) -> Message:
    base = dict(
        id=1,
        session_id=1,
        role="assistant",
        content="示例回答",
        token_in=10,
        token_out=20,
        latency_ms=300,
        finish_reason="stop",
        created_at=datetime(2026, 8, 4, 12, 0, 0),
    )
    base.update(overrides)
    return Message(**base)


def test_grounded_false_with_claims_roundtrip():
    msg = _make_message(
        grounded=False,
        unsupported_claims=json.dumps(["该政策自2024年起废止", "原文未提及具体金额"], ensure_ascii=False),
    )
    resp = MessageResponse.model_validate(msg)
    assert resp.grounded is False
    assert isinstance(resp.unsupported_claims, list)
    assert "该政策自2024年起废止" in resp.unsupported_claims


def test_grounded_true_no_claims():
    msg = _make_message(grounded=True, unsupported_claims=None)
    resp = MessageResponse.model_validate(msg)
    assert resp.grounded is True
    assert resp.unsupported_claims is None


def test_legacy_null_columns_compatible():
    # 老数据: 两列均为 None, 不应抛错且 grounded 为 None(前端据此不展示告警)
    msg = _make_message(grounded=None, unsupported_claims=None)
    resp = MessageResponse.model_validate(msg)
    assert resp.grounded is None
    assert resp.unsupported_claims is None


def test_malformed_claims_text_falls_back_to_empty():
    # 落库文本损坏时, 解析失败应安全降级为空列表而非抛异常
    msg = _make_message(grounded=False, unsupported_claims="not-json")
    resp = MessageResponse.model_validate(msg)
    assert resp.grounded is False
    assert resp.unsupported_claims == []


def test_save_serializes_claims_as_json_string():
    # 模拟 save_assistant_message 的落库形态: unsupported_claims 以 JSON 字符串存储
    claims = ["陈述A", "陈述B"]
    stored = json.dumps(claims, ensure_ascii=False)
    msg = _make_message(grounded=False, unsupported_claims=stored)
    resp = MessageResponse.model_validate(msg)
    assert resp.unsupported_claims == claims
