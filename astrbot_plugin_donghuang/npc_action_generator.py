"""
npc_action_generator.py — NPC 主动行为建议生成（B-11）

核心概念：
  generate_npc_action() = 根据 NPC 的关系和行为倾向，
  生成 NPC 可能采取的主动行为候选列表。

设计原则：
  - 只生成建议，不执行。
  - 不修改任何状态。
  - 由未来系统决定是否执行。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .npc_behavior import calculate_behavior, NPCBehaviorProfile
    from .npc_relationship import (
        REL_UNKNOWN, REL_FAMILIAR, REL_FRIENDLY,
        REL_RESPECTFUL, REL_SUSPICIOUS, REL_HOSTILE,
    )
except ImportError:
    from npc_behavior import calculate_behavior, NPCBehaviorProfile
    from npc_relationship import (
        REL_UNKNOWN, REL_FAMILIAR, REL_FRIENDLY,
        REL_RESPECTFUL, REL_SUSPICIOUS, REL_HOSTILE,
    )

# ──────────────────────────────────────────────
#  NPC 主动行为候选
# ──────────────────────────────────────────────

ACTION_HELP_PLAYER = "help_player"
ACTION_SEND_WARNING = "send_warning"
ACTION_OFFER_INFORMATION = "offer_information"
ACTION_IGNORE = "ignore"
ACTION_AVOID_PLAYER = "avoid_player"

GOAL_SURVIVE = "survive"
GOAL_CULTIVATE = "cultivate"
GOAL_TRADE = "trade"
GOAL_EXPLORE = "explore"
GOAL_REVENGE = "revenge"
GOAL_SOCIALIZE = "socialize"

# 关系 → 候选行为映射
_RELATIONSHIP_ACTION_MAP = {
    REL_RESPECTFUL: [ACTION_HELP_PLAYER, ACTION_OFFER_INFORMATION],
    REL_FRIENDLY: [ACTION_HELP_PLAYER, ACTION_SEND_WARNING],
    REL_FAMILIAR: [ACTION_SEND_WARNING, ACTION_IGNORE],
    REL_UNKNOWN: [ACTION_IGNORE],
    REL_SUSPICIOUS: [ACTION_AVOID_PLAYER, ACTION_IGNORE],
    REL_HOSTILE: [ACTION_AVOID_PLAYER],
}


def _collect_reason_tags(
    npc_info: Dict[str, Any],
    relationship: str,
    world_state: Optional[Dict[str, Any]],
    current_region: Optional[str],
    current_events: Optional[List[Dict[str, Any]]],
) -> List[str]:
    tags: List[str] = []

    if relationship == REL_HOSTILE:
        tags.append("relationship_hostile")
    elif relationship == REL_SUSPICIOUS:
        tags.append("relationship_suspicious")
    elif relationship == REL_FRIENDLY:
        tags.append("relationship_friendly")
    elif relationship == REL_RESPECTFUL:
        tags.append("relationship_respectful")

    role = str(npc_info.get("role", ""))
    if "商" in role:
        tags.append("role_merchant")

    personality = str(npc_info.get("personality", ""))
    if "谨慎" in personality or "多疑" in personality:
        tags.append("personality_cautious")
    if "豪爽" in personality or "正直" in personality:
        tags.append("personality_bold")

    if world_state and current_region:
        region_state = world_state.get("REGION", {}).get(current_region, {})
        environment = region_state.get("environment", {})
        anomaly = environment.get("anomaly_environment", "无")
        if anomaly and anomaly != "无":
            tags.append("environment_danger")

    for event in current_events or []:
        category = str(event.get("category", ""))
        title = str(event.get("title", ""))
        if "冲突" in category or "仇" in title:
            tags.append("event_conflict")
        if "CHAOS" in category or "裂" in title:
            if "environment_danger" not in tags:
                tags.append("environment_danger")

    return tags


def plan_npc_action(
    npc_info: Dict[str, Any],
    memories: List[Dict[str, Any]],
    world_state: Optional[Dict[str, Any]] = None,
    current_region: Optional[str] = None,
    current_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """生成 NPC 的结构化自主决策，不直接修改任何状态。"""
    behavior = calculate_behavior(memories)
    relationship = behavior.relationship or REL_UNKNOWN
    candidates = generate_npc_action(npc_info, relationship, behavior, world_state)
    reason_tags = _collect_reason_tags(
        npc_info=npc_info,
        relationship=relationship,
        world_state=world_state,
        current_region=current_region,
        current_events=current_events,
    )

    if "environment_danger" in reason_tags:
        goal = GOAL_SURVIVE
    elif "relationship_hostile" in reason_tags or "event_conflict" in reason_tags:
        goal = GOAL_REVENGE
    elif "role_merchant" in reason_tags:
        goal = GOAL_TRADE
    elif relationship in (REL_FRIENDLY, REL_RESPECTFUL):
        goal = GOAL_SOCIALIZE
    else:
        goal = GOAL_EXPLORE

    if goal == GOAL_SURVIVE:
        primary_action = ACTION_AVOID_PLAYER
    elif goal == GOAL_REVENGE:
        primary_action = ACTION_AVOID_PLAYER if ACTION_AVOID_PLAYER in candidates else ACTION_SEND_WARNING
    elif goal == GOAL_TRADE:
        if ACTION_HELP_PLAYER in candidates:
            primary_action = ACTION_HELP_PLAYER
        elif ACTION_OFFER_INFORMATION in candidates:
            primary_action = ACTION_OFFER_INFORMATION
        else:
            primary_action = ACTION_SEND_WARNING if ACTION_SEND_WARNING in candidates else ACTION_IGNORE
    elif goal == GOAL_SOCIALIZE:
        primary_action = ACTION_HELP_PLAYER if ACTION_HELP_PLAYER in candidates else ACTION_OFFER_INFORMATION
    else:
        primary_action = candidates[0] if candidates else ACTION_IGNORE

    return {
        "goal": goal,
        "primary_action": primary_action,
        "candidates": candidates,
        "reason_tags": reason_tags,
        "relationship": relationship,
    }


# ──────────────────────────────────────────────
#  行为建议生成
# ──────────────────────────────────────────────

def generate_npc_action(
    npc_info: Dict[str, Any],
    relationship: str,
    behavior_profile: NPCBehaviorProfile,
    world_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """根据 NPC 的关系和行为倾向，生成主动行为候选列表。

    Args:
        npc_info: NPC 信息（name, cultivation, type 等）
        relationship: 关系状态（来自 calculate_relationship）
        behavior_profile: 行为倾向档案（来自 calculate_behavior）
        world_state: 当前世界状态（可选，未来可用于更精细的判断）

    Returns:
        候选行为列表（如 ["help_player", "send_warning"]）
    """
    # 基础候选
    candidates = list(_RELATIONSHIP_ACTION_MAP.get(relationship, [ACTION_IGNORE]))

    # 根据行为倾向调整
    if behavior_profile.help_probability >= 0.65:
        if ACTION_HELP_PLAYER not in candidates:
            candidates.append(ACTION_HELP_PLAYER)

    if behavior_profile.secret_probability >= 0.25:
        if ACTION_OFFER_INFORMATION not in candidates:
            candidates.append(ACTION_OFFER_INFORMATION)

    if behavior_profile.risk_attitude == "cautious":
        if ACTION_AVOID_PLAYER not in candidates:
            candidates.append(ACTION_AVOID_PLAYER)

    # 去重
    seen = set()
    unique = []
    for action in candidates:
        if action not in seen:
            seen.add(action)
            unique.append(action)

    return unique


def generate_npc_action_from_memories(
    npc_info: Dict[str, Any],
    memories: List[Dict[str, Any]],
    world_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """从记忆列表直接生成 NPC 行为候选（便捷方法）。"""
    try:
        from .npc_relationship import calculate_relationship as _calc_rel
    except ImportError:
        from npc_relationship import calculate_relationship as _calc_rel
    behavior = calculate_behavior(memories)
    relationship = _calc_rel(memories)
    return generate_npc_action(npc_info, relationship, behavior, world_state)


# ──────────────────────────────────────────────
#  B-13: NPC 主动行为机会评估
# ──────────────────────────────────────────────

def evaluate_npc_opportunity(
    npc_info: Dict[str, Any],
    world_state: Optional[Dict[str, Any]] = None,
    player_state: Optional[Dict[str, Any]] = None,
    memories: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """评估 NPC 是否有主动行为机会。

    评估规则：
      - friendly/respectful → send_warning 或 offer_information
      - suspicious/hostile → avoid_player
      - familiar → 无主动行为
      - unknown → 无主动行为

    限制：只生成候选，不自动执行。

    Args:
        npc_info: NPC 信息
        world_state: 当前世界状态
        player_state: 玩家状态
        memories: NPC 对玩家的记忆

    Returns:
        候选行为名称（如 "send_warning"），或 None
    """
    if not memories:
        return None

    try:
        from .npc_relationship import calculate_relationship as _calc_rel
    except ImportError:
        from npc_relationship import calculate_relationship as _calc_rel

    relationship = _calc_rel(memories)

    if relationship in (REL_FRIENDLY, REL_RESPECTFUL):
        # 友善NPC：可能主动提醒或提供信息
        behavior = calculate_behavior(memories)
        if behavior.secret_probability >= 0.25:
            return ACTION_OFFER_INFORMATION
        elif behavior.help_probability >= 0.65:
            return ACTION_SEND_WARNING
        return None

    elif relationship in (REL_SUSPICIOUS, REL_HOSTILE):
        # 敌对NPC：可能主动回避
        return ACTION_AVOID_PLAYER

    else:
        # familiar / unknown：不产生主动行为
        return None
