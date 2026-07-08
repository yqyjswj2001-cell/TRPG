"""
test_world_tick.py - Core WorldTick integration tests
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_event_pool import EventCategory, EventPool
from world_tick import WorldTickManager


def make_campaign(cycle=1):
    return {
        "state": "active",
        "cycle": cycle,
        "next_event_id": 1,
    }


class StubNpcRegistry:
    def get_npc(self, npc_id):
        return {"id": npc_id, "name": npc_id, "region": "east"}

    def get_all_npcs(self):
        return []


def test_tick_advances_cycle():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)

    result = tm.tick("g1", campaign, [])

    assert result["cycle_before"] == 1
    assert result["cycle_after"] == 2
    assert campaign["cycle"] == 2


def test_tick_initializes_world_clock():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)

    result = tm.tick("g_clock", campaign, [])

    assert campaign["world_clock"]["tick_count"] == 1
    assert campaign["world_clock"]["world_day"] == 1
    assert campaign["world_clock"]["time_phase"] == "清晨"
    assert result["world_clock"]["changed"] is True


def test_world_clock_advances_time_phase():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)
    phases = []

    for _ in range(5):
        tm.tick("g_clock_2", campaign, [])
        phases.append(campaign["world_clock"]["time_phase"])

    assert phases[:4] == ["清晨", "白昼", "黄昏", "子夜"]
    assert campaign["world_clock"]["world_day"] == 2


def test_tick_generates_npc_proactive_queue():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)
    campaign["npc_memory"] = {
        "NPC-001": [{
            "player_id": "PLAYER-A",
            "memory_type": "rescue",
            "trust_change": 45,
            "summary": "rescued before",
            "importance": 90,
        }]
    }
    campaign["npc_action_cooldown"] = {}
    campaign["npc_action_log"] = []
    campaign["npc_world_queue"] = []
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    player_profiles = {"PLAYER-A": {"IDENTITY_STATE": {"region": "east"}}}

    result = tm.tick(
        "g_npc_1",
        campaign,
        [],
        world_state=world_state,
        player_profiles=player_profiles,
        npc_registry=StubNpcRegistry(),
    )

    assert result["npc_proactive"]
    assert campaign["npc_world_queue"]
    assert campaign["npc_world_queue"][0]["status"] == "pending"


def test_tick_records_tick_ledger_summary():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    result = tm.tick("g_ledger", campaign, [], world_state=world_state)

    summary = campaign["tick_ledger"]["last_tick_summary"]
    assert summary["cycle_after"] == result["cycle_after"]
    assert "proposal_generated" in summary
    assert "history_recorded" in summary
    assert "npc_life_candidates" in summary


def test_tick_records_environment_changes_into_world_history():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)
    world_state = {
        "GLOBAL": {"chaos_level": "stable", "leyline_flow_value": 50},
        "RESOURCE": {},
        "REGION": {
            "central": {
                "environment": {
                    "physical_weather": "storm",
                    "spiritual_weather": "chaotic",
                    "celestial_phenomenon": "blood moon",
                    "anomaly_environment": "space tear",
                    "effects": ["spirit flow reversal"],
                }
            }
        },
        "FACTION_STATE": {},
        "CHAOS": {"active_anomalies": []},
        "weather": {},
    }

    original_evolve = tm.evolution_manager.evolve

    def fake_evolve(*args, **kwargs):
        result = original_evolve(*args, **kwargs)
        result["environment_changed"] = [{
            "region": "central",
            "physical_weather": "storm",
            "spiritual_weather": "chaotic",
            "celestial_phenomenon": "blood moon",
            "anomaly_environment": "space tear",
            "effects": ["spirit flow reversal"],
        }]
        return result

    tm.evolution_manager.evolve = fake_evolve
    try:
        result = tm.tick("g_env", campaign, [], world_state=world_state)
    finally:
        tm.evolution_manager.evolve = original_evolve

    assert result["evolution"]["environment_changed"]
    assert any(entry["entry_type"] == "environment_changed" for entry in campaign["world_history"])


def test_tick_generates_faction_action_proposals():
    pool = EventPool()
    factions = {
        "STATE-01": {
            "code": "STATE-01",
            "name": "Xuandu Court",
            "type": "dynasty",
            "region": "central",
            "power": 90,
            "relations": [],
        }
    }
    tm = WorldTickManager(pool, factions=factions)
    campaign = make_campaign(cycle=9)
    world_state = {
        "GLOBAL": {},
        "RESOURCE": {},
        "REGION": {},
        "FACTION_STATE": {
            "STATE-01": {
                "power": 88,
                "stability": 0.8,
                "morale": 0.8,
                "active_goal": "扩张边境",
                "strategic_goal": "扩张",
                "internal_state": "stable",
                "faction_relations_runtime": {},
            }
        },
        "CHAOS": {},
        "weather": {},
    }

    result = tm.tick("g_faction_1", campaign, [], world_state=world_state)

    assert result["faction_actions"]
    assert campaign["world_action_proposals"]


def test_tick_consumes_pending_faction_action_proposals():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=10)
    campaign["world_clock"] = {
        "tick_count": 10,
        "world_day": 3,
        "time_phase": "白昼",
        "season": "spring",
        "calendar_label": "test",
    }
    campaign["world_action_proposals"] = [{
        "proposal_id": "FAP-g_faction_consume-000010-0010-STATE-01",
        "proposal_type": "faction_action",
        "source": "faction_ai",
        "status": "pending",
        "faction_code": "STATE-01",
        "goal": "expand",
        "action": "Xuandu Court expands",
        "priority": "high",
        "region": "central",
        "outcome_stub": {
            "event_id": "FAP-g_faction_consume-000010-0010-STATE-01",
            "outcome_type": "escalated",
            "summary": "Xuandu Court expands",
            "world_delta": {},
            "faction_delta": {},
            "profile_delta": {},
            "spawn_event_hints": [{
                "category": EventCategory.FACTION_CONFLICT.value,
                "region": "central",
                "reason": "faction:test",
            }],
            "applied_changes": [],
        },
    }]
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    result = tm.tick("g_faction_consume", campaign, [], world_state=world_state)

    assert result["proposal_events_spawned"]
    assert campaign["world_action_proposals"][0]["status"] == "spawned"


def test_tick_generates_npc_life_proposals_and_runtime_logs():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=12)
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_npc_life_tick_1",
        title="central leyline tide",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="central",
        progress=0.4,
    )

    class LifeRegistry:
        def get_npc(self, npc_id):
            return {"id": npc_id, "name": npc_id, "region": "central"}

        def get_all_npcs(self):
            return [{
                "name": "Li Elder",
                "role": "elder",
                "region": "central",
                "faction_code": "CULT-01",
                "personality": "calm",
            }]

    result = tm.tick(
        "g_npc_life_tick_1",
        campaign,
        [],
        world_state=world_state,
        player_profiles={},
        npc_registry=LifeRegistry(),
    )

    assert result["npc_life_actions"]
    proposal = result["npc_life_actions"][0]
    assert proposal["action"] == "seclusion"
    assert campaign["npc_life_state"]["Li Elder"]["life_status"] == "seclusion"
    assert campaign["npc_life_log"][0]["proposal_id"] == proposal["proposal_id"]
    assert campaign["npc_memory"]["Li Elder"]
    assert any(
        entry["entry_type"] == "npc_life_changed"
        and entry.get("npc_id") == "Li Elder"
        and entry.get("action") == "seclusion"
        for entry in campaign["world_history"]
    )
    assert any(
        entry["entry_type"] == "proposal_created"
        and entry["proposal_id"] == proposal["proposal_id"]
        for entry in campaign["world_history"]
    )


def test_tick_npc_life_multi_group_isolation():
    pool = EventPool()
    tm = WorldTickManager(pool)
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    campaign_a = make_campaign(cycle=12)
    campaign_b = make_campaign(cycle=12)

    pool.add(
        group_id="g_npc_life_A",
        title="south market recovers",
        category=EventCategory.DAILY.value,
        region="south",
        progress=0.25,
    )

    class RegistryA:
        def get_npc(self, npc_id):
            return {"id": npc_id, "name": npc_id, "region": "south"}

        def get_all_npcs(self):
            return [{"name": "Trader Zhou", "role": "merchant", "region": "south", "personality": "outgoing"}]

    class RegistryB:
        def get_npc(self, npc_id):
            return {"id": npc_id, "name": npc_id, "region": "north"}

        def get_all_npcs(self):
            return [{"name": "Rogue Mo", "role": "rogue cultivator", "region": "north", "personality": "careful"}]

    result_a = tm.tick("g_npc_life_A", campaign_a, [], world_state=world_state, player_profiles={}, npc_registry=RegistryA())
    result_b = tm.tick("g_npc_life_B", campaign_b, [], world_state=world_state, player_profiles={}, npc_registry=RegistryB())

    assert result_a["npc_life_actions"]
    assert result_b["npc_life_actions"] == []


def test_tick_generates_breakthrough_life_action_from_existing_seclusion():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=14)
    campaign["npc_life_state"] = {
        "Song Elder": {
            "location": "central",
            "identity": "elder",
            "current_goal": "cultivate",
            "life_status": "seclusion",
            "last_cycle": 13,
            "last_event_id": "NLP-OLD-1",
            "last_cause_ref": "event:EP0001",
        }
    }
    campaign["npc_memory"] = {
        "Song Elder": [{
            "memory_type": "help",
            "trust_change": 40,
            "importance": 60,
            "player_id": "PLAYER-A",
            "npc_id": "Song Elder",
        }]
    }
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_npc_life_breakthrough_tick",
        title="central leyline swells again",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="central",
        progress=0.55,
    )

    class BreakthroughRegistry:
        def get_npc(self, npc_id):
            return {"id": npc_id, "name": npc_id, "region": "central"}

        def get_all_npcs(self):
            return [{"name": "Song Elder", "role": "elder", "region": "central", "personality": "calm"}]

    result = tm.tick(
        "g_npc_life_breakthrough_tick",
        campaign,
        [],
        world_state=world_state,
        player_profiles={},
        npc_registry=BreakthroughRegistry(),
    )

    assert result["npc_life_actions"]
    assert result["npc_life_actions"][0]["action"] == "breakthrough"


def test_tick_generates_world_action_proposals():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=1)
    campaign["npc_memory"] = {
        "NPC-001": [{
            "player_id": "PLAYER-A",
            "memory_type": "rescue",
            "trust_change": 45,
            "summary": "rescued before",
            "importance": 90,
        }]
    }
    campaign["npc_action_cooldown"] = {}
    campaign["npc_action_log"] = []
    campaign["npc_world_queue"] = []
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    player_profiles = {"PLAYER-A": {"IDENTITY_STATE": {"region": "east"}}}

    result = tm.tick(
        "g_proposal_1",
        campaign,
        [],
        world_state=world_state,
        player_profiles=player_profiles,
        npc_registry=StubNpcRegistry(),
    )

    assert result["world_action_proposals"]
    assert campaign["world_action_proposals"]


def test_tick_maps_goals_to_event_categories():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=8)
    campaign["world_clock"] = {
        "tick_count": 8,
        "world_day": 3,
        "time_phase": "白昼",
        "season": "spring",
        "calendar_label": "test",
    }
    campaign["world_action_proposals"] = [{
        "proposal_id": "P-EXPLORE",
        "proposal_type": "npc_outcome",
        "source": "npc_proactive",
        "status": "pending",
        "npc_id": "NPC-EXPLORE",
        "player_id": "",
        "goal": "explore",
        "action": "offer_information",
        "priority": "medium",
        "reason_tags": [],
        "relationship": "friendly",
        "candidates": ["offer_information"],
        "source_cycle": 8,
        "source_tick": 8,
        "outcome_stub": {
            "event_id": "P-EXPLORE",
            "outcome_type": "escalated",
            "summary": "explore proposal",
            "world_delta": {},
            "faction_delta": {},
            "profile_delta": {},
            "spawn_event_hints": [{"category": "日常", "region": "east", "reason": "npc:explore"}],
            "applied_changes": [],
        },
    }]
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    result = tm.tick("g_proposal_goal_map", campaign, [], world_state=world_state, player_profiles={}, npc_registry=StubNpcRegistry())
    categories = {item["proposal_id"]: item["category"] for item in result["proposal_events_spawned"]}
    assert categories["P-EXPLORE"] == EventCategory.RUIN_OPPORTUNITY.value


def test_rollback_restores_tick_runtime_state():
    pool = EventPool()
    tm = WorldTickManager(pool)
    campaign = make_campaign(cycle=3)
    campaign["npc_memory"] = {
        "NPC-001": [{
            "player_id": "PLAYER-A",
            "memory_type": "rescue",
            "trust_change": 45,
            "summary": "rescued before",
            "importance": 90,
        }]
    }
    campaign["npc_action_cooldown"] = {}
    campaign["npc_action_log"] = []
    campaign["npc_world_queue"] = []
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    player_profiles = {"PLAYER-A": {"IDENTITY_STATE": {"region": "east"}}}

    snapshot = {
        "campaign": json.loads(json.dumps(campaign)),
        "event_pool": json.loads(json.dumps(pool.dump("g5_runtime"))),
        "event_log": [],
    }

    tm.tick(
        "g5_runtime",
        campaign,
        [],
        world_state=world_state,
        player_profiles=player_profiles,
        npc_registry=StubNpcRegistry(),
    )

    assert campaign["world_clock"]["tick_count"] == 1
    assert "last_tick_summary" in campaign["tick_ledger"]
    assert campaign["world_action_proposals"]

    campaign.clear()
    campaign.update(snapshot["campaign"])
    pool.clear("g5_runtime")
    if snapshot["event_pool"]:
        pool.load("g5_runtime", snapshot["event_pool"])

    assert "world_clock" not in campaign
    assert campaign["npc_world_queue"] == []
    assert campaign.get("world_action_proposals", []) == []
    assert campaign.get("world_history", []) == []


def test_multi_group_isolation():
    pool = EventPool()
    tm = WorldTickManager(pool)

    c1, c2 = make_campaign(cycle=1), make_campaign(cycle=5)
    c1["world_history"] = [{"entry_type": "seed", "group": "A"}]
    c2["world_history"] = [{"entry_type": "seed", "group": "B"}]

    pool.add(group_id="group_A", title="A event", category=EventCategory.DAILY.value, region="central", progress=0.10)
    pool.add(group_id="group_B", title="B event", category=EventCategory.DAILY.value, region="east", progress=0.50)

    r1 = tm.tick("group_A", c1, [])
    assert c1["cycle"] == 2
    assert c2["cycle"] == 5
    assert len(r1["events_progressed"]) == 1

    r2 = tm.tick("group_B", c2, [])
    assert c2["cycle"] == 6
    assert len(r2["events_progressed"]) == 1
    assert c1["world_history"][0]["group"] == "A"
    assert c2["world_history"][0]["group"] == "B"


if __name__ == "__main__":
    test_tick_advances_cycle()
    test_tick_initializes_world_clock()
    test_world_clock_advances_time_phase()
    test_tick_generates_npc_proactive_queue()
    test_tick_records_tick_ledger_summary()
    test_tick_records_environment_changes_into_world_history()
    test_tick_generates_faction_action_proposals()
    test_tick_consumes_pending_faction_action_proposals()
    test_tick_generates_npc_life_proposals_and_runtime_logs()
    test_tick_npc_life_multi_group_isolation()
    test_tick_generates_breakthrough_life_action_from_existing_seclusion()
    test_tick_generates_world_action_proposals()
    test_tick_maps_goals_to_event_categories()
    test_rollback_restores_tick_runtime_state()
    test_multi_group_isolation()
    print("\nWorld Tick tests passed")
