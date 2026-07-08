# -*- coding: utf-8 -*-
"""
spiritual_root.py — 灵根系统（LONG-A 第3阶段）

核心概念：
  SpiritualRoot = 玩家灵根属性的计算和判定模型。
  不直接修改 profile，只负责计算和构造合法的 delta。

设计原则：
  - 所有变更通过 EventOutcome → OutcomeApplier 写入，本模块不碰 profile。
  - 灵根效率 / 功法亲和 / 突破风险 全部由代码计算，AI 不决定数值。
  - 旧存档兼容：缺失字段使用 .get(key, default) 读取。
  - 复用现有 CORE_STATE 字段，扩展不破坏旧结构。

CORE_STATE 扩展字段：
  "spiritual_root": {
      "primary": "金",           # 主灵根属性
      "secondary": [],           # 副灵根属性列表
      "purity": 0.7,             # 灵根纯度 0.1~1.0
      "mutation": "none",        # 异变类型：none/雷/冰/风/空间
      "efficiency": 1.0,         # 修炼效率倍率（由纯度+异变综合计算）
  }
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────
#  五行灵根定义
# ──────────────────────────────────────────────

# 五行灵根：金/木/水/火/土
FIVE_ELEMENTS = ("金", "木", "水", "火", "土")

# 五行相生：金→水→木→火→土→金
ELEMENT_GENERATES = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}

# 五行相克：金→木→土→水→火→金
ELEMENT_OVERCOMES = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}

# 特殊灵根（异变灵根）
SPECIAL_ROOTS = ("雷", "冰", "风", "空间")

# 所有灵根属性
ALL_ROOT_ELEMENTS = FIVE_ELEMENTS + SPECIAL_ROOTS

# 灵根属性 → 中文描述
ELEMENT_NAMES = {
    "金": "金行", "木": "木行", "水": "水行", "火": "火行", "土": "土行",
    "雷": "雷属", "冰": "冰属", "风": "风属", "空间": "空间属",
}

# 灵根属性 → 修炼风格描述
ELEMENT_CULTIVATION_STYLE = {
    "金": "锋锐刚猛，攻伐之道",
    "木": "生机绵长，恢复之道",
    "水": "柔韧多变，适应之道",
    "火": "爆裂炽热，毁灭之道",
    "土": "厚重稳固，防御之道",
    "雷": "迅疾霸道，天罚之道",
    "冰": "凛冽肃杀，封禁之道",
    "风": "飘逸无形，遁走之道",
    "空间": "玄奥莫测，虚空之道",
}


# ──────────────────────────────────────────────
#  灵根纯度等级
# ──────────────────────────────────────────────

# 纯度 → 等级名称 → 修炼效率倍率
PURITY_TIERS = {
    (0.9, 1.0): {"name": "天灵根", "efficiency": 2.0, "desc": "单属性极致纯化，修炼速度极快"},
    (0.7, 0.9): {"name": "真灵根", "efficiency": 1.5, "desc": "主属性高度凝聚，修炼速度较快"},
    (0.5, 0.7): {"name": "灵根", "efficiency": 1.0, "desc": "主属性正常凝聚，修炼速度正常"},
    (0.3, 0.5): {"name": "杂灵根", "efficiency": 0.7, "desc": "主属性分散，修炼速度较慢"},
    (0.1, 0.3): {"name": "废灵根", "efficiency": 0.4, "desc": "主属性极度分散，修炼极难"},
}

# 纯度范围
PURITY_MIN = 0.1
PURITY_MAX = 1.0
PURITY_DEFAULT = 0.5


# ──────────────────────────────────────────────
#  异变灵根权重和效果
# ──────────────────────────────────────────────

# 异变灵根生成概率（在灵根生成时的触发概率）
MUTATION_PROBABILITY = 0.05  # 5% 概率出现异变

# 异变灵根 → 修炼效率修正
MUTATION_EFFICIENCY_BONUS = {
    "none": 0.0,
    "雷": 0.3,    # 雷属：修炼效率 +30%
    "冰": 0.2,    # 冰属：修炼效率 +20%
    "风": 0.15,   # 风属：修炼效率 +15%
    "空间": 0.5,  # 空间属：修炼效率 +50%（极稀有）
}

# 异变灵根 → 突破风险修正
MUTATION_BREAKTHROUGH_RISK = {
    "none": 0.0,
    "雷": 0.1,    # 雷属：突破时天劫概率 +10%
    "冰": -0.05,  # 冰属：突破反噬概率 -5%
    "风": -0.03,  # 风属：突破反噬概率 -3%
    "空间": 0.15, # 空间属：突破时空间裂缝概率 +15%
}

# 异变灵根 → 触发五行
MUTATION_TRIGGER_ELEMENT = {
    "雷": "水",   # 水行异变→雷
    "冰": "水",   # 水行异变→冰
    "风": "木",   # 木行异变→风
    "空间": "土", # 土行异变→空间
}

# 异变灵根生成权重
MUTATION_WEIGHTS = {
    "雷": 40,
    "冰": 30,
    "风": 20,
    "空间": 10,
}


# ──────────────────────────────────────────────
#  灵根属性亲和度矩阵
# ──────────────────────────────────────────────

# 灵根属性 → 功法属性亲和度（1.0=完全匹配，0.5=相生，0.3=中性，0.1=相克）
_AFFINITY_MATRIX = {
    # 同属性：完全匹配
    "金": {"金": 1.0, "水": 0.5, "木": 0.1, "火": 0.3, "土": 0.5, "无": 0.4},
    "木": {"木": 1.0, "火": 0.5, "土": 0.1, "金": 0.3, "水": 0.5, "无": 0.4},
    "水": {"水": 1.0, "木": 0.5, "火": 0.1, "土": 0.3, "金": 0.5, "无": 0.4},
    "火": {"火": 1.0, "土": 0.5, "金": 0.1, "水": 0.3, "木": 0.5, "无": 0.4},
    "土": {"土": 1.0, "金": 0.5, "水": 0.1, "木": 0.3, "火": 0.5, "无": 0.4},
    # 异变灵根的亲和度
    "雷": {"雷": 1.0, "水": 0.7, "金": 0.5, "火": 0.3, "木": 0.2, "土": 0.2, "无": 0.4},
    "冰": {"冰": 1.0, "水": 0.7, "金": 0.3, "火": 0.1, "木": 0.2, "土": 0.2, "无": 0.4},
    "风": {"风": 1.0, "木": 0.7, "水": 0.3, "火": 0.2, "金": 0.2, "土": 0.1, "无": 0.4},
    "空间": {"空间": 1.0, "土": 0.7, "金": 0.3, "水": 0.2, "火": 0.2, "木": 0.1, "无": 0.4},
}


# ──────────────────────────────────────────────
#  SpiritualRoot 数据类
# ──────────────────────────────────────────────

@dataclass
class SpiritualRoot:
    """灵根状态快照。从 profile 中提取后使用，不持有引用。"""

    primary: str = "金"           # 主灵根属性
    secondary: List[str] = field(default_factory=list)  # 副灵根属性
    purity: float = PURITY_DEFAULT  # 灵根纯度 0.1~1.0
    mutation: str = "none"        # 异变类型
    efficiency: float = 1.0       # 修炼效率倍率（由纯度+异变综合计算）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primary": self.primary,
            "secondary": self.secondary,
            "purity": self.purity,
            "mutation": self.mutation,
            "efficiency": self.efficiency,
        }

    @property
    def purity_tier(self) -> str:
        """获取纯度等级名称。"""
        for (lo, hi), info in PURITY_TIERS.items():
            if lo <= self.purity <= hi:
                return info["name"]
        return "灵根"

    @property
    def display_name(self) -> str:
        """获取灵根显示名称（如"天灵根·金"或"雷属异变灵根"）。"""
        if self.mutation != "none":
            return f"{ELEMENT_NAMES.get(self.mutation, self.mutation)}异变灵根"
        return f"{self.purity_tier}·{ELEMENT_NAMES.get(self.primary, self.primary)}"


# ──────────────────────────────────────────────
#  从 profile 提取灵根
# ──────────────────────────────────────────────

def extract_spiritual_root(profile: Dict[str, Any]) -> SpiritualRoot:
    """从玩家 profile 中提取灵根状态。

    旧存档兼容：
      - 如果 CORE_STATE.spiritual_root 存在，使用新结构
      - 否则从旧的 spirit_root_element / spirit_root_tier 推导

    Args:
        profile: 玩家档案 dict

    Returns:
        SpiritualRoot 对象
    """
    core = profile.get("CORE_STATE", {})

    # 尝试读取新结构
    sr_data = core.get("spiritual_root")
    if sr_data and isinstance(sr_data, dict):
        return SpiritualRoot(
            primary=sr_data.get("primary", "金"),
            secondary=sr_data.get("secondary", []),
            purity=sr_data.get("purity", PURITY_DEFAULT),
            mutation=sr_data.get("mutation", "none"),
            efficiency=sr_data.get("efficiency", 1.0),
        )

    # 旧存档兼容：从 spirit_root_element 和 spirit_root_tier 推导
    element = core.get("spirit_root_element", "金")
    tier = core.get("spirit_root_tier", 3)

    # 从 tier 推导纯度（tier 越高纯度越高）
    purity = _tier_to_purity(tier)

    # 检查 element 是否是异变灵根
    mutation = "none"
    primary = element
    if element in SPECIAL_ROOTS:
        mutation = element
        primary = MUTATION_TRIGGER_ELEMENT.get(element, "水")

    # 计算效率
    efficiency = calculate_cultivation_efficiency(purity, mutation)

    return SpiritualRoot(
        primary=primary,
        secondary=[],
        purity=purity,
        mutation=mutation,
        efficiency=efficiency,
    )


def _tier_to_purity(tier: Any) -> float:
    """将旧的灵根等级（1~5阶）转换为纯度值。

    旧 tier 映射：
      1阶 → 0.2（废灵根）
      2阶 → 0.35（杂灵根）
      3阶 → 0.5（灵根）
      4阶 → 0.75（真灵根）
      5阶 → 0.95（天灵根）
    """
    try:
        t = int(tier)
    except (ValueError, TypeError):
        t = 3
    mapping = {1: 0.2, 2: 0.35, 3: 0.5, 4: 0.75, 5: 0.95}
    return mapping.get(t, 0.5)


# ──────────────────────────────────────────────
#  修炼效率计算
# ──────────────────────────────────────────────

def calculate_cultivation_efficiency(
    purity: float = PURITY_DEFAULT,
    mutation: str = "none",
) -> float:
    """计算灵根修炼效率倍率。

    效率 = 纯度等级效率 + 异变加成

    Args:
        purity: 灵根纯度 0.1~1.0
        mutation: 异变类型

    Returns:
        修炼效率倍率（0.3~3.0）
    """
    # 根据纯度确定基础效率
    base_efficiency = 1.0
    for (lo, hi), info in PURITY_TIERS.items():
        if lo <= purity <= hi:
            base_efficiency = info["efficiency"]
            break

    # 异变加成
    mutation_bonus = MUTATION_EFFICIENCY_BONUS.get(mutation, 0.0)

    total = base_efficiency + mutation_bonus

    # clamp 到合理范围
    return max(0.3, min(3.0, total))


# ──────────────────────────────────────────────
#  功法亲和度计算
# ──────────────────────────────────────────────

def calculate_technique_affinity(
    spiritual_root: SpiritualRoot,
    technique_element: str,
) -> float:
    """计算灵根与功法属性的亲和度。

    亲和度决定：
      - 功法修炼速度倍率
      - 功法领悟难度
      - 功法威力加成

    规则：
      - 同属性：1.0（完全匹配）
      - 相生属性：0.5（辅助修炼）
      - 相克属性：0.1（极难修炼）
      - 中性属性：0.3（勉强修炼）
      - 异变灵根对触发五行有额外加成

    副灵根也会影响亲和度：取主灵根和副灵根中的最高亲和度，
    但副灵根的亲和度要打 0.6 折扣。

    Args:
        spiritual_root: 灵根状态
        technique_element: 功法属性

    Returns:
        亲和度 0.0~1.0
    """
    # 主灵根亲和度
    primary_affinity = _get_element_affinity(spiritual_root.primary, technique_element)

    # 异变灵根额外亲和度
    mutation_affinity = 0.0
    if spiritual_root.mutation != "none":
        mutation_affinity = _get_element_affinity(spiritual_root.mutation, technique_element)

    # 副灵根亲和度（取最高，打 0.6 折扣）
    secondary_affinity = 0.0
    for sec in spiritual_root.secondary:
        sec_aff = _get_element_affinity(sec, technique_element)
        secondary_affinity = max(secondary_affinity, sec_aff * 0.6)

    # 取三者中的最高值
    best = max(primary_affinity, mutation_affinity, secondary_affinity)

    # 纯度修正：纯度越高，亲和度越接近理论最大值
    purity_factor = 0.5 + 0.5 * spiritual_root.purity
    result = best * purity_factor

    return max(0.0, min(1.0, result))


def _get_element_affinity(root_element: str, technique_element: str) -> float:
    """获取单属性亲和度。"""
    row = _AFFINITY_MATRIX.get(root_element, {})
    return row.get(technique_element, 0.2)


# ──────────────────────────────────────────────
#  突破风险计算
# ──────────────────────────────────────────────

def calculate_breakthrough_risk(
    spiritual_root: SpiritualRoot,
    is_boundary: bool = False,
) -> Dict[str, Any]:
    """计算灵根对突破风险的影响。

    风险类型：
      - "backlash": 反噬概率（失败时额外伤害）
      - "tribulation": 天劫概率（大境界突破时触发）
      - "mutation_risk": 异变失控概率（异变灵根特有）

    Args:
        spiritual_root: 灵根状态
        is_boundary: 是否是大境界瓶颈点

    Returns:
        {"backlash": float, "tribulation": float, "mutation_risk": float}
    """
    # 基础反噬概率
    # 纯度越低，反噬概率越高
    base_backlash = max(0.0, 0.3 - spiritual_root.purity * 0.3)

    # 异变灵根修正
    mutation_risk_mod = MUTATION_BREAKTHROUGH_RISK.get(spiritual_root.mutation, 0.0)

    # 大境界突破时风险放大
    boundary_mult = 2.0 if is_boundary else 1.0

    backlash = min(0.8, (base_backlash + mutation_risk_mod) * boundary_mult)

    # 天劫概率：只有大境界突破才可能触发
    tribulation = 0.0
    if is_boundary:
        # 基础天劫概率 5%
        tribulation = 0.05
        # 异变灵根增加天劫概率
        if spiritual_root.mutation == "雷":
            tribulation += 0.15
        elif spiritual_root.mutation == "空间":
            tribulation += 0.10
        # 纯度越高，越容易引来天劫（天道关注）
        tribulation += spiritual_root.purity * 0.05
        tribulation = min(0.4, tribulation)

    # 异变失控概率
    mutation_risk = 0.0
    if spiritual_root.mutation != "none":
        # 异变灵根在突破时有概率失控
        mutation_risk = 0.05 * boundary_mult
        if spiritual_root.mutation == "空间":
            mutation_risk = 0.10 * boundary_mult

    return {
        "backlash": round(backlash, 3),
        "tribulation": round(tribulation, 3),
        "mutation_risk": round(mutation_risk, 3),
    }


# ──────────────────────────────────────────────
#  灵根生成
# ──────────────────────────────────────────────

def generate_spiritual_root(
    seed: Optional[int] = None,
    force_mutation: Optional[str] = None,
) -> SpiritualRoot:
    """随机生成灵根。

    生成规则：
      1. 随机选择主灵根属性（五行均匀分布）
      2. 随机生成纯度（正态分布，均值 0.5）
      3. 5% 概率触发异变
      4. 异变类型按权重随机选择
      5. 副灵根：纯度<0.7 时有概率出现副灵根

    Args:
        seed: 随机种子（用于可复现的角色生成）
        force_mutation: 强制异变类型（用于测试或特殊角色）

    Returns:
        SpiritualRoot 对象
    """
    rng = random.Random(seed) if seed is not None else random

    # 1. 主灵根属性
    primary = rng.choice(FIVE_ELEMENTS)

    # 2. 纯度：正态分布，均值 0.5，标准差 0.2
    purity = rng.gauss(0.5, 0.2)
    purity = max(PURITY_MIN, min(PURITY_MAX, purity))

    # 3. 异变
    mutation = "none"
    if force_mutation and force_mutation in SPECIAL_ROOTS:
        mutation = force_mutation
    elif rng.random() < MUTATION_PROBABILITY:
        # 按权重选择异变类型
        weights = [MUTATION_WEIGHTS.get(m, 0) for m in SPECIAL_ROOTS]
        total = sum(weights)
        if total > 0:
            r = rng.random() * total
            cumulative = 0
            for m, w in zip(SPECIAL_ROOTS, weights):
                cumulative += w
                if r <= cumulative:
                    mutation = m
                    break

    # 4. 副灵根：纯度越低越可能有副灵根
    secondary = []
    if purity < 0.7:
        # 副灵根数量：纯度越低越多
        num_secondary_prob = 1.0 - purity  # 0.3~0.7 的概率
        if rng.random() < num_secondary_prob:
            # 选择与主灵根相生的属性作为副灵根
            generates = ELEMENT_GENERATES.get(primary, "")
            if generates:
                secondary.append(generates)
            # 纯度很低时可能有第二个副灵根
            if purity < 0.4 and rng.random() < 0.3:
                overcomes = ELEMENT_OVERCOMES.get(primary, "")
                if overcomes and overcomes not in secondary:
                    secondary.append(overcomes)

    # 5. 计算效率
    efficiency = calculate_cultivation_efficiency(purity, mutation)

    return SpiritualRoot(
        primary=primary,
        secondary=secondary,
        purity=round(purity, 2),
        mutation=mutation,
        efficiency=round(efficiency, 2),
    )


# ──────────────────────────────────────────────
#  灵根纯度变化
# ──────────────────────────────────────────────

def calculate_purity_change(
    current_purity: float,
    event_type: str,
    is_boundary: bool = False,
) -> float:
    """计算灵根纯度变化量。

    纯度变化来源：
      - 突破成功：纯度 +0.02（大境界 +0.05）
      - 突破失败：纯度 -0.01（大境界 -0.03）
      - 服用洗髓丹：纯度 +0.1
      - 根基受损：纯度 -0.02
      - 天劫渡过：纯度 +0.1

    Args:
        current_purity: 当前纯度
        event_type: 事件类型
        is_boundary: 是否是大境界

    Returns:
        纯度变化量（可为负数）
    """
    if event_type == "breakthrough_success":
        return 0.05 if is_boundary else 0.02
    elif event_type == "breakthrough_failure":
        return -0.03 if is_boundary else -0.01
    elif event_type == "pill_cleansing":
        return 0.1
    elif event_type == "foundation_damage":
        return -0.02
    elif event_type == "tribulation_survived":
        return 0.1
    return 0.0


def clamp_purity(value: float) -> float:
    """纯度 clamp 到合法范围。"""
    return max(PURITY_MIN, min(PURITY_MAX, round(value, 2)))


# ──────────────────────────────────────────────
#  灵根对功法修炼速度的影响
# ──────────────────────────────────────────────

def calculate_technique_speed_bonus(
    spiritual_root: SpiritualRoot,
    technique_element: str,
    technique_tier: str = "黄级",
) -> float:
    """计算灵根对功法修炼速度的加成。

    速度加成 = 亲和度 × 纯度修正 × 品阶修正

    品阶修正：
      - 黄级：1.0（基础）
      - 玄级：0.8（需要更高亲和度才能发挥）
      - 地级：0.6
      - 天级：0.4

    Args:
        spiritual_root: 灵根状态
        technique_element: 功法属性
        technique_tier: 功法品阶

    Returns:
        修炼速度倍率 0.1~2.0
    """
    affinity = calculate_technique_affinity(spiritual_root, technique_element)

    # 纯度修正
    purity_factor = 0.5 + 0.5 * spiritual_root.purity

    # 品阶修正：品阶越高，对灵根匹配度要求越严
    tier_factor = {"黄级": 1.0, "玄级": 0.8, "地级": 0.6, "天级": 0.4}.get(technique_tier, 1.0)

    speed = affinity * purity_factor / tier_factor

    # 亲和度太低时，修炼速度极慢但不会完全为零
    if affinity < 0.2:
        speed = max(0.1, speed)

    return max(0.1, min(2.0, round(speed, 2)))


# ──────────────────────────────────────────────
#  灵根对突破概率的影响
# ──────────────────────────────────────────────

def calculate_breakthrough_bonus(
    spiritual_root: SpiritualRoot,
) -> float:
    """计算灵根对突破概率的加成。

    加成来源：
      - 纯度越高，突破越容易（专注度更高）
      - 异变灵根有额外加成（但风险也更高）

    Args:
        spiritual_root: 灵根状态

    Returns:
        突破概率加成 0.0~0.3
    """
    # 纯度加成：0.0.0~0.15
    purity_bonus = (spiritual_root.purity - 0.5) * 0.3
    purity_bonus = max(0.0, purity_bonus)

    # 异变加成
    mutation_bonus = 0.0
    if spiritual_root.mutation != "none":
        # 异变灵根突破加成
        mutation_bonus = {
            "雷": 0.1,
            "冰": 0.05,
            "风": 0.05,
            "空间": 0.15,
        }.get(spiritual_root.mutation, 0.0)

    return max(0.0, min(0.3, round(purity_bonus + mutation_bonus, 2)))


# ──────────────────────────────────────────────
#  旧存档迁移
# ──────────────────────────────────────────────

def migrate_profile_spiritual_root(profile: Dict[str, Any]) -> Dict[str, Any]:
    """为旧存档补全新灵根结构。

    从旧的 CORE_STATE.spirit_root_element / spirit_root_tier 推导新结构，
    不破坏已有内容。

    Args:
        profile: 玩家档案 dict（会被就地修改）

    Returns:
        修改后的 profile（同一引用）
    """
    core = profile.setdefault("CORE_STATE", {})

    # 如果已有新结构，跳过
    if "spiritual_root" in core and isinstance(core["spiritual_root"], dict):
        # 确保效率字段存在
        sr = core["spiritual_root"]
        if "efficiency" not in sr:
            sr["efficiency"] = calculate_cultivation_efficiency(
                sr.get("purity", PURITY_DEFAULT),
                sr.get("mutation", "none"),
            )
        return profile

    # 从旧字段推导
    element = core.get("spirit_root_element", "金")
    tier = core.get("spirit_root_tier", 3)

    purity = _tier_to_purity(tier)

    # 检查是否是异变灵根
    mutation = "none"
    primary = element
    if element in SPECIAL_ROOTS:
        mutation = element
        primary = MUTATION_TRIGGER_ELEMENT.get(element, "水")

    efficiency = calculate_cultivation_efficiency(purity, mutation)

    core["spiritual_root"] = {
        "primary": primary,
        "secondary": [],
        "purity": purity,
        "mutation": mutation,
        "efficiency": round(efficiency, 2),
    }

    return profile


# ──────────────────────────────────────────────
#  构造 CORE_STATE delta（供 OutcomeApplier 使用）
# ──────────────────────────────────────────────

def make_core_state_delta(
    purity_delta: Optional[float] = None,
    mutation: Optional[str] = None,
    efficiency: Optional[float] = None,
    spiritual_root: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造 CORE_STATE 的灵根 delta dict。

    只包含需要变更的字段。调用方将此 delta 包装进 profile_delta，
    交给 OutcomeApplier 写入。

    注意：purity_delta 是增量（变化量），其他字段是绝对值。

    Args:
        purity_delta: 纯度变化量
        mutation: 新的异变类型（绝对值）
        efficiency: 新的修炼效率（绝对值）
        spiritual_root: 完整的灵根子结构（绝对值，整体替换）

    Returns:
        CORE_STATE delta dict
    """
    delta: Dict[str, Any] = {}

    if spiritual_root is not None:
        # 整体替换灵根子结构
        delta["spiritual_root"] = spiritual_root
        return delta

    # 增量修改
    sr_delta: Dict[str, Any] = {}

    if purity_delta is not None:
        sr_delta["purity"] = purity_delta  # 增量
    if mutation is not None:
        sr_delta["mutation"] = mutation  # 绝对值
    if efficiency is not None:
        sr_delta["efficiency"] = efficiency  # 绝对值

    if sr_delta:
        delta["spiritual_root"] = sr_delta

    return delta


