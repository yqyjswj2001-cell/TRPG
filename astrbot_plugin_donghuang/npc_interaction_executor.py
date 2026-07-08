"""
npc_interaction_executor.py — NPC 交互执行层（B-12）

核心概念：
  execute_interaction() = 将判定层（resolve_npc_interaction）的结果
  转化为可执行的 InteractionExecutionResult，包含 EventOutcome 和 memory_hint。

设计原则：
  - 必须调用已有 resolve_npc_interaction()，不重新设计关系计算。
  - 不直接修改 player_profiles / world_state / faction_state。
  - 所有状态变化必须经过 EventOutcome → OutcomeApplier。
  - 交互完成后提供 memory_hint 供调用方写入记忆。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from .npc_interaction import (
        resolve_npc_interaction, InteractionResult,
        INTERACTION_TRADE, INTERACTION_ASK_INFO,
        INTERACTION_REQUEST_HELP, INTERACTION_THREATEN,
    )
    from .npc_behavior import calculate_behavior
    from .event_outcome import (
        EventOutcome, make_resolved_outcome, make_failed_outcome,
        make_partial_outcome, EventOutcomeType,
    )
    from .npc_memory import MEMORY_IMPORTANCE_THRESHOLD, SOURCE_FACTION_EVENT
except ImportError:
    from npc_interaction import (
        resolve_npc_interaction, InteractionResult,
        INTERACTION_TRADE, INTERACTION_ASK_INFO,
        INTERACTION_REQUEST_HELP, INTERACTION_THREATEN,
    )
    from npc_behavior import calculate_behavior
    from event_outcome import (
        EventOutcome, make_resolved_outcome, make_failed_outcome,
        make_partial_outcome, EventOutcomeType,
    )
    from npc_memory import MEMORY_IMPORTANCE_THRESHOLD, SOURCE_FACTION_EVENT


# ──────────────────────────────────────────────
#  InteractionExecutionResult 数据类
# ──────────────────────────────────────────────

@dataclass
class InteractionExecutionResult:
    """NPC 交互执行结果。

    包含交互判定结果、可执行的 EventOutcome、以及记忆提示。
    """

    success: bool = False
    response: str = ""                    # 叙事描述
    outcome: Optional[EventOutcome] = None  # 可执行的 EventOutcome
    memory_hint: Optional[Dict[str, Any]] = None  # 记忆提示

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "response": self.response,
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "memory_hint": self.memory_hint,
        }


# ──────────────────────────────────────────────
#  执行入口
# ──────────────────────────────────────────────

def execute_interaction(
    npc_info: Dict[str, Any],
    player_profile: Dict[str, Any],
    interaction_type: str,
    memories: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> InteractionExecutionResult:
    """执行 NPC 交互，生成完整的执行结果。

    流程：
      1. 调用 resolve_npc_interaction() 判定倾向
      2. 根据判定结果生成交互叙事描述
      3. 必要时构造 EventOutcome（状态变更）
      4. 提供记忆提示（memory_hint）

    Args:
        npc_info: NPC 信息（name, cultivation, type 等）
        player_profile: 玩家档案
        interaction_type: 交互类型（trade/ask_info/request_help/threaten）
        memories: 该 NPC 对该玩家的记忆列表
        context: 额外上下文（如 group_id, player_id, cycle 等）

    Returns:
        InteractionExecutionResult 对象
    """
    # 1. 判定层
    interaction_result = resolve_npc_interaction(
        npc_info, player_profile, interaction_type, memories,
    )

    npc_name = npc_info.get("name", "未知")
    player_id = (context or {}).get("player_id", "PLAYER-A")
    group_id = (context or {}).get("group_id", "")
    cycle = (context or {}).get("cycle", 0)

    # 2. 生成交互结果
    if interaction_type == INTERACTION_TRADE:
        return _execute_trade(npc_name, interaction_result, player_id, group_id, cycle)
    elif interaction_type == INTERACTION_ASK_INFO:
        return _execute_ask_info(npc_name, interaction_result, player_id, group_id, cycle)
    elif interaction_type == INTERACTION_REQUEST_HELP:
        return _execute_request_help(npc_name, interaction_result, player_id, group_id, cycle, player_profile)
    elif interaction_type == INTERACTION_THREATEN:
        return _execute_threaten(npc_name, interaction_result, player_id, group_id, cycle)
    else:
        return InteractionExecutionResult(
            success=False,
            response=f"与{npc_name}的交互未能进行：未知交互类型。",
        )


# ──────────────────────────────────────────────
#  交互执行子方法
# ──────────────────────────────────────────────

def _execute_trade(
    npc_name: str,
    result: InteractionResult,
    player_id: str,
    group_id: str,
    cycle: int,
) -> InteractionExecutionResult:
    """执行交易交互。"""
    if result.response_bias == "favorable":
        response = f"{npc_name}对你表示友好，愿意以优惠价格与你交易。"
        outcome = make_resolved_outcome(
            event_id=f"NPC_TRADE_{npc_name}",
            summary=f"与{npc_name}友好交易，获得优惠。",
            profile_delta={
                player_id: {
                    "RESOURCE_STATE": {"currency": {"灵石": -5}},
                }
            },
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "trade", "summary": f"与{npc_name}进行了友好交易。",
            "importance": 35, "emotion": "neutral", "trust_change": 5,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=True, response=response, outcome=outcome, memory_hint=memory_hint,
        )

    elif result.response_bias == "unfavorable":
        response = f"{npc_name}对你心存戒备，交易条件苛刻，要价偏高。"
        outcome = make_partial_outcome(
            event_id=f"NPC_TRADE_{npc_name}",
            summary=f"与{npc_name}交易，但价格不利。",
            profile_delta={
                player_id: {
                    "RESOURCE_STATE": {"currency": {"灵石": -15}},
                }
            },
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "trade", "summary": f"与{npc_name}进行了不利的交易。",
            "importance": 30, "emotion": "neutral", "trust_change": 0,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=True, response=response, outcome=outcome, memory_hint=memory_hint,
        )

    else:  # neutral
        response = f"{npc_name}以正常价格与你交易。"
        outcome = make_resolved_outcome(
            event_id=f"NPC_TRADE_{npc_name}",
            summary=f"与{npc_name}进行了正常交易。",
            profile_delta={
                player_id: {
                    "RESOURCE_STATE": {"currency": {"灵石": -10}},
                }
            },
        )
        memory_hint = None  # 普通交易不记录
        return InteractionExecutionResult(
            success=True, response=response, outcome=outcome, memory_hint=memory_hint,
        )


def _execute_ask_info(
    npc_name: str,
    result: InteractionResult,
    player_id: str,
    group_id: str,
    cycle: int,
) -> InteractionExecutionResult:
    """执行询问信息交互。"""
    if result.response_bias == "open":
        response = f"{npc_name}对你毫无保留，提供了大量有价值的信息。"
        # 信息不改变数值状态，但生成一个 resolved outcome 供叙事使用
        outcome = make_resolved_outcome(
            event_id=f"NPC_INFO_{npc_name}",
            summary=f"从{npc_name}处获得了重要信息。",
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "help", "summary": f"{npc_name}向你提供了重要信息。",
            "importance": 50, "emotion": "grateful", "trust_change": 5,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=True, response=response, outcome=outcome, memory_hint=memory_hint,
        )

    elif result.response_bias == "partial":
        response = f"{npc_name}提供了一些信息，但明显有所保留。"
        outcome = make_partial_outcome(
            event_id=f"NPC_INFO_{npc_name}",
            summary=f"从{npc_name}处获得了部分信息。",
        )
        memory_hint = None  # 部分信息不记录
        return InteractionExecutionResult(
            success=True, response=response, outcome=outcome, memory_hint=memory_hint,
        )

    elif result.response_bias == "reluctant":
        response = f"{npc_name}对你心存警惕，不愿透露太多。"
        outcome = make_failed_outcome(
            event_id=f"NPC_INFO_{npc_name}",
            summary=f"未能从{npc_name}处获得有价值的信息。",
        )
        return InteractionExecutionResult(
            success=False, response=response, outcome=outcome,
        )

    else:  # refused
        response = f"{npc_name}拒绝透露任何信息。"
        outcome = make_failed_outcome(
            event_id=f"NPC_INFO_{npc_name}",
            summary=f"{npc_name}拒绝提供信息。",
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "conflict", "summary": f"向{npc_name}询问信息被拒绝。",
            "importance": 40, "emotion": "hostile", "trust_change": -5,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=False, response=response, outcome=outcome, memory_hint=memory_hint,
        )


def _execute_request_help(
    npc_name: str,
    result: InteractionResult,
    player_id: str,
    group_id: str,
    cycle: int,
    player_profile: Dict[str, Any],
) -> InteractionExecutionResult:
    """执行请求帮助交互。"""
    if result.response_bias == "willing":
        response = f"{npc_name}毫不犹豫地答应帮助你。"
        outcome = make_resolved_outcome(
            event_id=f"NPC_HELP_{npc_name}",
            summary=f"{npc_name}提供了帮助。",
            profile_delta={
                player_id: {
                    "BASE_STATE": {"progress": 5},  # 帮助提升修为进度
                }
            },
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "help", "summary": f"{npc_name}帮助了你。",
            "importance": 60, "emotion": "grateful", "trust_change": 10,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=True, response=response, outcome=outcome, memory_hint=memory_hint,
        )

    elif result.response_bias == "considering":
        response = f"{npc_name}表示愿意考虑帮忙，但需要看情况。"
        outcome = make_partial_outcome(
            event_id=f"NPC_HELP_{npc_name}",
            summary=f"{npc_name}可能提供有限帮助。",
        )
        memory_hint = None
        return InteractionExecutionResult(
            success=True, response=response, outcome=outcome, memory_hint=memory_hint,
        )

    elif result.response_bias == "unlikely":
        response = f"{npc_name}不太愿意帮忙。"
        outcome = make_failed_outcome(
            event_id=f"NPC_HELP_{npc_name}",
            summary=f"{npc_name}不愿提供帮助。",
        )
        return InteractionExecutionResult(
            success=False, response=response, outcome=outcome,
        )

    else:  # refused
        response = f"{npc_name}断然拒绝提供帮助。"
        outcome = make_failed_outcome(
            event_id=f"NPC_HELP_{npc_name}",
            summary=f"{npc_name}拒绝帮助。",
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "conflict", "summary": f"请求{npc_name}帮助被拒绝。",
            "importance": 45, "emotion": "hostile", "trust_change": -5,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=False, response=response, outcome=outcome, memory_hint=memory_hint,
        )


def _execute_threaten(
    npc_name: str,
    result: InteractionResult,
    player_id: str,
    group_id: str,
    cycle: int,
) -> InteractionExecutionResult:
    """执行威胁交互。"""
    if result.response_bias == "compliant":
        response = f"{npc_name}在你的威胁下暂时顺从。"
        outcome = make_resolved_outcome(
            event_id=f"NPC_THREAT_{npc_name}",
            summary=f"通过威胁迫使{npc_name}顺从。",
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "conflict", "summary": f"威胁了{npc_name}使其暂时顺从。",
            "importance": 55, "emotion": "hostile", "trust_change": -15,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=True, response=response, outcome=outcome, memory_hint=memory_hint,
        )

    elif result.response_bias == "defiant":
        response = f"{npc_name}不惧你的威胁，态度反而更加强硬！"
        outcome = make_failed_outcome(
            event_id=f"NPC_THREAT_{npc_name}",
            summary=f"威胁{npc_name}失败，对方态度强硬。",
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "conflict", "summary": f"试图威胁{npc_name}但被强硬拒绝。",
            "importance": 65, "emotion": "hostile", "trust_change": -20,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=False, response=response, outcome=outcome, memory_hint=memory_hint,
        )

    else:  # neutral
        response = f"{npc_name}对你的威胁反应平淡。"
        outcome = make_partial_outcome(
            event_id=f"NPC_THREAT_{npc_name}",
            summary=f"威胁{npc_name}效果有限。",
        )
        memory_hint = {
            "npc_id": npc_name, "player_id": player_id, "group_id": group_id,
            "memory_type": "conflict", "summary": f"威胁了{npc_name}，效果有限。",
            "importance": 50, "emotion": "hostile", "trust_change": -10,
            "source": SOURCE_FACTION_EVENT, "cycle": cycle,
        }
        return InteractionExecutionResult(
            success=False, response=response, outcome=outcome, memory_hint=memory_hint,
        )
