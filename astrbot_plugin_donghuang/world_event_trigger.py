"""
world_event_trigger.py — 世界变化 → 事件触发桥接

检测 World Tick 后的世界变化，判断是否需要向 EventPool 注册已有类型事件。

职责：
  1. 灵脉异常检测（灵气连续下降 → 灵脉资源事件）
  2. CHAOS 异常检测（chaos_level 超阈值 → CHAOS异常事件）
  3. 资源异常检测（资源值持续过低 → 灵脉资源/日常事件）
  4. 势力动态检测（stance/内乱/衰退/盟友 → 势力冲突/遗迹机缘事件）——B-5.3
  5. 环境状态触发检测（灵气衰潮/血月/空间裂隙/灵墟投影/九曜乱象 → 已有事件类型）——B-15

不负责：
  - 新增事件类型
  - 自动生成剧情文本
  - 修改 AI Prompt
  - 修改 EventPool 数据结构
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from .world_event_pool import EventPool, EventCategory, EventPriority, EventVisibility
except ImportError:
    from world_event_pool import EventPool, EventCategory, EventPriority, EventVisibility

logger = logging.getLogger(__name__)

# CHAOS 活跃度阈值（达到此级别时触发 CHAOS 异常事件）
_CHAOS_THRESHOLD = "活跃"

# 灵气连续下降触发阈值
_LEYLINE_DECLINE_THRESHOLD = 3

# 资源低值阈值
_RESOURCE_LOW_THRESHOLD = 20

# 资源连续低值触发阈值
_RESOURCE_LOW_CONSECUTIVE = 2

# ──────────────────────────────────────────────
#  势力触发常量（B-5.3）
# ──────────────────────────────────────────────

# Power 连续下降触发阈值（连续 Tick 数）
_FACTION_POWER_DECLINE_THRESHOLD = 3

# Power 衰退阈值
_FACTION_POWER_LOW_THRESHOLD = 30

# 盟友联合的 power 阈值
_FACTION_ALLY_POWER_THRESHOLD = 70

# evolution_memory 初始结构
_DEFAULT_MEMORY = {
    "leyline_decline_count": 0,
    "resource_low_count": {},
    "faction_power_decline_ticks": {},
}


class WorldEventTrigger:
    """检测世界变化，判断是否需要向 EventPool 注册事件。"""

    def check(
        self,
        group_id: str,
        world_state: Dict[str, Any],
        event_pool: EventPool,
        evolution_result: Dict[str, Any],
        campaign: Dict[str, Any],
        cycle: int,
        factions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """检测世界变化并触发事件注册。

        Args:
            group_id: 群号
            world_state: 当前世界状态
            event_pool: EventPool 实例
            evolution_result: 本次 WorldEvolutionManager.evolve() 的返回值
            campaign: 团务状态字典（会被修改：写入 evolution_memory）
            cycle: 当前 cycle
            factions: 静态势力数据字典（可选，B-5.3 势力触发需要）

        Returns:
            触发结果字典：
            {
                "triggered": [{"event_id", "title", "category", "region"}],
                "skipped": [{"reason", "category", "region"}],
            }
        """
        result = {
            "triggered": [],
            "skipped": [],
        }

        # 确保 evolution_memory 存在
        if "evolution_memory" not in campaign:
            campaign["evolution_memory"] = dict(_DEFAULT_MEMORY)

        memory = campaign["evolution_memory"]
        # B-5.3: 补全新字段（向后兼容）
        if "faction_power_decline_ticks" not in memory:
            memory["faction_power_decline_ticks"] = {}

        # ── 灵脉异常检测 ──
        self._check_leyline_anomaly(
            group_id, world_state, event_pool, evolution_result,
            memory, result,
        )

        # ── CHAOS 异常检测 ──
        self._check_chaos_anomaly(
            group_id, world_state, event_pool, memory, result,
        )

        # ── 资源异常检测 ──
        self._check_resource_anomaly(
            group_id, world_state, event_pool, memory, result,
        )

        # ── 势力动态检测（B-5.3）──
        self._check_faction_trigger(
            group_id, world_state, event_pool, evolution_result,
            memory, result, cycle, factions,
        )

        # ── 环境状态触发检测（B-15）──
        self._check_environment_trigger(
            group_id, world_state, event_pool, evolution_result,
            memory, result, cycle,
        )

        logger.info(
            f"[WorldEventTrigger] check({group_id}): "
            f"触发{len(result['triggered'])}条, "
            f"跳过{len(result['skipped'])}条"
        )

        return result

    # ──────────────────────────────────────────────
    #  灵脉异常检测
    # ──────────────────────────────────────────────

    def _check_leyline_anomaly(
        self,
        group_id: str,
        world_state: Dict,
        event_pool: EventPool,
        evolution_result: Dict,
        memory: Dict,
        result: Dict,
    ) -> None:
        """灵气流向连续下降 → 触发灵脉资源事件。"""
        evo = evolution_result

        # 检测灵气是否下降
        if evo.get("leyline_flow_changed"):
            flow_from = evo.get("leyline_flow_from", 0)
            flow_to = evo.get("leyline_flow_to", 0)
            if flow_to < flow_from:
                memory["leyline_decline_count"] = memory.get("leyline_decline_count", 0) + 1
            else:
                # 灵气没有下降，连续性中断，重置计数
                memory["leyline_decline_count"] = 0
        else:
            # 本次灵气未变化，连续性中断，重置计数
            memory["leyline_decline_count"] = 0

        # 检查是否达到触发条件
        decline_count = memory.get("leyline_decline_count", 0)
        if decline_count < _LEYLINE_DECLINE_THRESHOLD:
            return

        # 检查是否已有灵脉资源事件
        if self._has_active_event(event_pool, group_id, category="灵脉资源"):
            result["skipped"].append({
                "reason": "已有同类别活跃事件",
                "category": "灵脉资源",
                "region": "",
            })
            return

        # 触发事件
        event = event_pool.add(
            group_id=group_id,
            title="灵脉流向异常",
            category=EventCategory.LEYLINE_RESOURCE.value,
            stage="萌芽",
            region="",
            location="",
            participants=[],
            summary=f"灵气流向连续{decline_count}次下降，灵脉出现异常征兆",
            progress=0.05,
            priority=EventPriority.MEDIUM.value,
            visibility=EventVisibility.PUBLIC.value,
            player_related=False,
        )

        result["triggered"].append({
            "event_id": event.event_id,
            "title": event.title,
            "category": event.category,
            "region": event.region,
        })

        # 重置计数
        memory["leyline_decline_count"] = 0

    # ──────────────────────────────────────────────
    #  CHAOS 异常检测
    # ──────────────────────────────────────────────

    def _check_chaos_anomaly(
        self,
        group_id: str,
        world_state: Dict,
        event_pool: EventPool,
        memory: Dict,
        result: Dict,
    ) -> None:
        """CHAOS 活跃度超阈值 → 触发 CHAOS 异常事件。"""
        chaos_level = world_state.get("GLOBAL", {}).get("chaos_level", "")

        # 检查是否达到阈值
        if not chaos_level or chaos_level not in ("活跃", "高压", "临界",
                                                    "活跃-非世界级"):
            return

        # 检查是否已有 CHAOS 异常事件
        if self._has_active_event(event_pool, group_id, category="CHAOS异常"):
            result["skipped"].append({
                "reason": "已有同类别活跃事件",
                "category": "CHAOS异常",
                "region": "",
            })
            return

        # 触发事件
        event = event_pool.add(
            group_id=group_id,
            title="CHAOS活跃度异常升高",
            category=EventCategory.CHAOS_ANOMALY.value,
            stage="萌芽",
            region="",
            location="",
            participants=[],
            summary=f"CHAOS活跃度达到{chaos_level}，天地灵气出现紊乱征兆",
            progress=0.05,
            priority=EventPriority.HIGH.value,
            visibility=EventVisibility.PUBLIC.value,
            player_related=False,
        )

        result["triggered"].append({
            "event_id": event.event_id,
            "title": event.title,
            "category": event.category,
            "region": event.region,
        })

    # ──────────────────────────────────────────────
    #  资源异常检测
    # ──────────────────────────────────────────────

    def _check_resource_anomaly(
        self,
        group_id: str,
        world_state: Dict,
        event_pool: EventPool,
        memory: Dict,
        result: Dict,
    ) -> None:
        """资源值持续过低 → 触发灵脉资源/日常事件。"""
        resource_state = world_state.get("RESOURCE", {})
        if not resource_state:
            return

        low_count = memory.get("resource_low_count", {})

        for name, info in resource_state.items():
            if not isinstance(info, dict):
                continue

            value = info.get("value", 50)

            if value <= _RESOURCE_LOW_THRESHOLD:
                # 资源低值，计数 +1
                low_count[name] = low_count.get(name, 0) + 1
            else:
                # 资源恢复，重置计数
                low_count[name] = 0

        memory["resource_low_count"] = low_count

        # 检查哪些资源连续低值
        for name, count in low_count.items():
            if count < _RESOURCE_LOW_CONSECUTIVE:
                continue

            # 判断事件类别：灵脉相关 → 灵脉资源，否则 → 日常
            if "灵脉" in name or "灵气" in name:
                category = EventCategory.LEYLINE_RESOURCE.value
                title = f"{name}资源告急"
                summary = f"{name}资源值连续{count}次低于{_RESOURCE_LOW_THRESHOLD}，供给紧张"
            else:
                category = EventCategory.DAILY.value
                title = f"{name}供给短缺"
                summary = f"{name}资源值连续{count}次低于{_RESOURCE_LOW_THRESHOLD}，日常运转受影响"

            # 检查是否已有同类别事件
            if self._has_active_event(event_pool, group_id, category=category):
                result["skipped"].append({
                    "reason": "已有同类别活跃事件",
                    "category": category,
                    "region": name,
                })
                continue

            # 触发事件
            event = event_pool.add(
                group_id=group_id,
                title=title,
                category=category,
                stage="萌芽",
                region="",
                location=name,
                participants=[],
                summary=summary,
                progress=0.05,
                priority=EventPriority.MEDIUM.value,
                visibility=EventVisibility.PUBLIC.value,
                player_related=False,
            )

            result["triggered"].append({
                "event_id": event.event_id,
                "title": event.title,
                "category": event.category,
                "region": event.region,
            })

            # 重置该资源计数
            low_count[name] = 0

    # ──────────────────────────────────────────────
    #  势力动态检测（B-5.3）
    # ──────────────────────────────────────────────

    def _check_faction_trigger(
        self,
        group_id: str,
        world_state: Dict,
        event_pool: EventPool,
        evolution_result: Dict,
        memory: Dict,
        result: Dict,
        cycle: int,
        factions: Optional[Dict[str, Any]],
    ) -> None:
        """检测势力状态变化，判断是否需要向 EventPool 注册势力相关事件。

        四条触发规则：
          Rule 1: stance → "对立" → FACTION_CONFLICT (HIGH)
          Rule 2: active_goal → "内乱" → FACTION_CONFLICT (MEDIUM)
          Rule 3: power 连续下降且 ≤30 → FACTION_CONFLICT (MEDIUM)
          Rule 4: 盟友 + power > 70 → RUIN_OPPORTUNITY (LOW)
        """
        faction_state = world_state.get("FACTION_STATE")
        if not faction_state or not isinstance(faction_state, dict):
            return
        if not factions:
            return

        faction_changed = evolution_result.get("faction_changed", [])

        # ── Rule 1: stance_overrides 中出现新的"对立" ──
        self._check_stance_hostility(
            group_id, world_state, event_pool, faction_state,
            faction_changed, factions, result, cycle,
        )

        # ── Rule 2: active_goal → "内乱" ──
        self._check_goal_civil_strife(
            group_id, event_pool, faction_state, faction_changed,
            factions, result, cycle,
        )

        # ── Rule 3: power 连续下降且 ≤30 ──
        self._check_power_decline(
            group_id, event_pool, faction_state, faction_changed,
            memory, factions, result, cycle,
        )

        # ── Rule 4: 盟友 + power > 70 → RUIN_OPPORTUNITY ──
        self._check_ally_opportunity(
            group_id, event_pool, faction_state, factions, result, cycle,
        )

    def _check_stance_hostility(
        self,
        group_id: str,
        world_state: Dict,
        event_pool: EventPool,
        faction_state: Dict,
        faction_changed: List[Dict],
        factions: Dict,
        result: Dict,
        cycle: int,
    ) -> None:
        """Rule 1: stance 从非'对立'变为'对立' → FACTION_CONFLICT (HIGH)。"""
        for change in faction_changed:
            if change.get("field") != "stance_overrides":
                continue
            code = change.get("code", "")
            to_val = change.get("to")
            # to_val 是 dict，检查是否包含新的"对立"
            if not isinstance(to_val, dict):
                continue
            fac_info = factions.get(code)
            if not fac_info:
                continue

            for target_code, new_stance in to_val.items():
                if new_stance != "对立":
                    continue
                # 检查原始 stance 是否非"对立"
                original_stance = self._get_default_stance(fac_info, target_code)
                if original_stance == "对立":
                    continue  # 原本就是对立，不是变化

                target_info = factions.get(target_code)
                fac_name = fac_info.get("name", code)
                target_name = target_info.get("name", target_code) if target_info else target_code
                region = fac_info.get("region", "")

                if self._has_active_event(event_pool, group_id, category="势力冲突", region=region):
                    result["skipped"].append({
                        "reason": "已有同类别势力事件",
                        "category": "势力冲突",
                        "region": region,
                    })
                    continue

                event = event_pool.add(
                    group_id=group_id,
                    title=f"{fac_name}与{target_name}关系恶化，边境冲突升级",
                    category=EventCategory.FACTION_CONFLICT.value,
                    region=region,
                    location=fac_info.get("stronghold", ""),
                    participants=[code, target_code],
                    summary=f"{fac_name}与{target_name}关系从'{original_stance}'恶化为'对立'，"
                            f"边境局势急剧升温 [faction_trigger]",
                    progress=0.05,
                    priority=EventPriority.HIGH.value,
                    visibility=EventVisibility.PUBLIC.value,
                    player_related=False,
                )

                result["triggered"].append({
                    "event_id": event.event_id,
                    "title": event.title,
                    "category": event.category,
                    "region": event.region,
                    "metadata": {
                        "trigger_source": "faction_trigger",
                        "faction_codes": [code, target_code],
                        "trigger_cycle": cycle,
                    },
                })

    def _check_goal_civil_strife(
        self,
        group_id: str,
        event_pool: EventPool,
        faction_state: Dict,
        faction_changed: List[Dict],
        factions: Dict,
        result: Dict,
        cycle: int,
    ) -> None:
        """Rule 2: active_goal → '内乱' → FACTION_CONFLICT (MEDIUM)。"""
        for change in faction_changed:
            if change.get("field") != "active_goal":
                continue
            if change.get("to") != "内乱":
                continue

            code = change.get("code", "")
            fac_info = factions.get(code)
            if not fac_info:
                continue

            fac_name = fac_info.get("name", code)
            region = fac_info.get("region", "")

            if self._has_active_event(event_pool, group_id, category="势力冲突", region=region):
                result["skipped"].append({
                    "reason": "已有同类别势力事件",
                    "category": "势力冲突",
                    "region": region,
                })
                continue

            event = event_pool.add(
                group_id=group_id,
                title=f"{fac_name}内部权力斗争激化",
                category=EventCategory.FACTION_CONFLICT.value,
                region=region,
                location=fac_info.get("stronghold", ""),
                participants=[code],
                summary=f"{fac_name}内部权力斗争白热化，派系冲突公开化 [faction_trigger]",
                progress=0.05,
                priority=EventPriority.MEDIUM.value,
                visibility=EventVisibility.PUBLIC.value,
                player_related=False,
            )

            result["triggered"].append({
                "event_id": event.event_id,
                "title": event.title,
                "category": event.category,
                "region": event.region,
                "metadata": {
                    "trigger_source": "faction_trigger",
                    "faction_codes": [code],
                    "trigger_cycle": cycle,
                },
            })

    def _check_power_decline(
        self,
        group_id: str,
        event_pool: EventPool,
        faction_state: Dict,
        faction_changed: List[Dict],
        memory: Dict,
        factions: Dict,
        result: Dict,
        cycle: int,
    ) -> None:
        """Rule 3: power 连续下降且 ≤30 → FACTION_CONFLICT (MEDIUM)。"""
        decline_ticks = memory.get("faction_power_decline_ticks", {})

        # 更新连续下降计数：基于 faction_changed 中 power 字段的变化
        power_decreased = set()
        for change in faction_changed:
            if change.get("field") != "power":
                continue
            code = change.get("code", "")
            from_val = change.get("from", 0)
            to_val = change.get("to", 0)
            if to_val < from_val:
                power_decreased.add(code)
                decline_ticks[code] = decline_ticks.get(code, 0) + 1
            else:
                decline_ticks[code] = 0

        # 对不在 faction_changed 中的势力，重置计数
        all_faction_codes = set(faction_state.keys())
        for code in all_faction_codes:
            if code not in power_decreased:
                decline_ticks[code] = 0

        memory["faction_power_decline_ticks"] = decline_ticks

        # 检查触发条件
        for code, count in decline_ticks.items():
            if count < _FACTION_POWER_DECLINE_THRESHOLD:
                continue

            entry = faction_state.get(code)
            if not isinstance(entry, dict):
                continue
            if entry.get("power", 100) > _FACTION_POWER_LOW_THRESHOLD:
                continue

            fac_info = factions.get(code)
            if not fac_info:
                continue

            fac_name = fac_info.get("name", code)
            region = fac_info.get("region", "")

            if self._has_active_event(event_pool, group_id, category="势力冲突", region=region):
                result["skipped"].append({
                    "reason": "已有同类别势力事件",
                    "category": "势力冲突",
                    "region": region,
                })
                continue

            event = event_pool.add(
                group_id=group_id,
                title=f"{fac_name}势力衰退，周边势力开始觊觎",
                category=EventCategory.FACTION_CONFLICT.value,
                region=region,
                location=fac_info.get("stronghold", ""),
                participants=[code],
                summary=f"{fac_name}实力连续{count}次下降且已衰退至{entry.get('power', 0)}，"
                        f"周边势力虎视眈眈 [faction_trigger]",
                progress=0.05,
                priority=EventPriority.MEDIUM.value,
                visibility=EventVisibility.PUBLIC.value,
                player_related=False,
            )

            result["triggered"].append({
                "event_id": event.event_id,
                "title": event.title,
                "category": event.category,
                "region": event.region,
                "metadata": {
                    "trigger_source": "faction_trigger",
                    "faction_codes": [code],
                    "trigger_cycle": cycle,
                },
            })

            # 重置计数
            decline_ticks[code] = 0

    def _check_ally_opportunity(
        self,
        group_id: str,
        event_pool: EventPool,
        faction_state: Dict,
        factions: Dict,
        result: Dict,
        cycle: int,
    ) -> None:
        """Rule 4: 盟友 + power > 70 → RUIN_OPPORTUNITY (LOW)。"""
        checked_pairs = set()

        for code, fac_info in factions.items():
            entry = faction_state.get(code)
            if not isinstance(entry, dict):
                continue
            if entry.get("power", 0) <= _FACTION_ALLY_POWER_THRESHOLD:
                continue

            for rel in fac_info.get("relations", []) or []:
                if not isinstance(rel, dict):
                    continue
                target_code = rel.get("code", "")
                stance = rel.get("stance", "")

                # 只检查盟友关系
                if stance != "盟友":
                    continue

                # 检查目标势力 power
                target_entry = faction_state.get(target_code)
                if not isinstance(target_entry, dict):
                    continue
                if target_entry.get("power", 0) <= _FACTION_ALLY_POWER_THRESHOLD:
                    continue

                # 防止同对势力重复检查
                pair_key = "|".join(sorted([code, target_code]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                target_info = factions.get(target_code)
                fac_name = fac_info.get("name", code)
                target_name = target_info.get("name", target_code) if target_info else target_code
                region = fac_info.get("region", "")

                if self._has_active_event(event_pool, group_id, category="遗迹与机缘", region=region):
                    result["skipped"].append({
                        "reason": "已有同类别势力事件",
                        "category": "遗迹与机缘",
                        "region": region,
                    })
                    continue

                event = event_pool.add(
                    group_id=group_id,
                    title=f"{fac_name}与{target_name}联合开发新机缘",
                    category=EventCategory.RUIN_OPPORTUNITY.value,
                    region=region,
                    location=fac_info.get("stronghold", ""),
                    participants=[code, target_code],
                    summary=f"盟友{fac_name}与{target_name}实力均强盛，联合开辟新机遇 [faction_trigger]",
                    progress=0.05,
                    priority=EventPriority.LOW.value,
                    visibility=EventVisibility.PUBLIC.value,
                    player_related=False,
                )

                result["triggered"].append({
                    "event_id": event.event_id,
                    "title": event.title,
                    "category": event.category,
                    "region": event.region,
                    "metadata": {
                        "trigger_source": "faction_trigger",
                        "faction_codes": [code, target_code],
                        "trigger_cycle": cycle,
                    },
                })

    @staticmethod
    def _get_default_stance(fac_info: Dict, target_code: str) -> str:
        """从 factions.json 的 relations 中获取默认 stance。"""
        for rel in fac_info.get("relations", []) or []:
            if isinstance(rel, dict) and rel.get("code") == target_code:
                return rel.get("stance", "中立观望")
        return "中立观望"

    # ──────────────────────────────────────────────
    #  环境状态触发检测（B-15）
    # ──────────────────────────────────────────────

    def _check_environment_trigger(
        self,
        group_id: str,
        world_state: Dict,
        event_pool: EventPool,
        evolution_result: Dict,
        memory: Dict,
        result: Dict,
        cycle: int,
    ) -> None:
        """检测环境状态变化，判断是否需要向 EventPool 注册已有类型事件。

        规则：
          1. 灵气衰潮连续存在 → 可能触发灵脉资源事件
          2. 血月临空 → 可能触发CHAOS异常事件
          3. 空间裂隙 → 可能触发CHAOS异常事件
          4. 灵墟投影 → 可能触发遗迹与机缘事件
          5. 九曜乱象 → 可能触发因果回响事件

        要求：
          - 必须继续执行防重复检查
          - 同类别、同区域已有事件时不重复创建
          - 环境状态只是触发条件
          - 不新增第七种正式事件类型
          - 不直接生成AI剧情
        """
        # 环境触发映射表：环境状态 → (事件类别, 事件标题模板, 事件摘要模板, 事件优先级)
        _ENVIRONMENT_TRIGGER_MAP = {
            "灵气衰潮": {
                "category": EventCategory.LEYLINE_RESOURCE.value,
                "title": "灵气衰潮持续，灵脉资源告急",
                "summary": "灵气衰潮持续不退，区域灵脉资源供给紧张 [environment_trigger]",
                "priority": EventPriority.MEDIUM.value,
            },
            "血月临空": {
                "category": EventCategory.CHAOS_ANOMALY.value,
                "title": "血月降临，混沌异象加剧",
                "summary": "血月临空，天地间混沌之气明显增强 [environment_trigger]",
                "priority": EventPriority.HIGH.value,
            },
            "空间裂隙": {
                "category": EventCategory.CHAOS_ANOMALY.value,
                "title": "空间裂隙出现，混沌力量渗透",
                "summary": "空间裂隙导致混沌力量不断渗透，异常事件概率上升 [environment_trigger]",
                "priority": EventPriority.HIGH.value,
            },
            "灵墟投影": {
                "category": EventCategory.RUIN_OPPORTUNITY.value,
                "title": "灵墟投影显现，遗迹机缘浮现",
                "summary": "灵墟投影导致隐藏遗迹入口活跃，机缘与危险并存 [environment_trigger]",
                "priority": EventPriority.LOW.value,
            },
            "九曜乱象": {
                "category": EventCategory.CAUSAL_ECHO.value,
                "title": "九曜乱象，因果回响增强",
                "summary": "九曜乱象导致因果噪音增强，因果回响概率上升 [environment_trigger]",
                "priority": EventPriority.MEDIUM.value,
            },
        }

        # 遍历所有区域的环境状态
        region_state = world_state.get("REGION", {})
        for region, region_data in region_state.items():
            if not isinstance(region_data, dict):
                continue
            env_dict = region_data.get("environment")
            if not env_dict or not isinstance(env_dict, dict):
                continue

            # 检查灵气天气
            spiritual = env_dict.get("spiritual_weather", "平稳")
            if spiritual in _ENVIRONMENT_TRIGGER_MAP:
                trigger_info = _ENVIRONMENT_TRIGGER_MAP[spiritual]
                self._try_trigger_env_event(
                    group_id, event_pool, result, cycle,
                    region, spiritual, trigger_info,
                )

            # 检查天象
            celestial = env_dict.get("celestial_phenomenon", "无")
            if celestial in _ENVIRONMENT_TRIGGER_MAP:
                trigger_info = _ENVIRONMENT_TRIGGER_MAP[celestial]
                self._try_trigger_env_event(
                    group_id, event_pool, result, cycle,
                    region, celestial, trigger_info,
                )

            # 检查异常环境
            anomaly = env_dict.get("anomaly_environment", "无")
            if anomaly in _ENVIRONMENT_TRIGGER_MAP:
                trigger_info = _ENVIRONMENT_TRIGGER_MAP[anomaly]
                self._try_trigger_env_event(
                    group_id, event_pool, result, cycle,
                    region, anomaly, trigger_info,
                )

    def _try_trigger_env_event(
        self,
        group_id: str,
        event_pool: EventPool,
        result: Dict,
        cycle: int,
        region: str,
        env_name: str,
        trigger_info: Dict,
    ) -> None:
        """尝试触发一个环境相关事件，有防重复检查。"""
        category = trigger_info["category"]

        # 防重复检查：同类别、同区域已有事件时不重复创建
        if self._has_active_event(event_pool, group_id, category=category, region=region):
            result["skipped"].append({
                "reason": "已有同类别同区域活跃事件",
                "category": category,
                "region": region,
            })
            return

        # 触发事件
        event = event_pool.add(
            group_id=group_id,
            title=trigger_info["title"],
            category=category,
            stage="萌芽",
            region=region,
            location="",
            participants=[],
            summary=trigger_info["summary"],
            progress=0.05,
            priority=trigger_info["priority"],
            visibility=EventVisibility.PUBLIC.value,
            player_related=False,
        )

        result["triggered"].append({
            "event_id": event.event_id,
            "title": event.title,
            "category": event.category,
            "region": event.region,
            "metadata": {
                "trigger_source": "environment_trigger",
                "environment_name": env_name,
                "trigger_cycle": cycle,
            },
        })

    # ──────────────────────────────────────────────
    #  辅助：检查是否已有同类活跃事件
    # ──────────────────────────────────────────────

    def _has_active_event(
        self,
        event_pool: EventPool,
        group_id: str,
        category: str,
        region: str = "",
    ) -> bool:
        """检查 EventPool 中是否已有同类别（+可选同区域）的活跃事件。"""
        existing = event_pool.query_by_category(group_id, category)
        if not region:
            return len(existing) > 0
        # 同类别 + 同区域
        return any(e.region == region for e in existing)
