"""
npc_memory.py — NPC 记忆数据模型（B-9）

核心概念：
  NPCMemory = 一条 NPC 对玩家的结构化记忆。
  不依赖 LLM 生成——记忆内容由调用方根据行为/事件结果构造。

设计原则：
  - AI 负责叙事描述，不保存记忆事实。
  - 记忆必须结构化、可序列化、可持久化。
  - 复用现有 player_profiles / ACTION_LOG / EVENT_LOG 体系。
  - 不新增第二套关系系统。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────
#  记忆类型常量
# ──────────────────────────────────────────────

MEMORY_TYPE_ENCOUNTER = "encounter"
MEMORY_TYPE_HELP = "help"
MEMORY_TYPE_CONFLICT = "conflict"
MEMORY_TYPE_TRADE = "trade"
MEMORY_TYPE_BETRAYAL = "betrayal"
MEMORY_TYPE_RESCUE = "rescue"
MEMORY_TYPE_MAJOR_EVENT = "major_event"

VALID_MEMORY_TYPES = frozenset({
    MEMORY_TYPE_ENCOUNTER,
    MEMORY_TYPE_HELP,
    MEMORY_TYPE_CONFLICT,
    MEMORY_TYPE_TRADE,
    MEMORY_TYPE_BETRAYAL,
    MEMORY_TYPE_RESCUE,
    MEMORY_TYPE_MAJOR_EVENT,
})

# ──────────────────────────────────────────────
#  情绪常量
# ──────────────────────────────────────────────

EMOTION_NEUTRAL = "neutral"
EMOTION_GRATEFUL = "grateful"
EMOTION_AFRAID = "afraid"
EMOTION_HOSTILE = "hostile"
EMOTION_RESPECTFUL = "respectful"

VALID_EMOTIONS = frozenset({
    EMOTION_NEUTRAL,
    EMOTION_GRATEFUL,
    EMOTION_AFRAID,
    EMOTION_HOSTILE,
    EMOTION_RESPECTFUL,
})

# ──────────────────────────────────────────────
#  来源常量
# ──────────────────────────────────────────────

SOURCE_PLAYER_ACTION = "player_action"
SOURCE_EVENT_LOG = "event_log"
SOURCE_FACTION_EVENT = "faction_event"
SOURCE_MANUAL = "manual"

VALID_SOURCES = frozenset({
    SOURCE_PLAYER_ACTION,
    SOURCE_EVENT_LOG,
    SOURCE_FACTION_EVENT,
    SOURCE_MANUAL,
})

# ──────────────────────────────────────────────
#  记忆重要性阈值
# ──────────────────────────────────────────────

# importance >= 此值才写入记忆（过滤普通行动）
MEMORY_IMPORTANCE_THRESHOLD = 40

# 情绪 → 态度映射（用于 /dh memories 展示）
EMOTION_TO_ATTITUDE = {
    EMOTION_NEUTRAL: "中立",
    EMOTION_GRATEFUL: "友善",
    EMOTION_AFRAID: "畏惧",
    EMOTION_HOSTILE: "敌对",
    EMOTION_RESPECTFUL: "敬重",
}

# 记忆类型 → 默认重要性
MEMORY_TYPE_DEFAULT_IMPORTANCE = {
    MEMORY_TYPE_ENCOUNTER: 20,
    MEMORY_TYPE_HELP: 60,
    MEMORY_TYPE_CONFLICT: 65,
    MEMORY_TYPE_TRADE: 35,
    MEMORY_TYPE_BETRAYAL: 90,
    MEMORY_TYPE_RESCUE: 80,
    MEMORY_TYPE_MAJOR_EVENT: 75,
}

# 记忆类型 → 默认情绪
MEMORY_TYPE_DEFAULT_EMOTION = {
    MEMORY_TYPE_ENCOUNTER: EMOTION_NEUTRAL,
    MEMORY_TYPE_HELP: EMOTION_GRATEFUL,
    MEMORY_TYPE_CONFLICT: EMOTION_HOSTILE,
    MEMORY_TYPE_TRADE: EMOTION_NEUTRAL,
    MEMORY_TYPE_BETRAYAL: EMOTION_HOSTILE,
    MEMORY_TYPE_RESCUE: EMOTION_GRATEFUL,
    MEMORY_TYPE_MAJOR_EVENT: EMOTION_NEUTRAL,
}

# 记忆类型 → trust_change 默认值
MEMORY_TYPE_DEFAULT_TRUST_CHANGE = {
    MEMORY_TYPE_ENCOUNTER: 0,
    MEMORY_TYPE_HELP: 10,
    MEMORY_TYPE_CONFLICT: -15,
    MEMORY_TYPE_TRADE: 5,
    MEMORY_TYPE_BETRAYAL: -30,
    MEMORY_TYPE_RESCUE: 20,
    MEMORY_TYPE_MAJOR_EVENT: 0,
}


# ──────────────────────────────────────────────
#  记忆 ID 生成
# ──────────────────────────────────────────────

_memory_counter = 0

def _next_memory_id() -> str:
    """生成唯一记忆 ID（MEM 格式）。"""
    global _memory_counter
    _memory_counter += 1
    return f"MEM{_memory_counter:04d}"

def reset_memory_counter() -> None:
    """重置记忆计数器（测试用）。"""
    global _memory_counter
    _memory_counter = 0


# ──────────────────────────────────────────────
#  NPCMemory 数据类
# ──────────────────────────────────────────────

@dataclass
class NPCMemory:
    """NPC 对玩家的一条结构化记忆。"""

    memory_id: str = ""
    npc_id: str = ""
    player_id: str = ""
    group_id: str = ""
    cycle: int = 0
    memory_type: str = ""
    summary: str = ""
    importance: int = 0
    emotion: str = EMOTION_NEUTRAL
    trust_change: int = 0
    source: str = SOURCE_MANUAL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "npc_id": self.npc_id,
            "player_id": self.player_id,
            "group_id": self.group_id,
            "cycle": self.cycle,
            "memory_type": self.memory_type,
            "summary": self.summary,
            "importance": self.importance,
            "emotion": self.emotion,
            "trust_change": self.trust_change,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NPCMemory":
        return cls(
            memory_id=d.get("memory_id", ""),
            npc_id=d.get("npc_id", ""),
            player_id=d.get("player_id", ""),
            group_id=d.get("group_id", ""),
            cycle=d.get("cycle", 0),
            memory_type=d.get("memory_type", ""),
            summary=d.get("summary", ""),
            importance=d.get("importance", 0),
            emotion=d.get("emotion", EMOTION_NEUTRAL),
            trust_change=d.get("trust_change", 0),
            source=d.get("source", SOURCE_MANUAL),
        )


def create_memory(
    npc_id: str,
    player_id: str,
    group_id: str,
    memory_type: str,
    summary: str,
    importance: Optional[int] = None,
    emotion: Optional[str] = None,
    trust_change: Optional[int] = None,
    source: str = SOURCE_MANUAL,
    cycle: int = 0,
) -> NPCMemory:
    """工厂函数：创建一条 NPC 记忆。

    如果 importance / emotion / trust_change 未指定，
    从 MEMORY_TYPE_DEFAULT_* 中取默认值。
    """
    if memory_type not in VALID_MEMORY_TYPES:
        memory_type = MEMORY_TYPE_ENCOUNTER

    if importance is None:
        importance = MEMORY_TYPE_DEFAULT_IMPORTANCE.get(memory_type, 30)

    if emotion is None:
        emotion = MEMORY_TYPE_DEFAULT_EMOTION.get(memory_type, EMOTION_NEUTRAL)

    if trust_change is None:
        trust_change = MEMORY_TYPE_DEFAULT_TRUST_CHANGE.get(memory_type, 0)

    return NPCMemory(
        memory_id=_next_memory_id(),
        npc_id=npc_id,
        player_id=player_id,
        group_id=group_id,
        cycle=cycle,
        memory_type=memory_type,
        summary=summary,
        importance=importance,
        emotion=emotion,
        trust_change=trust_change,
        source=source,
    )


# ──────────────────────────────────────────────
#  行为 → 记忆 映射规则
# ──────────────────────────────────────────────

def action_to_memory_params(
    action_type: str,
    outcome_type: str,
    target_id: str,
    target_type: str,
    description: str,
) -> Optional[Dict[str, Any]]:
    """根据玩家行动参数，推断是否应生成 NPC 记忆以及记忆参数。

    规则：
      - assist + resolved → help 记忆
      - oppose + resolved → conflict 记忆
      - oppose + failed → conflict 记忆（但重要性较低）
      - negotiate + resolved → trade 记忆
      - cultivate → 不生成记忆
      - investigate → 不生成记忆
      - 其他 → 不生成记忆

    Args:
        action_type: 行动类型（investigate/assist/oppose/cultivate/negotiate）
        outcome_type: 结果类型（resolved/failed/partial/expired/escalated）
        target_id: 目标 ID/名称
        target_type: 目标类型（event/faction/region/npc/resource）
        description: 行动描述

    Returns:
        记忆参数 dict（含 memory_type, summary, importance, emotion），
        或 None（不需要生成记忆）
    """
    # 基于行动类型的映射
    if action_type == "assist" and outcome_type in ("resolved", "partial"):
        return {
            "memory_type": MEMORY_TYPE_HELP,
            "summary": f"曾帮助{target_id}：{description}",
            "importance": 60 if outcome_type == "resolved" else 45,
            "emotion": EMOTION_GRATEFUL,
        }

    if action_type == "oppose" and outcome_type in ("resolved", "partial", "failed"):
        return {
            "memory_type": MEMORY_TYPE_CONFLICT,
            "summary": f"曾与{target_id}发生冲突：{description}",
            "importance": 65 if outcome_type == "resolved" else 50,
            "emotion": EMOTION_HOSTILE,
        }

    if action_type == "negotiate" and outcome_type == "resolved":
        return {
            "memory_type": MEMORY_TYPE_TRADE,
            "summary": f"曾与{target_id}进行交涉：{description}",
            "importance": 40,
            "emotion": EMOTION_NEUTRAL,
        }

    # investigate 和 cultivate 不生成记忆
    return None
