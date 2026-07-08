"""
npc_interaction.py — NPC 交互判定（B-11）

核心概念：
  resolve_npc_interaction() = 判定 NPC 对玩家交互请求的响应倾向。
  只负责判断，禁止直接修改玩家/NPC数据，禁止绕过 Outcome 系统。

设计原则：
  - 判定基于 NPCBehaviorProfile（由 memory 计算）。
  - 不修改任何状态。
  - 输出 InteractionResult 供上层决策使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from .npc_behavior import calculate_behavior, NPCBehaviorProfile
    from .npc_relationship import REL_LABELS
except ImportError:
    from npc_behavior import calculate_behavior, NPCBehaviorProfile
    from npc_relationship import REL_LABELS

# ──────────────────────────────────────────────
#  交互类型常量
# ──────────────────────────────────────────────

INTERACTION_TRADE = "trade"
INTERACTION_ASK_INFO = "ask_info"
INTERACTION_REQUEST_HELP = "request_help"
INTERACTION_THREATEN = "threaten"

VALID_INTERACTION_TYPES = frozenset({
    INTERACTION_TRADE,
    INTERACTION_ASK_INFO,
    INTERACTION_REQUEST_HELP,
    INTERACTION_THREATEN,
})


# ──────────────────────────────────────────────
#  InteractionResult 数据类
# ──────────────────────────────────────────────

@dataclass
class InteractionResult:
    """NPC 交互判定结果。"""

    success: bool = False
    response_bias: str = ""     # 倾向描述
    reason: str = ""            # 判定原因
    behavior_profile: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "response_bias": self.response_bias,
            "reason": self.reason,
            "behavior_profile": self.behavior_profile,
        }


# ──────────────────────────────────────────────
#  交互判定
# ──────────────────────────────────────────────

def resolve_npc_interaction(
    npc_info: Dict[str, Any],
    player_profile: Dict[str, Any],
    interaction_type: str,
    memories: List[Dict[str, Any]],
) -> InteractionResult:
    """判定 NPC 对玩家交互请求的响应。

    Args:
        npc_info: NPC 信息（name, cultivation, type 等）
        player_profile: 玩家档案
        interaction_type: 交互类型（trade/ask_info/request_help/threaten）
        memories: 该 NPC 对该玩家的记忆列表

    Returns:
        InteractionResult 对象
    """
    # 计算行为倾向
    behavior = calculate_behavior(memories)
    npc_name = npc_info.get("name", "未知")
    rel_label = REL_LABELS.get(behavior.relationship, "陌生")

    result = InteractionResult(
        behavior_profile=behavior.to_dict(),
    )

    if interaction_type == INTERACTION_TRADE:
        return _resolve_trade(npc_name, behavior, rel_label, result)
    elif interaction_type == INTERACTION_ASK_INFO:
        return _resolve_ask_info(npc_name, behavior, rel_label, result)
    elif interaction_type == INTERACTION_REQUEST_HELP:
        return _resolve_request_help(npc_name, behavior, rel_label, result)
    elif interaction_type == INTERACTION_THREATEN:
        return _resolve_threaten(npc_name, behavior, rel_label, result)
    else:
        result.success = False
        result.response_bias = "neutral"
        result.reason = f"未知交互类型：{interaction_type}"
        return result


def _resolve_trade(
    npc_name: str,
    behavior: NPCBehaviorProfile,
    rel_label: str,
    result: InteractionResult,
) -> InteractionResult:
    """交易交互判定。"""
    if behavior.price_bias >= 0.10:
        result.success = True
        result.response_bias = "favorable"
        result.reason = f"{npc_name}与你关系{rel_label}，愿意给予优惠。"
    elif behavior.price_bias <= -0.10:
        result.success = True  # 交易仍可进行，只是价格不利
        result.response_bias = "unfavorable"
        result.reason = f"{npc_name}对你心存戒备，价格偏高。"
    else:
        result.success = True
        result.response_bias = "neutral"
        result.reason = f"{npc_name}以正常价格交易。"
    return result


def _resolve_ask_info(
    npc_name: str,
    behavior: NPCBehaviorProfile,
    rel_label: str,
    result: InteractionResult,
) -> InteractionResult:
    """询问信息交互判定。"""
    if behavior.secret_probability >= 0.25:
        result.success = True
        result.response_bias = "open"
        result.reason = f"{npc_name}与你关系{rel_label}，愿意透露信息。"
    elif behavior.secret_probability >= 0.10:
        result.success = True
        result.response_bias = "partial"
        result.reason = f"{npc_name}愿意提供部分信息，但有所保留。"
    elif behavior.secret_probability >= 0.05:
        result.success = False
        result.response_bias = "reluctant"
        result.reason = f"{npc_name}对你心存警惕，不愿透露太多。"
    else:
        result.success = False
        result.response_bias = "refused"
        result.reason = f"{npc_name}拒绝透露任何信息。"
    return result


def _resolve_request_help(
    npc_name: str,
    behavior: NPCBehaviorProfile,
    rel_label: str,
    result: InteractionResult,
) -> InteractionResult:
    """请求帮助交互判定。"""
    if behavior.help_probability >= 0.65:
        result.success = True
        result.response_bias = "willing"
        result.reason = f"{npc_name}与你关系{rel_label}，愿意提供帮助。"
    elif behavior.help_probability >= 0.30:
        result.success = True
        result.response_bias = "considering"
        result.reason = f"{npc_name}愿意考虑帮忙，但需要看情况。"
    elif behavior.help_probability >= 0.10:
        result.success = False
        result.response_bias = "unlikely"
        result.reason = f"{npc_name}不太愿意帮忙。"
    else:
        result.success = False
        result.response_bias = "refused"
        result.reason = f"{npc_name}拒绝提供帮助。"
    return result


def _resolve_threaten(
    npc_name: str,
    behavior: NPCBehaviorProfile,
    rel_label: str,
    result: InteractionResult,
) -> InteractionResult:
    """威胁交互判定。"""
    if behavior.risk_attitude == "bold":
        result.success = False
        result.response_bias = "defiant"
        result.reason = f"{npc_name}不惧威胁，反而可能反击。"
    elif behavior.risk_attitude == "cautious":
        result.success = True
        result.response_bias = "compliant"
        result.reason = f"{npc_name}谨慎行事，暂时顺从。"
    else:
        result.success = False
        result.response_bias = "neutral"
        result.reason = f"{npc_name}对威胁反应平淡。"
    return result
