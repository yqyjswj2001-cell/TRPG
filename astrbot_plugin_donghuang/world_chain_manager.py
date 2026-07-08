"""
world_chain_manager.py - 世界因果链管理器

职责：
  1. 创建因果链候选（chain_candidate）
  2. 延迟消费候选，在后续 tick 转成正式 EventPool 事件
  3. 过期处理
  4. 深度限制，避免无限循环

边界：
  - 不直接修改 WorldState
  - 不绕过 EventPool 创建正式事件
  - 仅使用 campaign["world_history"] 持久化链状态
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .world_event_pool import EventCategory, EventPool, EventStage
except ImportError:
    from world_event_pool import EventCategory, EventPool, EventStage


class WorldChainManager:
    MAX_CHAIN_DEPTH = 3
    CHAIN_TTL_TICKS = 3
    HISTORY_LIMIT = 200

    def __init__(self, event_pool: EventPool, factions: Optional[Dict[str, Any]] = None):
        self.event_pool = event_pool
        self.factions = factions or {}

    def _ensure_world_history(self, campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        return campaign.setdefault("world_history", [])

    def _append_world_history(
        self,
        campaign: Dict[str, Any],
        entry: Dict[str, Any],
    ) -> Dict[str, Any]:
        history = self._ensure_world_history(campaign)
        history.append(entry)
        if len(history) > self.HISTORY_LIMIT:
            del history[:-self.HISTORY_LIMIT]
        return entry

    def _current_cycle(self, campaign: Dict[str, Any]) -> int:
        return campaign.get("cycle", 0)

    def _current_tick(self, campaign: Dict[str, Any]) -> int:
        return campaign.get("world_clock", {}).get("tick_count", 0)

    def _find_matching_leyline_event(self, group_id: str, region: str) -> Optional[Any]:
        for event in self.event_pool.query_by_category(group_id, EventCategory.LEYLINE_RESOURCE.value):
            if not region or event.region == region:
                return event
        return None

    def _find_matching_conflict_event(self, group_id: str, region: str) -> Optional[Any]:
        for event in self.event_pool.query_by_category(group_id, EventCategory.FACTION_CONFLICT.value):
            if not region or event.region == region:
                return event
        return None

    def _find_matching_resource_contention_event(
        self,
        group_id: str,
        region: str,
        event_id: str = "",
    ) -> Optional[Any]:
        if event_id:
            event = self.event_pool.get(group_id, event_id)
            if event is not None and event.category == EventCategory.DAILY.value:
                if not region or event.region == region:
                    return event
        for event in self.event_pool.query_by_category(group_id, EventCategory.DAILY.value):
            if not region or event.region == region:
                return event
        return None

    def _select_chain_participants(self, region: str) -> List[str]:
        if not isinstance(self.factions, dict):
            return []
        sects = [
            code for code, info in self.factions.items()
            if isinstance(info, dict) and info.get("region") == region and info.get("type") == "宗门"
        ]
        return sects[:2]

    def _build_chain_candidate(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        environment_change: Dict[str, Any],
        source_event: Any,
    ) -> Dict[str, Any]:
        region = environment_change.get("region", "") or source_event.region or "附近区域"
        cycle = self._current_cycle(campaign)
        tick_count = self._current_tick(campaign)
        parent_chain_id = environment_change.get("parent_chain_id", "")
        parent_depth = int(environment_change.get("chain_depth", 0) or 0)
        chain_depth = parent_depth + 1 if parent_chain_id else 1
        return {
            "entry_type": "chain_candidate",
            "chain_id": f"CHAIN-{group_id}-{cycle:06d}-{tick_count:04d}-{region}",
            "chain_type": "leyline_anomaly_to_faction_conflict",
            "parent_chain_id": parent_chain_id,
            "chain_depth": chain_depth,
            "cause_category": source_event.category,
            "source_refs": [
                f"event:{source_event.event_id}",
                f"history:environment_changed:{region}:{cycle}:{tick_count}",
            ],
            "trigger_conditions": {
                "requires_environment_change": True,
                "requires_leyline_event": True,
                "region": region,
            },
            "region": region,
            "source_event_id": source_event.event_id,
            "target_event_category": EventCategory.FACTION_CONFLICT.value,
            "target_event_title": f"{region}宗门争夺灵脉",
            "status": "pending",
            "created_cycle": cycle,
            "created_tick": tick_count,
        }

    def create_chain_candidates(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        environment_changes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        history = self._ensure_world_history(campaign)
        existing_pending = {
            (entry.get("chain_type", ""), entry.get("region", ""))
            for entry in history
            if entry.get("entry_type") == "chain_candidate" and entry.get("status") == "pending"
        }
        created: List[Dict[str, Any]] = []

        for change in environment_changes:
            region = change.get("region", "")
            parent_chain_id = change.get("parent_chain_id", "")
            parent_depth = int(change.get("chain_depth", 0) or 0)
            if parent_depth >= self.MAX_CHAIN_DEPTH:
                self._append_world_history(campaign, {
                    "entry_type": "chain_candidate_skipped",
                    "chain_type": "leyline_anomaly_to_faction_conflict",
                    "parent_chain_id": parent_chain_id,
                    "chain_depth": parent_depth,
                    "cause_category": EventCategory.LEYLINE_RESOURCE.value,
                    "source_refs": [f"history:environment_changed:{region}:{self._current_cycle(campaign)}:{self._current_tick(campaign)}"],
                    "trigger_conditions": {"region": region},
                    "region": region,
                    "skip_reason": "max_depth_reached",
                    "cycle": self._current_cycle(campaign),
                    "tick_count": self._current_tick(campaign),
                })
                continue

            if ("leyline_anomaly_to_faction_conflict", region) in existing_pending:
                continue

            source_event = self._find_matching_leyline_event(group_id, region)
            if source_event is None:
                continue

            candidate = self._build_chain_candidate(group_id, campaign, change, source_event)
            self._append_world_history(campaign, candidate)
            created.append(candidate)
            existing_pending.add((candidate["chain_type"], candidate["region"]))

        return created

    def create_followup_chain_candidates(
        self,
        group_id: str,
        campaign: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        history = self._ensure_world_history(campaign)
        created: List[Dict[str, Any]] = []
        existing_keys = {
            (entry.get("chain_type", ""), entry.get("parent_chain_id", ""))
            for entry in history
            if entry.get("entry_type") == "chain_candidate"
        }

        for entry in history:
            if entry.get("entry_type") != "chain_candidate_spawned":
                continue

            parent_chain_id = entry.get("chain_id", "")
            chain_depth = int(entry.get("chain_depth", 1) or 1)
            if chain_depth >= self.MAX_CHAIN_DEPTH:
                continue

            region = entry.get("region", "")
            chain_type = entry.get("chain_type", "")
            candidate: Optional[Dict[str, Any]] = None

            if chain_type == "leyline_anomaly_to_faction_conflict":
                if ("faction_conflict_to_resource_contention", parent_chain_id) in existing_keys:
                    continue
                conflict_event = self._find_matching_conflict_event(group_id, region)
                if conflict_event is None:
                    continue
                candidate = {
                    "entry_type": "chain_candidate",
                    "chain_id": f"CHAIN-{group_id}-{self._current_cycle(campaign):06d}-{self._current_tick(campaign):04d}-{region}-R",
                    "chain_type": "faction_conflict_to_resource_contention",
                    "parent_chain_id": parent_chain_id,
                    "chain_depth": chain_depth + 1,
                    "cause_category": EventCategory.FACTION_CONFLICT.value,
                    "source_refs": [
                        f"event:{conflict_event.event_id}",
                        f"chain:{parent_chain_id}",
                    ],
                    "trigger_conditions": {
                        "requires_conflict_event": True,
                        "region": region,
                    },
                    "region": region,
                    "source_event_id": conflict_event.event_id,
                    "target_event_category": EventCategory.DAILY.value,
                    "target_event_title": f"{region}灵脉资源争夺升级",
                    "status": "pending",
                    "created_cycle": self._current_cycle(campaign),
                    "created_tick": self._current_tick(campaign),
                }
            elif chain_type == "faction_conflict_to_resource_contention":
                if ("resource_contention_to_region_change", parent_chain_id) in existing_keys:
                    continue
                contention_event = self._find_matching_resource_contention_event(
                    group_id,
                    region,
                    event_id=entry.get("event_id", ""),
                )
                if contention_event is None:
                    continue
                candidate = {
                    "entry_type": "chain_candidate",
                    "chain_id": f"CHAIN-{group_id}-{self._current_cycle(campaign):06d}-{self._current_tick(campaign):04d}-{region}-G",
                    "chain_type": "resource_contention_to_region_change",
                    "parent_chain_id": parent_chain_id,
                    "chain_depth": chain_depth + 1,
                    "cause_category": EventCategory.DAILY.value,
                    "source_refs": [
                        f"event:{contention_event.event_id}",
                        f"chain:{parent_chain_id}",
                    ],
                    "trigger_conditions": {
                        "requires_resource_contention_event": True,
                        "region": region,
                    },
                    "region": region,
                    "source_event_id": contention_event.event_id,
                    "target_event_category": EventCategory.DAILY.value,
                    "target_event_title": f"{region}区域格局发生变化",
                    "status": "pending",
                    "created_cycle": self._current_cycle(campaign),
                    "created_tick": self._current_tick(campaign),
                }

            if candidate is None:
                continue

            self._append_world_history(campaign, candidate)
            created.append(candidate)
            existing_keys.add((candidate["chain_type"], candidate["parent_chain_id"]))

        return created

    def _build_spawn_summary(self, entry: Dict[str, Any]) -> str:
        chain_type = entry.get("chain_type", "")
        region = entry.get("region", "附近区域")
        if chain_type == "faction_conflict_to_resource_contention":
            return f"{region}势力冲突持续发酵，各方开始争夺灵脉与资源配给。"
        return f"{region}灵脉异常持续扩散，宗门围绕灵脉归属展开争夺。"

    def consume_pending_chains(
        self,
        group_id: str,
        campaign: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        spawned: List[Dict[str, Any]] = []
        cycle = self._current_cycle(campaign)
        tick_count = self._current_tick(campaign)

        for entry in self._ensure_world_history(campaign):
            if entry.get("entry_type") != "chain_candidate" or entry.get("status") != "pending":
                continue
            if entry.get("created_cycle") == cycle and entry.get("created_tick") == tick_count:
                continue

            region = entry.get("region", "")
            target_category = entry.get("target_event_category", EventCategory.FACTION_CONFLICT.value)
            if any(event.region == region for event in self.event_pool.query_by_category(group_id, target_category)):
                entry["status"] = "skipped"
                entry["skip_reason"] = "duplicate_category_region"
                continue

            participants = self._select_chain_participants(region)
            event = self.event_pool.add(
                group_id=group_id,
                title=entry.get("target_event_title", f"{region}宗门争夺灵脉"),
                category=target_category,
                stage=EventStage.SPROUT.value,
                region=region,
                location="",
                participants=participants,
                summary=self._build_spawn_summary(entry),
                progress=0.05,
                priority="medium",
                visibility="公开",
                player_related=False,
            )
            entry["status"] = "spawned"
            entry["spawned_event_id"] = event.event_id
            spawned_entry = {
                "entry_type": "chain_candidate_spawned",
                "chain_id": entry.get("chain_id", ""),
                "chain_type": entry.get("chain_type", ""),
                "parent_chain_id": entry.get("parent_chain_id", ""),
                "chain_depth": entry.get("chain_depth", 1),
                "cause_category": entry.get("cause_category", EventCategory.LEYLINE_RESOURCE.value),
                "source_refs": list(entry.get("source_refs", [])),
                "trigger_conditions": dict(entry.get("trigger_conditions", {})),
                "event_id": event.event_id,
                "category": event.category,
                "region": event.region,
                "cycle": cycle,
                "tick_count": tick_count,
            }
            self._append_world_history(campaign, spawned_entry)
            spawned.append(spawned_entry)

        return spawned

    def expire_pending_chains(self, campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        expired: List[Dict[str, Any]] = []
        cycle = self._current_cycle(campaign)
        tick_count = self._current_tick(campaign)

        for entry in self._ensure_world_history(campaign):
            if entry.get("entry_type") != "chain_candidate" or entry.get("status") != "pending":
                continue

            created_tick = entry.get("created_tick", 0)
            too_old = tick_count - created_tick >= self.CHAIN_TTL_TICKS
            if not too_old:
                continue

            entry["status"] = "expired"
            expired_entry = {
                "entry_type": "chain_candidate_expired",
                "chain_id": entry.get("chain_id", ""),
                "parent_chain_id": entry.get("parent_chain_id", ""),
                "chain_depth": entry.get("chain_depth", 1),
                "cause_category": entry.get("cause_category", EventCategory.LEYLINE_RESOURCE.value),
                "source_refs": list(entry.get("source_refs", [])),
                "trigger_conditions": dict(entry.get("trigger_conditions", {})),
                "region": entry.get("region", ""),
                "cycle": cycle,
                "tick_count": tick_count,
            }
            self._append_world_history(campaign, expired_entry)
            expired.append(expired_entry)

        return expired
