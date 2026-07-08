# -*- coding: utf-8 -*-
"""
cultivation_state.py — 修炼状态模型（LONG-A 第1阶段）

核心概念：
  CultivationState = 玩家修炼相关的综合状态计算器。
  不直接修改 profile，只负责计算和构造合法的 delta。

设计原则：
  - 所有变更通过 EventOutcome → OutcomeApplier 写入，本模块不碰 profile。
  - 根基 / 瓶颈 / 修炼倍率 全部由代码计算，AI 不决定数值。
  - 旧存档兼容：缺失字段使用 .get(key, default) 读取。
  - 复用现有 METHOD_STATE 字段，扩展不破坏旧结构。

METHOD_STATE 扩展字段：
  "foundation": 100,           # 根基值 0~200，影响突破成功率和修为上限
  "bottleneck": 0,             # 瓶颈等级 0~5，越高修炼越慢、突破越难
  "consecutive_failures": 0,   # 连续突破失败次数，影响瓶颈和反噬
  "cultivation_modifier": 1.0, # 修炼倍率（由功法+灵根+环境综合计算）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ──────────────────────────────────────────────
#  常量定义
# ──────────────────────────────────────────────

# 根基值范围
FOUNDATION_MIN = 0
FOUNDATION_MAX = 200
FOUNDATION_DEFAULT = 100

# 瓶颈等级范围
BOTTLENECK_MIN = 0
BOTTLENECK_MAX = 5

# 修炼进度范围（与 main.py 中 CULTIVATION_PROGRESS_MAX = 100 对齐）
CULTIVATION_PROGRESS_MIN = 0
CULTIVATION_PROGRESS_MAX = 100

# 瓶颈对修炼速度的衰减因子：每级瓶颈减少 15% 修炼效率
BOTTLENECK_EFFICIENCY_PENALTY = 0.15

# 瓶颈对突破 DC 的增加：每级瓶颈 DC +2
BOTTLENECK_DC_PENALTY = 2

# 根基对突破 DC 的影响：根基每 20 点提供 DC -1（最多 -5）
FOUNDATION_DC_BONUS_PER_20 = 1
FOUNDATION_DC_BONUS_MAX = 5

# 连续失败对瓶颈的推进：每 2 次连续失败，瓶颈 +1
CONSECUTIVE_FAILURE_BOTTLENECK_THRESHOLD = 2

# 根基恢复速率：每次成功修炼 +1 根基（最多到上限）
FOUNDATION_RECOVERY_PER_CULTIVATION = 1

# 突破失败根基损耗
FOUNDATION_LOSS_ON_FAILURE = 5
FOUNDATION_LOSS_ON_BOUNDARY_FAILURE = 15

# 现有境界列表（与 main.py _REALMS 对齐）
REALMS = [
    "练气一层", "练气二层", "练气三层", "练气四层", "练气五层",
    "练气六层", "练气七层", "练气八层", "练气九层",
    "筑基初期", "筑基中期", "筑基后期", "筑基巅峰",
    "金丹初期",
]

# 境界 → 大境界阶段映射
REALM_STAGE = {}
for _r in REALMS:
    if _r.startswith("练气"):
        REALM_STAGE[_r] = "练气"
    elif _r.startswith("筑基"):
        REALM_STAGE[_r] = "筑基"
    else:
        REALM_STAGE[_r] = "金丹"

# 大境界瓶颈点：从这些境界往上跨是跨大境界
BOUNDARY_REALMS = frozenset({"练气九层", "筑基巅峰"})

# 境界索引 → 基础修炼 DC（境界越高，修炼越难获得进展）
_REALM_CULTIVATION_DC = {}
for i, realm in enumerate(REALMS):
    # 练气 1-9: DC 10~14，筑基: DC 15~18，金丹: DC 20
    if i < 9:
        _REALM_CULTIVATION_DC[realm] = 10 + i
    elif i < 13:
        _REALM_CULTIVATION_DC[realm] = 15 + (i - 9)
    else:
        _REALM_CULTIVATION_DC[realm] = 20


# ──────────────────────────────────────────────
#  CultivationState 数据类
# ──────────────────────────────────────────────

@dataclass
class CultivationState:
    """修炼状态快照。从 profile 中提取后使用，不持有引用。"""

    realm: str = "练气一层"
    progress: int = 0
    foundation: int = FOUNDATION_DEFAULT
    bottleneck: int = 0
    consecutive_failures: int = 0
    cultivation_modifier: float = 1.0
    growth_stage: str = "练气"
    breakthrough_status: str = "none_pending"
    primary_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "realm": self.realm,
            "progress": self.progress,
            "foundation": self.foundation,
            "bottleneck": self.bottleneck,
            "consecutive_failures": self.consecutive_failures,
            "cultivation_modifier": self.cultivation_modifier,
            "growth_stage": self.growth_stage,
            "breakthrough_status": self.breakthrough_status,
            "primary_path": self.primary_path,
        }


def extract_cultivation_state(profile: Dict[str, Any]) -> CultivationState:
    """从玩家 profile 中提取修炼状态。

    旧存档兼容：缺失的新字段使用默认值。

    Args:
        profile: 玩家档案 dict

    Returns:
        CultivationState 对象
    """
    method = profile.get("METHOD_STATE", {})
    return CultivationState(
        realm=profile.get("cultivation_realm", REALMS[0]),
        progress=method.get("progress", 0),
        foundation=method.get("foundation", FOUNDATION_DEFAULT),
        bottleneck=method.get("bottleneck", 0),
        consecutive_failures=method.get("consecutive_failures", 0),
        cultivation_modifier=method.get("cultivation_modifier", 1.0),
        growth_stage=method.get("growth_stage", "练气"),
        breakthrough_status=method.get("breakthrough_status", "none_pending"),
        primary_path=method.get("primary_path", ""),
    )


# ──────────────────────────────────────────────
#  修炼增益计算
# ──────────────────────────────────────────────

def calculate_cultivation_gain(
    base_gain: int,
    cultivation_state: CultivationState,
    spiritual_root_efficiency: float = 1.0,
    technique_speed_bonus: float = 1.0,
    environment_bonus: float = 0.0,
) -> int:
    """综合计算修炼增益。

    修炼增益 = base_gain
        × 灵根效率
        × 功法速度倍率
        × 修炼倍率
        × (1 - 瓶颈衰减)
        + 环境固定加成

    结果 clamp 到 [CULTIVATION_PROGRESS_MIN, CULTIVATION_PROGRESS_MAX]。

    Args:
        base_gain: 基础增益（来自运气检定/丹药/天材地宝等）
        cultivation_state: 修炼状态快照
        spiritual_root_efficiency: 灵根效率倍率（默认 1.0）
        technique_speed_bonus: 功法速度倍率（默认 1.0）
        environment_bonus: 环境固定加成（如灵潮，默认 0）

    Returns:
        最终修炼增益（整数）
    """
    # 瓶颈衰减
    bottleneck_factor = max(0.1, 1.0 - cultivation_state.bottleneck * BOTTLENECK_EFFICIENCY_PENALTY)

    # 综合倍率
    total_multiplier = (
        spiritual_root_efficiency
        * technique_speed_bonus
        * cultivation_state.cultivation_modifier
        * bottleneck_factor
    )

    # 最终增益
    gain = int(base_gain * total_multiplier) + int(environment_bonus)

    # 不允许负增益超过 base（最差情况是倒扣 base_gain 的量）
    min_gain = -abs(base_gain) if base_gain < 0 else 0
    gain = max(min_gain, gain)

    return gain


# ──────────────────────────────────────────────
#  根基值计算
# ──────────────────────────────────────────────

def calculate_foundation_change(
    current_foundation: int,
    event_type: str,
    is_boundary: bool = False,
) -> int:
    """计算根基值变化量。

    Args:
        current_foundation: 当前根基值
        event_type: 事件类型：
            "cultivation_success" — 修炼成功，根基 +1
            "breakthrough_success" — 突破成功，根基 +5（大境界 +10）
            "breakthrough_failure" — 突破失败，根基 -5（大境界 -15）
            "foundation_damage" — 根基受损，根基 -10
        is_boundary: 是否是大境界瓶颈点

    Returns:
        根基变化量（可为负数）
    """
    if event_type == "cultivation_success":
        return FOUNDATION_RECOVERY_PER_CULTIVATION
    elif event_type == "breakthrough_success":
        return 10 if is_boundary else 5
    elif event_type == "breakthrough_failure":
        return -FOUNDATION_LOSS_ON_BOUNDARY_FAILURE if is_boundary else -FOUNDATION_LOSS_ON_FAILURE
    elif event_type == "foundation_damage":
        return -10
    return 0


def clamp_foundation(value: int) -> int:
    """根基值 clamp 到合法范围。"""
    return max(FOUNDATION_MIN, min(FOUNDATION_MAX, value))


# ──────────────────────────────────────────────
#  瓶颈计算
# ──────────────────────────────────────────────

def calculate_bottleneck_change(
    current_bottleneck: int,
    current_consecutive_failures: int,
    event_type: str,
) -> int:
    """计算瓶颈等级变化。

    规则：
      - 突破失败：consecutive_failures +1
        每 CONSECUTIVE_FAILURE_BOTTLENECK_THRESHOLD 次连续失败，瓶颈 +1
      - 突破成功：瓶颈 -1（最低为 0），consecutive_failures 重置为 0
      - 修炼成功（非突破）：瓶颈自然衰退 -0（不自动减少，需要突破来打破）

    Args:
        current_bottleneck: 当前瓶颈等级
        current_consecutive_failures: 当前连续失败次数
        event_type: "breakthrough_success" / "breakthrough_failure"

    Returns:
        (bottleneck_change, new_consecutive_failures)
    """
    if event_type == "breakthrough_success":
        # 突破成功：瓶颈 -1，连续失败归零
        bottleneck_change = -1 if current_bottleneck > 0 else 0
        return bottleneck_change, 0

    elif event_type == "breakthrough_failure":
        # 突破失败：连续失败 +1
        new_consecutive = current_consecutive_failures + 1
        # 检查是否触发瓶颈升级
        if new_consecutive > 0 and new_consecutive % CONSECUTIVE_FAILURE_BOTTLENECK_THRESHOLD == 0:
            if current_bottleneck < BOTTLENECK_MAX:
                return 1, new_consecutive
        return 0, new_consecutive

    return 0, current_consecutive_failures


def clamp_bottleneck(value: int) -> int:
    """瓶颈等级 clamp 到合法范围。"""
    return max(BOTTLENECK_MIN, min(BOTTLENECK_MAX, value))


# ──────────────────────────────────────────────
#  突破 DC 计算
# ──────────────────────────────────────────────

def calculate_breakthrough_dc(
    cultivation_state: CultivationState,
    technique_breakthrough_bonus: float = 0.0,
) -> int:
    """计算突破检定 DC。

    基础 DC = 20（困难）
      + 境界修正（练气 +0，筑基 +2，金丹 +5）
      + 瓶颈修正（每级 +2）
      - 根基修正（每 20 点 -1，最多 -5）
      - 功法突破加成（取整）

    Args:
        cultivation_state: 修炼状态快照
        technique_breakthrough_bonus: 功法突破概率加成（0.0~1.0）

    Returns:
        突破 DC（整数，最低 10）
    """
    # 基础 DC
    base_dc = 20

    # 境界修正
    stage = cultivation_state.growth_stage
    stage_modifier = {"练气": 0, "筑基": 2, "金丹": 5}.get(stage, 0)

    # 瓶颈修正
    bottleneck_modifier = cultivation_state.bottleneck * BOTTLENECK_DC_PENALTY

    # 根基修正（每 20 点 -1，最多 -5）
    foundation_bonus = min(
        FOUNDATION_DC_BONUS_MAX,
        cultivation_state.foundation // 20 * FOUNDATION_DC_BONUS_PER_20
    )

    # 功法突破加成（转换为 DC 减免：bonus * 5）
    technique_modifier = int(technique_breakthrough_bonus * 5)

    dc = base_dc + stage_modifier + bottleneck_modifier - foundation_bonus - technique_modifier

    # 最低 DC 10
    return max(10, dc)


# ──────────────────────────────────────────────
#  修炼进度调整（替代 main.py 中 _adjust_cultivation_progress）
# ──────────────────────────────────────────────

def adjust_cultivation_progress(
    current_progress: int,
    delta: int,
) -> int:
    """修炼进度调整，clamp 到 0~100。

    Args:
        current_progress: 当前进度
        delta: 变化量（正数增加，负数减少）

    Returns:
        调整后的进度
    """
    return max(
        CULTIVATION_PROGRESS_MIN,
        min(CULTIVATION_PROGRESS_MAX, current_progress + delta)
    )


# ──────────────────────────────────────────────
#  修炼倍率更新
# ──────────────────────────────────────────────

def calculate_cultivation_modifier(
    spiritual_root_efficiency: float = 1.0,
    technique_speed_bonus: float = 1.0,
    bottleneck: int = 0,
) -> float:
    """综合计算修炼倍率，存入 METHOD_STATE.cultivation_modifier。

    倍率 = 灵根效率 × 功法速度 × (1 - 瓶颈衰减)

    Args:
        spiritual_root_efficiency: 灵根效率倍率
        technique_speed_bonus: 功法速度倍率
        bottleneck: 当前瓶颈等级

    Returns:
        修炼倍率（0.1~3.0）
    """
    bottleneck_factor = max(0.1, 1.0 - bottleneck * BOTTLENECK_EFFICIENCY_PENALTY)
    modifier = spiritual_root_efficiency * technique_speed_bonus * bottleneck_factor
    return max(0.1, min(3.0, modifier))


# ──────────────────────────────────────────────
#  境界工具函数
# ──────────────────────────────────────────────

def get_realm_index(realm: str) -> int:
    """获取境界在列表中的索引，未知境界返回 0。"""
    try:
        return REALMS.index(realm)
    except ValueError:
        return 0


def get_next_realm(current_realm: str) -> Optional[str]:
    """获取下一个境界，已是最高则返回 None。"""
    idx = get_realm_index(current_realm)
    if idx < len(REALMS) - 1:
        return REALMS[idx + 1]
    return None


def is_boundary_realm(realm: str) -> bool:
    """判断是否是大境界瓶颈点。"""
    return realm in BOUNDARY_REALMS


def is_major_breakthrough(current_realm: str, next_realm: str) -> bool:
    """判断是否是跨大境界的突破。"""
    if current_realm not in REALM_STAGE or next_realm not in REALM_STAGE:
        return False
    return REALM_STAGE[current_realm] != REALM_STAGE[next_realm]


# ──────────────────────────────────────────────
#  旧存档迁移
# ──────────────────────────────────────────────

def migrate_profile_cultivation(profile: Dict[str, Any]) -> Dict[str, Any]:
    """为旧存档补全新增的修炼字段。

    缺失字段从现有数据推导默认值，不破坏已有内容。

    Args:
        profile: 玩家档案 dict（会被就地修改）

    Returns:
        修改后的 profile（同一引用）
    """
    method = profile.setdefault("METHOD_STATE", {})

    # foundation：不存在时默认 100
    if "foundation" not in method:
        method["foundation"] = FOUNDATION_DEFAULT

    # bottleneck：不存在时默认 0
    if "bottleneck" not in method:
        method["bottleneck"] = 0

    # consecutive_failures：不存在时默认 0；
    # 如果 breakthrough_status 是 "attempted_failed"，推断为 1
    if "consecutive_failures" not in method:
        if method.get("breakthrough_status") == "attempted_failed":
            method["consecutive_failures"] = 1
        else:
            method["consecutive_failures"] = 0

    # cultivation_modifier：不存在时默认 1.0
    if "cultivation_modifier" not in method:
        method["cultivation_modifier"] = 1.0

    # abilities：不存在时创建空能力表
    if "abilities" not in method:
        method["abilities"] = _default_abilities()

    # active_technique：不存在时为空
    if "active_technique" not in method:
        method["active_technique"] = ""

    # technique_details：不存在时为空
    if "technique_details" not in method:
        method["technique_details"] = {}

    return profile


def _default_abilities() -> Dict[str, Any]:
    """生成默认能力表。"""
    return {
        "剑意": {"level": 0, "exp": 0, "max_level": 5},
        "炼丹": {"level": 0, "exp": 0, "max_level": 5},
        "炼器": {"level": 0, "exp": 0, "max_level": 5},
        "阵法": {"level": 0, "exp": 0, "max_level": 5},
        "符箓": {"level": 0, "exp": 0, "max_level": 5},
    }


# ──────────────────────────────────────────────
#  构造 METHOD_STATE delta（供 OutcomeApplier 使用）
# ──────────────────────────────────────────────

def make_method_state_delta(
    progress_delta: Optional[int] = None,
    foundation_delta: Optional[int] = None,
    bottleneck_delta: Optional[int] = None,
    consecutive_failures_delta: Optional[int] = None,
    cultivation_modifier: Optional[float] = None,
    growth_stage: Optional[str] = None,
    breakthrough_status: Optional[str] = None,
    cultivation_realm: Optional[str] = None,
) -> Dict[str, Any]:
    """构造 METHOD_STATE 的 delta dict。

    只包含需要变更的字段，值为增量（数值）或绝对值（字符串）。
    调用方将此 delta 包装进 profile_delta，交给 OutcomeApplier 写入。

    Args:
        progress_delta: 修炼进度变化量
        foundation_delta: 根基变化量
        bottleneck_delta: 瓶颈变化量
        consecutive_failures_delta: 连续失败变化量
        cultivation_modifier: 新的修炼倍率（绝对值）
        growth_stage: 新的大境界阶段（绝对值）
        breakthrough_status: 新的突破状态（绝对值）
        cultivation_realm: 新的境界（绝对值，写入 profile 顶层）

    Returns:
        METHOD_STATE delta dict
    """
    delta: Dict[str, Any] = {}

    if progress_delta is not None:
        delta["progress"] = progress_delta
    if foundation_delta is not None:
        delta["foundation"] = foundation_delta
    if bottleneck_delta is not None:
        delta["bottleneck"] = bottleneck_delta
    if consecutive_failures_delta is not None:
        delta["consecutive_failures"] = consecutive_failures_delta
    if cultivation_modifier is not None:
        delta["cultivation_modifier"] = cultivation_modifier
    if growth_stage is not None:
        delta["growth_stage"] = growth_stage
    if breakthrough_status is not None:
        delta["breakthrough_status"] = breakthrough_status

    return delta
