"""
test_npc_life_manager.py - Phase E NPCLifeManager tests
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from npc_life_manager import NPCLifeManager
from world_event_pool import EventCategory, EventPool


class _FakeRegistry:
    def __init__(self, npcs=None):
        self._npcs = list(npcs or [])

    def get_all_npcs(self):
        return list(self._npcs)


def _make_campaign(cycle=20):
    return {
        "cycle": cycle,
        "world_clock": {
            "tick_count": 8,
            "world_day": 3,
            "time_phase": "day",
            "season": "spring",
            "calendar_label": "Donghuang Spring Day 3",
        },
        "world_history": [],
        "npc_memory": {},
        "npc_life_state": {},
        "npc_life_log": [],
        "world_action_proposals": [],
    }


def test_generate_seclusion_candidate_from_leyline_signal():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    registry = _FakeRegistry([{
        "name": "Li Elder",
        "role": "elder",
        "region": "central",
        "faction_code": "CULT-01",
        "personality": "calm",
        "spirit_root_tier": "mystic",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    pool.add(
        group_id="g_life_1",
        title="central leyline surge",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="central",
        progress=0.35,
    )

    candidates = manager.generate_candidates(
        group_id="g_life_1",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )

    assert candidates
    candidate = candidates[0]
    assert candidate["npc_id"] == "Li Elder"
    assert candidate["action"] == "seclusion"
    assert candidate["goal"] == "cultivate"
    assert candidate["source_refs"][0].startswith("event:")


def test_death_requires_cause_chain():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    registry = _FakeRegistry([{
        "name": "Han Deacon",
        "role": "deacon",
        "region": "west",
        "faction_code": "CULT-02",
        "personality": "careful",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_life_2",
        title="west faction conflict",
        category=EventCategory.FACTION_CONFLICT.value,
        region="west",
        progress=0.8,
    )

    no_chain = manager.generate_candidates(
        group_id="g_life_2",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )
    assert not any(item["action"] == "death" for item in no_chain)

    campaign["world_history"].append({
        "entry_type": "chain_candidate_spawned",
        "chain_id": "CHAIN-DEATH-1",
        "chain_type": "faction_conflict_to_resource_contention",
        "region": "west",
        "category": EventCategory.FACTION_CONFLICT.value,
        "cycle": 20,
        "tick_count": 8,
    })
    campaign["npc_memory"]["Han Deacon"] = [{
        "memory_type": "conflict",
        "trust_change": -80,
        "importance": 80,
        "player_id": "PLAYER-A",
        "npc_id": "Han Deacon",
    }]

    with_chain = manager.generate_candidates(
        group_id="g_life_2",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )
    death_candidates = [item for item in with_chain if item["action"] == "death"]
    assert death_candidates
    assert death_candidates[0]["cause_category"] == EventCategory.FACTION_CONFLICT.value
    assert "chain:CHAIN-DEATH-1" in death_candidates[0]["source_refs"]


def test_record_candidate_updates_state_log_memory_and_history_entry():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    proposal = {
        "proposal_id": "NLP-g_life_3-000020-0008-LiElder",
        "proposal_type": "npc_life_action",
        "source": "npc_life",
        "status": "pending",
        "npc_id": "Li Elder",
        "goal": "cultivate",
        "action": "seclusion",
        "priority": "medium",
        "region": "central",
        "identity": "elder",
        "source_cycle": 20,
        "source_tick": 8,
        "source_refs": ["event:EP0001"],
        "cause_category": EventCategory.LEYLINE_RESOURCE.value,
        "trigger_conditions": {"region": "central"},
        "memory_summary": "Li Elder enters seclusion because of the central leyline surge.",
    }

    record = manager.record_candidate(campaign=campaign, group_id="g_life_3", proposal=proposal)

    assert record["npc_life_log_entry"]["npc_id"] == "Li Elder"
    assert campaign["npc_life_state"]["Li Elder"]["current_goal"] == "cultivate"
    assert campaign["npc_life_state"]["Li Elder"]["life_status"] == "seclusion"
    assert campaign["npc_life_log"][0]["proposal_id"] == proposal["proposal_id"]
    assert campaign["npc_memory"]["Li Elder"][0]["summary"] == proposal["memory_summary"]
    assert record["history_entry"]["entry_type"] == "npc_life_changed"
    assert record["history_entry"]["npc_id"] == "Li Elder"
    assert record["history_entry"]["action"] == "seclusion"


def test_generate_relocate_candidate_from_cross_region_ruin():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    registry = _FakeRegistry([{
        "name": "Traveller Luo",
        "role": "merchant",
        "region": "east",
        "personality": "outgoing",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_life_relocate",
        title="north ruin opening",
        category=EventCategory.RUIN_OPPORTUNITY.value,
        region="north",
        progress=0.45,
    )

    candidates = manager.generate_candidates(
        group_id="g_life_relocate",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )

    relocate = [item for item in candidates if item["action"] == "relocate"]
    assert relocate
    assert relocate[0]["goal"] == "explore"
    assert relocate[0]["region"] == "north"


def test_cautious_npc_does_not_relocate_for_cross_region_ruin():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["npc_memory"]["Merchant Chen"] = [{
        "memory_type": "conflict",
        "trust_change": -40,
        "importance": 65,
        "player_id": "PLAYER-A",
        "npc_id": "Merchant Chen",
    }]
    registry = _FakeRegistry([{
        "name": "Merchant Chen",
        "role": "merchant",
        "region": "east",
        "personality": "careful",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_life_relocate_cautious",
        title="north ruin opening",
        category=EventCategory.RUIN_OPPORTUNITY.value,
        region="north",
        progress=0.45,
    )

    candidates = manager.generate_candidates(
        group_id="g_life_relocate_cautious",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )

    assert not any(item["action"] == "relocate" for item in candidates)


def test_generate_join_event_candidate_from_local_conflict():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["npc_memory"]["Wanderer Peng"] = [{
        "memory_type": "conflict",
        "trust_change": -35,
        "importance": 65,
        "player_id": "PLAYER-A",
        "npc_id": "Wanderer Peng",
    }]
    registry = _FakeRegistry([{
        "name": "Wanderer Peng",
        "role": "rogue cultivator",
        "region": "south",
        "personality": "outgoing",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_life_join",
        title="south conflict reignites",
        category=EventCategory.FACTION_CONFLICT.value,
        region="south",
        progress=0.52,
    )

    candidates = manager.generate_candidates(
        group_id="g_life_join",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )

    joined = [item for item in candidates if item["action"] == "join_event"]
    assert joined
    assert joined[0]["goal"] == "revenge"
    assert joined[0]["cause_category"] == EventCategory.FACTION_CONFLICT.value
    assert joined[0]["trigger_conditions"]["relationship"] == "suspicious"


def test_hostile_relationship_drives_join_event():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["npc_memory"]["Wanderer Peng"] = [{
        "memory_type": "conflict",
        "trust_change": -70,
        "importance": 75,
        "player_id": "PLAYER-A",
        "npc_id": "Wanderer Peng",
    }]
    registry = _FakeRegistry([{
        "name": "Wanderer Peng",
        "role": "rogue cultivator",
        "region": "south",
        "personality": "careful",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_life_join_hostile",
        title="south conflict reignites",
        category=EventCategory.FACTION_CONFLICT.value,
        region="south",
        progress=0.52,
    )

    candidates = manager.generate_candidates(
        group_id="g_life_join_hostile",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )

    joined = [item for item in candidates if item["action"] == "join_event"]
    assert joined
    assert joined[0]["trigger_conditions"]["relationship"] == "hostile"


def test_generate_breakthrough_candidate_from_existing_seclusion():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["npc_life_state"]["Song Elder"] = {
        "location": "central",
        "identity": "elder",
        "current_goal": "cultivate",
        "life_status": "seclusion",
        "last_cycle": 18,
        "last_event_id": "NLP-OLD-1",
        "last_cause_ref": "event:EP0001",
    }
    campaign["npc_memory"]["Song Elder"] = [{
        "memory_type": "help",
        "trust_change": 40,
        "importance": 60,
        "player_id": "PLAYER-A",
        "npc_id": "Song Elder",
    }]
    registry = _FakeRegistry([{
        "name": "Song Elder",
        "role": "elder",
        "region": "central",
        "personality": "calm",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_life_breakthrough",
        title="central leyline surges again",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="central",
        progress=0.61,
    )

    candidates = manager.generate_candidates(
        group_id="g_life_breakthrough",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )

    breakthroughs = [item for item in candidates if item["action"] == "breakthrough"]
    assert breakthroughs
    assert breakthroughs[0]["goal"] == "cultivate"


def test_disappear_requires_cause_chain():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    registry = _FakeRegistry([{
        "name": "Rogue Luo",
        "role": "rogue cultivator",
        "region": "west",
        "personality": "careful",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_life_disappear",
        title="west chaos tear",
        category=EventCategory.CHAOS_ANOMALY.value,
        region="west",
        progress=0.7,
    )

    no_chain = manager.generate_candidates(
        group_id="g_life_disappear",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )
    assert not any(item["action"] == "disappear" for item in no_chain)

    campaign["world_history"].append({
        "entry_type": "chain_candidate_spawned",
        "chain_id": "CHAIN-DISAPPEAR-1",
        "chain_type": "resource_contention_to_region_change",
        "region": "west",
        "category": EventCategory.CHAOS_ANOMALY.value,
        "cycle": 20,
        "tick_count": 8,
    })

    with_chain = manager.generate_candidates(
        group_id="g_life_disappear",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )
    disappeared = [item for item in with_chain if item["action"] == "disappear"]
    assert disappeared
    assert disappeared[0]["cause_category"] == EventCategory.CHAOS_ANOMALY.value
    assert "chain:CHAIN-DISAPPEAR-1" in disappeared[0]["source_refs"]


def test_rollback_restores_npc_life_runtime_fields():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()

    snapshot = json.loads(json.dumps(campaign))

    manager.record_candidate(
        campaign=campaign,
        group_id="g_life_4",
        proposal={
            "proposal_id": "NLP-g_life_4-000020-0008-Shopkeeper",
            "proposal_type": "npc_life_action",
            "source": "npc_life",
            "status": "pending",
            "npc_id": "Shopkeeper",
            "goal": "trade",
            "action": "trade",
            "priority": "low",
            "region": "east",
            "identity": "shopkeeper",
            "source_cycle": 20,
            "source_tick": 8,
            "source_refs": ["event:EP0009"],
            "cause_category": EventCategory.DAILY.value,
            "trigger_conditions": {"region": "east"},
            "memory_summary": "Shopkeeper is preparing to expand trade.",
        },
    )

    assert campaign["npc_life_state"]
    assert campaign["npc_life_log"]
    assert campaign["npc_memory"]

    campaign.clear()
    campaign.update(snapshot)

    assert campaign["npc_life_state"] == {}
    assert campaign["npc_life_log"] == []
    assert campaign["npc_memory"] == {}


def test_join_faction_requires_diplomacy_event_and_friendly_relationship():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["npc_memory"]["Free Cultivator Bai"] = [{
        "memory_type": "help", "trust_change": 50, "importance": 70,
        "player_id": "PLAYER-A", "npc_id": "Free Cultivator Bai",
    }]
    registry = _FakeRegistry([{
        "name": "Free Cultivator Bai", "role": "rogue cultivator",
        "region": "central", "personality": "calm",
        # 没有 faction_code -> 散修，当前未隶属任何势力
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    # 没有外交事件时不应生成 npc_join_faction
    no_event = manager.generate_candidates(
        group_id="g_join_1", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    assert not any(item["action"] == "npc_join_faction" for item in no_event)

    pool.add(
        group_id="g_join_1", title="central diplomacy overture",
        category=EventCategory.CAUSAL_ECHO.value, region="central",
        progress=0.4, participants=["CULT-01"],
    )
    with_event = manager.generate_candidates(
        group_id="g_join_1", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    joins = [item for item in with_event if item["action"] == "npc_join_faction"]
    assert joins
    assert joins[0]["trigger_conditions"]["target_faction"] == "CULT-01"
    assert joins[0]["extra_state"]["current_faction"] == "CULT-01"


def test_join_faction_blocked_when_already_affiliated():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["npc_memory"]["Elder Song"] = [{
        "memory_type": "help", "trust_change": 50, "importance": 70,
        "player_id": "PLAYER-A", "npc_id": "Elder Song",
    }]
    registry = _FakeRegistry([{
        "name": "Elder Song", "role": "elder", "region": "central",
        "personality": "calm", "faction_code": "CULT-01",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    pool.add(
        group_id="g_join_2", title="central diplomacy overture",
        category=EventCategory.CAUSAL_ECHO.value, region="central",
        progress=0.4, participants=["STATE-01"],
    )

    candidates = manager.generate_candidates(
        group_id="g_join_2", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    assert not any(item["action"] == "npc_join_faction" for item in candidates)


def test_leave_faction_requires_conflict_chain_and_hostility():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    registry = _FakeRegistry([{
        # 用非易损角色（不在 FRAGILE_ROLES 里），避免和 death 规则的判定条件重叠
        "name": "Elder Mo", "role": "elder", "region": "west",
        "personality": "careful", "faction_code": "CULT-02",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    pool.add(
        group_id="g_leave_1", title="west faction conflict",
        category=EventCategory.FACTION_CONFLICT.value, region="west", progress=0.7,
    )

    # 没有因果链佐证时不应生成 npc_leave_faction
    no_chain = manager.generate_candidates(
        group_id="g_leave_1", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    assert not any(item["action"] == "npc_leave_faction" for item in no_chain)

    campaign["world_history"].append({
        "entry_type": "chain_candidate_spawned",
        "chain_id": "CHAIN-LEAVE-1",
        "region": "west",
        "category": EventCategory.FACTION_CONFLICT.value,
        "cycle": 20,
        "tick_count": 8,
    })
    campaign["npc_memory"]["Elder Mo"] = [{
        "memory_type": "conflict", "trust_change": -75, "importance": 80,
        "player_id": "PLAYER-A", "npc_id": "Elder Mo",
    }]

    with_chain = manager.generate_candidates(
        group_id="g_leave_1", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    leaves = [item for item in with_chain if item["action"] == "npc_leave_faction"]
    assert leaves
    assert leaves[0]["trigger_conditions"]["former_faction"] == "CULT-02"
    assert leaves[0]["extra_state"]["current_faction"] == ""


def test_leave_faction_blocked_when_unaffiliated():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["world_history"].append({
        "entry_type": "chain_candidate_spawned",
        "chain_id": "CHAIN-LEAVE-2",
        "region": "west",
        "category": EventCategory.FACTION_CONFLICT.value,
        "cycle": 20,
        "tick_count": 8,
    })
    campaign["npc_memory"]["Rogue Han"] = [{
        "memory_type": "conflict", "trust_change": -75, "importance": 80,
        "player_id": "PLAYER-A", "npc_id": "Rogue Han",
    }]
    registry = _FakeRegistry([{
        "name": "Rogue Han", "role": "rogue cultivator", "region": "west",
        "personality": "careful",
        # 没有 faction_code -> 本来就没隶属，不能离开
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    pool.add(
        group_id="g_leave_2", title="west faction conflict",
        category=EventCategory.FACTION_CONFLICT.value, region="west", progress=0.7,
    )

    candidates = manager.generate_candidates(
        group_id="g_leave_2", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    assert not any(item["action"] == "npc_leave_faction" for item in candidates)


def test_multi_group_isolation():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    registry_a = _FakeRegistry([{
        "name": "Trader Zhou",
        "role": "merchant",
        "region": "south",
        "faction_code": "",
        "personality": "outgoing",
    }])
    registry_b = _FakeRegistry([{
        "name": "Rogue Mo",
        "role": "rogue cultivator",
        "region": "north",
        "faction_code": "",
        "personality": "careful",
    }])
    campaign_a = _make_campaign()
    campaign_b = _make_campaign()
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    pool.add(
        group_id="g_life_A",
        title="south market recovers",
        category=EventCategory.DAILY.value,
        region="south",
        progress=0.2,
    )

    candidates_a = manager.generate_candidates(
        group_id="g_life_A",
        campaign=campaign_a,
        world_state=world_state,
        npc_registry=registry_a,
    )
    candidates_b = manager.generate_candidates(
        group_id="g_life_B",
        campaign=campaign_b,
        world_state=world_state,
        npc_registry=registry_b,
    )

    assert candidates_a
    assert not candidates_b


def test_generate_candidates_scans_event_pool_once_regardless_of_npc_count():
    # /optimize 审查发现：_build_candidate_for_npc 原来对每个 NPC 都会
    # 调用最多 6 次 event_pool.query_by_category（内部每次都重新
    # list_all+sort 一遍），是 O(NPC×Events) 的重复线性扫描。现在
    # generate_candidates 应该只在循环开始前调用一次 list_all 建索引，
    # 之后所有 NPC 复用同一份分组结果——这里用调用计数验证，而不是
    # 只看结果是否正确（结果正确不代表没有重复扫描）。
    pool = EventPool()
    original_list_all = pool.list_all
    call_count = {"n": 0}

    def _counting_list_all(group_id):
        call_count["n"] += 1
        return original_list_all(group_id)

    pool.list_all = _counting_list_all

    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    registry = _FakeRegistry([
        {"name": f"NPC-{i}", "role": "disciple", "region": "central",
         "faction_code": "", "personality": "calm"}
        for i in range(5)
    ])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    pool.add(
        group_id="g_life_scan",
        title="central leyline surge",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="central",
        progress=0.35,
    )

    manager.generate_candidates(
        group_id="g_life_scan",
        campaign=campaign,
        world_state=world_state,
        npc_registry=registry,
    )

    assert call_count["n"] == 1, f"expected exactly 1 list_all() call for 5 NPCs, got {call_count['n']}"


if __name__ == "__main__":
    test_generate_seclusion_candidate_from_leyline_signal()
    test_death_requires_cause_chain()
    test_record_candidate_updates_state_log_memory_and_history_entry()
    test_generate_relocate_candidate_from_cross_region_ruin()
    test_cautious_npc_does_not_relocate_for_cross_region_ruin()
    test_generate_join_event_candidate_from_local_conflict()
    test_hostile_relationship_drives_join_event()
    test_generate_breakthrough_candidate_from_existing_seclusion()
    test_disappear_requires_cause_chain()
    test_join_faction_requires_diplomacy_event_and_friendly_relationship()
    test_join_faction_blocked_when_already_affiliated()
    test_leave_faction_requires_conflict_chain_and_hostility()
    test_leave_faction_blocked_when_unaffiliated()
    test_rollback_restores_npc_life_runtime_fields()
    test_multi_group_isolation()
    test_generate_candidates_scans_event_pool_once_regardless_of_npc_count()
    print("\nNPCLifeManager tests passed")