# ──────────────────────────────────────────────
#  灵根描述生成（用于 /dh status 展示）
# ──────────────────────────────────────────────

def describe_spiritual_root(spiritual_root: SpiritualRoot) -> str:
    """生成灵根的人类可读描述。

    Args:
        spiritual_root: 灵根状态

    Returns:
        描述字符串
    """
    parts = []

    # 主灵根
    parts.append(f"{ELEMENT_NAMES.get(spiritual_root.primary, spiritual_root.primary)}灵根")

    # 纯度等级
    parts.append(f"（{spiritual_root.purity_tier}，纯度{spiritual_root.purity:.0%}）")

    # 副灵根
    if spiritual_root.secondary:
        sec_names = "、".join(
            ELEMENT_NAMES.get(s, s) for s in spiritual_root.secondary
        )
        parts.append(f"兼修{sec_names}")

    # 异变
    if spiritual_root.mutation != "none":
        parts.append(f"异变为{ELEMENT_NAMES.get(spiritual_root.mutation, spiritual_root.mutation)}")

    # 效率
    parts.append(f"修炼效率×{spiritual_root.efficiency:.1f}")

    return "　".join(parts)


# ──────────────────────────────────────────────
#  灵根对能力的影响
# ──────────────────────────────────────────────

def calculate_ability_affinity(
    spiritual_root: SpiritualRoot,
    ability_name: str,
) -> float:
    """计算灵根对特定能力的亲和度。

    能力亲和度决定能力升级速度和上限。

    规则：
      - 剑意：金行/雷属加成
      - 炼丹：火行加成
      - 炼器：金行/土行加成
      - 阵法：水行/空间属加成
      - 符箓：木行/风属加成

    Args:
        spiritual_root: 灵根状态
        ability_name: 能力名称

    Returns:
        亲和度 0.5~2.0
    """
    # 能力 → 有利灵根属性 → 加成倍率
    ABILITY_ELEMENT_BONUS = {
        "剑意": {"金": 1.5, "雷": 1.3, "火": 1.1},
        "炼丹": {"火": 1.5, "木": 1.2, "水": 1.1},
        "炼器": {"金": 1.4, "土": 1.3, "火": 1.2},
        "阵法": {"水": 1.4, "空间": 1.5, "土": 1.1},
        "符箓": {"木": 1.4, "风": 1.3, "水": 1.1},
    }

    bonus_map = ABILITY_ELEMENT_BONUS.get(ability_name, {})
    if not bonus_map:
        return 1.0

    # 检查主灵根
    primary_bonus = bonus_map.get(spiritual_root.primary, 1.0)

    # 检查异变灵根
    mutation_bonus = 1.0
    if spiritual_root.mutation != "none":
        mutation_bonus = bonus_map.get(spiritual_root.mutation, 1.0)

    # 检查副灵根
    secondary_bonus = 1.0
    for sec in spiritual_root.secondary:
        sec_b = bonus_map.get(sec, 1.0)
        secondary_bonus = max(secondary_bonus, sec_b * 0.8)  # 副灵根打 8 折

    # 取最高加成
    best = max(primary_bonus, mutation_bonus, secondary_bonus)

    # 纯度修正
    purity_factor = 0.8 + 0.2 * spiritual_root.purity

    return max(0.5, min(2.0, round(best * purity_factor, 2)))
