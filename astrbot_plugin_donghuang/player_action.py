"""
player_action.py — 玩家行动模型（B-7.1）

定义玩家主动行为的数据结构。

核心概念：
  PlayerAction = {
    "action_id": str,      # 唯一 ID
    "player_id": str,      # 玩家 slot_id
    "group_id": str,       # 群号
    "cycle": int,          # 当前 Cycle
    "action_type": str,    # investigate / assist / oppose / cultivate / negotiate / unknown
    "target_type": str,    # event / faction / region / npc / resource
    "target_id": str,      # 目标标识
    "description": str,    # 人类可读描述
    "metadata": dict,      # 额外信息
  }

不修改任何状态，只表示一次行动意图。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ──────────────────────────────────────────────
#  行动类型常量
# ──────────────────────────────────────────────

class ActionType(str):
    INVESTIGATE = "investigate"     # 调查
    ASSIST = "assist"               # 协助
    OPPOSE = "oppose"               # 对抗
    CULTIVATE = "cultivate"         # 修炼
    NEGOTIATE = "negotiate"         # 交涉
    UNKNOWN = "unknown"             # 未识别


class TargetType(str):
    EVENT = "event"                 # 目标是事件
    FACTION = "faction"             # 目标是势力
    REGION = "region"               # 目标是区域
    NPC = "npc"                     # 目标是 NPC
    RESOURCE = "resource"           # 目标是资源


# ──────────────────────────────────────────────
#  PlayerAction 数据类
# ──────────────────────────────────────────────

@dataclass
class PlayerAction:
    """玩家行动对象。不修改任何状态，只表示一次行动意图。"""

    action_id: str
    player_id: str
    group_id: str
    cycle: int
    action_type: str = ActionType.UNKNOWN
    target_type: str = ""
    target_id: str = ""
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "player_id": self.player_id,
            "group_id": self.group_id,
            "cycle": self.cycle,
            "action_type": self.action_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlayerAction":
        return cls(
            action_id=d["action_id"],
            player_id=d.get("player_id", ""),
            group_id=d.get("group_id", ""),
            cycle=d.get("cycle", 0),
            action_type=d.get("action_type", ActionType.UNKNOWN),
            target_type=d.get("target_type", ""),
            target_id=d.get("target_id", ""),
            description=d.get("description", ""),
            metadata=d.get("metadata", {}),
        )


# ──────────────────────────────────────────────
#  工厂函数
# ──────────────────────────────────────────────

_action_counter: int = 0


def make_action(
    player_id: str,
    group_id: str,
    cycle: int,
    action_type: str,
    target_type: str = "",
    target_id: str = "",
    description: str = "",
    metadata: Optional[Dict] = None,
) -> PlayerAction:
    """创建一个 PlayerAction，自动分配递增 ID。"""
    global _action_counter
    _action_counter += 1
    return PlayerAction(
        action_id=f"PA{_action_counter:04d}",
        player_id=player_id,
        group_id=group_id,
        cycle=cycle,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        description=description,
        metadata=metadata or {},
    )


def reset_action_counter() -> None:
    """重置 ID 计数器（仅用于测试）。"""
    global _action_counter
    _action_counter = 0
