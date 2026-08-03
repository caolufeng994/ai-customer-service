"""
策略路由模块（Strategy Router）

将「意图」映射到「处理链路」。设计为纯函数、单分发、终态：
- 知识类意图 → RAG 主链路（检索 → 上下文 → 生成）
- 兜底/未知意图 → 无上下文兜底提示（不注入任何 RAG 内容）

边界与健壮性
------------
* 路由是「一次映射」，不存在循环或递归调用，天然无死循环风险。
* 任何未明确列出（含落库的 FALLBACK、未来新增未知枚举）都收敛到 FALLBACK，
  不存在「路由遗漏」导致的未处理分支。
* 扩展新意图时，只需在 KNOWLEDGE_INTENTS 中登记即可接入 RAG；否则自动兜底。
"""
from enum import Enum
from typing import Set
from app.agent.intent_classifier import IntentCategory


class RouteTarget(str, Enum):
    """处理链路目标。"""
    RAG = "rag"            # 走知识库检索生成主链路
    FALLBACK = "fallback"  # 走无上下文兜底提示（不检索）


# 知识类意图：进入 RAG 主链路检索知识库。
KNOWLEDGE_INTENTS: Set[IntentCategory] = {
    IntentCategory.PRODUCT,
    IntentCategory.PRICING,
    IntentCategory.REFUND,
    IntentCategory.ACCOUNT,
    IntentCategory.KB_DOC,
    IntentCategory.ORDER,
}


def route(intent: IntentCategory) -> RouteTarget:
    """将意图映射到处理链路。

    纯函数，O(1) 集合查询，单分发、终态、无循环。
    未知/兜底意图一律收敛到 FALLBACK，保证无遗漏分支。
    """
    if intent in KNOWLEDGE_INTENTS:
        return RouteTarget.RAG
    return RouteTarget.FALLBACK
