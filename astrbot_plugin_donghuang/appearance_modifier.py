"""
appearance_modifier.py — 外貌变化接口（B-8）

核心概念：
  外貌变化必须走现有状态修改链（OutcomeApplier + profile_delta），
  不直接修改 profile。本模块只负责构造合法的 profile_delta，
  由调用方通过 OutcomeApplier 写入。

设计原则：
  - 本模块只产出 profile_delta dict，不直接修改 profile。
  - 所有修改必须通过 OutcomeApplier.apply_outcome() 写入。
  - Snapshot/Rollback 自动覆盖，因为 appearance 是 profile 的一部分。
  - appearance 已加入 PROFILE_FIELD_WHITELIST，OutcomeApplier 会递归合并。

支持的变化类型：
  - 战斗：增加伤痕
  - 突破：改变气质
  - 特殊事件：增加特殊印记

profile_delta 格式：
  {slot_id: {"appearance": {subfield: value}}}
  OutcomeApplier 会通过 _merge_dict_no_clamp 递归合并到 profile["appearance"]。
  注意：marks 是 list，dict 合并不会追加 list，需要特殊处理。
  因此 marks 的修改采用整体替换策略（新 list = 旧 list + 新增项）。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
#  外貌变化类型常量
# ──────────────────────────────────────────────

CHANGE_TYPE_BATTLE = "battle"        # 战斗
CHANGE_TYPE_BREAKTHROUGH = "breakthrough"  # 突破
CHANGE_TYPE_SPECIAL = "special"      # 特殊事件


# ──────────────────────────────────────────────
#  外貌变化接口
# ──────────────────────────────────────────────

def modify_appearance_delta(
    player_id: str,
    change_type: str,
    changes: Dict[str, Any],
    current_appearance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造外貌变化的 profile_delta。

    本函数不直接修改 profile，只构造合法的 profile_delta dict，
    由调用方通过 OutcomeApplier 写入。

    Args:
        player_id: 玩家 ID（如 "PLAYER-A"）
        change_type: 变化类型（battle / breakthrough / special）
        changes: 变化内容，结构取决于 change_type：
            - battle: {"marks": ["左臂新伤"], "clothing": {"style": "破损剑袍"}}
            - breakthrough: {"aura": {"feeling": "锋锐内敛"}, "eyes": {"special": "瞳中剑意"}}
            - special: {"marks": ["额头封印"], "first_impression": "...", ...}
        current_appearance: 当前外观 dict（用于增量修改，如追加印记）

    Returns:
        合法的 profile_delta dict，格式为：
        {player_id: {"appearance": {subfield: value}}}
        可直接用于 OutcomeApplier
    """
    if change_type == CHANGE_TYPE_BATTLE:
        appearance_delta = _battle_appearance_delta(changes, current_appearance)
    elif change_type == CHANGE_TYPE_BREAKTHROUGH:
        appearance_delta = _breakthrough_appearance_delta(changes, current_appearance)
    elif change_type == CHANGE_TYPE_SPECIAL:
        appearance_delta = _special_appearance_delta(changes, current_appearance)
    else:
        return {}

    if not appearance_delta:
        return {}

    return {
        player_id: {
            "appearance": appearance_delta,
        }
    }


def _battle_appearance_delta(
    changes: Dict[str, Any],
    current_appearance: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """战斗外貌变化：增加伤痕、衣物破损。"""
    delta = {}

    # 伤痕：追加到 marks 列表（整体替换策略）
    new_marks = changes.get("marks", [])
    if new_marks:
        existing_marks = []
        if current_appearance:
            existing_marks = list(current_appearance.get("marks", []))
        delta["marks"] = existing_marks + new_marks

    # 衣物破损
    clothing_changes = changes.get("clothing", {})
    if clothing_changes:
        delta["clothing"] = clothing_changes

    # 气质变化（战斗后可能改变）
    aura_changes = changes.get("aura", {})
    if aura_changes:
        delta["aura"] = aura_changes

    return delta


def _breakthrough_appearance_delta(
    changes: Dict[str, Any],
    current_appearance: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """突破外貌变化：改变气质、瞳色特效。"""
    delta = {}

    # 气质变化
    aura_changes = changes.get("aura", {})
    if aura_changes:
        delta["aura"] = aura_changes

    # 瞳色特效
    eyes_changes = changes.get("eyes", {})
    if eyes_changes:
        delta["eyes"] = eyes_changes

    # 突破可能改变第一印象
    first_imp = changes.get("first_impression", "")
    if first_imp:
        delta["first_impression"] = first_imp

    # 突破可能带来印记
    new_marks = changes.get("marks", [])
    if new_marks:
        existing_marks = []
        if current_appearance:
            existing_marks = list(current_appearance.get("marks", []))
        delta["marks"] = existing_marks + new_marks

    return delta


def _special_appearance_delta(
    changes: Dict[str, Any],
    current_appearance: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """特殊事件外貌变化：增加特殊印记、改变外貌。"""
    delta = {}

    # 印记
    new_marks = changes.get("marks", [])
    if new_marks:
        existing_marks = []
        if current_appearance:
            existing_marks = list(current_appearance.get("marks", []))
        delta["marks"] = existing_marks + new_marks

    # 其他字段都可以直接覆盖
    for key in ["face", "body", "hair", "eyes", "clothing", "aura", "first_impression"]:
        if key in changes:
            delta[key] = changes[key]

    return delta


# ──────────────────────────────────────────────
#  便捷函数：直接将外观增量应用到 profile
# ──────────────────────────────────────────────

def apply_appearance_to_profile(
    profile: Dict[str, Any],
    appearance_delta: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """将外观增量直接应用到 profile 的 appearance 字段。

    本函数用于不经过 OutcomeApplier 的场景（如内部状态更新），
    仍然遵循"不直接修改 profile"的原则——通过 delta 方式修改。

    规则：
      - marks: 追加（不去重）
      - 其他字段: 深度合并（新值覆盖旧值）
      - first_impression: 直接覆盖

    Args:
        profile: 玩家 profile dict
        appearance_delta: appearance 子字段的增量内容

    Returns:
        applied_changes 列表，每项为 {"path": "...", "old": ..., "new": ...}
    """
    if "appearance" not in profile:
        profile["appearance"] = {}

    current = profile["appearance"]
    applied = []

    for key, value in appearance_delta.items():
        if key == "marks":
            # marks 追加
            old_marks = list(current.get("marks", []))
            if isinstance(value, list):
                new_marks = old_marks + [m for m in value if m not in old_marks]
                current["marks"] = new_marks
                applied.append({
                    "path": "appearance.marks",
                    "old": old_marks,
                    "new": new_marks,
                })
        elif isinstance(value, dict):
            # 深度合并
            old_val = dict(current.get(key, {}))
            merged = dict(old_val)
            merged.update(value)
            current[key] = merged
            applied.append({
                "path": f"appearance.{key}",
                "old": old_val,
                "new": merged,
            })
        else:
            # 直接覆盖
            old_val = current.get(key)
            current[key] = value
            applied.append({
                "path": f"appearance.{key}",
                "old": old_val,
                "new": value,
            })

    return applied
