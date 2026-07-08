# -*- coding: utf-8 -*-
"""
cultivation_ability.py — 技能能力系统（LONG-A 第5阶段）

核心概念：
  CultivationAbility = 修仙技能数据模型，独立于境界。
  AbilityManager = 技能管理器，负责技能的升级、判定、效果计算。
  不直接修改 profile，只负责计算和构造合法的 delta。

设计原则：
  - 所有变更通过 EventOutcome → OutcomeApplier 写入，本模块不碰 profile。
  - 技能等级/经验/效果全部由代码计算，AI 不决定数值。
  - 技能独立于境界：低境界也可以有高技能，高境界也可能技能平平。
  - 旧存档兼容：缺失字段使用 .get(key, default) 读取。

METHOD_STATE 扩展字段：
  "abilities": {
      "剑意": {"level": 0, "exp": 0, "max_level": 5},
      "炼丹": {"level": 0, "exp": 0, "max_level": 5},
      "炼器": {"level": 0, "exp": 0, "max_level": 5},
      "阵法": {"level": 0, "exp": 0, "max_level": 5},
      "符箓": {"level": 0, "exp": 0, "max_level": 5},
  }
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────
#  常量定义
# ──────────────────────────────────────────────

# 技能名称列表
ABILITY_NAMES = ("剑意", "炼丹", "炼器", "阵法", "符箓")

# 技能最大等级
ABILITY_MAX_LEVEL = 5

# 技能等级 → 经验需求
ABILITY_EXP_REQUIREMENTS = {
    1: 10,    # 0→1: 10 exp
    2: 30,    # 1→2: 30 exp
    3: 60,    # 2→3: 60 exp
    4: 100,   # 3→4: 100 exp
    5: 200,   # 4→5: 200 exp
}

# 技能等级 → 名称
ABILITY_LEVEL_NAMES = {
    0: "未入门",
    1: "初窥",
    2: "小成",
    3: "大成",
    4: "圆满",
    5: "化境",
}

# 技能等级 → 修炼速度修正（影响相关行动的效率）
ABILITY_LEVEL_SPEED_BONUS = {
    0: 0.0,
    1: 0.1,
    2: 0.2,
    3: 0.4,
    4: 0.6,
    5: 1.0,
}

# 技能 → 对应的修炼行动关键词
ABILITY_CULTIVATION_KEYWORDS = {
    "剑意": {"练剑", "悟剑", "剑道", "挥剑", "剑修"},
    "炼丹": {"炼丹", "炼药", "丹道", "丹修", "制药"},
    "炼器": {"炼器", "锻造", "器道", "器修", "铸器"},
    "阵法": {"布阵", "阵道", "阵修", "推演阵法", "刻阵"},
    "符箓": {"画符", "符道", "符修", "制符", "刻符"},
}

# 技能 → 对应的灵根有利属性
ABILITY_FAVORABLE_ELEMENTS = {
    "剑意": ["金", "雷"],
    "炼丹": ["火", "木"],
    "炼器": ["金", "土"],
    "阵法": ["水", "空间"],
    "符箓": ["木", "风"],
}

# 技能 → 基础经验获取速率（每次修炼行动）
ABILITY_BASE_EXP_GAIN = {
    "剑意": 3,
    "炼丹": 2,
    "炼器": 2,
    "阵法": 2,
    "符箓": 2,
}

# 技能 → 境界最低要求（某些技能需要最低境界才能入门）
ABILITY_MIN_REALM = {
    "剑意": 0,   # 练气一层即可
    "炼丹": 3,   # 练气四层
    "炼器": 3,   # 练气四层
    "阵法": 5,   # 练气六层
    "符箓": 2,   # 练气三层
}


# ──────────────────────────────────────────────
#  CultivationAbility 数据类
# ──────────────────────────────────────────────

@dataclass
class CultivationAbility:
    """修仙技能数据模型。"""

    name: str = ""
    level: int = 0
    exp: int = 0
    max_level: int = ABILITY_MAX_LEVEL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "exp": self.exp,
            "max_level": self.max_level,
        }

    @property
    def level_name(self) -> str:
        """获取等级名称。"""
        return ABILITY_LEVEL_NAMES.get(self.level, "未知")

    @property
    def exp_to_next(self) -> int:
        """获取升到下一级所需的经验。"""
        if self.level >= self.max_level:
            return 0
        return ABILITY_EXP_REQUIREMENTS.get(self.level + 1, 999)

    @property
    def exp_progress(self) -> float:
        """获取当前等级的经验进度（0.0~1.0）。"""
        if self.level >= self.max_level:
            return 1.0
        required = self.exp_to_next
        if required <= 0:
            return 1.0
        prev_required = ABILITY_EXP_REQUIREMENTS.get(self.level, 0)
        current_level_exp = self.exp - prev_required
        level_range = required - prev_required
        if level_range <= 0:
            return 1.0
        return min(1.0, max(0.0, current_level_exp / level_range))

    @property
    def speed_bonus(self) -> float:
        """获取修炼速度修正。"""
        return ABILITY_LEVEL_SPEED_BONUS.get(self.level, 0.0)

    def can_level_up(self) -> bool:
        """是否可以升级。"""
        if self.level >= self.max_level:
            return False
        return self.exp >= self.exp_to_next


# ──────────────────────────────────────────────
#  AbilityManager 技能管理器
# ──────────────────────────────────────────────

class AbilityManager:
    """技能管理器，负责技能的升级、判定、效果计算。"""

    def extract_abilities(self, profile: Dict[str, Any]) -> Dict[str, CultivationAbility]:
        """从 profile 中提取所有技能。

        Args:
            profile: 玩家档案

        Returns:
            {ability_name: CultivationAbility}
        """
        method = profile.get("METHOD_STATE", {})
        abilities_data = method.get("abilities", {})

        result = {}
        for name in ABILITY_NAMES:
            data = abilities_data.get(name, {})
            if isinstance(data, dict):
                result[name] = CultivationAbility(
                    name=name,
                    level=data.get("level", 0),
                    exp=data.get("exp", 0),
                    max_level=data.get("max_level", ABILITY_MAX_LEVEL),
                )
            else:
                result[name] = CultivationAbility(name=name)

        return result

    def get_ability(self, profile: Dict[str, Any], ability_name: str) -> CultivationAbility:
        """获取单个技能。"""
        abilities = self.extract_abilities(profile)
        return abilities.get(ability_name, CultivationAbility(name=ability_name))

    def can_learn(self, profile: Dict[str, Any], ability_name: str) -> Tuple[bool, str]:
        """判断是否可以学习某技能。

        条件：
          1. 境界达到最低要求
          2. 技能未满级

        Args:
            profile: 玩家档案
            ability_name: 技能名称

        Returns:
            (是否可以学习, 原因)
        """
        ability = self.get_ability(profile, ability_name)

        if ability.level >= ability.max_level:
            return False, f"{ability_name}已满级"

        # 境界要求
        min_realm = ABILITY_MIN_REALM.get(ability_name, 0)
        current_realm = profile.get("cultivation_realm", "练气一层")
        realm_idx = self._get_realm_index(current_realm)
        if realm_idx < min_realm:
            return False, f"境界不足（需要≥{self._realm_idx_to_name(min_realm)}）"

        return True, ""

    def calculate_exp_gain(
        self,
        ability_name: str,
        action_type: str = "practice",
        luck_level: str = "成功",
        spiritual_root: Any = None,
    ) -> int:
        """计算技能经验获取量。

        经验 = 基础获取 × 运气修正 × 灵根亲和修正

        Args:
            ability_name: 技能名称
            action_type: 行动类型（practice/practice_with_teacher/use_in_combat）
            luck_level: 运气等级
            spiritual_root: 灵根状态

        Returns:
            获得的经验值
        """
        base = ABILITY_BASE_EXP_GAIN.get(ability_name, 2)

        # 行动类型修正
        action_mult = {
            "practice": 1.0,
            "practice_with_teacher": 1.5,
            "use_in_combat": 0.8,
            "enlightenment": 3.0,
        }.get(action_type, 1.0)

        # 运气修正
        luck_mult = {
            "极大成功": 2.0,
            "大成功": 1.5,
            "成功": 1.0,
            "失败": 0.3,
            "大失败": 0.0,
        }.get(luck_level, 1.0)

        # 灵根亲和修正
        root_mult = 1.0
        if spiritual_root is not None:
            root_element = spiritual_root.primary if hasattr(spiritual_root, 'primary') else "金"
            favorable = ABILITY_FAVORABLE_ELEMENTS.get(ability_name, [])
            if root_element in favorable:
                root_mult = 1.3
            # 异变灵根检查
            mutation = spiritual_root.mutation if hasattr(spiritual_root, 'mutation') else "none"
            if mutation != "none" and mutation in favorable:
                root_mult = max(root_mult, 1.5)

        exp = int(base * action_mult * luck_mult * root_mult)
        return max(0, exp)

    def add_exp(
        self,
        ability: CultivationAbility,
        exp_gain: int,
    ) -> Tuple[CultivationAbility, bool]:
        """给技能增加经验，检查是否升级。

        Args:
            ability: 技能对象
            exp_gain: 经验增量

        Returns:
            (更新后的技能, 是否升级)
        """
        ability.exp += exp_gain
        leveled_up = False

        while ability.can_level_up():
            ability.level += 1
            leveled_up = True

        return ability, leveled_up

    def check_ability_action(
        self,
        ability: CultivationAbility,
        difficulty: int = 10,
        seed: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """技能行动检定。

        1d20 + 技能等级×2 vs 难度 DC

        Args:
            ability: 技能对象
            difficulty: 难度 DC
            seed: 随机种子

        Returns:
            (是否成功, 掷骰结果)
        """
        rng = random.Random(seed) if seed is not None else random
        roll = rng.randint(1, 20) + ability.level * 2
        return roll >= difficulty, roll

    def get_ability_effects(self, ability: CultivationAbility) -> Dict[str, Any]:
        """获取技能效果描述。

        Args:
            ability: 技能对象

        Returns:
            效果描述 dict
        """
        effects = {
            "speed_bonus": ability.speed_bonus,
            "level_name": ability.level_name,
        }

        # 根据技能类型和等级添加具体效果
        if ability.name == "剑意":
            effects.update(self._sword_intent_effects(ability))
        elif ability.name == "炼丹":
            effects.update(self._alchemy_effects(ability))
        elif ability.name == "炼器":
            effects.update(self._forging_effects(ability))
        elif ability.name == "阵法":
            effects.update(self._formation_effects(ability))
        elif ability.name == "符箓":
            effects.update(self._talisman_effects(ability))

        return effects

    def _sword_intent_effects(self, ability: CultivationAbility) -> Dict[str, Any]:
        """剑意效果。"""
        return {
            "attack_bonus": ability.level * 2,
            "crit_chance": ability.level * 0.05,
            "desc": f"剑气加成+{ability.level * 2}，暴击率+{ability.level * 5}%",
        }

    def _alchemy_effects(self, ability: CultivationAbility) -> Dict[str, Any]:
        """炼丹效果。"""
        return {
            "pill_quality_bonus": ability.level,
            "pill_success_rate": 0.5 + ability.level * 0.1,
            "desc": f"丹药品质+{ability.level}，炼丹成功率{50 + ability.level * 10}%",
        }

    def _forging_effects(self, ability: CultivationAbility) -> Dict[str, Any]:
        """炼器效果。"""
        return {
            "item_quality_bonus": ability.level,
            "forge_success_rate": 0.5 + ability.level * 0.1,
            "desc": f"器物品质+{ability.level}，炼器成功率{50 + ability.level * 10}%",
        }

    def _formation_effects(self, ability: CultivationAbility) -> Dict[str, Any]:
        """阵法效果。"""
        return {
            "formation_power": ability.level * 2,
            "formation_duration": 1 + ability.level,
            "desc": f"阵法威力+{ability.level * 2}，持续{1 + ability.level}回合",
        }

    def _talisman_effects(self, ability: CultivationAbility) -> Dict[str, Any]:
        """符箓效果。"""
        return {
            "talisman_power": ability.level * 2,
            "talisman_count": 1 + ability.level,
            "desc": f"符箓威力+{ability.level * 2}，可同时激活{1 + ability.level}张",
        }

    def _get_realm_index(self, realm: str) -> int:
        """获取境界索引。"""
        REALMS = ["练气一层","练气二层","练气三层","练气四层","练气五层",
                  "练气六层","练气七层","练气八层","练气九层",
                  "筑基初期","筑基中期","筑基后期","筑基巅峰",
                  "金丹初期"]
        try:
            return REALMS.index(realm)
        except ValueError:
            return 0

    def _realm_idx_to_name(self, idx: int) -> str:
        """境界索引转名称。"""
        REALMS = ["练气一层","练气二层","练气三层","练气四层","练气五层",
                  "练气六层","练气七层","练气八层","练气九层",
                  "筑基初期","筑基中期","筑基后期","筑基巅峰",
                  "金丹初期"]
        if 0 <= idx < len(REALMS):
            return REALMS[idx]
        return "练气一层"


# ──────────────────────────────────────────────
#  技能描述生成
# ──────────────────────────────────────────────

def describe_ability(ability: CultivationAbility) -> str:
    """生成技能的人类可读描述。

    Args:
        ability: 技能对象

    Returns:
        描述字符串
    """
    if ability.level == 0:
        return f"{ability.name}：未入门"

    parts = [f"{ability.name}（{ability.level_name}）"]

    if ability.level < ability.max_level:
        parts.append(f"经验{ability.exp}/{ability.exp_to_next}")
    else:
        parts.append("已满级")

    # 效果描述
    manager = AbilityManager()
    effects = manager.get_ability_effects(ability)
    desc = effects.get("desc", "")
    if desc:
        parts.append(desc)

    return "　".join(parts)


def describe_all_abilities(profile: Dict[str, Any]) -> str:
    """生成所有技能的描述。

    Args:
        profile: 玩家档案

    Returns:
        描述字符串
    """
    manager = AbilityManager()
    abilities = manager.extract_abilities(profile)

    lines = []
    for name in ABILITY_NAMES:
        ability = abilities.get(name, CultivationAbility(name=name))
        if ability.level > 0:
            lines.append(describe_ability(ability))

    if not lines:
        return "尚未入门任何技能"

    return "\n".join(lines)


# ──────────────────────────────────────────────
#  旧存档迁移
# ──────────────────────────────────────────────

def migrate_profile_abilities(profile: Dict[str, Any]) -> Dict[str, Any]:
    """为旧存档补全技能字段。

    Args:
        profile: 玩家档案 dict

    Returns:
        修改后的 profile
    """
    method = profile.setdefault("METHOD_STATE", {})

    if "abilities" not in method:
        method["abilities"] = _default_abilities()
    else:
        # 补全缺失的技能
        existing = method["abilities"]
        for name in ABILITY_NAMES:
            if name not in existing:
                existing[name] = {"level": 0, "exp": 0, "max_level": ABILITY_MAX_LEVEL}
            elif isinstance(existing[name], dict):
                # 确保字段完整
                if "max_level" not in existing[name]:
                    existing[name]["max_level"] = ABILITY_MAX_LEVEL

    return profile


def _default_abilities() -> Dict[str, Any]:
    """生成默认能力表。"""
    return {
        name: {"level": 0, "exp": 0, "max_level": ABILITY_MAX_LEVEL}
        for name in ABILITY_NAMES
    }


# ──────────────────────────────────────────────
#  构造 METHOD_STATE delta（供 OutcomeApplier 使用）
# ──────────────────────────────────────────────

def make_ability_delta(
    ability_name: str,
    exp_delta: Optional[int] = None,
    level: Optional[int] = None,
) -> Dict[str, Any]:
    """构造技能变更的 delta dict。

    Args:
        ability_name: 技能名称
        exp_delta: 经验变化量
        level: 新等级（绝对值）

    Returns:
        METHOD_STATE.abilities delta dict
    """
    ability_delta: Dict[str, Any] = {}

    if exp_delta is not None:
        ability_delta["exp"] = exp_delta
    if level is not None:
        ability_delta["level"] = level

    if not ability_delta:
        return {}

    return {"abilities": {ability_name: ability_delta}}
