"""
npc_context.py — NPC 上下文生成（B-10）

核心概念：
  为 AI 叙事生成特定 NPC 对玩家的上下文描述。
  让 AI 知道：当前 NPC 认识玩家、曾发生事件、当前态度。

设计原则：
  - 只注入当前相关 NPC 的上下文，不把所有 NPC 记忆塞入 Prompt。
  - 最多 5 条记忆，按优先级排序。
  - AI 负责叙事描述，代码只提供结构化标签。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .npc_relationship import (
        calculate_relationship,
        detect_special_memories,
        REL_LABELS,
        SPECIAL_MEMORY_NARRATIVE,
    )
except ImportError:
    from npc_relationship import (
        calculate_relationship,
        detect_special_memories,
        REL_LABELS,
        SPECIAL_MEMORY_NARRATIVE,
    )

try:
    from .npc_memory import NPCMemory
except ImportError:
    from npc_memory import NPCMemory

try:
    from .npc_perception import perceive_player
except ImportError:
    from npc_perception import perceive_player


# NPC 身份文本 → 粗略修为数值的映射，供 perceive_player() 判断"NPC 感知
# 玩家的深度"用。npc_perception.py 的 _extract_cultivation_level 只认
# 数字，NPCRegistry 里的角色只有 role 文本（"长老"/"散修"等），这里做一层
# 简单换算，不追求精确，只求让感知深度不至于全部退化成同一档。
_NPC_ROLE_CULTIVATION_HINT = {
    "宗主": 90, "掌门": 90, "大长老": 80, "长老": 70, "真传弟子": 50,
    "核心弟子": 40, "内门弟子": 30, "外门弟子": 15, "杂役弟子": 5,
    "散修": 20, "百姓": 0,
}


def _guess_npc_cultivation(role: str) -> int:
    for key, val in _NPC_ROLE_CULTIVATION_HINT.items():
        if key in (role or ""):
            return val
    return 20


# ──────────────────────────────────────────────
#  记忆排序优先级
# ──────────────────────────────────────────────

# 类型 → 优先级（数字越小越优先）
_MEMORY_TYPE_PRIORITY = {
    "major_event": 0,
    "rescue": 1,
    "betrayal": 2,
    "conflict": 3,
    "help": 4,
    "encounter": 5,
    "trade": 6,
}


# ──────────────────────────────────────────────
#  build_npc_context()
# ──────────────────────────────────────────────

def build_npc_context(
    npc_id: str,
    player_id: str,
    npc_memory: Dict[str, Any],
    max_memories: int = 5,
    max_chars: int = 500,
) -> str:
    """为 AI 生成 NPC 对玩家的上下文描述。

    Args:
        npc_id: NPC ID
        player_id: 玩家 ID
        npc_memory: campaign[group_id]["npc_memory"] 数据
        max_memories: 最多展示的记忆条数
        max_chars: 最大字符数

    Returns:
        NPC 上下文文本，格式为：

        【NPC对你的印象】
        <NPC_id>当前态度：<态度>
        - <记忆摘要>
        - <记忆摘要>
        [特殊叙事提示]
    """
    # 收集该 NPC 对该玩家的记忆
    mem_list = npc_memory.get(npc_id, [])
    if not isinstance(mem_list, list):
        mem_list = []

    player_memories = [m for m in mem_list if isinstance(m, dict) and m.get("player_id") == player_id]

    if not player_memories:
        return ""

    # 计算关系状态
    relationship = calculate_relationship(player_memories)
    rel_label = REL_LABELS.get(relationship, "陌生")

    # 按优先级排序记忆
    def sort_key(m):
        type_pri = _MEMORY_TYPE_PRIORITY.get(m.get("memory_type", ""), 6)
        importance = m.get("importance", 0)
        return (type_pri, -importance)

    sorted_memories = sorted(player_memories, key=sort_key)
    top_memories = sorted_memories[:max_memories]

    # 构建文本
    lines = [f"【{npc_id}对你的印象】"]
    lines.append(f"当前态度：{rel_label}")

    for mem in top_memories:
        summary = mem.get("summary", "")
        if summary:
            lines.append(f"- {summary}")

    # 检测特殊记忆触发
    special_tags = detect_special_memories(player_memories)
    for tag in special_tags:
        narrative = SPECIAL_MEMORY_NARRATIVE.get(tag, "")
        if narrative:
            lines.append(f"[{narrative}]")

    text = "\n".join(lines)

    # 长度控制
    if len(text) > max_chars:
        text = text[:max_chars] + "..."

    return text


def build_npc_context_for_ai(
    npc_id: str,
    player_id: str,
    npc_memory: Dict[str, Any],
    max_memories: int = 5,
    max_chars: int = 500,
    player_profile: Optional[Dict[str, Any]] = None,
    npc_info: Optional[Dict[str, Any]] = None,
) -> str:
    """build_npc_context 的增强版本，专为 AI 注入使用。

    原本没有记忆时直接返回空字符串——"这个 NPC 认识这个玩家吗"跟"这个
    NPC 第一次见到这个玩家会看到什么"是两件事，之前只处理了前者。现在
    如果传入了 player_profile/npc_info，没有记忆时会调用
    npc_perception.perceive_player() 生成一段基于外貌/气息的初见印象，
    让 AI 在双方从未打过交道时也有具体的观察线索可用，而不是完全没有
    上下文。不传这两个参数时行为和原来完全一样（向后兼容）。
    """
    text = build_npc_context(npc_id, player_id, npc_memory, max_memories, max_chars)
    if text:
        return text

    if not player_profile or not npc_info:
        return ""

    npc_info = dict(npc_info)
    npc_info.setdefault("cultivation", _guess_npc_cultivation(npc_info.get("type") or npc_info.get("role", "")))

    result = perceive_player(player_profile, npc_info)
    if not result.overall_impression:
        return ""

    lines = [f"【{npc_id}对你的初见印象】", result.overall_impression]
    for flag in result.warning_flags:
        lines.append(f"[{flag}]")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "..."
    return text
