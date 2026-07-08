"""
event_outcome_resolver.py — 事件结果判定器（B-6.2）

根据事件类别、阶段、进度、参与势力、世界状态，判定事件最终结果。

核心接口：
  resolve(event, world_state, campaign, factions=None, profiles=None) -> EventOutcome

规则：
  - 不同 category 有不同 outcome
  - outcome 可预测，不依赖 AI 文本
  - 可用 deterministic rule 测试
  - 不直接修改状态
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from .event_outcome import (
        EventOutcome, EventOutcomeType,
        make_resolved_outcome, make_failed_outcome,
        make_partial_outcome, make_expired_outcome,
        make_escalated_outcome,
    )
except ImportError:
    from event_outcome import (
        EventOutcome, EventOutcomeType,
        make_resolved_outcome, make_failed_outcome,
        make_partial_outcome, make_expired_outcome,
        make_escalated_outcome,
    )

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  判定规则常量
# ──────────────────────────────────────────────

# 进度阈值：progress >= 此值时倾向 resolved
_PROGRESS_RESOLVE_THRESHOLD = 0.8

# 进度阈值：progress < 此值时倾向 failed
_PROGRESS_FAIL_THRESHOLD = 0.3

# CHAOS 阈值：chaos_level 在这些值时倾向失败
_CHAOS_HIGH_LEVELS = frozenset({"活跃-世界级", "活跃-非世界级", "临界"})

# stability 阈值：stability > 此值时势力冲突事件倾向成功
_STABILITY_OK_THRESHOLD = 0.5

# morale 阈值：morale > 此值时势力冲突事件倾向成功
_MORALE_OK_THRESHOLD = 0.5


class EventOutcomeResolver:
    """事件结果判定器。

    根据事件类别和当前世界状态，生成结构化的 EventOutcome。
    不直接修改任何状态。
    """

    def resolve(
        self,
        event: Any,
        world_state: Dict[str, Any],
        campaign: Optional[Dict[str, Any]] = None,
        factions: Optional[Dict[str, Any]] = None,
        profiles: Optional[Dict[str, Any]] = None,
    ) -> EventOutcome:
        """根据事件和当前世界状态生成 EventOutcome。

        Args:
            event: ActiveEvent 对象（或兼容的 dict）
            world_state: 当前世界状态
            campaign: 团务状态（可选）
            factions: 势力静态数据（可选）
            profiles: 玩家档案（可选）

        Returns:
            EventOutcome 对象
        """
        # 提取事件属性（兼容 ActiveEvent 和 dict）
        event_id = self._get_attr(event, "event_id", "UNKNOWN")
        category = self._get_attr(event, "category", "日常")
        progress = self._get_attr(event, "progress", 0.0)
        region = self._get_attr(event, "region", "")
        participants = self._get_attr(event, "participants", [])
        title = self._get_attr(event, "title", "")

        # 按类别分发判定
        if category == "灵脉资源":
            return self._resolve_leyline(event_id, title, progress, region, world_state)
        elif category == "CHAOS异常":
            return self._resolve_chaos(event_id, title, progress, region, world_state)
        elif category == "势力冲突":
            return self._resolve_faction_conflict(
                event_id, title, progress, region, participants, world_state, factions
            )
        elif category == "遗迹与机缘":
            return self._resolve_ruin(event_id, title, progress, region, world_state)
        elif category == "日常":
            return self._resolve_daily(event_id, title, progress, region, world_state)
        elif category == "修行突破":
            return self._resolve_cultivation(event_id, title, progress, region, world_state)
        else:
            # 未知类别：按 progress 判定
            return self._resolve_generic(event_id, title, progress)

    # ──────────────────────────────────────────────
    #  各类别判定方法
    # ──────────────────────────────────────────────

    def _resolve_leyline(
        self, event_id: str, title: str, progress: float,
        region: str, world_state: Dict,
    ) -> EventOutcome:
        """灵脉资源事件判定。

        成功倾向：灵气值稳定、相关资源恢复
        失败倾向：灵气继续下降、资源低值
        """
        # 检查区域灵气/资源状态
        resource_state = world_state.get("RESOURCE", {})
        region_key = self._region_to_resource_key(region)
        region_resource = resource_state.get(region_key, {})
        resource_state_text = region_resource.get("state", "")

        # 判定逻辑
        is_stable = "稳定" in resource_state_text or "活跃" in resource_state_text
        is_low = "紧张" in resource_state_text or "高压" in resource_state_text or "趋紧" in resource_state_text

        if progress >= _PROGRESS_RESOLVE_THRESHOLD and is_stable:
            return make_resolved_outcome(
                event_id,
                summary=f"灵脉资源事件「{title}」成功解决，{region}灵气趋于稳定。",
                world_delta=self._leyline_resolve_delta(region),
            )
        elif progress < _PROGRESS_FAIL_THRESHOLD and is_low:
            return make_failed_outcome(
                event_id,
                summary=f"灵脉资源事件「{title}」失败，{region}灵气持续恶化。",
                world_delta=self._leyline_fail_delta(region),
            )
        elif progress >= _PROGRESS_RESOLVE_THRESHOLD:
            return make_partial_outcome(
                event_id,
                summary=f"灵脉资源事件「{title}」部分成功，{region}灵气有所恢复但未完全稳定。",
                world_delta=self._leyline_partial_delta(region),
            )
        else:
            return make_expired_outcome(
                event_id,
                summary=f"灵脉资源事件「{title}」自然消散，{region}灵气状态未明显变化。",
            )

    def _resolve_chaos(
        self, event_id: str, title: str, progress: float,
        region: str, world_state: Dict,
    ) -> EventOutcome:
        """CHAOS异常事件判定。

        成功倾向：chaos_level 降低
        失败倾向：chaos_level 高压/临界
        """
        global_state = world_state.get("GLOBAL", {})
        chaos_level = global_state.get("chaos_level", "平稳")

        is_high_chaos = chaos_level in _CHAOS_HIGH_LEVELS

        if progress >= _PROGRESS_RESOLVE_THRESHOLD and not is_high_chaos:
            return make_resolved_outcome(
                event_id,
                summary=f"CHAOS异常事件「{title}」成功压制，异常活跃度下降。",
                world_delta=self._chaos_resolve_delta(),
            )
        elif is_high_chaos:
            return make_failed_outcome(
                event_id,
                summary=f"CHAOS异常事件「{title}」恶化，异常活跃度持续升高。",
                world_delta=self._chaos_fail_delta(),
            )
        elif progress >= 0.5:
            return make_partial_outcome(
                event_id,
                summary=f"CHAOS异常事件「{title}」部分压制，异常活跃度有所降低。",
                world_delta=self._chaos_partial_delta(),
            )
        else:
            return make_expired_outcome(
                event_id,
                summary=f"CHAOS异常事件「{title}」自然消散，异常活跃度未明显变化。",
            )

    def _resolve_faction_conflict(
        self, event_id: str, title: str, progress: float,
        region: str, participants: list, world_state: Dict,
        factions: Optional[Dict],
    ) -> EventOutcome:
        """势力冲突事件判定。

        成功倾向：相关势力 stability 回升
        失败倾向：stability / morale 继续下降
        """
        faction_state = world_state.get("FACTION_STATE", {})

        # 收集参与势力的状态
        involved_stabilities = []
        involved_morales = []
        involved_codes = []

        for p in participants:
            # participants 可能是势力名或 code
            code = self._find_faction_code(p, factions)
            if not code:
                continue
            entry = faction_state.get(code, {})
            if isinstance(entry, dict):
                involved_stabilities.append(entry.get("stability", 0.5))
                involved_morales.append(entry.get("morale", 0.5))
                involved_codes.append(code)

        avg_stability = sum(involved_stabilities) / len(involved_stabilities) if involved_stabilities else 0.5
        avg_morale = sum(involved_morales) / len(involved_morales) if involved_morales else 0.5

        # 无参与势力时，回退到 generic 判定
        if not involved_codes:
            return self._resolve_generic(event_id, title, progress)

        if progress >= _PROGRESS_RESOLVE_THRESHOLD and avg_stability > _STABILITY_OK_THRESHOLD and avg_morale > _MORALE_OK_THRESHOLD:
            # 成功：stability 回升
            faction_delta = {}
            for code in involved_codes:
                faction_delta[code] = {"stability": 0.05, "morale": 0.03}
            return make_resolved_outcome(
                event_id,
                summary=f"势力冲突事件「{title}」成功调解，相关势力稳定度回升。",
                faction_delta=faction_delta,
            )
        elif avg_stability <= _STABILITY_OK_THRESHOLD or avg_morale <= _MORALE_OK_THRESHOLD:
            # 失败：stability / morale 下降
            faction_delta = {}
            for code in involved_codes:
                faction_delta[code] = {"stability": -0.05, "morale": -0.03}
            return make_failed_outcome(
                event_id,
                summary=f"势力冲突事件「{title}」恶化，相关势力动荡加剧。",
                faction_delta=faction_delta,
            )
        elif progress >= 0.5:
            # 部分成功
            faction_delta = {}
            for code in involved_codes:
                faction_delta[code] = {"stability": 0.02, "morale": 0.01}
            return make_partial_outcome(
                event_id,
                summary=f"势力冲突事件「{title}」部分缓解，局势有所缓和。",
                faction_delta=faction_delta,
            )
        else:
            return make_expired_outcome(
                event_id,
                summary=f"势力冲突事件「{title}」自然平息，但根源未解。",
            )

    def _resolve_ruin(
        self, event_id: str, title: str, progress: float,
        region: str, world_state: Dict,
    ) -> EventOutcome:
        """遗迹与机缘事件判定。

        成功倾向：探索成功、资源增加
        失败倾向：异常增强、CHAOS 上升
        """
        global_state = world_state.get("GLOBAL", {})
        chaos_level = global_state.get("chaos_level", "平稳")
        is_high_chaos = chaos_level in _CHAOS_HIGH_LEVELS

        if progress >= _PROGRESS_RESOLVE_THRESHOLD and not is_high_chaos:
            return make_resolved_outcome(
                event_id,
                summary=f"遗迹探索事件「{title}」成功，获得珍贵资源与发现。",
                world_delta=self._ruin_resolve_delta(region),
            )
        elif is_high_chaos or progress < _PROGRESS_FAIL_THRESHOLD:
            return make_failed_outcome(
                event_id,
                summary=f"遗迹探索事件「{title}」失败，异常活跃度上升。",
                world_delta=self._chaos_fail_delta(),
            )
        elif progress >= 0.5:
            return make_partial_outcome(
                event_id,
                summary=f"遗迹探索事件「{title}」部分成功，获得少量发现但未完全探索。",
                world_delta=self._ruin_partial_delta(region),
            )
        else:
            return make_expired_outcome(
                event_id,
                summary=f"遗迹探索事件「{title}」自然消散，机缘已逝。",
            )

    def _resolve_daily(
        self, event_id: str, title: str, progress: float,
        region: str, world_state: Dict,
    ) -> EventOutcome:
        """日常事件判定。

        成功倾向：小幅正向结果
        失败倾向：无明显影响
        """
        if progress >= _PROGRESS_RESOLVE_THRESHOLD:
            return make_resolved_outcome(
                event_id,
                summary=f"日常事件「{title}」顺利结束，小幅正向影响。",
            )
        elif progress >= 0.5:
            return make_partial_outcome(
                event_id,
                summary=f"日常事件「{title}」平淡收场，无明显影响。",
            )
        else:
            return make_expired_outcome(
                event_id,
                summary=f"日常事件「{title}」自然消散。",
            )

    def _resolve_cultivation(
        self, event_id: str, title: str, progress: float,
        region: str, world_state: Dict,
    ) -> EventOutcome:
        """修行突破事件判定。

        成功倾向：灵气稳定、资源充足
        失败倾向：灵气波动、资源紧张
        """
        resource_state = world_state.get("RESOURCE", {})
        region_key = self._region_to_resource_key(region)
        region_resource = resource_state.get(region_key, {})
        resource_state_text = region_resource.get("state", "")

        is_stable = "稳定" in resource_state_text or "活跃" in resource_state_text

        if progress >= _PROGRESS_RESOLVE_THRESHOLD and is_stable:
            return make_resolved_outcome(
                event_id,
                summary=f"修行突破事件「{title}」成功，灵气条件有利。",
            )
        elif progress < _PROGRESS_FAIL_THRESHOLD:
            return make_failed_outcome(
                event_id,
                summary=f"修行突破事件「{title}」失败，灵气条件不利。",
            )
        else:
            return make_partial_outcome(
                event_id,
                summary=f"修行突破事件「{title}」部分成功，有所收获但未完全突破。",
            )

    def _resolve_generic(
        self, event_id: str, title: str, progress: float,
    ) -> EventOutcome:
        """通用判定：仅按 progress 判定。"""
        if progress >= _PROGRESS_RESOLVE_THRESHOLD:
            return make_resolved_outcome(
                event_id,
                summary=f"事件「{title}」成功解决。",
            )
        elif progress < _PROGRESS_FAIL_THRESHOLD:
            return make_failed_outcome(
                event_id,
                summary=f"事件「{title}」失败。",
            )
        elif progress >= 0.5:
            return make_partial_outcome(
                event_id,
                summary=f"事件「{title}」部分成功。",
            )
        else:
            return make_expired_outcome(
                event_id,
                summary=f"事件「{title}」自然消散。",
            )

    # ──────────────────────────────────────────────
    #  Delta 生成辅助
    # ──────────────────────────────────────────────

    def _leyline_resolve_delta(self, region: str) -> Dict:
        """灵脉资源成功：区域灵气恢复。"""
        region_key = self._region_to_resource_key(region)
        return {"RESOURCE": {region_key: {"state": "稳定"}}}

    def _leyline_fail_delta(self, region: str) -> Dict:
        """灵脉资源失败：区域灵气恶化。"""
        region_key = self._region_to_resource_key(region)
        return {"RESOURCE": {region_key: {"state": "紧张、波动"}}}

    def _leyline_partial_delta(self, region: str) -> Dict:
        """灵脉资源部分成功：区域灵气有所恢复。"""
        region_key = self._region_to_resource_key(region)
        return {"RESOURCE": {region_key: {"state": "趋稳"}}}

    def _chaos_resolve_delta(self) -> Dict:
        """CHAOS 成功：chaos_level 下降。"""
        return {"GLOBAL": {"chaos_level": "平稳"}}

    def _chaos_fail_delta(self) -> Dict:
        """CHAOS 失败：chaos_level 上升。"""
        return {"GLOBAL": {"chaos_level": "活跃-非世界级"}}

    def _chaos_partial_delta(self) -> Dict:
        """CHAOS 部分成功：chaos_level 略降。"""
        return {"GLOBAL": {"chaos_level": "低度活跃"}}

    def _ruin_resolve_delta(self, region: str) -> Dict:
        """遗迹成功：资源增加。"""
        region_key = self._region_to_resource_key(region)
        return {"RESOURCE": {region_key: {"state": "活跃"}}}

    def _ruin_partial_delta(self, region: str) -> Dict:
        """遗迹部分成功：少量发现。"""
        region_key = self._region_to_resource_key(region)
        return {"RESOURCE": {region_key: {"state": "波动"}}}

    # ──────────────────────────────────────────────
    #  工具方法
    # ──────────────────────────────────────────────

    _REGION_RESOURCE_MAP = {
        "中部": "中部主脉残核",
        "东部": "东部新生支脉",
        "南部": "南部资源网络",
        "北地": "北地沉潜资源",
        "西部": "西部遗迹与异常资源",
    }

    def _region_to_resource_key(self, region: str) -> str:
        """将区域名映射到 RESOURCE 中的 key。"""
        return self._REGION_RESOURCE_MAP.get(region, region)

    def _find_faction_code(self, name_or_code: str, factions: Optional[Dict]) -> Optional[str]:
        """从势力名或 code 中找到 faction code。"""
        if not factions:
            return None
        # 先尝试直接匹配 code
        if name_or_code in factions:
            return name_or_code
        # 再尝试匹配 name
        for code, fac in factions.items():
            if fac.get("name") == name_or_code:
                return code
        return None

    @staticmethod
    def _get_attr(obj: Any, attr: str, default: Any = None) -> Any:
        """从对象中获取属性，兼容 ActiveEvent 和 dict。"""
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)
