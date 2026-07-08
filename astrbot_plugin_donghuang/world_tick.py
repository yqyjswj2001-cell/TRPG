"""
world_tick.py — 世界时间推进（World Tick）

手动执行一次世界时间推进，编排以下步骤：
  1. 推进 campaign cycle
  2. 推进活跃事件 progress（+0.01~0.03）
  3. 处理结束事件归档（复用 EventPool 两阶段归档）
  4. 世界状态自然演化（天气、灵气流向、资源微调）
  5. 世界变化事件触发（灵脉异常/CHAOS异常/资源异常 → EventPool）

不负责：
  - 自动定时执行
  - NPC 行为模拟
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

try:
    from .world_event_pool import EventPool, EventStage, EventCategory
    from .world_evolution import WorldEvolutionManager
    from .world_event_trigger import WorldEventTrigger
    from .world_chain_manager import WorldChainManager
    from .faction_ai_manager import FactionAIManager
    from .npc_life_manager import NPCLifeManager
    from .event_outcome import make_escalated_outcome
    from .event_outcome_resolver import EventOutcomeResolver
    from .outcome_applier import OutcomeApplier
    from .npc_action_scheduler import NPCActionScheduler
except ImportError:
    from world_event_pool import EventPool, EventStage, EventCategory
    from world_evolution import WorldEvolutionManager
    from world_event_trigger import WorldEventTrigger
    from world_chain_manager import WorldChainManager
    from faction_ai_manager import FactionAIManager
    from npc_life_manager import NPCLifeManager
    from event_outcome import make_escalated_outcome
    from event_outcome_resolver import EventOutcomeResolver
    from outcome_applier import OutcomeApplier
    from npc_action_scheduler import NPCActionScheduler

logger = logging.getLogger(__name__)


class WorldTickManager:
    """管理世界时间推进。

    每个 tick 执行：
      1. campaign cycle += 1
      2. 所有活跃事件 progress += 0.01~0.03
      3. 根据 progress 检查阶段推进（不允许跳阶段）
      4. 已结束事件走两阶段归档
      5. 世界状态自然演化（天气、灵气流向、资源微调）
    """

    _TIME_PHASES = ["子夜", "清晨", "白昼", "黄昏"]
    _SEASONS = ["春", "夏", "秋", "冬"]
    _DAYS_PER_SEASON = 30

    _GOAL_EVENT_CATEGORY_MAP = {
        "survive": EventCategory.CHAOS_ANOMALY.value,
        "cultivate": EventCategory.CULTIVATION_BREAKTHROUGH.value,
        "trade": EventCategory.DAILY.value,
        "explore": EventCategory.RUIN_OPPORTUNITY.value,
        "revenge": EventCategory.FACTION_CONFLICT.value,
        "socialize": EventCategory.CAUSAL_ECHO.value,
    }

    def __init__(self, event_pool: EventPool, factions: Optional[Dict[str, Any]] = None):
        self.event_pool = event_pool
        self.evolution_manager = WorldEvolutionManager()
        self.trigger_manager = WorldEventTrigger()
        self.chain_manager = WorldChainManager(event_pool, factions=factions)
        self.faction_ai_manager = FactionAIManager(event_pool, factions=factions)
        self.npc_life_manager = NPCLifeManager(event_pool)
        self.outcome_resolver = EventOutcomeResolver()
        self.outcome_applier = OutcomeApplier()
        self.npc_action_scheduler = NPCActionScheduler()
        self.factions = factions or {}

    def _format_calendar_label(self, clock: Dict[str, Any]) -> str:
        return f"东荒历1年{clock['season']}{clock['world_day']}日{clock['time_phase']}"

    def _ensure_world_clock(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        clock = campaign.setdefault("world_clock", {})
        clock.setdefault("tick_count", 0)
        clock.setdefault("world_day", 1)
        clock.setdefault("time_phase", "子夜")
        clock.setdefault("season", "春")
        clock["calendar_label"] = self._format_calendar_label(clock)
        return clock

    def _advance_world_clock(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        clock = self._ensure_world_clock(campaign)
        before = dict(clock)

        phase_index = self._TIME_PHASES.index(clock["time_phase"])
        next_index = (phase_index + 1) % len(self._TIME_PHASES)
        clock["time_phase"] = self._TIME_PHASES[next_index]
        clock["tick_count"] += 1

        if clock["time_phase"] == "子夜" and clock["tick_count"] > 1:
            clock["world_day"] += 1
            season_index = min((clock["world_day"] - 1) // self._DAYS_PER_SEASON, len(self._SEASONS) - 1)
            clock["season"] = self._SEASONS[season_index]

        clock["calendar_label"] = self._format_calendar_label(clock)
        return {
            "before": before,
            "after": dict(clock),
            "changed": before != clock,
        }

    def _ensure_npc_world_queue(self, campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        return campaign.setdefault("npc_world_queue", [])

    def _ensure_world_action_proposals(self, campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        return campaign.setdefault("world_action_proposals", [])

    def _ensure_world_history(self, campaign: Dict[str, Any]) -> List[Dict[str, Any]]:
        return campaign.setdefault("world_history", [])

    def _append_world_history(
        self,
        campaign: Dict[str, Any],
        entry: Dict[str, Any],
    ) -> Dict[str, Any]:
        history = self._ensure_world_history(campaign)
        history.append(entry)
        if len(history) > 200:
            del history[:-200]
        return entry

    def _build_npc_action_proposal(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        item: Dict[str, Any],
    ) -> Dict[str, Any]:
        event_id = (
            f"NPCP-{group_id}-{campaign.get('cycle', 0):06d}-"
            f"{campaign.get('world_clock', {}).get('tick_count', 0):04d}-"
            f"{item.get('npc_id', 'UNKNOWN')}"
        )
        target_region = item.get("target_region") or item.get("region") or "附近区域"
        outcome = make_escalated_outcome(
            event_id=event_id,
            summary=f"{item.get('npc_id', '某NPC')} 准备采取 {item.get('action', 'unknown')}，等待世界系统转为事件或结果。",
            hints=[{
                "category": "日常",
                "region": target_region,
                "reason": f"npc:{item.get('npc_id', '')}:{item.get('goal', '')}:{item.get('action', '')}",
            }],
        )
        return {
            "proposal_id": event_id,
            "proposal_type": "npc_outcome",
            "source": "npc_proactive",
            "status": "pending",
            "npc_id": item.get("npc_id", ""),
            "player_id": item.get("player_id", ""),
            "goal": item.get("goal", ""),
            "action": item.get("action", ""),
            "priority": item.get("priority", "low"),
            "reason_tags": list(item.get("reason_tags", [])),
            "relationship": item.get("relationship", ""),
            "candidates": list(item.get("candidates", [])),
            "source_cycle": campaign.get("cycle", 0),
            "source_tick": campaign.get("world_clock", {}).get("tick_count", 0),
            "outcome_stub": outcome.to_dict(),
        }

    def _spawn_event_from_proposal(
        self,
        group_id: str,
        proposal: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        outcome_stub = proposal.get("outcome_stub", {})
        hints = outcome_stub.get("spawn_event_hints", [])
        if not hints:
            proposal["status"] = "rejected"
            proposal["reject_reason"] = "missing_spawn_event_hints"
            return None

        hint = hints[0]
        category = hint.get("category", "日常")
        region = hint.get("region", "")
        category = self._GOAL_EVENT_CATEGORY_MAP.get(proposal.get("goal", ""), category)
        existing = self.event_pool.query_by_category(group_id, category)
        if region and any(e.region == region for e in existing):
            proposal["status"] = "skipped"
            proposal["skip_reason"] = "duplicate_category_region"
            return None
        if not region and existing:
            proposal["status"] = "skipped"
            proposal["skip_reason"] = "duplicate_category"
            return None

        npc_id = proposal.get("npc_id", "")
        player_id = proposal.get("player_id", "")
        participants = [p for p in [npc_id, player_id] if p]
        event = self.event_pool.add(
            group_id=group_id,
            title=f"{npc_id or '某NPC'}引发的{category}",
            category=category,
            stage=EventStage.SPROUT.value,
            region=region,
            location="",
            participants=participants,
            summary=outcome_stub.get("summary", ""),
            progress=0.05,
            priority=proposal.get("priority", "中"),
            visibility="公开",
            player_related=bool(player_id),
        )
        proposal["status"] = "spawned"
        proposal["spawned_event_id"] = event.event_id
        proposal["spawned_cycle"] = proposal.get("source_cycle", 0)
        return {
            "proposal_id": proposal.get("proposal_id", ""),
            "event_id": event.event_id,
            "title": event.title,
            "category": event.category,
            "region": event.region,
        }

    def _consume_world_action_proposals(
        self,
        group_id: str,
        campaign: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        spawned: List[Dict[str, Any]] = []
        for proposal in self._ensure_world_action_proposals(campaign):
            if proposal.get("status") != "pending":
                continue
            spawned_event = self._spawn_event_from_proposal(group_id, proposal)
            if spawned_event is not None:
                self._append_world_history(campaign, {
                    "entry_type": "proposal_spawned",
                    "proposal_id": proposal.get("proposal_id", ""),
                    "event_id": spawned_event["event_id"],
                    "category": spawned_event["category"],
                    "region": spawned_event["region"],
                    "cycle": campaign.get("cycle", 0),
                    "tick_count": campaign.get("world_clock", {}).get("tick_count", 0),
                })
                spawned.append(spawned_event)
        return spawned

    def _record_tick_ledger(self, campaign: Dict[str, Any], result: Dict[str, Any]) -> None:
        ledger = campaign.setdefault("tick_ledger", {})
        ledger["last_tick_summary"] = {
            "cycle_before": result["cycle_before"],
            "cycle_after": result["cycle_after"],
            "world_clock_changed": result["world_clock"]["changed"],
            "events_progressed": len(result["events_progressed"]),
            "stage_changed": len(result["stage_changed"]),
            "archived": len(result["archived"]),
            "npc_candidates": len(result.get("npc_proactive", [])),
            "faction_candidates": len(result.get("faction_actions", [])),
            "npc_life_candidates": len(result.get("npc_life_actions", [])),
            "proposal_generated": len(result.get("world_action_proposals", [])),
            "proposal_spawned": len(result.get("proposal_events_spawned", [])),
            "chain_candidate_created": len(result.get("chain_candidates_created", [])),
            "chain_candidate_expired": len(result.get("chain_candidates_expired", [])),
            "chain_event_spawned": len(result.get("chain_events_spawned", [])),
            "history_recorded": len(result.get("world_history_recorded", [])),
            "faction_changed": len(result["evolution"].get("faction_changed", [])),
            "environment_changed": len(result["evolution"].get("environment_changed", [])),
            "triggered": len(result.get("triggered", [])),
        }

    def _record_faction_changes(
        self,
        campaign: Dict[str, Any],
        changes: List[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> None:
        tick_count = campaign.get("world_clock", {}).get("tick_count", 0)
        cycle = campaign.get("cycle", 0)
        for change in changes:
            code = change.get("code", "")
            faction_info = self.factions.get(code, {}) if isinstance(self.factions, dict) else {}
            result["world_history_recorded"].append(self._append_world_history(campaign, {
                "entry_type": "faction_changed",
                "code": code,
                "faction_name": faction_info.get("name", code or "未知势力"),
                "field": change.get("field", ""),
                "from": change.get("from"),
                "to": change.get("to"),
                "region": faction_info.get("region", ""),
                "cycle": cycle,
                "tick_count": tick_count,
            }))

    def _record_environment_changes(
        self,
        campaign: Dict[str, Any],
        changes: List[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> None:
        tick_count = campaign.get("world_clock", {}).get("tick_count", 0)
        cycle = campaign.get("cycle", 0)
        for change in changes:
            result["world_history_recorded"].append(self._append_world_history(campaign, {
                "entry_type": "environment_changed",
                "region": change.get("region", ""),
                "physical_weather": change.get("physical_weather", ""),
                "spiritual_weather": change.get("spiritual_weather", ""),
                "celestial_phenomenon": change.get("celestial_phenomenon", ""),
                "anomaly_environment": change.get("anomaly_environment", ""),
                "effects": list(change.get("effects", [])),
                "cycle": cycle,
                "tick_count": tick_count,
            }))

    def _find_matching_leyline_event(self, group_id: str, region: str) -> Optional[Any]:
        for event in self.event_pool.query_by_category(group_id, EventCategory.LEYLINE_RESOURCE.value):
            if not region or event.region == region:
                return event
        return None

    def _build_chain_candidate(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        environment_change: Dict[str, Any],
        source_event: Any,
    ) -> Dict[str, Any]:
        region = environment_change.get("region", "") or source_event.region or "附近区域"
        tick_count = campaign.get("world_clock", {}).get("tick_count", 0)
        cycle = campaign.get("cycle", 0)
        return {
            "entry_type": "chain_candidate",
            "chain_id": f"CHAIN-{group_id}-{cycle:06d}-{tick_count:04d}-{region}",
            "chain_type": "leyline_anomaly_to_faction_conflict",
            "region": region,
            "source_event_id": source_event.event_id,
            "source_history_refs": [f"environment_changed:{region}:{cycle}:{tick_count}"],
            "target_event_category": EventCategory.FACTION_CONFLICT.value,
            "target_event_title": f"{region}宗门争夺灵脉",
            "status": "pending",
            "created_cycle": cycle,
            "created_tick": tick_count,
        }

    def _create_chain_candidates(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        environment_changes: List[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> None:
        result["world_history_recorded"].extend(
            self.chain_manager.create_chain_candidates(
                group_id=group_id,
                campaign=campaign,
                environment_changes=environment_changes,
            )
        )
        result["world_history_recorded"].extend(
            self.chain_manager.create_followup_chain_candidates(
                group_id=group_id,
                campaign=campaign,
            )
        )

    def _select_chain_participants(self, region: str) -> List[str]:
        if not isinstance(self.factions, dict):
            return []
        sects = [
            code for code, info in self.factions.items()
            if isinstance(info, dict) and info.get("region") == region and info.get("type") == "宗门"
        ]
        return sects[:2]

    def _consume_chain_candidates(
        self,
        group_id: str,
        campaign: Dict[str, Any],
        result: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        spawned = self.chain_manager.consume_pending_chains(group_id=group_id, campaign=campaign)
        result["world_history_recorded"].extend(spawned)
        return spawned

    def tick(self, group_id: str, campaign: Dict[str, Any],
             event_log: List[Dict[str, Any]],
             world_state: Optional[Dict[str, Any]] = None,
             player_profiles: Optional[Dict[str, Any]] = None,
             npc_registry: Any = None) -> Dict[str, Any]:
        """执行一次世界时间推进。

        Args:
            group_id: 群号
            campaign: 团务状态字典（会被修改：cycle +1）
            event_log: 事件历史列表（归档记录追加到此列表）
            world_state: 世界状态字典（可选，传入后执行自然演化）

        Returns:
            推进结果字典：
            {
                "cycle_before": int,
                "cycle_after": int,
                "events_progressed": [...],
                "stage_changed": [...],
                "archived": [...],
                "evolution": {         # 世界演化结果
                    "weather_changed": [...],
                    "region_changed": [],
                    "resource_changed": [...],
                    "leyline_flow_changed": bool,
                },
            }
        """
        import random

        result = {
            "cycle_before": campaign.get("cycle", 1),
            "cycle_after": 0,
            "world_clock": {
                "before": {},
                "after": {},
                "changed": False,
            },
            "events_progressed": [],
            "stage_changed": [],
            "archived": [],
            "faction_actions": [],
            "npc_life_actions": [],
            "world_action_proposals": [],
            "proposal_events_spawned": [],
            "chain_candidates_created": [],
            "chain_candidates_expired": [],
            "chain_events_spawned": [],
            "world_history_recorded": [],
            "evolution": {
                "weather_changed": [],
                "region_changed": [],
                "resource_changed": [],
                "leyline_flow_changed": False,
                "leyline_flow_from": 0,
                "leyline_flow_to": 0,
            },
        }

        # ── 步骤1: 推进 cycle ──
        campaign["cycle"] = campaign.get("cycle", 1) + 1
        result["cycle_after"] = campaign["cycle"]
        result["world_clock"] = self._advance_world_clock(campaign)

        # ── 步骤2: 推进活跃事件 progress ──
        pool = self.event_pool
        active_events = [
            e for e in pool.list_all(group_id)
            if e.stage not in (EventStage.ENDED.value, EventStage.ARCHIVED.value)
        ]

        ended_ids: List[str] = []

        for event in active_events:
            old_progress = event.progress
            increment = random.uniform(0.01, 0.03)
            new_progress = min(event.progress + increment, 1.0)

            # 调用已有接口更新进度
            pool.update_progress(group_id, event.event_id, round(new_progress, 4))

            result["events_progressed"].append({
                "event_id": event.event_id,
                "title": event.title,
                "progress_before": round(old_progress, 4),
                "progress_after": round(new_progress, 4),
            })

            # 检查阶段推进（复用 EventPool 内部方法）
            old_stage = event.stage
            pool._check_and_advance_stage(group_id, event)
            if event.stage != old_stage:
                result["stage_changed"].append({
                    "event_id": event.event_id,
                    "title": event.title,
                    "old_stage": old_stage,
                    "new_stage": event.stage,
                })

            # 记录已结束的事件
            if event.stage == EventStage.ENDED.value:
                ended_ids.append(event.event_id)

        # ── 步骤3: 归档已结束事件（两阶段提交 + Outcome） ──
        archive_ids: List[str] = []
        outcomes: List[Dict[str, Any]] = []
        for event_id in ended_ids:
            event = pool.get(group_id, event_id)
            if not event:
                continue

            # B-6: 为结束事件生成 Outcome
            outcome = self.outcome_resolver.resolve(
                event=event,
                world_state=world_state or {},
                campaign=campaign,
                factions=self.factions,
            )

            # B-6: 应用 Outcome 到世界/势力/玩家状态
            apply_result = {"applied": False, "applied_changes": [], "rejected": []}
            if world_state is not None:
                apply_result = self.outcome_applier.apply_outcome(
                    outcome=outcome,
                    world_state=world_state,
                    campaign=campaign,
                )

            # 记录 outcome 信息
            outcome_info = outcome.to_dict()
            outcome_info["applied_changes"] = apply_result.get("applied_changes", [])
            outcomes.append(outcome_info)

            record = pool.preview_archive(group_id, event_id)
            if record:
                record["cycle"] = f"Cycle-{campaign['cycle']:06d}"
                # B-6.4: 归档记录中嵌入 outcome
                record["outcome"] = {
                    "outcome_type": outcome.outcome_type,
                    "summary": outcome.summary,
                    "applied_changes": apply_result.get("applied_changes", []),
                }
                event_log.append(record)
                archive_ids.append(event_id)
                result["archived"].append({
                    "event_id": record["event_id"],
                    "title": record["title"],
                    "category": record["category"],
                    "outcome_type": outcome.outcome_type,
                })
                result["world_history_recorded"].append(self._append_world_history(campaign, {
                    "entry_type": "event_archived",
                    "event_id": record["event_id"],
                    "title": record["title"],
                    "category": record["category"],
                    "outcome_type": outcome.outcome_type,
                    "cycle": campaign.get("cycle", 0),
                    "tick_count": campaign.get("world_clock", {}).get("tick_count", 0),
                }))

        # EVENT_LOG 写入成功后 commit
        # （调用方负责保存 event_log，保存成功后再 commit）
        # 本方法返回 archive_ids，由调用方在保存后调用 _commit_archives
        result["_archive_ids"] = archive_ids

        # ── 步骤4: 世界状态自然演化 ──
        if world_state is not None:
            evolution = self.evolution_manager.evolve(
                group_id=group_id,
                world_state=world_state,
                cycle=campaign["cycle"],
                campaign=campaign,
                factions=self.factions,
            )
            result["evolution"] = evolution
            self._record_faction_changes(
                campaign=campaign,
                changes=evolution.get("faction_changed", []),
                result=result,
            )
            self._record_environment_changes(
                campaign=campaign,
                changes=evolution.get("environment_changed", []),
                result=result,
            )
            result["chain_candidates_expired"] = self.chain_manager.expire_pending_chains(campaign)
            result["world_history_recorded"].extend(result["chain_candidates_expired"])
            result["chain_events_spawned"] = self._consume_chain_candidates(
                group_id=group_id,
                campaign=campaign,
                result=result,
            )
            result["proposal_events_spawned"] = self._consume_world_action_proposals(
                group_id=group_id,
                campaign=campaign,
            )
            self._create_chain_candidates(
                group_id=group_id,
                campaign=campaign,
                environment_changes=evolution.get("environment_changed", []),
                result=result,
            )
            result["chain_candidates_created"] = [
                entry for entry in result["world_history_recorded"]
                if entry.get("entry_type") == "chain_candidate"
                and entry.get("created_cycle") == campaign.get("cycle", 0)
                and entry.get("created_tick") == campaign.get("world_clock", {}).get("tick_count", 0)
            ]
            result["world_history_recorded"].extend([
                entry for entry in self._ensure_world_history(campaign)
                if entry.get("entry_type") == "proposal_spawned"
                and entry.get("cycle") == campaign.get("cycle", 0)
                and entry.get("tick_count") == campaign.get("world_clock", {}).get("tick_count", 0)
            ])

            faction_candidates = self.faction_ai_manager.generate_candidates(
                group_id=group_id,
                campaign=campaign,
                world_state=world_state,
            )
            result["faction_actions"] = faction_candidates
            proposal_queue = self._ensure_world_action_proposals(campaign)
            for proposal in faction_candidates:
                proposal_queue.append(proposal)
                result["world_action_proposals"].append(proposal)
                result["world_history_recorded"].append(self._append_world_history(campaign, {
                    "entry_type": "proposal_created",
                    "proposal_id": proposal["proposal_id"],
                    "faction_code": proposal.get("faction_code", ""),
                    "goal": proposal.get("goal", ""),
                    "action": proposal.get("action", ""),
                    "source": proposal.get("source", ""),
                    "cycle": campaign.get("cycle", 0),
                    "tick_count": campaign.get("world_clock", {}).get("tick_count", 0),
                }))

            npc_life_candidates = self.npc_life_manager.generate_candidates(
                group_id=group_id,
                campaign=campaign,
                world_state=world_state,
                npc_registry=npc_registry,
            )
            result["npc_life_actions"] = npc_life_candidates
            for proposal in npc_life_candidates:
                life_record = self.npc_life_manager.record_candidate(
                    campaign=campaign,
                    group_id=group_id,
                    proposal=proposal,
                )
                result["world_history_recorded"].append(self._append_world_history(
                    campaign,
                    life_record["history_entry"],
                ))
                if life_record.get("event_log_entry"):
                    event_log.append(life_record["event_log_entry"])
                proposal_queue.append(proposal)
                result["world_action_proposals"].append(proposal)
                result["world_history_recorded"].append(self._append_world_history(campaign, {
                    "entry_type": "proposal_created",
                    "proposal_id": proposal["proposal_id"],
                    "npc_id": proposal.get("npc_id", ""),
                    "goal": proposal.get("goal", ""),
                    "action": proposal.get("action", ""),
                    "source": proposal.get("source", ""),
                    "cycle": campaign.get("cycle", 0),
                    "tick_count": campaign.get("world_clock", {}).get("tick_count", 0),
                }))

            result["npc_proactive"] = []
            if player_profiles is not None:
                npc_candidates = self.npc_action_scheduler.check_npc_actions(
                    group_id=group_id,
                    world_state=world_state,
                    player_profiles=player_profiles,
                    npc_registry=npc_registry,
                    npc_memory=campaign.get("npc_memory", {}),
                    campaign=campaign,
                )
                result["npc_proactive"] = npc_candidates

                npc_queue = self._ensure_npc_world_queue(campaign)
                for item in npc_candidates:
                    npc_queue.append({
                        "npc_id": item["npc_id"],
                        "action": item["action"],
                        "player_id": item["player_id"],
                        "priority": item["priority"],
                        "hint": item["hint"],
                        "goal": item.get("goal", ""),
                        "reason_tags": list(item.get("reason_tags", [])),
                        "relationship": item.get("relationship", ""),
                        "candidates": list(item.get("candidates", [])),
                        "source_cycle": campaign["cycle"],
                        "source_tick": campaign["world_clock"]["tick_count"],
                        "status": "pending",
                    })
                    proposal = self._build_npc_action_proposal(group_id, campaign, item)
                    proposal_queue.append(proposal)
                    result["world_action_proposals"].append(proposal)
                    result["world_history_recorded"].append(self._append_world_history(campaign, {
                        "entry_type": "proposal_created",
                        "proposal_id": proposal["proposal_id"],
                        "npc_id": proposal.get("npc_id", ""),
                        "goal": proposal.get("goal", ""),
                        "action": proposal.get("action", ""),
                        "cycle": campaign.get("cycle", 0),
                        "tick_count": campaign.get("world_clock", {}).get("tick_count", 0),
                    }))

            # ── 步骤5: 世界变化 → 事件触发 ──
            trigger_result = self.trigger_manager.check(
                group_id=group_id,
                world_state=world_state,
                event_pool=pool,
                evolution_result=evolution,
                campaign=campaign,
                cycle=campaign["cycle"],
                factions=self.factions,
            )
            result["triggered"] = trigger_result["triggered"]
            result["skipped"] = trigger_result["skipped"]
        else:
            result["triggered"] = []
            result["skipped"] = []

        logger.info(
            f"[WorldTick] tick({group_id}): "
            f"Cycle {result['cycle_before']}→{result['cycle_after']}, "
            f"推进{len(result['events_progressed'])}条, "
            f"阶段变化{len(result['stage_changed'])}条, "
            f"归档{len(result['archived'])}条, "
            f"天气变化{len(result['evolution']['weather_changed'])}处, "
            f"资源变化{len(result['evolution']['resource_changed'])}处, "
            f"触发事件{len(result.get('triggered', []))}条"
        )

        self._record_tick_ledger(campaign, result)
        return result

    def commit_archives(self, group_id: str, archive_ids: List[str]) -> None:
        """确认归档：在 EVENT_LOG 保存成功后调用。"""
        for event_id in archive_ids:
            self.event_pool.commit_archive(group_id, event_id)
