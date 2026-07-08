"""
outcome_applier.py — State Delta 应用器（B-6.3）

把 EventOutcome 转化为真实状态变化。

核心接口：
  apply_outcome(outcome, world_state, campaign, profiles=None) -> dict

要求：
  - 所有数值必须 clamp
  - 不允许任意字段写入
  - 只允许白名单字段变更
  - 返回 applied_changes
  - 支持 rollback（因为修改对象已在 snapshot 范围内）
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

try:
    from .event_outcome import (
        EventOutcome, EventOutcomeType,
        WORLD_FIELD_WHITELIST, FACTION_FIELD_WHITELIST,
        PROFILE_FIELD_WHITELIST,
        METHOD_STATE_WHITELIST, CORE_STATE_WHITELIST,
    )
except ImportError:
    from event_outcome import (
        EventOutcome, EventOutcomeType,
        WORLD_FIELD_WHITELIST, FACTION_FIELD_WHITELIST,
        PROFILE_FIELD_WHITELIST,
        METHOD_STATE_WHITELIST, CORE_STATE_WHITELIST,
    )

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  数值 clamp 范围
# ──────────────────────────────────────────────

# 字段 → (min, max)，注意 profile 中 progress 为百分比 0~100
_FIELD_RANGES = {
    "power": (0, 100),
    "stability": (0.0, 1.0),
    "morale": (0.0, 1.0),
    "progress": (0.0, 1.0),       # 通用进度（小数），用于世界/势力状态
    "realm": None,                 # 无 clamp
    "growth_stage": None,          # 无 clamp
    # LONG-A: 修炼相关字段 clamp
    "foundation": (0, 200),        # 根基值 0~200
    "bottleneck": (0, 5),          # 瓶颈等级 0~5
    "consecutive_failures": (0, 10),  # 连续失败次数
    "cultivation_modifier": (0.1, 3.0),  # 修炼倍率
    "purity": (0.1, 1.0),         # 灵根纯度
    "efficiency": (0.3, 3.0),     # 灵根效率
    "contribution": (0, 99999),    # 宗门贡献点
}


def clamp(value: Any, field_name: str) -> Any:
    """根据字段名 clamp 数值到合法范围。"""
    if field_name not in _FIELD_RANGES:
        return value
    range_spec = _FIELD_RANGES[field_name]
    if range_spec is None:
        return value  # 无 clamp 范围的字段
    lo, hi = range_spec
    if isinstance(value, (int, float)):
        return max(lo, min(hi, value))
    return value


class OutcomeApplier:
    """将 EventOutcome 应用到世界/势力/玩家状态。

    所有修改都经过白名单校验和数值 clamp。
    返回 applied_changes 列表，用于审计和 rollback。
    """

    def apply_outcome(
        self,
        outcome: EventOutcome,
        world_state: Dict[str, Any],
        campaign: Optional[Dict[str, Any]] = None,
        profiles: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """应用事件结果，返回实际变更摘要。

        Args:
            outcome: EventOutcome 对象
            world_state: 世界状态（会被修改）
            campaign: 团务状态（可选）
            profiles: 玩家档案 dict（slot_id → profile，可选）

        Returns:
            {
                "applied": True/False,
                "applied_changes": [{"path": str, "old": Any, "new": Any}],
                "rejected": [{"path": str, "reason": str}],
            }
        """
        applied_changes: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        # 1. 应用 world_delta
        self._apply_world_delta(outcome.world_delta, world_state, applied_changes, rejected)

        # 2. 应用 faction_delta
        self._apply_faction_delta(outcome.faction_delta, world_state, applied_changes, rejected)

        # 3. 应用 profile_delta
        if profiles and outcome.profile_delta:
            self._apply_profile_delta(outcome.profile_delta, profiles, applied_changes, rejected)

        # 4. 记录到 outcome 的 applied_changes
        outcome.applied_changes = applied_changes

        return {
            "applied": len(applied_changes) > 0,
            "applied_changes": applied_changes,
            "rejected": rejected,
        }

    # ──────────────────────────────────────────────
    #  world_delta 应用
    # ──────────────────────────────────────────────

    def _apply_world_delta(
        self,
        world_delta: Dict[str, Any],
        world_state: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
    ) -> None:
        """应用世界状态变更。"""
        for top_key, sub_delta in world_delta.items():
            if top_key not in WORLD_FIELD_WHITELIST:
                rejected.append({"path": top_key, "reason": f"顶层字段 '{top_key}' 不在白名单中"})
                continue

            target = world_state.get(top_key)
            if target is None or not isinstance(target, dict):
                rejected.append({"path": top_key, "reason": f"world_state['{top_key}'] 不存在或非 dict"})
                continue

            if not isinstance(sub_delta, dict):
                rejected.append({"path": top_key, "reason": f"delta['{top_key}'] 非 dict"})
                continue

            # 递归应用子字段
            self._apply_nested_delta(top_key, sub_delta, target, applied, rejected)

    def _apply_nested_delta(
        self,
        path_prefix: str,
        delta: Dict[str, Any],
        target: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
        depth: int = 0,
    ) -> None:
        """递归应用嵌套 delta。限制深度防止无限递归。"""
        if depth > 5:
            rejected.append({"path": path_prefix, "reason": "嵌套深度超过限制"})
            return

        for key, value in delta.items():
            current_path = f"{path_prefix}.{key}"

            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                # 递归处理嵌套 dict
                self._apply_nested_delta(current_path, value, target[key], applied, rejected, depth + 1)
            else:
                # 直接赋值
                old_value = target.get(key)
                # 对已知数值字段进行 clamp
                clamped_value = self._clamp_if_needed(key, value)
                target[key] = clamped_value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": clamped_value,
                })

    # ──────────────────────────────────────────────
    #  faction_delta 应用
    # ──────────────────────────────────────────────

    def _apply_faction_delta(
        self,
        faction_delta: Dict[str, Dict[str, Any]],
        world_state: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
    ) -> None:
        """应用势力状态变更。

        faction_delta 格式：{faction_code: {field: delta_value}}
        delta_value 可以是绝对值（直接赋值）或增量（数值加减）。
        """
        faction_state = world_state.get("FACTION_STATE", {})
        if not isinstance(faction_state, dict):
            rejected.append({"path": "FACTION_STATE", "reason": "FACTION_STATE 不存在或非 dict"})
            return

        for faction_code, field_deltas in faction_delta.items():
            entry = faction_state.get(faction_code)
            if entry is None or not isinstance(entry, dict):
                rejected.append({
                    "path": f"FACTION_STATE.{faction_code}",
                    "reason": f"势力 '{faction_code}' 不在 FACTION_STATE 中或非 dict",
                })
                continue

            for field_name, delta_value in field_deltas.items():
                if field_name not in FACTION_FIELD_WHITELIST:
                    rejected.append({
                        "path": f"FACTION_STATE.{faction_code}.{field_name}",
                        "reason": f"字段 '{field_name}' 不在势力白名单中",
                    })
                    continue

                current_path = f"FACTION_STATE.{faction_code}.{field_name}"
                old_value = entry.get(field_name)

                # 数值增量模式：如果 delta 和 old 都是数值，则相加
                if isinstance(delta_value, (int, float)) and isinstance(old_value, (int, float)):
                    new_value = old_value + delta_value
                    new_value = clamp(new_value, field_name)
                    entry[field_name] = new_value
                    applied.append({
                        "path": current_path,
                        "old": old_value,
                        "new": new_value,
                        "delta": delta_value,
                    })
                else:
                    # 绝对值模式：直接赋值
                    clamped_value = clamp(delta_value, field_name) if isinstance(delta_value, (int, float)) else delta_value
                    entry[field_name] = clamped_value
                    applied.append({
                        "path": current_path,
                        "old": old_value,
                        "new": clamped_value,
                    })

    # ──────────────────────────────────────────────
    #  profile_delta 应用
    # ──────────────────────────────────────────────

    def _apply_profile_delta(
        self,
        profile_delta: Dict[str, Any],
        profiles: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
    ) -> None:
        """应用玩家状态变更。

        profile_delta 格式：{slot_id: {field_path: value}}

        LONG-A 扩展：
          - 支持 METHOD_STATE 子字段白名单
          - 支持 CORE_STATE 子字段白名单
          - 支持 cultivation_realm 顶层字段（通过特殊通道）
        """
        for slot_id, slot_delta in profile_delta.items():
            profile = profiles.get(slot_id)
            if profile is None or not isinstance(profile, dict):
                rejected.append({
                    "path": f"profiles.{slot_id}",
                    "reason": f"玩家 '{slot_id}' 不存在或非 dict",
                })
                continue

            if not isinstance(slot_delta, dict):
                rejected.append({
                    "path": f"profiles.{slot_id}",
                    "reason": "delta 非dict",
                })
                continue

            for field_name, value in slot_delta.items():
                current_path = f"profiles.{slot_id}.{field_name}"

                # LONG-A: 特殊处理 METHOD_STATE
                if field_name == "METHOD_STATE" and isinstance(value, dict):
                    self._apply_method_state_delta(
                        current_path, value, profile, applied, rejected
                    )
                    continue

                # LONG-A: 特殊处理 CORE_STATE
                if field_name == "CORE_STATE" and isinstance(value, dict):
                    self._apply_core_state_delta(
                        current_path, value, profile, applied, rejected
                    )
                    continue

                # LONG-A: 特殊处理 cultivation_realm（受保护字段，只允许代码通道写入）
                if field_name == "cultivation_realm":
                    # cultivation_realm 只能通过代码通道写入，不允许 AI STATE_DELTA
                    # 但如果是从突破管理器等代码路径来的，直接写入
                    old_val = profile.get("cultivation_realm")
                    profile["cultivation_realm"] = value
                    applied.append({
                        "path": current_path,
                        "old": old_val,
                        "new": value,
                    })
                    continue

                if field_name not in PROFILE_FIELD_WHITELIST:
                    rejected.append({
                        "path": current_path,
                        "reason": f"字段 '{field_name}' 不在 Profile 白名单中",
                    })
                    continue

                old_value = profile.get(field_name)

                if isinstance(value, dict) and field_name in profile and isinstance(profile[field_name], dict):
                    # 递归合并 dict（如 relations、INFORMATION 等）
                    self._merge_dict_no_clamp(current_path, value, profile[field_name], applied, rejected)
                else:
                    # 数值字段：如果新旧值都是数值，则增量；否则绝对赋值
                    # 注意：profile 字段的 clamp 由业务规则单独处理，此处跳过
                    if isinstance(old_value, (int, float)) and isinstance(value, (int, float)):
                        new_value = old_value + value
                        # 不 clamp profile 字段——业务层自行校验
                        profile[field_name] = new_value
                        applied.append({
                            "path": current_path,
                            "old": old_value,
                            "new": new_value,
                        })
                    else:
                        clamped_value = self._clamp_if_needed(field_name, value)
                        profile[field_name] = clamped_value
                        applied.append({
                            "path": current_path,
                            "old": old_value,
                            "new": clamped_value,
                        })

    # ──────────────────────────────────────────────
    #  LONG-A: METHOD_STATE delta 应用
    # ──────────────────────────────────────────────

    def _apply_method_state_delta(
        self,
        path_prefix: str,
        method_delta: Dict[str, Any],
        profile: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
    ) -> None:
        """应用 METHOD_STATE 子字段变更。

        只允许白名单中的子字段写入，数值字段进行 clamp。
        """
        method = profile.setdefault("METHOD_STATE", {})

        for field_name, value in method_delta.items():
            if field_name not in METHOD_STATE_WHITELIST:
                rejected.append({
                    "path": f"{path_prefix}.{field_name}",
                    "reason": f"METHOD_STATE 字段 '{field_name}' 不在白名单中",
                })
                continue

            current_path = f"{path_prefix}.{field_name}"
            old_value = method.get(field_name)

            # abilities 是嵌套 dict，需要特殊处理
            if field_name == "abilities" and isinstance(value, dict):
                if "abilities" not in method or not isinstance(method.get("abilities"), dict):
                    method["abilities"] = {}
                self._merge_dict_no_clamp(
                    current_path, value, method["abilities"], applied, rejected
                )
                continue

            # known_techniques 是 list，整体替换
            if field_name == "known_techniques" and isinstance(value, list):
                method["known_techniques"] = value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": value,
                })
                continue

            # 数值增量模式
            if isinstance(old_value, (int, float)) and isinstance(value, (int, float)):
                new_value = old_value + value
                # clamp 修炼相关字段
                new_value = self._clamp_cultivation_field(field_name, new_value)
                method[field_name] = new_value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": new_value,
                })
            else:
                # 绝对值模式
                clamped_value = self._clamp_cultivation_field(field_name, value) if isinstance(value, (int, float)) else value
                method[field_name] = clamped_value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": clamped_value,
                })

    # ──────────────────────────────────────────────
    #  LONG-A: CORE_STATE delta 应用
    # ──────────────────────────────────────────────

    def _apply_core_state_delta(
        self,
        path_prefix: str,
        core_delta: Dict[str, Any],
        profile: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
    ) -> None:
        """应用 CORE_STATE 子字段变更。

        只允许白名单中的子字段写入。
        """
        core = profile.setdefault("CORE_STATE", {})

        for field_name, value in core_delta.items():
            if field_name not in CORE_STATE_WHITELIST:
                rejected.append({
                    "path": f"{path_prefix}.{field_name}",
                    "reason": f"CORE_STATE 字段 '{field_name}' 不在白名单中",
                })
                continue

            current_path = f"{path_prefix}.{field_name}"

            # spiritual_root 是嵌套 dict
            if field_name == "spiritual_root" and isinstance(value, dict):
                if "spiritual_root" not in core or not isinstance(core.get("spiritual_root"), dict):
                    core["spiritual_root"] = {}
                self._merge_spiritual_root_delta(
                    current_path, value, core["spiritual_root"], applied, rejected
                )
                continue

            # 其他字段直接赋值
            old_value = core.get(field_name)
            core[field_name] = value
            applied.append({
                "path": current_path,
                "old": old_value,
                "new": value,
            })

    def _merge_spiritual_root_delta(
        self,
        path_prefix: str,
        delta: Dict[str, Any],
        target: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
    ) -> None:
        """合并灵根 delta。

        数值字段（purity, efficiency）使用增量模式并 clamp。
        字符串字段（primary, mutation）使用绝对值模式。
        列表字段（secondary）使用整体替换。
        """
        for key, value in delta.items():
            current_path = f"{path_prefix}.{key}"
            old_value = target.get(key)

            if key in ("purity", "efficiency") and isinstance(value, (int, float)):
                # 数值增量 + clamp
                if isinstance(old_value, (int, float)):
                    new_value = old_value + value
                else:
                    new_value = value
                new_value = self._clamp_cultivation_field(key, new_value)
                target[key] = new_value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": new_value,
                })
            elif key == "secondary" and isinstance(value, list):
                # 列表整体替换
                target["secondary"] = value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": value,
                })
            else:
                # 绝对值模式
                target[key] = value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": value,
                })

    def _clamp_cultivation_field(self, field_name: str, value: Any) -> Any:
        """对修炼相关字段进行 clamp。"""
        if not isinstance(value, (int, float)):
            return value

        # progress 特殊处理：METHOD_STATE.progress 是 0~100 整数
        if field_name == "progress":
            return max(0, min(100, int(value)))

        if field_name in _FIELD_RANGES:
            range_spec = _FIELD_RANGES[field_name]
            if range_spec is not None:
                lo, hi = range_spec
                return max(lo, min(hi, value))

        return value

    def _merge_dict(
        self,
        path_prefix: str,
        delta: Dict[str, Any],
        target: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
    ) -> None:
        """合并 dict delta 到目标 dict。"""
        for key, value in delta.items():
            current_path = f"{path_prefix}.{key}"
            old_value = target.get(key)

            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._merge_dict(current_path, value, target[key], applied, rejected)
            else:
                clamped_value = self._clamp_if_needed(key, value)
                target[key] = clamped_value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": clamped_value,
                })

    def _merge_dict_no_clamp(
        self,
        path_prefix: str,
        delta: Dict[str, Any],
        target: Dict[str, Any],
        applied: List[Dict],
        rejected: List[Dict],
    ) -> None:
        """合并 dict delta 到目标 dict，不做数值 clamp（用于 profile 字段）。

        数值增量模式：如果新旧值都是数值，则相加。
        否则直接赋值。
        """
        for key, value in delta.items():
            current_path = f"{path_prefix}.{key}"
            old_value = target.get(key)

            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._merge_dict_no_clamp(current_path, value, target[key], applied, rejected)
            elif isinstance(old_value, (int, float)) and isinstance(value, (int, float)):
                # 数值增量
                new_value = old_value + value
                target[key] = new_value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": new_value,
                })
            else:
                target[key] = value
                applied.append({
                    "path": current_path,
                    "old": old_value,
                    "new": value,
                })

    # ──────────────────────────────────────────────
    #  工具方法
    # ──────────────────────────────────────────────

    def _clamp_if_needed(self, field_name: str, value: Any) -> Any:
        """如果字段在 clamp 范围内，则 clamp。"""
        if field_name in _FIELD_RANGES and isinstance(value, (int, float)):
            return clamp(value, field_name)
        return value
