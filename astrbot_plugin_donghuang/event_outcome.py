"""
event_outcome.py — 事件结果模型（B-6.1）

定义事件结束后可以产生的结构化结果，以及如何被序列化。

核心概念：
  EventOutcome = {
    "event_id": str,
    "outcome_type": str,        # resolved / failed / partial / expired / escalated
    "summary": str,             # 人类可读的结果摘要
    "world_delta": {},          # 对世界状态的变更（白名单字段）
    "faction_delta": {},        # 对势力状态的变更（code → delta）
    "profile_delta": {},        # 对玩家状态的变更（key → new_value）
    "spawn_event_hints": [],    # 后续事件触发线索（B-6.5）
    "applied_changes": [],      # 实际应用的变更列表（用于审计和 rollback）
  }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
#  结果类型枚举
# ──────────────────────────────────────────────

class EventOutcomeType(str):
    """事件结果类型。"""
    RESOLVED = "resolved"       # 成功解决
    FAILED = "failed"           # 失败恶化
    PARTIAL = "partial"         # 部分成功
    EXPIRED = "expired"         # 自然消散
    ESCALATED = "escalated"     # 升级为后续事件


# ──────────────────────────────────────────────
#  白名单常量
# ──────────────────────────────────────────────

# 允许写入的世界状态字段
WORLD_FIELD_WHITELIST = frozenset({
    "GLOBAL",
    "REGION",
    "RESOURCE",
    "FACTION_STATE",
})

# 允许写入的 FACTION_STATE 子字段
FACTION_FIELD_WHITELIST = frozenset({
    "power",
    "stability",
    "morale",
    "active_goal",
    "stance_overrides",
})

# 允许写入的 PROFILE 顶层字段
PROFILE_FIELD_WHITELIST = frozenset({
    "BASE_STATE",
    "FACTION_STATE",
    "relations",
    "appearance",  # B-8: 外观档案
    # LONG-A 扩展：修炼相关字段（通过 METHOD_STATE / CORE_STATE 嵌套访问）
})

# 允许写入的 METHOD_STATE 子字段
METHOD_STATE_WHITELIST = frozenset({
    "progress",      # 修炼进度 0~100
    "foundation",    # 根基值 0~200
    "bottleneck",    # 瓶颈等级 0~5
    "consecutive_failures",  # 连续失败次数
    "cultivation_modifier",  # 修炼倍率
    "growth_stage",   # 大境界阶段
    "breakthrough_status",  # 突破状态
    "active_technique",     # 当前主修功法
    "known_techniques",     # 已掌握功法列表
    "abilities",            # 技能能力表
})

# 允许写入的 CORE_STATE 子字段
CORE_STATE_WHITELIST = frozenset({
    "spiritual_root",  # 灵根状态
})


# ──────────────────────────────────────────────
#  EventOutcome 数据类
# ──────────────────────────────────────────────

@dataclass
class EventOutcome:
    """事件结果对象。

    所有数值变更必须经过 clamp 处理（0~100 或 0.0~1.0），
    不允许任意字段写入。
    """

    event_id: str
    outcome_type: str = EventOutcomeType.RESOLVED
    summary: str = ""
    world_delta: Dict[str, Any] = field(default_factory=dict)
    faction_delta: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    profile_delta: Dict[str, Any] = field(default_factory=dict)
    spawn_event_hints: List[Dict[str, str]] = field(default_factory=list)
    applied_changes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "outcome_type": self.outcome_type,
            "summary": self.summary,
            "world_delta": self.world_delta,
            "faction_delta": self.faction_delta,
            "profile_delta": self.profile_delta,
            "spawn_event_hints": self.spawn_event_hints,
            "applied_changes": self.applied_changes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EventOutcome":
        return cls(
            event_id=d["event_id"],
            outcome_type=d.get("outcome_type", EventOutcomeType.RESOLVED),
            summary=d.get("summary", ""),
            world_delta=d.get("world_delta", {}),
            faction_delta=d.get("faction_delta", {}),
            profile_delta=d.get("profile_delta", {}),
            spawn_event_hints=d.get("spawn_event_hints", []),
            applied_changes=d.get("applied_changes", []),
        )


# ──────────────────────────────────────────────
#  工厂函数
# ──────────────────────────────────────────────

def make_resolved_outcome(event_id: str, summary: str,
                          world_delta: Dict = None,
                          faction_delta: Dict = None,
                          profile_delta: Dict = None) -> EventOutcome:
    """创建一个成功解决的事件结果。"""
    return EventOutcome(
        event_id=event_id,
        outcome_type=EventOutcomeType.RESOLVED,
        summary=summary,
        world_delta=world_delta or {},
        faction_delta=faction_delta or {},
        profile_delta=profile_delta or {},
    )


def make_failed_outcome(event_id: str, summary: str,
                        world_delta: Dict = None,
                        faction_delta: Dict = None,
                        profile_delta: Dict = None) -> EventOutcome:
    """创建一个失败恶化的事件结果。"""
    return EventOutcome(
        event_id=event_id,
        outcome_type=EventOutcomeType.FAILED,
        summary=summary,
        world_delta=world_delta or {},
        faction_delta=faction_delta or {},
        profile_delta=profile_delta or {},
    )


def make_partial_outcome(event_id: str, summary: str,
                        world_delta: Dict = None,
                        faction_delta: Dict = None,
                        profile_delta: Dict = None) -> EventOutcome:
    """创建一个部分成功的事件结果。"""
    return EventOutcome(
        event_id=event_id,
        outcome_type=EventOutcomeType.PARTIAL,
        summary=summary,
        world_delta=world_delta or {},
        faction_delta=faction_delta or {},
        profile_delta=profile_delta or {},
    )


def make_expired_outcome(event_id: str, summary: str) -> EventOutcome:
    """创建一个自然消散的事件结果。"""
    return EventOutcome(
        event_id=event_id,
        outcome_type=EventOutcomeType.EXPIRED,
        summary=summary,
    )


def make_escalated_outcome(event_id: str, summary: str,
                          hints: List[Dict] = None) -> EventOutcome:
    """创建一个升级为后续事件的事件结果。"""
    return EventOutcome(
        event_id=event_id,
        outcome_type=EventOutcomeType.ESCALATED,
        summary=summary,
        spawn_event_hints=hints or [],
    )
