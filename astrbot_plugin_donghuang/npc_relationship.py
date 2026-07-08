"""
npc_relationship.py — NPC 关系状态计算（B-10）

核心概念：
  根据NPC记忆列表计算NPC对玩家的关系状态。
  不保存额外数值——每次从 memory 列表实时计算。

设计原则：
  - 不新增 reputation 系统。
  - 关系状态由 memory 的 trust_change 总和决定。
  - 不持久化计算结果（避免数据冗余）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────
#  关系状态常量
# ──────────────────────────────────────────────

REL_UNKNOWN = "unknown"
REL_FAMILIAR = "familiar"
REL_FRIENDLY = "friendly"
REL_RESPECTFUL = "respectful"
REL_SUSPICIOUS = "suspicious"
REL_HOSTILE = "hostile"

# 中文标签
REL_LABELS = {
    REL_UNKNOWN: "陌生",
    REL_FAMILIAR: "熟悉",
    REL_FRIENDLY: "友善",
    REL_RESPECTFUL: "敬重",
    REL_SUSPICIOUS: "警惕",
    REL_HOSTILE: "敌对",
}


# ──────────────────────────────────────────────
#  关系状态计算
# ──────────────────────────────────────────────

def calculate_relationship(memories: List[Dict[str, Any]]) -> str:
    """根据 NPC 记忆列表计算关系状态。

    规则：
      - 无记忆 → unknown
      - trust_change 总和 >= 60 → respectful
      - trust_change 总和 >= 30 → friendly
      - trust_change 总和 > 0 → familiar
      - trust_change 总和 <= -60 → hostile
      - trust_change 总和 <= -30 → suspicious
      - trust_change 总和 < 0 → familiar（有记忆但略有负面）

    特殊规则：
      - 存在 rescue 记忆 → 至少 friendly
      - 存在 betrayal 记忆 → 至少 suspicious
      - 存在 major_event 记忆 → 至少 familiar

    Args:
        memories: NPC 对该玩家的记忆列表（dict 格式）

    Returns:
        关系状态字符串
    """
    if not memories:
        return REL_UNKNOWN

    # 计算 trust_change 总和
    total_trust = sum(m.get("trust_change", 0) for m in memories)

    # 检查特殊记忆类型
    memory_types = {m.get("memory_type", "") for m in memories}
    has_rescue = "rescue" in memory_types
    has_betrayal = "betrayal" in memory_types
    has_major_event = "major_event" in memory_types

    # 基础关系判定
    if total_trust >= 60:
        base_rel = REL_RESPECTFUL
    elif total_trust >= 30:
        base_rel = REL_FRIENDLY
    elif total_trust > 0:
        base_rel = REL_FAMILIAR
    elif total_trust <= -60:
        base_rel = REL_HOSTILE
    elif total_trust <= -30:
        base_rel = REL_SUSPICIOUS
    elif total_trust < 0:
        base_rel = REL_FAMILIAR  # 有记忆但略有负面
    else:
        # total_trust == 0 但有记忆
        base_rel = REL_FAMILIAR

    # 特殊规则叠加
    if has_betrayal:
        # 背叛记忆：至少 suspicious
        if base_rel in (REL_UNKNOWN, REL_FAMILIAR, REL_FRIENDLY, REL_RESPECTFUL):
            base_rel = REL_SUSPICIOUS

    if has_rescue:
        # 救援记忆：至少 friendly
        if base_rel in (REL_UNKNOWN, REL_FAMILIAR, REL_SUSPICIOUS):
            base_rel = REL_FRIENDLY

    if has_major_event:
        # 重大事件：至少 familiar
        if base_rel == REL_UNKNOWN:
            base_rel = REL_FAMILIAR

    return base_rel


def calculate_relationship_from_objects(memories: list) -> str:
    """从 NPCMemory 对象列表计算关系状态（便捷方法）。"""
    dicts = [m.to_dict() if hasattr(m, "to_dict") else m for m in memories]
    return calculate_relationship(dicts)


# ──────────────────────────────────────────────
#  特殊记忆触发检测
# ──────────────────────────────────────────────

# 特殊记忆类型 → 叙事提示标签
SPECIAL_MEMORY_TAGS = {
    "rescue": "RESCUE_MEMORY",
    "major_event": "MAJOR_EVENT_MEMORY",
    "betrayal": "BETRAYAL_MEMORY",
}

# 标签 → 叙事提示文本
SPECIAL_MEMORY_NARRATIVE = {
    "RESCUE_MEMORY": "他看见你的瞬间，眼中闪过一丝感激，似乎想起了你曾经救过他。",
    "MAJOR_EVENT_MEMORY": "他看见你的瞬间，神色复杂，似乎想起了多年前那场大事。",
    "BETRAYAL_MEMORY": "他看见你的瞬间，脸色微变，眼中闪过一丝警惕与不信任。",
}


def detect_special_memories(memories: List[Dict[str, Any]]) -> List[str]:
    """检测是否存在特殊记忆类型，返回叙事提示标签列表。

    用于 NPC 首次再见到玩家时生成特殊叙事提示。
    AI 描述叙事内容，代码只提供标签。

    Args:
        memories: NPC 对该玩家的记忆列表

    Returns:
        叙事提示标签列表（如 ["RESCUE_MEMORY", "BETRAYAL_MEMORY"]）
    """
    if not memories:
        return []

    tags = []
    memory_types = {m.get("memory_type", "") for m in memories}

    for mtype, tag in SPECIAL_MEMORY_TAGS.items():
        if mtype in memory_types:
            tags.append(tag)

    return tags
