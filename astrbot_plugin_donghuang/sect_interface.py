# -*- coding: utf-8 -*-
"""
sect_interface.py — 宗门成长接口（LONG-A 第8阶段）

核心概念：
  SectInterface = 宗门成长系统的接口定义。
  只设计接口，不完整实现。预留贡献、职位、传承、师徒等功能的扩展点。

设计原则：
  - 本模块只定义接口和数据结构，不实现具体逻辑。
  - 所有变更通过 EventOutcome → OutcomeApplier 写入。
  - 接口设计要考虑未来扩展，但不提前实现。

FACTION_STATE 扩展字段（预留）：
  "sect": {
      "name": "",               # 宗门名称
      "position": "外门弟子",   # 职位
      "contribution": 0,        # 贡献点
      "contribution_rank": 0,   # 贡献等级
      "heritage": [],           # 传承列表
      "master": "",             # 师父名称
      "disciples": [],          # 徒弟列表
      "joined_cycle": 0,        # 加入周期
      "status": "active",       # 状态：active/suspended/expelled
  }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────
#  宗门职位等级
# ──────────────────────────────────────────────

SECT_POSITIONS = [
    "杂役弟子",   # 0 - 最低
    "外门弟子",   # 1
    "内门弟子",   # 2
    "核心弟子",   # 3
    "真传弟子",   # 4
    "长老",       # 5
    "大长老",     # 6
    "副宗主",     # 7
    "宗主",       # 8
]

# 职位 → 贡献点需求
POSITION_CONTRIBUTION_REQUIREMENTS = {
    "杂役弟子": 0,
    "外门弟子": 50,
    "内门弟子": 200,
    "核心弟子": 500,
    "真传弟子": 1000,
    "长老": 2000,
    "大长老": 5000,
    "副宗主": 10000,
    "宗主": 99999,
}

# 职位 → 可学习的功法品阶上限
POSITION_TECHNIQUE_TIER_LIMIT = {
    "杂役弟子": "黄级",
    "外门弟子": "黄级",
    "内门弟子": "玄级",
    "核心弟子": "地级",
    "真传弟子": "地级",
    "长老": "天级",
    "大长老": "天级",
    "副宗主": "天级",
    "宗主": "天级",
}

# 职位 → 日常贡献点获取
POSITION_DAILY_CONTRIBUTION = {
    "杂役弟子": 1,
    "外门弟子": 2,
    "内门弟子": 5,
    "核心弟子": 10,
    "真传弟子": 20,
    "长老": 30,
    "大长老": 50,
    "副宗主": 80,
    "宗主": 100,
}


# ──────────────────────────────────────────────
#  传承类型
# ──────────────────────────────────────────────

HERITAGE_TYPES = {
    "功法传承": "从师父处学习功法",
    "秘术传承": "从师父处学习秘术",
    "血脉传承": "继承宗门血脉之力",
    "器物传承": "获得宗门传承器物",
    "道心传承": "继承师父的道心感悟",
}

# 传承 → 数值效果。规模参照已有的装备品阶加成（黄级武器+2攻/+2防）和
# 天赋效果（talent_data.py 里常见 hp_max +5~+15 这一档），传承作为"要先
# 满足职位/师承门槛才能拿到"的稀缺资源，效果定得比黄级装备略高、比
# 天赋略低，避免一步到位碾压装备/天赋成长线。
#   - hp_bonus/mp_bonus/progress_bonus：一次性效果，在 /dh sect claim
#     领取的那一刻直接生效（写入 profile），不需要每次战斗/修炼现算。
#   - attack_bonus/defense_bonus：常驻加成，在 main.py._combat_stats()
#     里跟武器品阶加成同一个位置动态累加（不重复写入 profile，避免
#     "领取时+3、后来又不知道从哪儿再+3"这种脏数据）。
HERITAGE_EFFECTS = {
    "功法传承": {"progress_bonus": 5, "desc": "领取时获得+5点修为进度"},
    "秘术传承": {"attack_bonus": 3, "desc": "攻击力常驻+3"},
    "血脉传承": {"hp_bonus": 10, "desc": "气血上限永久+10"},
    "器物传承": {"defense_bonus": 3, "desc": "防御力常驻+3"},
    "道心传承": {"mp_bonus": 5, "desc": "灵力上限永久+5"},
}


def describe_heritage_effect(heritage_type: str) -> str:
    """获取某个传承类型的效果描述文本。"""
    effect = HERITAGE_EFFECTS.get(heritage_type)
    return effect["desc"] if effect else ""


def sum_heritage_combat_bonus(heritage: List[str]) -> Dict[str, int]:
    """汇总已获得传承里的常驻攻防加成（不含一次性效果），供
    main.py._combat_stats() 调用，用法跟武器品阶加成完全对称。"""
    atk = sum(HERITAGE_EFFECTS.get(h, {}).get("attack_bonus", 0) for h in heritage)
    dfn = sum(HERITAGE_EFFECTS.get(h, {}).get("defense_bonus", 0) for h in heritage)
    return {"attack_bonus": atk, "defense_bonus": dfn}


# ──────────────────────────────────────────────
#  SectInfo 数据类（接口定义）
# ──────────────────────────────────────────────

@dataclass
class SectInfo:
    """宗门信息（接口定义，不完整实现）。"""

    name: str = ""
    position: str = "外门弟子"
    contribution: int = 0
    contribution_rank: int = 0
    heritage: List[str] = field(default_factory=list)
    master: str = ""
    disciples: List[str] = field(default_factory=list)
    joined_cycle: int = 0
    status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "position": self.position,
            "contribution": self.contribution,
            "contribution_rank": self.contribution_rank,
            "heritage": self.heritage,
            "master": self.master,
            "disciples": self.disciples,
            "joined_cycle": self.joined_cycle,
            "status": self.status,
        }


# ──────────────────────────────────────────────
#  SectInterface 接口类
# ──────────────────────────────────────────────

class SectInterface:
    """宗门成长系统接口。

    只定义接口，不实现具体逻辑。
    未来扩展时实现这些方法。
    """

    def get_sect_info(self, profile: Dict[str, Any]) -> SectInfo:
        """获取宗门信息。

        Args:
            profile: 玩家档案

        Returns:
            SectInfo 对象
        """
        faction = profile.get("FACTION_STATE", {})
        sect_data = faction.get("sect", {})

        if not sect_data:
            return SectInfo()

        return SectInfo(
            name=sect_data.get("name", ""),
            position=sect_data.get("position", "外门弟子"),
            contribution=sect_data.get("contribution", 0),
            contribution_rank=sect_data.get("contribution_rank", 0),
            heritage=sect_data.get("heritage", []),
            master=sect_data.get("master", ""),
            disciples=sect_data.get("disciples", []),
            joined_cycle=sect_data.get("joined_cycle", 0),
            status=sect_data.get("status", "active"),
        )

    def can_join_sect(
        self,
        profile: Dict[str, Any],
        sect_name: str,
    ) -> Tuple[bool, str]:
        """判断是否可以加入宗门。

        预留接口，未来实现：
          - 境界要求
          - 灵根要求
          - 宗门状态检查
          - 是否已有宗门

        Args:
            profile: 玩家档案
            sect_name: 宗门名称

        Returns:
            (是否可以加入, 原因)
        """
        # 检查是否已有宗门
        current = self.get_sect_info(profile)
        if current.name:
            return False, f"已加入{current.name}，需先退出"

        return True, ""

    def can_leave_sect(self, profile: Dict[str, Any]) -> Tuple[bool, str]:
        """判断是否可以退出宗门。

        预留接口，未来实现：
          - 贡献点清算
          - 传承回收
          - 师徒关系处理

        Args:
            profile: 玩家档案

        Returns:
            (是否可以退出, 原因)
        """
        current = self.get_sect_info(profile)
        if not current.name:
            return False, "未加入任何宗门"

        if current.status == "expelled":
            return False, "已被逐出宗门"

        return True, ""

    def calculate_contribution_gain(
        self,
        profile: Dict[str, Any],
        action_type: str,
        action_result: str = "success",
    ) -> int:
        """计算贡献点获取量。

        预留接口，未来实现：
          - 任务贡献
          - 战斗贡献
          - 资源贡献
          - 日常贡献

        Args:
            profile: 玩家档案
            action_type: 行动类型
            action_result: 行动结果

        Returns:
            贡献点获取量
        """
        current = self.get_sect_info(profile)
        if not current.name:
            return 0

        # 日常贡献
        daily = POSITION_DAILY_CONTRIBUTION.get(current.position, 0)

        # 行动修正
        action_mult = {
            "mission_success": 3.0,
            "mission_failure": 0.5,
            "combat_victory": 2.0,
            "resource_donation": 1.0,
            "daily": 1.0,
        }.get(action_type, 1.0)

        return int(daily * action_mult)

    def check_position_promotion(
        self,
        profile: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """检查是否可以晋升职位。

        预留接口，未来实现：
          - 贡献点检查
          - 境界检查
          - 宗门事件触发

        Args:
            profile: 玩家档案

        Returns:
            (是否可以晋升, 原因)
        """
        current = self.get_sect_info(profile)
        if not current.name:
            return False, "未加入任何宗门"

        current_idx = SECT_POSITIONS.index(current.position) if current.position in SECT_POSITIONS else 0
        if current_idx >= len(SECT_POSITIONS) - 1:
            return False, "已是最高职位"

        next_position = SECT_POSITIONS[current_idx + 1]
        required = POSITION_CONTRIBUTION_REQUIREMENTS.get(next_position, 99999)

        if current.contribution < required:
            return False, f"贡献点不足（需要{required}，当前{current.contribution}）"

        return True, f"可以晋升为{next_position}"

    def get_available_heritage(
        self,
        profile: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """获取可用的传承列表。

        预留接口，未来实现：
          - 根据职位和贡献解锁传承
          - 师徒传承
          - 宗门秘传

        Args:
            profile: 玩家档案

        Returns:
            可用传承列表
        """
        current = self.get_sect_info(profile)
        if not current.name:
            return []

        # 根据职位返回可用的传承类型
        position_idx = SECT_POSITIONS.index(current.position) if current.position in SECT_POSITIONS else 0

        available = []
        if position_idx >= 2:  # 内门弟子以上
            available.append({"type": "功法传承", "desc": HERITAGE_TYPES["功法传承"]})
        if position_idx >= 4:  # 真传弟子以上
            available.append({"type": "秘术传承", "desc": HERITAGE_TYPES["秘术传承"]})
        if position_idx >= 5:  # 长老以上
            available.append({"type": "血脉传承", "desc": HERITAGE_TYPES["血脉传承"]})
            available.append({"type": "器物传承", "desc": HERITAGE_TYPES["器物传承"]})
        if current.master:  # 有师父
            available.append({"type": "道心传承", "desc": HERITAGE_TYPES["道心传承"]})

        return available

    def get_master_disciple_info(
        self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """获取师徒关系信息。

        预留接口，未来实现：
          - 师父信息
          - 徒弟列表
          - 师徒任务
          - 传承进度

        Args:
            profile: 玩家档案

        Returns:
            师徒关系信息
        """
        current = self.get_sect_info(profile)
        return {
            "master": current.master,
            "disciples": current.disciples,
            "has_master": bool(current.master),
            "has_disciples": bool(current.disciples),
        }


# ──────────────────────────────────────────────
#  旧存档迁移
# ──────────────────────────────────────────────

def migrate_profile_sect(profile: Dict[str, Any]) -> Dict[str, Any]:
    """为旧存档补全宗门字段。

    Args:
        profile: 玩家档案 dict

    Returns:
        修改后的 profile
    """
    faction = profile.setdefault("FACTION_STATE", {})

    if "sect" not in faction:
        faction["sect"] = {
            "name": "",
            "position": "外门弟子",
            "contribution": 0,
            "contribution_rank": 0,
            "heritage": [],
            "master": "",
            "disciples": [],
            "joined_cycle": 0,
            "status": "active",
            "pending_task": None,  # 师徒任务系统：师父布置、徒弟完成
        }
    else:
        faction["sect"].setdefault("pending_task", None)

    return profile


# ──────────────────────────────────────────────
#  构造 FACTION_STATE delta（供 OutcomeApplier 使用）
# ──────────────────────────────────────────────

def make_sect_delta(
    name: Optional[str] = None,
    position: Optional[str] = None,
    contribution_delta: Optional[int] = None,
    heritage: Optional[List[str]] = None,
    master: Optional[str] = None,
    disciples: Optional[List[str]] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """构造宗门变更的 delta dict。

    Args:
        name: 宗门名称
        position: 职位
        contribution_delta: 贡献点变化量
        heritage: 传承列表
        master: 师父名称
        disciples: 徒弟列表
        status: 状态

    Returns:
        FACTION_STATE.sect delta dict
    """
    sect_delta: Dict[str, Any] = {}

    if name is not None:
        sect_delta["name"] = name
    if position is not None:
        sect_delta["position"] = position
    if contribution_delta is not None:
        sect_delta["contribution"] = contribution_delta
    if heritage is not None:
        sect_delta["heritage"] = heritage
    if master is not None:
        sect_delta["master"] = master
    if disciples is not None:
        sect_delta["disciples"] = disciples
    if status is not None:
        sect_delta["status"] = status

    if not sect_delta:
        return {}

    return {"sect": sect_delta}


# ──────────────────────────────────────────────
#  宗门描述生成
# ──────────────────────────────────────────────

def describe_sect_info(sect: SectInfo) -> str:
    """生成宗门信息的人类可读描述。

    Args:
        sect: 宗门信息

    Returns:
        描述字符串
    """
    if not sect.name:
        return "散修（未加入宗门）"

    parts = [f"{sect.name}·{sect.position}"]
    parts.append(f"贡献点：{sect.contribution}")

    if sect.master:
        parts.append(f"师承：{sect.master}")
    if sect.disciples:
        parts.append(f"徒弟：{'、'.join(sect.disciples)}")
    if sect.heritage:
        parts.append(f"传承：{'、'.join(sect.heritage)}")

    if sect.status != "active":
        parts.append(f"状态：{sect.status}")

    return "　".join(parts)
