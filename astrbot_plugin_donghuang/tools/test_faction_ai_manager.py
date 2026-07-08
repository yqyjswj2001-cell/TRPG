"""
test_faction_ai_manager.py - FactionAIManager 候选生成测试

FactionAIManager 只生成势力行动候选（不直接改 world_state/EventPool），
跟 NPCLifeManager 是同一套"候选生成器"架构。这个文件此前没有专门的测试，
现在补上，覆盖 _select_goal 的几条主要判定路径。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faction_ai_manager import FactionAIManager
from world_event_pool import EventCategory, EventPool


def _make_campaign(cycle=10):
    return {
        "cycle": cycle,
        "world_clock": {"tick_count": 4},
        "world_history": [],
        "world_action_proposals": [],
    }


def _make_faction(code="CULT-01", region="central", power=60, relations=None):
    return {
        code: {
            "name": "归墟宗",
            "code": code,
            "region": region,
            "power": power,
            "relations": relations or [],
        }
    }


def _make_runtime(power=60, stability=0.6, morale=0.7, active_goal="", relations_runtime=None):
    return {
        "power": power,
        "stability": stability,
        "morale": morale,
        "active_goal": active_goal,
        "faction_relations_runtime": relations_runtime or {},
    }


def test_defend_goal_when_low_stability():
    pool = EventPool()
    manager = FactionAIManager(pool, factions=_make_faction())
    campaign = _make_campaign()
    world_state = {"FACTION_STATE": {"CULT-01": _make_runtime(stability=0.2)}}

    candidates = manager.generate_candidates(group_id="g_fac_1", campaign=campaign, world_state=world_state)

    assert candidates
    assert candidates[0]["goal"] == "defend"
    assert candidates[0]["faction_code"] == "CULT-01"


def test_expand_goal_when_high_tension_and_power():
    pool = EventPool()
    manager = FactionAIManager(pool, factions=_make_faction(power=80))
    campaign = _make_campaign()
    world_state = {
        "FACTION_STATE": {
            "CULT-01": _make_runtime(
                power=80,
                stability=0.6,
                relations_runtime={"STATE-01": {"tension": 0.9, "trust": 0.2}},
            )
        }
    }

    candidates = manager.generate_candidates(group_id="g_fac_2", campaign=campaign, world_state=world_state)

    assert candidates
    assert candidates[0]["goal"] == "expand"
    assert candidates[0]["priority"] == "high"


def test_diplomacy_goal_when_high_trust_and_no_conflict():
    pool = EventPool()
    manager = FactionAIManager(pool, factions=_make_faction())
    campaign = _make_campaign()
    world_state = {
        "FACTION_STATE": {
            "CULT-01": _make_runtime(
                stability=0.6,
                relations_runtime={"STATE-01": {"tension": 0.3, "trust": 0.8}},
            )
        }
    }

    candidates = manager.generate_candidates(group_id="g_fac_3", campaign=campaign, world_state=world_state)

    assert candidates
    assert candidates[0]["goal"] == "diplomacy"
    assert "runtime_relations:high_trust" in candidates[0]["source_refs"]


def test_resource_compete_goal_from_chain_signal():
    pool = EventPool()
    manager = FactionAIManager(pool, factions=_make_faction(region="west"))
    campaign = _make_campaign()
    campaign["world_history"].append({
        "entry_type": "chain_candidate_spawned",
        "chain_type": "leyline_anomaly_to_faction_conflict",
        "region": "west",
        "cycle": 10,
        "tick_count": 4,
    })
    world_state = {"FACTION_STATE": {"CULT-01": _make_runtime(stability=0.6)}}

    candidates = manager.generate_candidates(group_id="g_fac_4", campaign=campaign, world_state=world_state)

    assert candidates
    assert candidates[0]["goal"] == "resource_compete"


def test_no_candidate_without_faction_state():
    pool = EventPool()
    manager = FactionAIManager(pool, factions=_make_faction())
    campaign = _make_campaign()

    candidates = manager.generate_candidates(group_id="g_fac_5", campaign=campaign, world_state={})
    assert candidates == []

    candidates = manager.generate_candidates(group_id="g_fac_5", campaign=campaign, world_state=None)
    assert candidates == []


def test_duplicate_pending_blocks_new_candidate():
    pool = EventPool()
    manager = FactionAIManager(pool, factions=_make_faction())
    campaign = _make_campaign()
    campaign["world_action_proposals"].append({
        "status": "pending",
        "source": "faction_ai",
        "faction_code": "CULT-01",
        "goal": "defend",
    })
    world_state = {"FACTION_STATE": {"CULT-01": _make_runtime(stability=0.2)}}

    candidates = manager.generate_candidates(group_id="g_fac_6", campaign=campaign, world_state=world_state)
    assert candidates == []


def test_multi_group_isolation():
    pool = EventPool()
    manager = FactionAIManager(pool, factions=_make_faction(region="south"))

    campaign_a = _make_campaign()
    campaign_a["world_history"].append({
        "entry_type": "chain_candidate_spawned",
        "chain_type": "leyline_anomaly_to_faction_conflict",
        "region": "south",
        "cycle": 10,
        "tick_count": 4,
    })
    campaign_b = _make_campaign()
    world_state = {"FACTION_STATE": {"CULT-01": _make_runtime(stability=0.6)}}

    candidates_a = manager.generate_candidates(group_id="g_fac_a", campaign=campaign_a, world_state=world_state)
    candidates_b = manager.generate_candidates(group_id="g_fac_b", campaign=campaign_b, world_state=world_state)

    assert candidates_a
    # group B 没有链信号、没有高张力关系、稳定/权力也不达"expand"默认阈值组合，不应生成候选
    assert candidates_b == []


def test_generate_candidates_scans_event_pool_once_regardless_of_faction_count():
    # /optimize 审查发现：_select_goal 原来对每个势力都会调用
    # event_pool.query_by_category（内部每次都重新 list_all+sort 一遍），
    # 是 O(Factions×Events) 的重复线性扫描。现在 generate_candidates
    # 应该只在循环开始前调用一次 list_all 建索引，之后所有势力复用同一份
    # 分组结果——这里用调用计数验证。
    pool = EventPool()
    original_list_all = pool.list_all
    call_count = {"n": 0}

    def _counting_list_all(group_id):
        call_count["n"] += 1
        return original_list_all(group_id)

    pool.list_all = _counting_list_all

    factions = {}
    for i in range(5):
        code = f"CULT-{i}"
        factions[code] = {"name": f"势力{i}", "code": code, "region": "central", "power": 60, "relations": []}

    manager = FactionAIManager(pool, factions=factions)
    campaign = _make_campaign()
    world_state = {"FACTION_STATE": {code: _make_runtime(stability=0.2) for code in factions}}

    manager.generate_candidates(group_id="g_fac_scan", campaign=campaign, world_state=world_state)

    assert call_count["n"] == 1, f"expected exactly 1 list_all() call for 5 factions, got {call_count['n']}"


if __name__ == "__main__":
    test_defend_goal_when_low_stability()
    test_expand_goal_when_high_tension_and_power()
    test_diplomacy_goal_when_high_trust_and_no_conflict()
    test_resource_compete_goal_from_chain_signal()
    test_no_candidate_without_faction_state()
    test_duplicate_pending_blocks_new_candidate()
    test_multi_group_isolation()
    test_generate_candidates_scans_event_pool_once_regardless_of_faction_count()
    print("\nfaction_ai_manager tests passed")
