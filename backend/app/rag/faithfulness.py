"""
Faithfulness Gate (防编造自检)

在 RAG 回答生成之后, 用 LLM-as-Judge 评估"回答内容"是否真正由"召回上下文"
支撑, 检测并拦截:
  - 凭空编造(知识库中不存在的信息)
  - 与召回内容相矛盾
  - 引用了知识库里没有的来源

若判定不忠实, 触发一次"基于 [K编号] 内容的自我纠正"并重检; 仍不通过则标记
grounded=False (前端展示告警), 绝不静默放行编造内容。

设计原则:
  - 失效安全(fail-safe): 任何 LLM/解析异常都退化为"视为忠实", 不阻断主链路。
  - 低延迟: 判定用低温度; 纠正最多 1 次(可配置)。
  - 与 citation_verification(仅编号范围校验)互补, 二者不冲突。
"""
from dataclasses import dataclass, field
from typing import List, Optional
import json
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class FaithfulnessResult:
    """自检结果"""
    is_faithful: bool
    unsupported_claims: List[str] = field(default_factory=list)


_JUDGE_SYSTEM = (
    "你是一个严格的事实一致性核验器。你会拿到【知识库内容】与【AI回答】。"
    "请逐条判断 AI 回答中的事实性陈述, 找出其中【无法被知识库内容支撑】的部分——"
    "包括: 凭空编造、与知识库矛盾、或引用了知识库中不存在的信息。"
    "只依据知识库内容判定, 不要使用你自己的外部知识。"
    "必须只输出一个 JSON 对象, 不要输出任何多余文字, 格式如下:\n"
    "{\n"
    '  "is_faithful": true 或 false,\n'
    '  "unsupported_claims": ["无法被支撑的具体陈述1", "..."]\n'
    "}\n"
    "若回答完全基于知识库、无编造无矛盾, is_faithful 为 true, unsupported_claims 为空数组。"
)

_JUDGE_USER_TMPL = "【知识库内容】\n{context}\n\n【AI回答】\n{response}\n\n请输出核验 JSON:"

_CORRECT_SYSTEM = (
    "你是一个严谨的智能客服助手。下面的回答被核验发现包含无法被知识库支撑的内容"
    "(编造或矛盾)。请重写该回答:\n"
    "1. 删除所有无法被知识库支撑的陈述;\n"
    "2. 仅使用【知识库内容】中 [K编号] 标注的内容作答;\n"
    "3. 若知识库确实无法回答某一点, 明确说明'知识库中没有相关信息';\n"
    "4. 保留 [K编号] 引用格式;\n"
    "5. 保持简洁、友好、自然。\n"
    "只输出重写后的回答, 不要解释你的修改。"
)

_CORRECT_USER_TMPL = (
    "【知识库内容】\n{context}\n\n"
    "【原回答】\n{response}\n\n"
    "【被判定为无法支撑的陈述】\n{unsupported}\n\n"
    "请重写回答:"
)


class FaithfulnessChecker:
    """基于 LLM 的忠实度自检器"""

    def __init__(self, llm_client, temperature: float = 0.2):
        """
        Args:
            llm_client: 具备 chat(messages, temperature, max_tokens, stream) 接口的客户端
            temperature: 判定采样温度(低=更一致)
        """
        self.llm = llm_client
        self.temperature = temperature

    def check(self, response: str, context: str) -> FaithfulnessResult:
        """
        评估回答是否忠实于上下文。

        失效安全: 空输入或任何异常都返回 is_faithful=True, 不阻断主链路。
        """
        if not response or not response.strip():
            return FaithfulnessResult(is_faithful=True, unsupported_claims=[])
        if not context or not context.strip():
            # 无上下文时无法核验, 退化为忠实(避免误杀兜底回答)
            return FaithfulnessResult(is_faithful=True, unsupported_claims=[])

        messages = [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": _JUDGE_USER_TMPL.format(context=context, response=response)},
        ]
        try:
            raw = self.llm.chat(messages, temperature=self.temperature, max_tokens=700, stream=False)
        except Exception as e:
            logger.warning(f"Faithfulness judge LLM failed (degraded to faithful): {e}")
            return FaithfulnessResult(is_faithful=True, unsupported_claims=[])

        return self._parse_judge(raw)

    def _parse_judge(self, raw: str) -> FaithfulnessResult:
        """鲁棒解析 judge 返回的 JSON; 解析失败退化为忠实。"""
        if not raw:
            return FaithfulnessResult(is_faithful=True, unsupported_claims=[])
        try:
            # 容忍模型在 JSON 外包裹了多余文字: 提取首个 {...}
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return FaithfulnessResult(is_faithful=True, unsupported_claims=[])
            data = json.loads(match.group(0))
            is_faithful = bool(data.get("is_faithful", True))
            claims = data.get("unsupported_claims", []) or []
            if not isinstance(claims, list):
                claims = []
            claims = [str(c).strip() for c in claims if str(c).strip()]
            return FaithfulnessResult(is_faithful=is_faithful, unsupported_claims=claims)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse faithfulness judge output (degraded to faithful): {e}")
            return FaithfulnessResult(is_faithful=True, unsupported_claims=[])

    def correct(self, response: str, context: str, unsupported_claims: List[str]) -> Optional[str]:
        """
        基于 [K编号] 内容对回答做一次性重写, 去掉无法支撑的陈述。
        失败时返回 None(调用方应标记 grounded=False 而非保留原编造内容)。
        """
        if not unsupported_claims:
            return None

        unsupported_text = "\n".join(f"- {c}" for c in unsupported_claims)
        messages = [
            {"role": "system", "content": _CORRECT_SYSTEM},
            {
                "role": "user",
                "content": _CORRECT_USER_TMPL.format(
                    context=context, response=response, unsupported=unsupported_text
                ),
            },
        ]
        try:
            corrected = self.llm.chat(messages, temperature=0.3, max_tokens=1000, stream=False)
            return corrected.strip() or None
        except Exception as e:
            logger.warning(f"Faithfulness correction LLM failed: {e}")
            return None
