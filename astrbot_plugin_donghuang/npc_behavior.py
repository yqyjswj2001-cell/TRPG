"""
npc_behavior.py — NPC 行为倾向计算（B-11）

核心概念：
  NPCBehaviorProfile = 根据 memory 列表计算出的 NPC 行为倾向。
  不持久化——每次从 memory 实时计算。

设计原则：
  - 不新增好感度系统或 reputation 数值。
  - 所有行为判断来自 NPCMemory → calculate_relationship() → behavior。
  - 只输出倾向，不直接修改世界状态。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from .npc_relationship import (
        calculate_relationship, REL_UNKNOWN, REL_FAMILIAR, REL_FRIENDLY,
        REL_RESPECTFUL, REL_SUSPICIOUS, REL_HOSTILE, REL_LABELS,
    )
except ImportError:
    from npc_relationship import (
        calculate_relationship, REL_UNKNOWN, REL_FAMILIAR, REL_FRIENDLY,
        REL_RESPECTFUL, REL_SUSPICIOUS, REL_HOSTILE, REL_LABELS,
    )

# ──────────────────────────────────────────────
#  行为倾向常量
# ──────────────────────────────────────────────

RISK_CAUTIOUS = "cautious"
RISK_NEUTRAL = "neutral"
RISK_BOLD = "bold"

# help_probability 基准值
HELP_BASELINE = 0.30       # 无记忆时帮助概率
HELP_FRIENDLY = 0.65       # 友善
HELP_RESPECTFUL = 0.85     # 敬重
HELP_FAMILIAR = 0.45       # 熟悉
HELP_SUSPICIOUS = 0.20     # 警惕
HELP_HOSTILE = 0.05        # 敌对

# secret_probability 基准值
SECRET_BASELINE = 0.10
SECRET_FRIENDLY = 0.25
SECRET_RESPECTFUL = 0.45
SECRET_FAMILIAR = 0.15
SECRET_SUSPICIOUS = 0.05
SECRET_HOSTILE = 0.01

# price_bias 修正值（正数=优惠，负数=不利）
PRICE_BASELINE = 0.00
PRICE_FRIENDLY = 0.10      # +10% 优惠
PRICE_RESPECTFUL = 0.20    # +20% 优惠
PRICE_FAMILIAR = 0.00
PRICE_SUSPICIOUS = -0.10   # -10% 加价
PRICE_HOSTILE = -0.30      # -30% 加价

# risk_attitude 映射
RISK_ATTITUDE_MAP = {
    REL_HOSTILE: RISK_CAUTIOUS,
    REL_SUSPICIOUS: RISK_CAUTIOUS,
    REL_FAMILIAR: RISK_NEUTRAL,
    REL_FRIENDLY: RISK_BOLD,
    REL_RESPECTFUL: RISK_BOLD,
}


# ──────────────────────────────────────────────
#  NPCBehaviorProfile 数据类
# ──────────────────────────────────────────────

@dataclass
class NPCBehaviorProfile:
    """NPC 行为倾向档案。每次调用 calculate_behavior() 生成，不持久化。"""

    relationship: str = ""           # 关系状态
    trust_bias: float = 0.0         # 信任偏移（用于内部计算）
    help_probability: float = 0.0   # 帮助玩家的概率 [0, 1]
    secret_probability: float = 0.0 # 透露隐藏信息的概率 [0, 1]
    price_bias: float = 0.0         # 交易价格修正（正数=优惠，负数=不利）
    risk_attitude: str = RISK_NEUTRAL  # cautious / neutral / bold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relationship": self.relationship,
            "trust_bias": round(self.trust_bias, 2),
            "help_probability": round(self.help_probability, 2),
            "secret_probability": round(self.secret_probability, 2),
            "price_bias": round(self.price_bias, 2),
            "risk_attitude": self.risk_attitude,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NPCBehaviorProfile":
        return cls(
            relationship=d.get("relationship", ""),
            trust_bias=d.get("trust_bias", 0.0),
            help_probability=d.get("help_probability", 0.0),
            secret_probability=d.get("secret_probability", 0.0),
            price_bias=d.get("price_bias", 0.0),
            risk_attitude=d.get("risk_attitude", RISK_NEUTRAL),
        )


# ──────────────────────────────────────────────
#  行为计算
# ──────────────────────────────────────────────

def calculate_behavior(memories: List[Dict[str, Any]]) -> NPCBehaviorProfile:
    """根据 memory 列表计算 NPC 行为倾向。

    规则：
      - 无记忆 → unknown/低概率/中性态度
      - friendly → 高帮助率、小幅信息开放、优惠倾向
      - respectful → 最高帮助率、高信息开放、最大优惠、大胆态度
      - familiar → 普通互动水平
      - suspicious → 降低合作、谨慎态度
      - hostile → 极低帮助率、极低信息开放、不利价格、极度谨慎

    Args:
        memories: NPC 对该玩家的记忆列表（dict 格式）

    Returns:
        NPCBehaviorProfile 对象
    """
    if not memories:
        return NPCBehaviorProfile(
            relationship=REL_UNKNOWN,
            trust_bias=0.0,
            help_probability=HELP_BASELINE,
            secret_probability=SECRET_BASELINE,
            price_bias=PRICE_BASELINE,
            risk_attitude=RISK_NEUTRAL,
        )

    # 计算关系状态
    relationship = calculate_relationship(memories)

    # 根据关系状态选择参数
    if relationship == REL_FRIENDLY:
        profile = NPCBehaviorProfile(
            relationship=relationship,
            trust_bias=1.0,
            help_probability=HELP_FRIENDLY,
            secret_probability=SECRET_FRIENDLY,
            price_bias=PRICE_FRIENDLY,
            risk_attitude=RISK_BOLD,
        )
    elif relationship == REL_RESPECTFUL:
        profile = NPCBehaviorProfile(
            relationship=relationship,
            trust_bias=1.5,
            help_probability=HELP_RESPECTFUL,
            secret_probability=SECRET_RESPECTFUL,
            price_bias=PRICE_RESPECTFUL,
            risk_attitude=RISK_BOLD,
        )
    elif relationship == REL_FAMILIAR:
        profile = NPCBehaviorProfile(
            relationship=relationship,
            trust_bias=0.5,
            help_probability=HELP_FAMILIAR,
            secret_probability=SECRET_FAMILIAR,
            price_bias=PRICE_FAMILIAR,
            risk_attitude=RISK_NEUTRAL,
        )
    elif relationship == REL_SUSPICIOUS:
        profile = NPCBehaviorProfile(
            relationship=relationship,
            trust_bias=-0.5,
            help_probability=HELP_SUSPICIOUS,
            secret_probability=SECRET_SUSPICIOUS,
            price_bias=PRICE_SUSPICIOUS,
            risk_attitude=RISK_CAUTIOUS,
        )
    elif relationship == REL_HOSTILE:
        profile = NPCBehaviorProfile(
            relationship=relationship,
            trust_bias=-1.5,
            help_probability=HELP_HOSTILE,
            secret_probability=SECRET_HOSTILE,
            price_bias=PRICE_HOSTILE,
            risk_attitude=RISK_CAUTIOUS,
        )
    else:
        # unknown（理论上不会走到这里，因为 calculate_relationship 保证返回有效值）
        profile = NPCBehaviorProfile(
            relationship=REL_UNKNOWN,
            trust_bias=0.0,
            help_probability=HELP_BASELINE,
            secret_probability=SECRET_BASELINE,
            price_bias=PRICE_BASELINE,
            risk_attitude=RISK_NEUTRAL,
        )

    return profile


def calculate_behavior_from_objects(memories: list) -> NPCBehaviorProfile:
    """calculate_behavior 的便捷方法，接受 NPCMemory 对象列表。"""
    dicts = [m.to_dict() if hasattr(m, "to_dict") else m for m in memories]
    return calculate_behavior(dicts)


# ──────────────────────────────────────────────
#  身份修正（B-13）
# ──────────────────────────────────────────────

# NPC 身份 → 行为修正量
IDENTITY_MODIFIERS = {
    "长老": {"help_probability": 0.0, "secret_probability": 0.10, "price_bias": 0.0, "risk_attitude": "cautious"},
    "宗主": {"help_probability": 0.0, "secret_probability": 0.15, "price_bias": 0.0, "risk_attitude": "cautious"},
    "掌门": {"help_probability": 0.0, "secret_probability": 0.20, "price_bias": 0.0, "risk_attitude": "cautious"},
    "商人": {"help_probability": -0.05, "secret_probability": -0.05, "price_bias": 0.05, "risk_attitude": "neutral"},
    "货郎": {"help_probability": -0.05, "secret_probability": -0.05, "price_bias": 0.05, "risk_attitude": "neutral"},
    "弟子": {"help_probability": 0.05, "secret_probability": -0.05, "price_bias": 0.0, "risk_attitude": "neutral"},
    "丞相": {"help_probability": 0.0, "secret_probability": 0.15, "price_bias": 0.0, "risk_attitude": "cautious"},
    "散修": {"help_probability": 0.0, "secret_probability": 0.0, "price_bias": 0.0, "risk_attitude": "neutral"},
}

# 人格标签 → 行为修正量
PERSONALITY_MODIFIERS = {
    "谨慎": {"help_probability": -0.05, "secret_probability": -0.10, "price_bias": 0.0, "risk_attitude": "cautious"},
    "豪爽": {"help_probability": 0.10, "secret_probability": 0.05, "price_bias": -0.05, "risk_attitude": "bold"},
    "冷漠": {"help_probability": -0.10, "secret_probability": -0.10, "price_bias": 0.0, "risk_attitude": "neutral"},
    "贪婪": {"help_probability": -0.05, "secret_probability": -0.05, "price_bias": 0.10, "risk_attitude": "neutral"},
    "正直": {"help_probability": 0.10, "secret_probability": 0.05, "price_bias": 0.0, "risk_attitude": "neutral"},
    "多疑": {"help_probability": -0.10, "secret_probability": -0.15, "price_bias": 0.0, "risk_attitude": "cautious"},
}

# 敌对势力修正（faction_code 前缀）
_FACTION_TYPE_MODIFIERS = {
    "HIDDEN": {"help_probability": -0.10, "secret_probability": -0.10, "price_bias": -0.05, "risk_attitude": "cautious"},
}


def apply_identity_modifier(
    profile: NPCBehaviorProfile,
    npc_info: Dict[str, Any],
) -> NPCBehaviorProfile:
    """对行为倾向应用身份修正（B-13）。

    优先级：memory > identity > 基础人格
    身份修正只能微调，不能覆盖 memory 计算的关系。

    Args:
        profile: 由 calculate_behavior 计算的基础行为倾向
        npc_info: NPC 信息字典（含 role, faction_code, personality 等）

    Returns:
        修正后的 NPCBehaviorProfile
    """
    # 身份修正（基于 role）
    role = npc_info.get("role", "")
    for identity_key, modifier in IDENTITY_MODIFIERS.items():
        if identity_key in role:
            profile.help_probability = clamp_probability(profile.help_probability + modifier.get("help_probability", 0))
            profile.secret_probability = clamp_probability(profile.secret_probability + modifier.get("secret_probability", 0))
            profile.price_bias = max(-0.30, min(0.30, profile.price_bias + modifier.get("price_bias", 0)))
            if modifier.get("risk_attitude"):
                profile.risk_attitude = modifier["risk_attitude"]
            break

    # 势力类型修正（基于 faction_code 前缀）
    faction_code = npc_info.get("faction_code", "")
    for prefix, modifier in _FACTION_TYPE_MODIFIERS.items():
        if faction_code.startswith(prefix):
            profile.help_probability = clamp_probability(profile.help_probability + modifier.get("help_probability", 0))
            profile.secret_probability = clamp_probability(profile.secret_probability + modifier.get("secret_probability", 0))
            profile.price_bias = max(-0.30, min(0.30, profile.price_bias + modifier.get("price_bias", 0)))
            if modifier.get("risk_attitude"):
                profile.risk_attitude = modifier["risk_attitude"]
            break

    # 人格标签修正（基于 personality 字段）
    personality = npc_info.get("personality", "")
    if personality:
        for tag, modifier in PERSONALITY_MODIFIERS.items():
            if tag in personality:
                profile.help_probability = clamp_probability(profile.help_probability + modifier.get("help_probability", 0))
                profile.secret_probability = clamp_probability(profile.secret_probability + modifier.get("secret_probability", 0))
                profile.price_bias = max(-0.30, min(0.30, profile.price_bias + modifier.get("price_bias", 0)))
                if modifier.get("risk_attitude"):
                    profile.risk_attitude = modifier["risk_attitude"]

    return profile


def clamp_probability(value: float) -> float:
    """将概率值限制在 [0.01, 1.0] 范围内。"""
    return max(0.01, min(1.0, value))
