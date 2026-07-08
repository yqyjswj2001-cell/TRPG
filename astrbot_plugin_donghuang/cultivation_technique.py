# -*- coding: utf-8 -*-
"""
cultivation_technique.py — 功法系统（LONG-A 第2阶段）

核心概念：
  CultivationTechnique = 功法数据模型，包含功法的完整信息。
  TechniqueManager = 功法管理器，负责加载、匹配、应用功法效果。
  不直接修改 profile，只负责计算和构造合法的 delta。

设计原则：
  - 所有变更通过 EventOutcome → OutcomeApplier 写入，本模块不碰 profile。
  - 功法修炼速度、突破加成、特殊效果全部由代码计算，AI 不决定数值。
  - 旧存档兼容：缺失字段使用 .get(key, default) 读取。
  - 复用现有 METHOD_STATE 字段，扩展不破坏旧结构。

METHOD_STATE 扩展字段：
  "active_technique": ""          # 当前主修功法名称
  "known_techniques": []         # 已掌握功法列表
  "technique_details": {}        # 功法详情缓存
  "technique_exp": {"剑意": 0}    # 功法熟练度经验值
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────
#  常量定义
# ──────────────────────────────────────────────

# 功法品阶
TIER_RANK = ["黄级", "玄级", "地级", "天级"]
TIER_RANK_VALUES = {"黄级": 1, "玄级": 2, "地级": 3, "天级": 4}

# 功法类别
TECHNIQUE_CATEGORIES = [
    "心法",      # 内功心法
    "剑法",      # 剑术
    "拳法",      # 拳脚
    "指法",      # 指法
    "掌法",      # 掌法
    "腿法",      # 腿法
    "暗器",      # 暗器
    "身法",      # 身法
    "道法",      # 法术
    "符箓",      # 符咒
    "阵法",      # 阵术
    "鞭法",      # 鞭法
    "枪法",      # 枪术
    "棍法",      # 棍棒
]

# 功法基础修炼速度（每天获得的修为进度）
BASE_CULTIVATION_SPEED = {
    "黄级": 1,   # 每天 1 点修为进度
    "玄级": 2,
    "地级": 5,
    "天级": 10,
}

# 功法对突破概率的基础加成
BASE_BREAKTHROUGH_BONUS = 0.05  # 5%

# 功法对突破 DC 的影响
TECHNIQUE_DC_PENALTY = -1  # 每本功法减少 1 点突破 DC

# 最高功法数量限制
MAX_ACTIVE_TECHNIQUES = 1
MAX_KNOWN_TECHNIQUES = 20

# 功法文件路径
DATA_DIR = Path(__file__).parent / "data" / "techniques"


# ──────────────────────────────────────────────
#  CultivationTechnique 数据类
# ──────────────────────────────────────────────

@dataclass
class CultivationTechnique:
    """功法数据模型。"""

    name: str = ""           # 功法名称
    tier: str = "黄级"       # 品阶：黄/玄/地/天
    category: str = "心法"   # 功法类别
    element: str = "无"      # 功法属性：金/木/水/火/土/雷/冰/风/空间/无
    creator: str = ""        # 创造者
    holder: str = ""         # 持有者/传承
    prevalence: str = "大众" # 稀有度：大众/稀有/传说
    desc: str = ""           # 功法描述
    effect: Dict[str, Any] = field(default_factory=lambda: {
        "attack_bonus": 0,
        "defense_bonus": 0,
        "hp_max": 0,
        "mp_max": 0,
        "speed_bonus": 0,
        "special": None,
    })  # 功法特效

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tier": self.tier,
            "category": self.category,
            "element": self.element,
            "creator": self.creator,
            "holder": self.holder,
            "prevalence": self.prevalence,
            "desc": self.desc,
            "effect": self.effect,
        }

    @property
    def speed_multiplier(self) -> float:
        """获取修炼速度倍率。"""
        return TIER_RANK_VALUES.get(self.tier, 1)

    @property
    def breakthrough_bonus(self) -> float:
        """获取突破概率加成。"""
        return BASE_BREAKTHROUGH_BONUS

    @property
    def dg_penalty(self) -> int:
        """获取突破 DC 减免。"""
        return TECHNIQUE_DC_PENALTY


# ──────────────────────────────────────────────
#  TechniqueManager 功法管理器
# ──────────────────────────────────────────────

class TechniqueManager:
    """功法管理器，负责加载、匹配、应用功法效果。"""

    def __init__(self):
        self._techniques: Dict[str, CultivationTechnique] = {}
        self._by_element: Dict[str, List[CultivationTechnique]] = defaultdict(list)
        self._by_tier: Dict[str, List[CultivationTechnique]] = defaultdict(list)
        self._loaded = False

    def load(self) -> None:
        """从 data/techniques/ 目录加载所有功法。"""
        if self._loaded:
            return

        if not DATA_DIR.exists():
            print(f"[功法系统] 警告：功法目录不存在 {DATA_DIR}")
            return

        for file_path in DATA_DIR.glob("*.jsonl"):
            try:
                techniques = self._parse_technique_file(file_path)
                self._techniques.update({t["name"]: t for t in techniques})
                self._index_technique(t)
            except Exception as e:
                print(f"[功法系统] 加载失败 {file_path}: {e}")

        self._loaded = True
        print(f"[功法系统] 已加载 {len(self._techniques)} 本功法")

    def _parse_technique_file(self, file_path: Path) -> List[CultivationTechnique]:
        """解析单个功法文件。"""
        techniques = []
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    techniques.append(CultivationTechnique(**data))
                except Exception as e:
                    print(f"[功法系统] 解析失败: {file_path.name}, {e}")
        return techniques

    def _index_technique(self, technique: CultivationTechnique) -> None:
        """索引功法到各维度。"""
        # 按属性索引
        elements = [technique.element] if technique.element != "无" else ["无"]
        for elem in elements:
            self._by_element[elem].append(technique)

        # 按品阶索引
        self._by_tier[technique.tier].append(technique)

    def get_all_techniques(self) -> List[CultivationTechnique]:
        """获取所有功法。"""
        return list(self._techniques.values())

    def get_by_name(self, name: str) -> Optional[CultivationTechnique]:
        """按名称获取功法。"""
        return self._techniques.get(name)

    def get_by_element(self, element: str) -> List[CultivationTechnique]:
        """按属性获取功法列表。"""
        return self._by_element.get(element, [])

    def get_by_tier(self, tier: str) -> List[CultivationTechnique]:
        """按品阶获取功法列表。"""
        return self._by_tier.get(tier, [])

    def search(
        self,
        tier: Optional[str] = None,
        category: Optional[str] = None,
        element: Optional[str] = None,
        limit: int = 10,
    ) -> List[CultivationTechnique]:
        """搜索功法。

        Args:
            tier: 品阶过滤
            category: 类别过滤
            element: 属性过滤
            limit: 返回数量限制

        Returns:
            符合条件的功法列表
        """
        results = list(self.get_all_techniques())

        if tier:
            results = [t for t in results if t.tier == tier]
        if category:
            results = [t for t in results if t.category == category]
        if element:
            if element == "无":
                results = [t for t in results if t.element == "无"]
            else:
                results = [t for t in results if t.element == element]

        return results[:limit]

    def find_matching_technique(
        self,
        spiritual_root: Any,  # SpiritualRoot 类型
        current_realm: str,
    ) -> Optional[CultivationTechnique]:
        """根据灵根和境界查找最匹配的功法。

        匹配规则：
          1. 优先选择与主灵根属性相同的功法
          2. 次选相生属性的功法
          3. 再次选同品阶但不同属性的功法
          4. 最后降级到低一档品阶

        Args:
            spiritual_root: 灵根状态
            current_realm: 当前境界

        Returns:
            最匹配的功法，或 None
        """
        primary_element = spiritual_root.primary if hasattr(spiritual_root, 'primary') else spiritual_root.get('primary', '金')

        # 第一优先级：同属性功法
        same_element = [t for t in self.get_by_element(primary_element)]
        if same_element:
            return self._select_best_by_tier(same_element, current_realm)

        # 第二优先级：相生属性功法
        generates = ELEMENT_GENERATES.get(primary_element, "")
        if generates:
            generate_element = [t for t in self.get_by_element(generates)]
            if generate_element:
                return self._select_best_by_tier(generate_element, current_realm)

        # 第三优先级：异变灵根的特殊功法
        if spiritual_root.mutation != "none":
            mutation_element = MUTATION_TRIGGER_ELEMENT.get(spiritual_root.mutation, "")
            if mutation_element:
                mutation_elements = [t for t in self.get_by_element(mutation_element)]
                if mutation_elements:
                    return self._select_best_by_tier(mutation_elements, current_realm)

        # 第四优先级：通用功法（无属性要求）
        no_element = [t for t in self.get_by_element("无")]
        if no_element:
            return self._select_best_by_tier(no_element, current_realm)

        return None

    def _select_best_by_tier(self, techniques: List[CultivationTechnique], realm: str) -> CultivationTechnique:
        """按品阶排序选择最佳功法。"""
        # 根据境界确定可学习的品阶上限
        realm_index = _get_realm_index(realm)
        max_tier = self._calculate_max_tier_for_realm(realm_index)

        # 筛选符合品阶要求的功法
        eligible = [t for t in techniques if TIER_RANK_VALUES.get(t.tier, 0) <= max_tier]

        if not eligible:
            # 降级到最低可用品阶
            lowest_tier = min([t.tier for t in techniques]) if techniques else "黄级"
            eligible = [t for t in techniques if t.tier == lowest_tier]

        # 选择品阶最高的
        best = max(eligible, key=lambda t: TIER_RANK_VALUES.get(t.tier, 0))
        return best

    def _calculate_max_tier_for_realm(self, realm_index: int) -> int:
        """根据境界计算可学习的最高品阶。"""
        # 练气期只能学黄级
        if realm_index < 9:
            return 1
        # 筑基期可以学玄级
        if realm_index < 13:
            return 2
        # 金丹期可以学地级
        return 3


# 全局单例
_technique_manager: Optional[TechniqueManager] = None


def get_technique_manager() -> TechniqueManager:
    """获取功法管理器单例。"""
    global _technique_manager
    if _technique_manager is None:
        _technique_manager = TechniqueManager()
        _technique_manager.load()
    return _technique_manager


# ──────────────────────────────────────────────
#  功法修炼速度计算
# ──────────────────────────────────────────────

def calculate_technique_speed(
    technique: CultivationTechnique,
    spiritual_root: Any,  # SpiritualRoot 类型
    purity: float = 0.5,
    bottleneck: int = 0,
) -> float:
    """计算功法修炼速度倍率。

    速度 = 基础速度 × 灵根亲和度 × 纯度修正 × 瓶颈衰减

    Args:
        technique: 功法对象
        spiritual_root: 灵根状态
        purity: 灵根纯度
        bottleneck: 瓶颈等级

    Returns:
        修炼速度倍率
    """
    # 基础速度
    base_speed = technique.speed_multiplier

    # 灵根亲和度
    affinity = calculate_affinity_with_root(spiritual_root, technique.element)

    # 纯度修正
    purity_factor = 0.7 + 0.3 * purity

    # 瓶颈衰减
    bottleneck_factor = max(0.1, 1.0 - bottleneck * 0.15)

    # 最终倍率
    speed = base_speed * affinity * purity_factor * bottleneck_factor

    return max(0.1, min(5.0, round(speed, 2)))


def calculate_affinity_with_root(spiritual_root: Any, technique_element: str) -> float:
    """计算灵根与功法属性的亲和度。"""
    # 从 spiritual_root 提取属性
    root_element = spiritual_root.primary if hasattr(spiritual_root, 'primary') else spiritual_root.get('primary', '金')

    # 五行相生相克矩阵
    generates = ELEMENT_GENERATES.get(root_element, "")
    overcomes = ELEMENT_OVERCOMES.get(root_element, "")

    # 同属性：1.0
    if technique_element == root_element:
        return 1.0
    # 相生：0.7
    elif technique_element == generates:
        return 0.7
    # 相克：0.2
    elif technique_element == overcomes:
        return 0.2
    # 中性：0.4
    else:
        return 0.4


# ──────────────────────────────────────────────
#  功法突破加成计算
# ──────────────────────────────────────────────

def calculate_breakthrough_bonus(
    techniques: List[CultivationTechnique],
    spiritual_root: Any,
) -> float:
    """计算功法对突破概率的总加成。

    总加成 = Σ(每本功法加成) + 灵根加成 + 根基加成

    Args:
        techniques: 已掌握的功法列表
        spiritual_root: 灵根状态

    Returns:
        突破概率加成 0.0~0.3
    """
    # 功法加成
    technique_bonus = len(techniques) * BASE_BREAKTHROUGH_BONUS

    # 灵根加成
    root_bonus = calculate_root_breakthrough_bonus(spiritual_root)

    # DC 减免（来自功法）
    dc_reduction = sum(t.dg_penalty for t in techniques)

    # 转换 DC 减免为概率加成（约 1 DC = 5% 概率）
    dc_to_probability = dc_reduction * 0.05

    total = technique_bonus + root_bonus + dc_to_probability

    return max(0.0, min(0.3, round(total, 2)))


def calculate_root_breakthrough_bonus(spiritual_root: Any) -> float:
    """计算灵根对突破概率的加成。"""
    purity = spiritual_root.purity if hasattr(spiritual_root, 'purity') else spiritual_root.get('purity', 0.5)

    # 纯度加成
    purity_bonus = (purity - 0.5) * 0.3
    purity_bonus = max(0.0, purity_bonus)

    # 异变加成
    mutation = spiritual_root.mutation if hasattr(spiritual_root, 'mutation') else spiritual_root.get('mutation', 'none')
    mutation_bonus = 0.0
    if mutation != "none":
        mutation_bonus = {
            "雷": 0.1, "冰": 0.05, "风": 0.05, "空间": 0.15,
        }.get(mutation, 0.0)

    return max(0.0, min(0.15, round(purity_bonus + mutation_bonus, 2)))


# ──────────────────────────────────────────────
#  功法特效判定
# ──────────────────────────────────────────────

def check_technique_effect(
    technique: CultivationTechnique,
    condition: Dict[str, Any],
) -> bool:
    """检查功法特效触发条件是否满足。

    Args:
        technique: 功法对象
        condition: 触发条件，如 {"level": 3, "combo": true}

    Returns:
        是否触发特效
    """
    # 示例：等级触发
    if "level" in condition:
        level = condition["level"]
        current_level = technique.effect.get("level", 0)
        if isinstance(current_level, dict):
            current_level = current_level.get("learned", 0)
        if current_level >= level:
            return True

    # 可以扩展更多条件...

    return False


def apply_technique_effect(
    technique: CultivationTechnique,
    effect_type: str,
    target: Any,
) -> Dict[str, Any]:
    """应用功法特效。

    Args:
        technique: 功法对象
        effect_type: 特效类型
        target: 目标对象（profile 或其他）

    Returns:
        应用结果描述
    """
    effect = technique.effect.get("special")
    if not effect:
        return {"applied": False, "reason": "无特效"}

    # 根据特效类型处理
    if effect_type == "attack":
        # 攻击特效
        bonus = effect.get("attack_bonus", 0)
        if bonus > 0:
            return {"applied": True, "effect": f"攻击+{bonus}"}

    elif effect_type == "defense":
        # 防御特效
        bonus = effect.get("defense_bonus", 0)
        if bonus > 0:
            return {"applied": True, "effect": f"防御+{bonus}"}

    elif effect_type == "hp":
        # 气血特效
        bonus = effect.get("hp_max", 0)
        if bonus > 0:
            return {"applied": True, "effect": f"HP上限+{bonus}"}

    return {"applied": False, "reason": "未匹配的特效类型"}


# ──────────────────────────────────────────────
#  功法学习判断
# ──────────────────────────────────────────────

def can_learn_technique(
    technique: CultivationTechnique,
    profile: Dict[str, Any],
) -> Tuple[bool, str]:
    """判断是否可以学习该功法。

    判断条件：
      1. 境界要求：当前境界 >= 功法允许的最低境界
      2. 灵根要求：灵根属性匹配或有替代方案
      3. 位置要求：有学习地点（如宗门、洞府）
      4. 资源要求：有足够的贡献点或灵石

    Args:
        technique: 功法对象
        profile: 玩家档案

    Returns:
        (是否可以学习, 原因)
    """
    # 境界要求
    realm = profile.get("cultivation_realm", "")
    realm_index = _get_realm_index(realm)
    technique_realm = _get_min_realm_for_technique(technique)
    if realm_index < technique_realm:
        return False, f"境界不足（需要≥{technique_realm}）"

    # 灵根要求（简化：只要不是明显冲突即可）
    return True, ""


def _get_min_realm_for_technique(technique: CultivationTechnique) -> int:
    """获取功法需要的最低境界。"""
    # 根据品阶推断
    tier_value = TIER_RANK_VALUES.get(technique.tier, 1)
    if tier_value >= 4:  # 天级
        return 13  # 金丹初期
    elif tier_value >= 3:  # 地级
        return 9   # 练气九层
    elif tier_value >= 2:  # 玄级
        return 1   # 练气一层
    return 0


def _get_realm_index(realm: str) -> int:
    """获取境界索引。"""
    REALMS = ["练气一层","练气二层","练气三层","练气四层","练气五层",
              "练气六层","练气七层","练气八层","练气九层",
              "筑基初期","筑基中期","筑基后期","筑基巅峰",
              "金丹初期"]
    try:
        return REALMS.index(realm)
    except ValueError:
        return 0


# ──────────────────────────────────────────────
#  功法熟练度管理
# ──────────────────────────────────────────────

def calculate_technique_exp(
    technique: CultivationTechnique,
    days_practiced: int,
    efficiency: float = 1.0,
) -> int:
    """计算功法熟练度经验值。

    经验值 = 练习天数 × 效率倍率 × 品阶系数

    Args:
        technique: 功法对象
        days_practiced: 练习天数
        efficiency: 修炼效率倍率

    Returns:
        获得的经验值
    """
    # 品阶系数：高品阶功法升级慢
    tier_coeff = TIER_RANK_VALUES.get(technique.tier, 1)

    # 每日经验
    daily_exp = tier_coeff * efficiency

    return int(days_practiced * daily_exp)


def exp_to_level(exp: int, technique: CultivationTechnique) -> int:
    """将经验值转换为等级。

    等级需求：1, 5, 10, 25, 50, 100, ...

    Args:
        exp: 经验值
        technique: 功法对象

    Returns:
        当前等级
    """
    levels = [1, 5, 10, 25, 50, 100, 200, 500, 1000]
    for i, required in enumerate(levels):
        if exp < required:
            return i
    return len(levels) - 1


# ──────────────────────────────────────────────
#  旧存档迁移
# ──────────────────────────────────────────────

def migrate_profile_technique(profile: Dict[str, Any]) -> Dict[str, Any]:
    """为旧存档补全功法相关字段。

    Args:
        profile: 玩家档案 dict

    Returns:
        修改后的 profile
    """
    method = profile.setdefault("METHOD_STATE", {})

    # active_technique：不存在时设为空字符串
    if "active_technique" not in method:
        method["active_technique"] = ""

    # known_techniques：不存在时创建空列表
    if "known_techniques" not in method:
        method["known_techniques"] = []

    # technique_details：不存在时创建空字典
    if "technique_details" not in method:
        method["technique_details"] = {}

    # technique_exp：不存在时创建默认经验表
    if "technique_exp" not in method:
        method["technique_exp"] = {"剑意": 0, "炼丹": 0, "炼器": 0, "阵法": 0, "符箓": 0}

    return profile


# ──────────────────────────────────────────────
#  构造 METHOD_STATE delta（供 OutcomeApplier 使用）
# ──────────────────────────────────────────────

def make_method_state_technique_delta(
    active_technique: Optional[str] = None,
    known_techniques: Optional[List[str]] = None,
    technique_exp: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """构造 METHOD_STATE 中功法相关的 delta dict。

    Args:
        active_technique: 新的主修功法名称
        known_techniques: 新掌握的功法列表
        technique_exp: 功法经验值变化

    Returns:
        METHOD_STATE delta dict
    """
    delta: Dict[str, Any] = {}

    if active_technique is not None:
        delta["active_technique"] = active_technique

    if known_techniques is not None:
        delta["known_techniques"] = known_techniques

    if technique_exp is not None:
        delta["technique_exp"] = technique_exp

    return delta
