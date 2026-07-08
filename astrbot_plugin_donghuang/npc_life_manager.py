"""
npc_life_manager.py - Phase E NPC life-cycle candidate manager
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .npc_behavior import apply_identity_modifier, calculate_behavior
    from .npc_relationship import (
        REL_FRIENDLY,
        REL_HOSTILE,
        REL_RESPECTFUL,
        REL_SUSPICIOUS,
        REL_UNKNOWN,
        calculate_relationship,
    )
    from .npc_memory import EMOTION_NEUTRAL, MEMORY_TYPE_MAJOR_EVENT, SOURCE_FACTION_EVENT
    from .npc_memory_manager import NPCMemoryManager
    from .npc_life_rules import (
        is_major_npc_event,
        validate_breakthrough,
        validate_death,
        validate_disappear,
        validate_npc_join_faction,
        validate_npc_leave_faction,
        validate_relocate,
    )
    from .world_event_pool import EventCategory, EventPool
except ImportError:
    from npc_behavior import apply_identity_modifier, calculate_behavior
    from npc_relationship import (
        REL_FRIENDLY,
        REL_HOSTILE,
        REL_RESPECTFUL,
        REL_SUSPICIOUS,
        REL_UNKNOWN,
        calculate_relationship,
    )
    from npc_memory import EMOTION_NEUTRAL, MEMORY_TYPE_MAJOR_EVENT, SOURCE_FACTION_EVENT
    from npc_memory_manager import NPCMemoryManager
    from npc_life_rules import (
        is_major_npc_event,
        validate_breakthrough,
        validate_death,
        validate_disappear,
        validate_npc_join_faction,
        validate_npc_leave_faction,
        validate_relocate,
    )
    from world_event_pool import EventCategory, EventPool


class NPCLifeManager:
    """Generate low-frequency NPC life-cycle proposals without mutating world state."""

    _GOAL_EVENT_CATEGORY_MAP = {
        "survive": EventCategory.CHAOS_ANOMALY.value,
        "cultivate": EventCategory.CULTIVATION_BREAKTHROUGH.value,
        "trade": EventCategory.DAILY.value,
        "explore": EventCategory.RUIN_OPPORTUNITY.value,
        "revenge": EventCategory.FACTION_CONFLICT.value,
    }
    _BOLD_PERSONALITIES = ("bold", "adventurous", "外向", "果决", "激进")
    _FRAGILE_ROLES = ("执事", "弟子", "散修", "deacon", "disciple", "rogue cultivator", "鎵т簨", "寮熷瓙", "鏁ｄ慨")
    _BOLD_RISKS = ("bold",)

    def __init__(self, event_pool: EventPool):
        self.event_pool = event_pool
        self.memory_manager = NPCMemoryManager()

    def ensure_runtime_fields(self, campaign: Dict[str, Any]) -> None:
        campaign.setdefault("npc_life_state", {})
        campaign.setdefault("npc_life_log", [])

    def generate_candidates(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        world_state: Optional[Dict[str, Any]] = None,
        npc_registry: Any = None,
    ) -> List[Dict[str, Any]]:
        self.ensure_runtime_fields(campaign)
        _ = world_state or {}
        if npc_registry is None or not hasattr(npc_registry, "get_all_npcs"):
            return []

        cycle = campaign.get("cycle", 0)
        tick_count = campaign.get("world_clock", {}).get("tick_count", 0)
        candidates: List[Dict[str, Any]] = []
        # 按 category 分组一次，避免每个 NPC 都对事件池做一次全量线性
        # 扫描（query_by_category 内部会重新 list_all+sort 一遍）。
        events_by_category = self._index_events_by_category(group_id)

        for npc in npc_registry.get_all_npcs() or []:
            if not isinstance(npc, dict):
                continue
            npc_id = npc.get("name", "") or npc.get("id", "")
            if not npc_id:
                continue

            state = self._ensure_npc_state(campaign, npc_id, npc)
            candidate = self._build_candidate_for_npc(
                group_id=group_id,
                campaign=campaign,
                npc=npc,
                state=state,
                cycle=cycle,
                tick_count=tick_count,
                events_by_category=events_by_category,
            )
            if candidate is None:
                continue
            if self._has_duplicate_pending(campaign, candidate):
                continue
            candidates.append(candidate)

        return candidates

    def record_candidate(
        self,
        campaign: Dict[str, Any],
        group_id: str,
        proposal: Dict[str, Any],
    ) -> Dict[str, Any]:
        self.ensure_runtime_fields(campaign)
        npc_id = proposal.get("npc_id", "")
        state = campaign.setdefault("npc_life_state", {}).setdefault(npc_id, {})
        state.update({
            "location": proposal.get("region", state.get("location", "")),
            "identity": proposal.get("identity", state.get("identity", "")),
            "current_goal": proposal.get("goal", state.get("current_goal", "")),
            "life_status": proposal.get("action", state.get("life_status", "active")),
            "last_cycle": proposal.get("source_cycle", campaign.get("cycle", 0)),
            "last_event_id": proposal.get("proposal_id", ""),
            "last_cause_ref": proposal.get("source_refs", [""])[0] if proposal.get("source_refs") else "",
        })
        extra_state = proposal.get("extra_state") or {}
        if extra_state:
            state.update(extra_state)

        log_entry = {
            "type": "npc_life",
            "proposal_id": proposal.get("proposal_id", ""),
            "npc_id": npc_id,
            "goal": proposal.get("goal", ""),
            "action": proposal.get("action", ""),
            "region": proposal.get("region", ""),
            "cycle": proposal.get("source_cycle", campaign.get("cycle", 0)),
            "tick_count": proposal.get("source_tick", campaign.get("world_clock", {}).get("tick_count", 0)),
            "cause_category": proposal.get("cause_category", ""),
            "source_refs": list(proposal.get("source_refs", [])),
            "status": "pending",
        }
        campaign.setdefault("npc_life_log", []).append(log_entry)

        summary = proposal.get("memory_summary", "")
        memory = None
        if npc_id and summary:
            memory = self.memory_manager.add_memory(
                campaign=campaign,
                group_id=group_id,
                npc_id=npc_id,
                player_id="",
                memory_type=MEMORY_TYPE_MAJOR_EVENT,
                summary=summary,
                importance=75,
                emotion=EMOTION_NEUTRAL,
                trust_change=0,
                source=SOURCE_FACTION_EVENT,
                cycle=proposal.get("source_cycle", campaign.get("cycle", 0)),
            ).to_dict()

        action = proposal.get("action", "")
        source_cycle = proposal.get("source_cycle", campaign.get("cycle", 0))
        source_refs = list(proposal.get("source_refs", []))
        region = proposal.get("region", "")

        event_log_entry = None
        if is_major_npc_event(proposal.get("registry_id", ""), action):
            event_log_entry = {
                # ---- EVENT_LOG 标准字段（对齐 world_event_pool.preview_archive）----
                "event_id": proposal.get("proposal_id", ""),
                "cycle": f"Cycle-{source_cycle:06d}" if isinstance(source_cycle, int) else str(source_cycle),
                "category": "npc_life",
                "participants": [npc_id] if npc_id else [],
                "trigger_source": "npc_life_manager",
                "result": summary,
                "causal_linkage": source_refs,
                "state_before": {},
                "state_after": {},
                "info_tier": "PUBLIC",
                "irreversible": action == "death",
                "residue": f"[NPC生命周期] {npc_id}：{summary}",
                "snapshot_ref": None,
                # ---- 扩展字段 ----
                "npc_id": npc_id,
                "action": action,
                "region": region,
            }

        return {
            "npc_life_log_entry": log_entry,
            "memory": memory,
            "state": dict(state),
            "event_log_entry": event_log_entry,
            "history_entry": {
                "entry_type": "npc_life_changed",
                "npc_id": npc_id,
                "goal": proposal.get("goal", ""),
                "action": action,
                "region": region,
                "identity": proposal.get("identity", ""),
                "cause_category": proposal.get("cause_category", ""),
                "source_refs": source_refs,
                "summary": summary,
                "cycle": source_cycle,
                "tick_count": proposal.get("source_tick", campaign.get("world_clock", {}).get("tick_count", 0)),
            },
        }

    def _ensure_npc_state(
        self,
        campaign: Dict[str, Any],
        npc_id: str,
        npc: Dict[str, Any],
    ) -> Dict[str, Any]:
        state = campaign.setdefault("npc_life_state", {}).setdefault(npc_id, {})
        state.setdefault("location", npc.get("region", ""))
        state.setdefault("identity", npc.get("role", ""))
        state.setdefault("current_goal", "")
        state.setdefault("life_status", "active")
        state.setdefault("last_cycle", 0)
        state.setdefault("last_event_id", "")
        state.setdefault("last_cause_ref", "")
        # 势力隶属：静态数据里已有 faction_code 的（多为重要NPC）视为初始已隶属，
        # 没有的（多为散修/普通NPC）初始为空，之后可能通过 npc_join_faction/
        # npc_leave_faction 变化，只存在 npc_life_state 里，不改动 NPCRegistry 静态数据。
        state.setdefault("current_faction", npc.get("faction_code", ""))
        return state

    def _get_npc_memories(
        self,
        campaign: Dict[str, Any],
        npc_id: str,
    ) -> List[Dict[str, Any]]:
        npc_memory = campaign.get("npc_memory", {})
        memories = npc_memory.get(npc_id, [])
        return [item for item in memories if isinstance(item, dict)]

    def _build_social_profile(
        self,
        campaign: Dict[str, Any],
        npc_id: str,
        npc: Dict[str, Any],
    ) -> Dict[str, Any]:
        memories = self._get_npc_memories(campaign, npc_id)
        relationship = calculate_relationship(memories) if memories else REL_UNKNOWN
        behavior = calculate_behavior(memories) if memories else calculate_behavior([])
        behavior = apply_identity_modifier(behavior, npc)
        return {
            "memories": memories,
            "relationship": relationship,
            "behavior": behavior,
        }

    def _build_candidate_for_npc(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        npc: Dict[str, Any],
        state: Dict[str, Any],
        cycle: int,
        tick_count: int,
        events_by_category: Optional[Dict[str, List[Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        npc_id = npc.get("name", "") or npc.get("id", "")
        registry_id = npc.get("npc_id", "")
        region = npc.get("region", "") or state.get("location", "")
        role = npc.get("role", "")
        personality = str(npc.get("personality", ""))
        social = self._build_social_profile(campaign, npc_id, npc)
        relationship = social["relationship"]
        behavior = social["behavior"]
        risk_attitude = getattr(behavior, "risk_attitude", "neutral")
        help_probability = float(getattr(behavior, "help_probability", 0.0) or 0.0)
        price_bias = float(getattr(behavior, "price_bias", 0.0) or 0.0)

        if events_by_category is None:
            events_by_category = self._index_events_by_category(group_id)

        conflict_event = self._find_event(events_by_category, EventCategory.FACTION_CONFLICT.value, region)
        leyline_event = self._find_event(events_by_category, EventCategory.LEYLINE_RESOURCE.value, region)
        daily_event = self._find_event(events_by_category, EventCategory.DAILY.value, region)
        chaos_event = self._find_event(events_by_category, EventCategory.CHAOS_ANOMALY.value, region)
        cross_region_ruin = self._find_cross_region_event(
            events_by_category=events_by_category,
            category=EventCategory.RUIN_OPPORTUNITY.value,
            current_region=region,
        )
        diplomacy_event = self._find_event(events_by_category, EventCategory.CAUSAL_ECHO.value, region)
        cause_chain = self._find_recent_chain(campaign, region)
        current_faction = state.get("current_faction", "") or npc.get("faction_code", "")

        join_faction_ok, _join_reason = validate_npc_join_faction(
            relationship=relationship,
            has_diplomacy_event=diplomacy_event is not None,
            already_affiliated=bool(current_faction),
        )
        if join_faction_ok:
            target_faction = (diplomacy_event.participants[0] if diplomacy_event.participants else "")
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=region,
                identity=role,
                goal="diplomacy",
                action="npc_join_faction",
                cause_category=EventCategory.CAUSAL_ECHO.value,
                source_refs=[f"event:{diplomacy_event.event_id}"],
                trigger_conditions={
                    "region": region,
                    "relationship": relationship,
                    "target_faction": target_faction,
                },
                summary=f"{npc_id}经{region or '附近'}因果牵线，准备投效{target_faction or '当地势力'}。",
                extra_state={"current_faction": target_faction},
            )

        disappear_ok, _disappear_reason = validate_disappear(
            has_chaos_event=chaos_event is not None,
            has_cause_chain=self._has_cause_chain(cause_chain),
        )
        if disappear_ok:
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=region,
                identity=role,
                goal="survive",
                action="disappear",
                cause_category=EventCategory.CHAOS_ANOMALY.value,
                source_refs=[f"event:{chaos_event.event_id}", f"chain:{cause_chain.get('chain_id', '')}"],
                trigger_conditions={
                    "region": region,
                    "event_category": EventCategory.CHAOS_ANOMALY.value,
                    "relationship": relationship,
                    "risk_attitude": risk_attitude,
                },
                summary=f"{npc_id}在{region or '附近区域'}异常中失去踪迹的风险开始浮现。",
            )

        death_ok, _death_reason = validate_death(
            has_conflict_event=conflict_event is not None,
            has_cause_chain=self._has_cause_chain(cause_chain),
            role=role,
            relationship=relationship,
        )
        if death_ok:
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=region,
                identity=role,
                goal="survive",
                action="death",
                cause_category=EventCategory.FACTION_CONFLICT.value,
                source_refs=[f"event:{conflict_event.event_id}", f"chain:{cause_chain.get('chain_id', '')}"],
                trigger_conditions={
                    "region": region,
                    "event_category": EventCategory.FACTION_CONFLICT.value,
                    "relationship": relationship,
                },
                summary=f"{npc_id}在{region or '附近区域'}冲突中陨落的风险开始浮现。",
            )

        leave_faction_ok, _leave_reason = validate_npc_leave_faction(
            relationship=relationship,
            has_conflict_event=conflict_event is not None,
            has_cause_chain=self._has_cause_chain(cause_chain),
            currently_affiliated=bool(current_faction),
        )
        if leave_faction_ok:
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=region,
                identity=role,
                goal="survive",
                action="npc_leave_faction",
                cause_category=EventCategory.FACTION_CONFLICT.value,
                source_refs=[f"event:{conflict_event.event_id}", f"chain:{cause_chain.get('chain_id', '')}"],
                trigger_conditions={
                    "region": region,
                    "relationship": relationship,
                    "former_faction": current_faction,
                },
                summary=f"{npc_id}因{region or '附近'}冲突与{current_faction or '原势力'}生隙，准备脱离。",
                extra_state={"current_faction": ""},
            )

        breakthrough_ok, _breakthrough_reason = validate_breakthrough(
            life_status=state.get("life_status", ""),
            has_leyline_event=leyline_event is not None,
            help_probability=help_probability,
        )
        if breakthrough_ok:
            refs = [f"event:{leyline_event.event_id}"]
            if state.get("last_cause_ref"):
                refs.append(state["last_cause_ref"])
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=region,
                identity=role,
                goal="cultivate",
                action="breakthrough",
                cause_category=EventCategory.LEYLINE_RESOURCE.value,
                source_refs=refs,
                trigger_conditions={
                    "region": region,
                    "previous_status": "seclusion",
                    "relationship": relationship,
                    "help_probability": round(help_probability, 2),
                },
                summary=f"{npc_id}闭关已久，借{region or '附近'}灵脉震荡尝试突破。",
            )

        if (
            leyline_event is not None
            and relationship in (REL_FRIENDLY, REL_RESPECTFUL, REL_UNKNOWN)
        ):
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=region,
                identity=role,
                goal="cultivate",
                action="seclusion",
                cause_category=EventCategory.LEYLINE_RESOURCE.value,
                source_refs=[f"event:{leyline_event.event_id}"],
                trigger_conditions={
                    "region": region,
                    "event_category": EventCategory.LEYLINE_RESOURCE.value,
                    "relationship": relationship,
                },
                summary=f"{npc_id}因{region or '附近'}灵脉异动而准备闭关。",
            )

        if (
            conflict_event is not None
            and (
                relationship in (REL_HOSTILE, REL_SUSPICIOUS)
                or risk_attitude in self._BOLD_RISKS
                or self._is_bold_personality(personality)
            )
        ):
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=region,
                identity=role,
                goal="revenge",
                action="join_event",
                cause_category=EventCategory.FACTION_CONFLICT.value,
                source_refs=[f"event:{conflict_event.event_id}"],
                trigger_conditions={
                    "region": region,
                    "event_category": EventCategory.FACTION_CONFLICT.value,
                    "relationship": relationship,
                    "risk_attitude": risk_attitude,
                },
                summary=f"{npc_id}被{region or '附近'}冲突卷入，准备主动投身事局。",
            )

        relocate_ok, _relocate_reason = validate_relocate(
            has_cross_region_event=cross_region_ruin is not None,
            relationship=relationship,
        )
        if relocate_ok:
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=cross_region_ruin.region,
                identity=role,
                goal="explore",
                action="relocate",
                cause_category=EventCategory.RUIN_OPPORTUNITY.value,
                source_refs=[f"event:{cross_region_ruin.event_id}", f"origin_region:{region}"],
                trigger_conditions={
                    "origin_region": region,
                    "target_region": cross_region_ruin.region,
                    "risk_attitude": risk_attitude,
                },
                summary=f"{npc_id}听闻{cross_region_ruin.region or '外地'}机缘，准备迁往新区域探索。",
            )

        if daily_event is not None and price_bias >= 0.0:
            return self._build_proposal(
                group_id=group_id,
                cycle=cycle,
                tick_count=tick_count,
                npc_id=npc_id,
                registry_id=registry_id,
                region=region,
                identity=role,
                goal="trade",
                action="trade",
                cause_category=EventCategory.DAILY.value,
                source_refs=[f"event:{daily_event.event_id}"],
                trigger_conditions={
                    "region": region,
                    "event_category": EventCategory.DAILY.value,
                    "price_bias": round(price_bias, 2),
                },
                summary=f"{npc_id}准备借{region or '附近'}市面变化扩大交易。",
            )

        return None

    def _build_proposal(
        self,
        group_id: str,
        cycle: int,
        tick_count: int,
        npc_id: str,
        region: str,
        identity: str,
        goal: str,
        action: str,
        cause_category: str,
        source_refs: List[str],
        trigger_conditions: Dict[str, Any],
        summary: str,
        registry_id: str = "",
        extra_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        proposal_id = f"NLP-{group_id}-{cycle:06d}-{tick_count:04d}-{npc_id}"
        event_category = self._GOAL_EVENT_CATEGORY_MAP.get(goal, EventCategory.DAILY.value)
        return {
            "proposal_id": proposal_id,
            "proposal_type": "npc_life_action",
            "source": "npc_life",
            "status": "pending",
            "npc_id": npc_id,
            "registry_id": registry_id,
            "extra_state": dict(extra_state or {}),
            "goal": goal,
            "action": action,
            "priority": "high" if action in ("death", "disappear") else "medium",
            "region": region,
            "identity": identity,
            "source_cycle": cycle,
            "source_tick": tick_count,
            "source_refs": [item for item in source_refs if item],
            "cause_category": cause_category,
            "trigger_conditions": dict(trigger_conditions),
            "memory_summary": summary,
            "outcome_stub": {
                "event_id": proposal_id,
                "outcome_type": "escalated",
                "summary": summary,
                "world_delta": {},
                "faction_delta": {},
                "profile_delta": {},
                "spawn_event_hints": [{
                    "category": event_category,
                    "region": region,
                    "reason": f"npc_life:{npc_id}:{goal}:{action}",
                }],
                "applied_changes": [],
            },
        }

    def _index_events_by_category(self, group_id: str) -> Dict[str, List[Any]]:
        """把事件池按 category 分组一次，供同一轮 generate_candidates 内
        所有 NPC 复用，避免每个 NPC 都触发一次 query_by_category（内部
        会重新 list_all+sort 一次，等于全量线性扫描）。"""
        index: Dict[str, List[Any]] = {}
        for event in self.event_pool.list_all(group_id):
            index.setdefault(event.category, []).append(event)
        return index

    def _find_event(self, events_by_category: Dict[str, List[Any]], category: str, region: str) -> Optional[Any]:
        for event in events_by_category.get(category, []):
            if not region or event.region == region:
                return event
        return None

    def _find_cross_region_event(
        self, events_by_category: Dict[str, List[Any]], category: str, current_region: str
    ) -> Optional[Any]:
        for event in events_by_category.get(category, []):
            if event.region and event.region != current_region:
                return event
        return None

    def _find_recent_chain(self, campaign: Dict[str, Any], region: str) -> Optional[Dict[str, Any]]:
        for entry in reversed(campaign.get("world_history", [])[-40:]):
            if entry.get("entry_type") != "chain_candidate_spawned":
                continue
            if region and entry.get("region", "") != region:
                continue
            return entry
        return None

    def _has_cause_chain(self, cause_chain: Optional[Dict[str, Any]]) -> bool:
        return isinstance(cause_chain, dict) and bool(cause_chain.get("chain_id"))

    def _is_bold_personality(self, personality: str) -> bool:
        return any(flag in personality for flag in self._BOLD_PERSONALITIES)

    def _has_duplicate_pending(self, campaign: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
        for proposal in campaign.get("world_action_proposals", []):
            if proposal.get("status") != "pending":
                continue
            if proposal.get("source") != "npc_life":
                continue
            if proposal.get("npc_id") != candidate.get("npc_id"):
                continue
            if proposal.get("action") == candidate.get("action"):
                return True
        return False
