"""
faction_ai_manager.py - 势力行动候选生成器

职责：
  1. 读取既有 FACTION_STATE / 静态 factions / EventPool / world_history
  2. 为每个势力生成低频、可解释的 faction_action 候选
  3. 只返回候选，不直接修改 world_state，不直接写入 EventPool

边界：
  - 不重写 FACTION_STATE
  - 不绕过 EventPool
  - 不直接执行 OutcomeApplier
  - 候选由 WorldTick 统一持久化到 proposal/history
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .world_event_pool import EventCategory, EventPool
except ImportError:
    from world_event_pool import EventCategory, EventPool


class FactionAIManager:
    """根据世界状态生成势力行动候选。"""

    _GOAL_EVENT_CATEGORY_MAP = {
        "expand": EventCategory.FACTION_CONFLICT.value,
        "defend": EventCategory.FACTION_CONFLICT.value,
        "resource_compete": EventCategory.LEYLINE_RESOURCE.value,
        "research": EventCategory.CULTIVATION_BREAKTHROUGH.value,
        "diplomacy": EventCategory.CAUSAL_ECHO.value,
    }

    _GOAL_REASON_TAGS = {
        "expand": ["goal_expand", "resource_pressure"],
        "defend": ["goal_defend", "low_stability"],
        "resource_compete": ["goal_resource_compete", "leyline_signal"],
        "research": ["goal_research", "stable_window"],
        "diplomacy": ["goal_diplomacy", "relationship_driven"],
    }

    def __init__(self, event_pool: EventPool, factions: Optional[Dict[str, Any]] = None):
        self.event_pool = event_pool
        self.factions = factions or {}

    def generate_candidates(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        world_state: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        world_state = world_state or {}
        faction_state = world_state.get("FACTION_STATE", {})
        if not isinstance(faction_state, dict) or not isinstance(self.factions, dict):
            return []

        cycle = campaign.get("cycle", 0)
        tick_count = campaign.get("world_clock", {}).get("tick_count", 0)
        candidates: List[Dict[str, Any]] = []
        # 按 category 分组一次，避免每个势力都对事件池做一次全量线性
        # 扫描（query_by_category 内部会重新 list_all+sort 一遍）。
        events_by_category = self._index_events_by_category(group_id)

        for code, fac_info in self.factions.items():
            runtime = faction_state.get(code)
            if not isinstance(runtime, dict):
                continue

            goal = self._select_goal(code, fac_info, runtime, campaign, events_by_category)
            if not goal:
                continue

            region = fac_info.get("region", "")
            if self._has_duplicate_pending(campaign, code, goal, region):
                continue

            candidate = self._build_candidate(
                group_id=group_id,
                faction_code=code,
                fac_info=fac_info,
                runtime=runtime,
                goal=goal,
                region=region,
                cycle=cycle,
                tick_count=tick_count,
            )
            if candidate is not None:
                candidates.append(candidate)

        return candidates

    def _select_goal(
        self,
        faction_code: str,
        fac_info: Dict[str, Any],
        runtime: Dict[str, Any],
        campaign: Dict[str, Any],
        events_by_category: Dict[str, List[Any]],
    ) -> str:
        active_goal = str(runtime.get("active_goal", ""))
        stability = float(runtime.get("stability", 0.5) or 0.5)
        morale = float(runtime.get("morale", 0.7) or 0.7)
        power = int(runtime.get("power", fac_info.get("power", 50)) or 50)
        region = fac_info.get("region", "")
        relation_signal = self._relation_signal(runtime)

        if self._has_recent_chain_signal(campaign, region):
            return "resource_compete"
        if stability <= 0.35 or "自保" in active_goal or "防" in active_goal:
            return "defend"
        if relation_signal["high_tension"] and power >= 60:
            return "expand"
        if relation_signal["high_trust"] and not self._has_conflict_event(events_by_category, region):
            return "diplomacy"
        if morale >= 0.72 and power >= 70 and ("拓展" in active_goal or "扩张" in active_goal):
            return "expand"
        if "寻找新脉" in active_goal or "研究" in active_goal:
            return "research"
        if self._has_diplomacy_relation(faction_code, fac_info) and not self._has_conflict_event(events_by_category, region):
            return "diplomacy"
        if self._has_leyline_event(events_by_category, region):
            return "resource_compete"
        if power >= 65 and stability >= 0.55:
            return "expand"
        return ""

    def _build_candidate(
        self,
        group_id: str,
        faction_code: str,
        fac_info: Dict[str, Any],
        runtime: Dict[str, Any],
        goal: str,
        region: str,
        cycle: int,
        tick_count: int,
    ) -> Optional[Dict[str, Any]]:
        event_category = self._GOAL_EVENT_CATEGORY_MAP.get(goal)
        if not event_category:
            return None

        title = self._build_title(fac_info, goal, region)
        reason_tags = list(self._GOAL_REASON_TAGS.get(goal, []))
        source_refs = [f"faction:{faction_code}"]
        if region:
            source_refs.append(f"region:{region}")
        if goal == "diplomacy":
            source_refs.append("runtime_relations:high_trust")
        elif goal == "expand":
            source_refs.append("runtime_relations:high_tension")

        return {
            "proposal_id": f"FAP-{group_id}-{cycle:06d}-{tick_count:04d}-{faction_code}",
            "proposal_type": "faction_action",
            "source": "faction_ai",
            "status": "pending",
            "faction_code": faction_code,
            "faction_name": fac_info.get("name", faction_code),
            "goal": goal,
            "action": title,
            "priority": "high" if goal in ("expand", "resource_compete") else "medium",
            "reason_tags": reason_tags,
            "region": region,
            "source_cycle": cycle,
            "source_tick": tick_count,
            "source_refs": source_refs,
            "faction_snapshot": {
                "power": runtime.get("power"),
                "stability": runtime.get("stability"),
                "morale": runtime.get("morale"),
                "active_goal": runtime.get("active_goal", ""),
                "strategic_goal": runtime.get("strategic_goal", ""),
                "internal_state": runtime.get("internal_state", ""),
            },
            "outcome_stub": {
                "event_id": f"FAP-{group_id}-{cycle:06d}-{tick_count:04d}-{faction_code}",
                "outcome_type": "escalated",
                "summary": title,
                "world_delta": {},
                "faction_delta": {},
                "profile_delta": {},
                "spawn_event_hints": [{
                    "category": event_category,
                    "region": region,
                    "reason": f"faction:{faction_code}:{goal}",
                }],
                "applied_changes": [],
            },
        }

    def _build_title(self, fac_info: Dict[str, Any], goal: str, region: str) -> str:
        name = fac_info.get("name", fac_info.get("code", "未知势力"))
        if goal == "expand":
            return f"{name}开始向{region or '周边区域'}扩张势力"
        if goal == "defend":
            return f"{name}开始巩固{region or '本部'}防线"
        if goal == "resource_compete":
            return f"{name}开始争夺{region or '附近'}灵脉资源"
        if goal == "research":
            return f"{name}开始研究{region or '本部'}修炼机缘"
        return f"{name}开始推动与周边势力的外交试探"

    def _has_duplicate_pending(
        self,
        campaign: Dict[str, Any],
        faction_code: str,
        goal: str,
        region: str,
    ) -> bool:
        for proposal in campaign.get("world_action_proposals", []):
            if proposal.get("status") != "pending":
                continue
            if proposal.get("source") != "faction_ai":
                continue
            if proposal.get("faction_code") == faction_code and proposal.get("goal") == goal:
                return True
            if region and proposal.get("region") == region and proposal.get("goal") == goal:
                return True
        return False

    def _has_recent_chain_signal(self, campaign: Dict[str, Any], region: str) -> bool:
        history = campaign.get("world_history", [])
        for entry in reversed(history[-40:]):
            if entry.get("region", "") != region:
                continue
            if entry.get("entry_type") == "chain_candidate_spawned":
                return True
            if entry.get("chain_type") in (
                "leyline_anomaly_to_faction_conflict",
                "faction_conflict_to_resource_contention",
                "resource_contention_to_region_change",
            ):
                return True
        return False

    def _has_diplomacy_relation(self, faction_code: str, fac_info: Dict[str, Any]) -> bool:
        for rel in fac_info.get("relations", []) or []:
            if rel.get("code") == faction_code:
                continue
            if rel.get("stance") in ("盟友", "中立观望", "合作竞争"):
                return True
        return False

    def _relation_signal(self, runtime: Dict[str, Any]) -> Dict[str, bool]:
        runtime_rel = runtime.get("faction_relations_runtime", {})
        if not isinstance(runtime_rel, dict):
            return {"high_tension": False, "high_trust": False}

        high_tension = False
        high_trust = False
        for item in runtime_rel.values():
            if not isinstance(item, dict):
                continue
            tension = float(item.get("tension", 0.5) or 0.5)
            trust = float(item.get("trust", 0.5) or 0.5)
            if tension >= 0.7:
                high_tension = True
            if trust >= 0.7 and tension <= 0.5:
                high_trust = True

        return {
            "high_tension": high_tension,
            "high_trust": high_trust,
        }

    def _index_events_by_category(self, group_id: str) -> Dict[str, List[Any]]:
        """把事件池按 category 分组一次，供同一轮 generate_candidates 内
        所有势力复用，避免每个势力都触发一次 query_by_category（内部
        会重新 list_all+sort 一次，等于全量线性扫描）。"""
        index: Dict[str, List[Any]] = {}
        for event in self.event_pool.list_all(group_id):
            index.setdefault(event.category, []).append(event)
        return index

    def _has_leyline_event(self, events_by_category: Dict[str, List[Any]], region: str) -> bool:
        for event in events_by_category.get(EventCategory.LEYLINE_RESOURCE.value, []):
            if not region or event.region == region:
                return True
        return False

    def _has_conflict_event(self, events_by_category: Dict[str, List[Any]], region: str) -> bool:
        for event in events_by_category.get(EventCategory.FACTION_CONFLICT.value, []):
            if not region or event.region == region:
                return True
        return False
