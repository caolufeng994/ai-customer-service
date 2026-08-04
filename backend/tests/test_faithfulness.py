"""
Unit tests for FaithfulnessChecker (防编造自检)
"""
import pytest
from app.rag.faithfulness import FaithfulnessChecker, FaithfulnessResult


class _FakeLLM:
    """可控的假 LLM 客户端, 仅实现 chat(...) 接口。"""
    def __init__(self, reply, raise_error=False):
        self.reply = reply
        self.raise_error = raise_error
        self.last_messages = None

    def chat(self, messages, temperature=0.2, max_tokens=700, stream=False):
        self.last_messages = messages
        if self.raise_error:
            raise RuntimeError("simulated LLM failure")
        return self.reply


class TestFaithfulnessCheck:
    def test_faithful_response(self):
        llm = _FakeLLM('{"is_faithful": true, "unsupported_claims": []}')
        checker = FaithfulnessChecker(llm)
        res = checker.check("根据[K1]的内容，价格是100元。", "[K1] 价格100元")
        assert res.is_faithful is True
        assert res.unsupported_claims == []

    def test_unsupported_claims_detected(self):
        llm = _FakeLLM(
            '{"is_faithful": false, "unsupported_claims": ["我们支持免费试用30天"]}'
        )
        checker = FaithfulnessChecker(llm)
        res = checker.check("我们支持免费试用30天。", "[K1] 标准版月费99元")
        assert res.is_faithful is False
        assert "我们支持免费试用30天" in res.unsupported_claims

    def test_judge_output_with_surrounding_text(self):
        # 模型常在 JSON 外包裹说明文字, 解析应鲁棒
        llm = _FakeLLM(
            '经核验，回答存在编造：\n{"is_faithful": false, '
            '"unsupported_claims": ["编造陈述A", "编造陈述B"]}\n以上为结论。'
        )
        checker = FaithfulnessChecker(llm)
        res = checker.check("编造陈述A。编造陈述B。", "[K1] 真实内容")
        assert res.is_faithful is False
        assert len(res.unsupported_claims) == 2

    def test_invalid_json_degrades_to_faithful(self):
        # 解析失败必须退化为"忠实", 不阻断主链路
        llm = _FakeLLM("抱歉我无法判断。")
        checker = FaithfulnessChecker(llm)
        res = checker.check("任意回答", "[K1] 上下文")
        assert res.is_faithful is True
        assert res.unsupported_claims == []

    def test_llm_error_degrades_to_faithful(self):
        llm = _FakeLLM("", raise_error=True)
        checker = FaithfulnessChecker(llm)
        res = checker.check("任意回答", "[K1] 上下文")
        assert res.is_faithful is True

    def test_empty_inputs_degrade(self):
        checker = FaithfulnessChecker(_FakeLLM(""))
        assert checker.check("", "[K1] x").is_faithful is True
        assert checker.check("回答", "").is_faithful is True


class TestFaithfulnessCorrect:
    def test_correct_rewrites(self):
        llm = _FakeLLM("根据[K1]内容，标准版月费99元。知识库中没有免费试用相关信息。")
        checker = FaithfulnessChecker(llm)
        out = checker.correct(
            "我们支持免费试用30天。",
            "[K1] 标准版月费99元",
            ["我们支持免费试用30天"],
        )
        assert out is not None
        # 编造的具体断言(我们支持免费试用30天)应被剔除, 仅可就话题做"无相关信息"说明
        assert "我们支持免费试用30天" not in out

    def test_correct_returns_none_when_no_claims(self):
        checker = FaithfulnessChecker(_FakeLLM(""))
        assert checker.correct("回答", "[K1] ctx", []) is None
