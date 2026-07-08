"""
test_npc_life_consistency.py - Phase E-2 NPC 生命周期一致性与因果约束测试

覆盖：
  1. NPC突破需要条件
  2. 普通NPC不会随机死亡
  3. 死亡有原因
  4. world_history 格式统一
  5. EVENT_LOG 重大事件写入
  6. NPCMemory 保留（历史记忆不因新事件被覆盖）
  7. rollback 恢复（campaign + event_log 一并回退）
  8. 多group隔离
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from npc_life_manager import NPCLifeManager
from npc_life_rules import is_major_npc_event, validate_breakthrough, validate_death
from world_event_pool import EventCategory, EventPool


class _FakeRegistry:
    def __init__(self, npcs=None):
        self._npcs = list(npcs or [])

    def get_all_npcs(self):
        return list(self._npcs)


def _make_campaign(cycle=20):
    return {
        "cycle": cycle,
        "world_clock": {"tick_count": 8},
        "world_history": [],
        "npc_memory": {},
        "npc_life_state": {},
        "npc_life_log": [],
        "world_action_proposals": [],
    }


def _make_proposal(npc_id, action, registry_id="", cause_category="", source_refs=None, region="central"):
    return {
        "proposal_id": f"NLP-test-000020-0008-{npc_id}",
        "proposal_type": "npc_life_action",
        "source": "npc_life",
        "status": "pending",
        "npc_id": npc_id,
        "registry_id": registry_id,
        "goal": "cultivate",
        "action": action,
        "priority": "high" if action in ("death", "disappear") else "medium",
        "region": region,
        "identity": "elder",
        "source_cycle": 20,
        "source_tick": 8,
        "source_refs": source_refs or ["event:EP0001"],
        "cause_category": cause_category or EventCategory.DAILY.value,
        "trigger_conditions": {"region": region},
        "memory_summary": f"{npc_id} {action} 的因果摘要。",
    }


# ── 1. NPC突破需要条件 ──

def test_breakthrough_requires_conditions():
    # 未闭关 -> 拒绝
    ok, reason = validate_breakthrough(life_status="active", has_leyline_event=True, help_probability=0.9)
    assert not ok and reason

    # 无灵脉事件 -> 拒绝
    ok, reason = validate_breakthrough(life_status="seclusion", has_leyline_event=False, help_probability=0.9)
    assert not ok and reason

    # 天时不足 -> 拒绝
    ok, reason = validate_breakthrough(life_status="seclusion", has_leyline_event=True, help_probability=0.1)
    assert not ok and reason

    # 三个条件同时满足 -> 通过
    ok, reason = validate_breakthrough(life_status="seclusion", has_leyline_event=True, help_probability=0.9)
    assert ok and reason

    # 端到端：未闭关的 NPC 即使遇到灵脉事件也不会生成突破候选
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    registry = _FakeRegistry([{
        "name": "Idle Elder",
        "role": "elder",
        "region": "central",
        "personality": "calm",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    pool.add(group_id="g_bt", title="central leyline surge",
              category=EventCategory.LEYLINE_RESOURCE.value, region="central", progress=0.4)

    candidates = manager.generate_candidates(
        group_id="g_bt", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    assert not any(item["action"] == "breakthrough" for item in candidates)


# ── 2. 普通NPC不会随机死亡 ──

def test_ordinary_npc_does_not_die_randomly():
    ok, reason = validate_death(
        has_conflict_event=False, has_cause_chain=False, role="elder", relationship="friendly",
    )
    assert not ok and reason

    # 端到端：没有冲突事件、没有因果链时，任何 NPC 都不应该产生死亡候选
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    registry = _FakeRegistry([{
        "name": "Quiet Disciple",
        "role": "disciple",
        "region": "west",
        "personality": "careful",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}

    candidates = manager.generate_candidates(
        group_id="g_no_death", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    assert not any(item["action"] == "death" for item in candidates)


# ── 3. 死亡有原因 ──

def test_death_has_cause():
    ok, reason = validate_death(
        has_conflict_event=True, has_cause_chain=True, role="disciple", relationship="hostile",
    )
    assert ok and reason

    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["world_history"].append({
        "entry_type": "chain_candidate_spawned",
        "chain_id": "CHAIN-CAUSE-1",
        "region": "west",
        "category": EventCategory.FACTION_CONFLICT.value,
        "cycle": 20,
        "tick_count": 8,
    })
    campaign["npc_memory"]["Han Deacon"] = [{
        "memory_type": "conflict", "trust_change": -80, "importance": 80,
        "player_id": "PLAYER-A", "npc_id": "Han Deacon",
    }]
    registry = _FakeRegistry([{
        "name": "Han Deacon", "role": "deacon", "region": "west", "personality": "careful",
    }])
    world_state = {"GLOBAL": {}, "RESOURCE": {}, "REGION": {}, "FACTION_STATE": {}}
    pool.add(group_id="g_death_cause", title="west conflict",
              category=EventCategory.FACTION_CONFLICT.value, region="west", progress=0.8)

    candidates = manager.generate_candidates(
        group_id="g_death_cause", campaign=campaign, world_state=world_state, npc_registry=registry,
    )
    deaths = [c for c in candidates if c["action"] == "death"]
    assert deaths
    assert deaths[0]["cause_category"]
    assert deaths[0]["source_refs"]


# ── 4. world_history 格式统一 ──

def test_world_history_format_unified():
    pool = EventPool()
    manager = NPCLifeManager(pool)

    campaign_a = _make_campaign()
    record_a = manager.record_candidate(
        campaign=campaign_a, group_id="g_fmt_a",
        proposal=_make_proposal("NPC-A", "breakthrough", cause_category=EventCategory.LEYLINE_RESOURCE.value),
    )

    campaign_b = _make_campaign()
    record_b = manager.record_candidate(
        campaign=campaign_b, group_id="g_fmt_b",
        proposal=_make_proposal("NPC-B", "relocate", cause_category=EventCategory.RUIN_OPPORTUNITY.value),
    )

    entry_a = record_a["history_entry"]
    entry_b = record_b["history_entry"]

    assert entry_a["entry_type"] == "npc_life_changed"
    assert entry_b["entry_type"] == "npc_life_changed"
    # 不同变化类型必须共用同一套字段（不能有的多字段有的少字段）
    assert set(entry_a.keys()) == set(entry_b.keys())
    required_fields = {"entry_type", "npc_id", "action", "cause_category", "region", "cycle", "source_refs", "summary"}
    assert required_fields.issubset(entry_a.keys())


# ── 5. EVENT_LOG 重大事件写入 ──

def test_event_log_written_for_major_npc_event():
    # 重要NPC + 死亡 -> 写入 EVENT_LOG
    assert is_major_npc_event("MAJ-001", "death") is True
    # 普通NPC + 死亡 -> 不写入
    assert is_major_npc_event("MIN-001", "death") is False
    # 重要NPC + 非重大变化（交易）-> 不写入
    assert is_major_npc_event("MAJ-001", "trade") is False
    # 无 registry_id -> 不写入
    assert is_major_npc_event("", "death") is False

    pool = EventPool()
    manager = NPCLifeManager(pool)

    campaign_major = _make_campaign()
    record_major = manager.record_candidate(
        campaign=campaign_major, group_id="g_evt_major",
        proposal=_make_proposal("Elder Song", "breakthrough", registry_id="MAJ-010",
                                  cause_category=EventCategory.LEYLINE_RESOURCE.value),
    )
    assert record_major["event_log_entry"] is not None
    assert record_major["event_log_entry"]["category"] == "npc_life"
    assert record_major["event_log_entry"]["npc_id"] == "Elder Song"
    assert record_major["event_log_entry"]["irreversible"] is False

    campaign_minor = _make_campaign()
    record_minor = manager.record_candidate(
        campaign=campaign_minor, group_id="g_evt_minor",
        proposal=_make_proposal("Rogue Wu", "death", registry_id="MIN-020",
                                  cause_category=EventCategory.FACTION_CONFLICT.value),
    )
    assert record_minor["event_log_entry"] is None

    campaign_death = _make_campaign()
    record_death = manager.record_candidate(
        campaign=campaign_death, group_id="g_evt_death",
        proposal=_make_proposal("Sect Master Ye", "death", registry_id="MAJ-002",
                                  cause_category=EventCategory.FACTION_CONFLICT.value),
    )
    assert record_death["event_log_entry"] is not None
    assert record_death["event_log_entry"]["irreversible"] is True


# ── 6. NPCMemory 保留 ──

def test_npc_memory_retains_history_on_major_event():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    campaign["npc_memory"]["Elder Song"] = [{
        "memory_type": "help", "trust_change": 40, "importance": 60,
        "player_id": "PLAYER-A", "npc_id": "Elder Song",
    }]

    manager.record_candidate(
        campaign=campaign, group_id="g_mem",
        proposal=_make_proposal("Elder Song", "breakthrough", registry_id="MAJ-010",
                                  cause_category=EventCategory.LEYLINE_RESOURCE.value),
    )

    memories = campaign["npc_memory"]["Elder Song"]
    assert len(memories) == 2
    assert memories[0]["memory_type"] == "help"
    assert memories[-1]["memory_type"] == "major_event"


# ── 7. rollback 恢复 ──

def test_rollback_restores_npc_life_and_event_log():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign = _make_campaign()
    event_log = []

    campaign_snapshot = json.loads(json.dumps(campaign))
    event_log_snapshot = json.loads(json.dumps(event_log))

    record = manager.record_candidate(
        campaign=campaign, group_id="g_rollback",
        proposal=_make_proposal("Elder Rollback", "death", registry_id="MAJ-099",
                                  cause_category=EventCategory.FACTION_CONFLICT.value),
    )
    if record["event_log_entry"]:
        event_log.append(record["event_log_entry"])

    assert campaign["npc_life_state"]
    assert campaign["npc_life_log"]
    assert campaign["npc_memory"]
    assert event_log

    # 回滚：campaign 和 event_log 一并恢复到快照前
    campaign.clear()
    campaign.update(campaign_snapshot)
    event_log.clear()
    event_log.extend(event_log_snapshot)

    assert campaign["npc_life_state"] == {}
    assert campaign["npc_life_log"] == []
    assert campaign["npc_memory"] == {}
    assert event_log == []


# ── 8. 多group隔离 ──

def test_multi_group_isolation_for_major_events():
    pool = EventPool()
    manager = NPCLifeManager(pool)
    campaign_a = _make_campaign()
    campaign_b = _make_campaign()
    event_log_a = []
    event_log_b = []

    record_a = manager.record_candidate(
        campaign=campaign_a, group_id="g_iso_a",
        proposal=_make_proposal("Elder A", "death", registry_id="MAJ-100",
                                  cause_category=EventCategory.FACTION_CONFLICT.value),
    )
    if record_a["event_log_entry"]:
        event_log_a.append(record_a["event_log_entry"])

    # group B 没有发生任何 NPC 生命周期事件
    assert campaign_a["npc_life_state"]
    assert campaign_b["npc_life_state"] == {}
    assert event_log_a
    assert event_log_b == []
    assert campaign_a["npc_memory"].get("Elder A")
    assert not campaign_b["npc_memory"]


if __name__ == "__main__":
    test_breakthrough_requires_conditions()
    test_ordinary_npc_does_not_die_randomly()
    test_death_has_cause()
    test_world_history_format_unified()
    test_event_log_written_for_major_npc_event()
    test_npc_memory_retains_history_on_major_event()
    test_rollback_restores_npc_life_and_event_log()
    test_multi_group_isolation_for_major_events()
    print("\nnpc_life_consistency tests passed")
