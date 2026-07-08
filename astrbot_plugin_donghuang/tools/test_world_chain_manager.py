"""
test_world_chain_manager.py - Phase C 世界因果链测试

运行方式：
  python tools/test_world_chain_manager.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_chain_manager import WorldChainManager
from world_event_pool import EventCategory, EventPool


def make_factions():
    return {
        "CULT-01": {"code": "CULT-01", "name": "归墟宗", "type": "宗门", "region": "中部"},
        "CULT-02": {"code": "CULT-02", "name": "青岚门", "type": "宗门", "region": "中部"},
    }


def test_create_chain_candidate_with_required_metadata():
    pool = EventPool()
    manager = WorldChainManager(pool, factions=make_factions())
    campaign = {
        "cycle": 12,
        "world_clock": {"tick_count": 8},
        "world_history": [],
    }
    pool.add(group_id="g1", title="中部灵脉异常", category=EventCategory.LEYLINE_RESOURCE.value, region="中部")

    created = manager.create_chain_candidates(
        group_id="g1",
        campaign=campaign,
        environment_changes=[{
            "region": "中部",
            "spiritual_weather": "紊乱",
            "celestial_phenomenon": "血月映空",
            "anomaly_environment": "无",
            "effects": ["灵气逆流"],
        }],
    )

    assert len(created) == 1
    candidate = created[0]
    assert candidate["entry_type"] == "chain_candidate"
    assert candidate["parent_chain_id"] == ""
    assert candidate["chain_depth"] == 1
    assert candidate["cause_category"] == EventCategory.LEYLINE_RESOURCE.value
    assert candidate["source_refs"]
    assert candidate["trigger_conditions"]["requires_environment_change"] is True
    print("✅ Phase C 测试1通过：链创建包含必需元数据")


def test_consume_pending_chain_spawns_formal_event():
    pool = EventPool()
    manager = WorldChainManager(pool, factions=make_factions())
    campaign = {
        "cycle": 13,
        "world_clock": {"tick_count": 9},
        "world_history": [{
            "entry_type": "chain_candidate",
            "chain_id": "CHAIN-1",
            "chain_type": "leyline_anomaly_to_faction_conflict",
            "parent_chain_id": "",
            "chain_depth": 1,
            "cause_category": EventCategory.LEYLINE_RESOURCE.value,
            "source_refs": ["event:EP0001", "history:environment_changed:中部:12:8"],
            "trigger_conditions": {"requires_environment_change": True, "requires_leyline_event": True},
            "region": "中部",
            "target_event_category": EventCategory.FACTION_CONFLICT.value,
            "target_event_title": "中部宗门争夺灵脉",
            "status": "pending",
            "created_cycle": 12,
            "created_tick": 8,
        }],
    }

    spawned = manager.consume_pending_chains("g1", campaign)

    assert len(spawned) == 1
    assert campaign["world_history"][0]["status"] == "spawned"
    assert pool.query_by_category("g1", EventCategory.FACTION_CONFLICT.value)
    print("✅ Phase C 测试2通过：链消费生成正式事件")


def test_expire_old_pending_chain():
    pool = EventPool()
    manager = WorldChainManager(pool)
    campaign = {
        "cycle": 20,
        "world_clock": {"tick_count": 12},
        "world_history": [{
            "entry_type": "chain_candidate",
            "chain_id": "CHAIN-OLD",
            "chain_type": "leyline_anomaly_to_faction_conflict",
            "parent_chain_id": "",
            "chain_depth": 1,
            "cause_category": EventCategory.LEYLINE_RESOURCE.value,
            "source_refs": ["event:EP0001"],
            "trigger_conditions": {},
            "region": "中部",
            "target_event_category": EventCategory.FACTION_CONFLICT.value,
            "target_event_title": "中部宗门争夺灵脉",
            "status": "pending",
            "created_cycle": 18,
            "created_tick": 1,
        }],
    }

    expired = manager.expire_pending_chains(campaign)

    assert len(expired) == 1
    assert campaign["world_history"][0]["status"] == "expired"
    assert any(entry["entry_type"] == "chain_candidate_expired" for entry in campaign["world_history"])
    print("✅ Phase C 测试3通过：旧链会过期")


def test_create_followup_chain_from_faction_conflict():
    pool = EventPool()
    manager = WorldChainManager(pool, factions=make_factions())
    conflict = pool.add(
        group_id="g1",
        title="中部宗门争夺灵脉",
        category=EventCategory.FACTION_CONFLICT.value,
        region="中部",
    )
    campaign = {
        "cycle": 14,
        "world_clock": {"tick_count": 10},
        "world_history": [{
            "entry_type": "chain_candidate_spawned",
            "chain_id": "CHAIN-ROOT",
            "chain_type": "leyline_anomaly_to_faction_conflict",
            "parent_chain_id": "",
            "chain_depth": 1,
            "cause_category": EventCategory.LEYLINE_RESOURCE.value,
            "source_refs": ["event:EP0001"],
            "trigger_conditions": {"region": "中部"},
            "event_id": conflict.event_id,
            "category": conflict.category,
            "region": "中部",
            "cycle": 13,
            "tick_count": 9,
        }],
    }

    created = manager.create_followup_chain_candidates("g1", campaign)

    assert len(created) == 1
    candidate = created[0]
    assert candidate["chain_type"] == "faction_conflict_to_resource_contention"
    assert candidate["parent_chain_id"] == "CHAIN-ROOT"
    assert candidate["chain_depth"] == 2
    assert candidate["cause_category"] == EventCategory.FACTION_CONFLICT.value
    assert candidate["target_event_category"] == EventCategory.DAILY.value
    print("✅ Phase C 测试3.1通过：势力冲突生成第二跳资源争夺候选")


def test_create_third_hop_chain_from_resource_contention():
    pool = EventPool()
    manager = WorldChainManager(pool, factions=make_factions())
    contention = pool.add(
        group_id="g1",
        title="涓儴鐏佃剦璧勬簮浜夊ず鍗囩骇",
        category=EventCategory.DAILY.value,
        region="涓儴",
    )
    campaign = {
        "cycle": 15,
        "world_clock": {"tick_count": 11},
        "world_history": [{
            "entry_type": "chain_candidate_spawned",
            "chain_id": "CHAIN-SECOND",
            "chain_type": "faction_conflict_to_resource_contention",
            "parent_chain_id": "CHAIN-ROOT",
            "chain_depth": 2,
            "cause_category": EventCategory.FACTION_CONFLICT.value,
            "source_refs": ["event:EP0002", "chain:CHAIN-ROOT"],
            "trigger_conditions": {"requires_conflict_event": True, "region": "涓儴"},
            "event_id": contention.event_id,
            "category": contention.category,
            "region": "涓儴",
            "cycle": 14,
            "tick_count": 10,
        }],
    }

    created = manager.create_followup_chain_candidates("g1", campaign)

    assert len(created) == 1
    candidate = created[0]
    assert candidate["chain_type"] == "resource_contention_to_region_change"
    assert candidate["parent_chain_id"] == "CHAIN-SECOND"
    assert candidate["chain_depth"] == 3
    assert candidate["cause_category"] == EventCategory.DAILY.value
    assert candidate["target_event_category"] == EventCategory.DAILY.value
    assert candidate["trigger_conditions"]["requires_resource_contention_event"] is True
    print("Phase C test 3.2 passed: third-hop chain candidate created")


def test_prevent_infinite_loop_when_chain_depth_exceeds_limit():
    pool = EventPool()
    manager = WorldChainManager(pool)
    campaign = {
        "cycle": 30,
        "world_clock": {"tick_count": 5},
        "world_history": [],
    }
    pool.add(group_id="g1", title="中部灵脉异常", category=EventCategory.LEYLINE_RESOURCE.value, region="中部")

    created = manager.create_chain_candidates(
        group_id="g1",
        campaign=campaign,
        environment_changes=[{
            "region": "中部",
            "spiritual_weather": "紊乱",
            "celestial_phenomenon": "血月映空",
            "anomaly_environment": "无",
            "effects": [],
            "parent_chain_id": "CHAIN-PARENT",
            "chain_depth": 3,
        }],
    )

    assert created == []
    assert any(entry.get("entry_type") == "chain_candidate_skipped" for entry in campaign["world_history"])
    print("✅ Phase C 测试4通过：深度限制防止无限循环")


def test_rollback_restores_chain_history():
    pool = EventPool()
    manager = WorldChainManager(pool, factions=make_factions())
    group_id = "g_rollback"
    campaign = {
        "cycle": 12,
        "world_clock": {"tick_count": 8},
        "world_history": [],
    }
    pool.add(group_id=group_id, title="中部灵脉异常", category=EventCategory.LEYLINE_RESOURCE.value, region="中部")
    snapshot = {
        "campaign": json.loads(json.dumps(campaign)),
        "event_pool": json.loads(json.dumps(pool.dump(group_id))),
    }

    manager.create_chain_candidates(
        group_id=group_id,
        campaign=campaign,
        environment_changes=[{
            "region": "中部",
            "spiritual_weather": "紊乱",
            "celestial_phenomenon": "血月映空",
            "anomaly_environment": "无",
            "effects": [],
        }],
    )
    assert campaign["world_history"]

    campaign.clear()
    campaign.update(snapshot["campaign"])
    pool.clear(group_id)
    pool.load(group_id, snapshot["event_pool"])

    assert campaign["world_history"] == []
    assert len(pool.query_by_category(group_id, EventCategory.LEYLINE_RESOURCE.value)) == 1
    print("✅ Phase C 测试5通过：rollback 恢复链历史")


def test_multi_group_isolation():
    pool = EventPool()
    manager = WorldChainManager(pool, factions=make_factions())
    pool.add(group_id="group_A", title="中部灵脉异常A", category=EventCategory.LEYLINE_RESOURCE.value, region="中部")
    pool.add(group_id="group_B", title="中部灵脉异常B", category=EventCategory.LEYLINE_RESOURCE.value, region="中部")
    campaign_a = {"cycle": 10, "world_clock": {"tick_count": 4}, "world_history": []}
    campaign_b = {"cycle": 40, "world_clock": {"tick_count": 7}, "world_history": []}

    manager.create_chain_candidates("group_A", campaign_a, [{"region": "中部"}])

    assert campaign_a["world_history"]
    assert campaign_b["world_history"] == []
    print("✅ Phase C 测试6通过：多 group 隔离")


if __name__ == "__main__":
    test_create_chain_candidate_with_required_metadata()
    test_consume_pending_chain_spawns_formal_event()
    test_expire_old_pending_chain()
    test_create_followup_chain_from_faction_conflict()
    test_create_third_hop_chain_from_resource_contention()
    test_prevent_infinite_loop_when_chain_depth_exceeds_limit()
    test_rollback_restores_chain_history()
    test_multi_group_isolation()
    print("\n🎉 Phase C WorldChainManager 全部测试通过！")
