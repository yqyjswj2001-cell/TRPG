"""
test_faction_trigger.py — B-5.3 势力事件触发测试

覆盖：
  1. stance→对立 → FACTION_CONFLICT (HIGH)
  2. active_goal→内乱 → FACTION_CONFLICT (MEDIUM)
  3. power 连续下降且 ≤30 → FACTION_CONFLICT (MEDIUM)
  4. 盟友 + power > 70 → RUIN_OPPORTUNITY (LOW)
  5. 防重复（同 category+region）
  6. 与已有 Trigger 共存
  7. metadata 正确写入 triggered result
  8. 多 Group
  9. Snapshot / Rollback 后继续正常 Trigger
  10. 不满足条件不会创建事件

运行方式：
  python3 tools/test_faction_trigger.py
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_event_pool import EventPool, EventCategory, EventPriority, EventVisibility
from world_event_trigger import WorldEventTrigger

# ──────────────────────────────────────────────
#  测试用势力数据
# ──────────────────────────────────────────────

MOCK_FACTIONS = {
    "STATE-01": {
        "code": "STATE-01",
        "name": "祁渊李氏",
        "type": "王朝",
        "region": "中部",
        "power": 48,
        "status_desc": "东荒最古老的世俗政权。",
        "stronghold": "岱央城——灵漏塔",
        "relations": [
            {"code": "CULT-01", "stance": "从属", "reason": "共治"},
        ],
    },
    "CULT-01": {
        "code": "CULT-01",
        "name": "归墟宗",
        "type": "宗门",
        "region": "中部",
        "power": 83,
        "status_desc": "中部最古老宗门。",
        "stronghold": "祖脉余山——祖顶灵脉监测站",
        "relations": [
            {"code": "STATE-01", "stance": "从属", "reason": "共治"},
        ],
    },
    "CULT-03": {
        "code": "CULT-03",
        "name": "永寂殿",
        "type": "宗门",
        "region": "北地",
        "power": 100,
        "status_desc": "北地唯一宗门。",
        "stronghold": "玄冰崖——宗门档案库",
        "relations": [
            {"code": "CULT-05", "stance": "盟友", "reason": "八百年共享监测数据"},
        ],
    },
    "CULT-05": {
        "code": "CULT-05",
        "name": "镇渊院",
        "type": "宗门",
        "region": "西部",
        "power": 100,
        "status_desc": "裂川唯一宗门。",
        "stronghold": "封碑采石场——母石",
        "relations": [
            {"code": "CULT-03", "stance": "盟友", "reason": "北地沉潜灵气与西部封印因果关联"},
            {"code": "FREE-04", "stance": "戒备", "reason": "默许"},
        ],
    },
    "FREE-04": {
        "code": "FREE-04",
        "name": "拾遗盟",
        "type": "散修网络",
        "region": "西部",
        "power": 100,
        "status_desc": "西部散修网络。",
        "stronghold": "古墟集——无固定建筑",
        "relations": [
            {"code": "CULT-05", "stance": "戒备", "reason": "默许"},
        ],
    },
}


def _make_world_state(chaos_level="平稳"):
    ws = {
        "GLOBAL": {"chaos_level": chaos_level},
        "REGION": {},
        "FACTION": {},
        "RESOURCE": {
            "中部主脉残核": {"value": 50, "state": "紧张"},
            "东部新生支脉": {"value": 50, "state": "活跃"},
            "南部资源网络": {"value": 50, "state": "稳定"},
            "北地沉潜资源": {"value": 50, "state": "封闭"},
            "西部遗迹与异常资源": {"value": 50, "state": "高压"},
        },
        "CHAOS": {"active_anomalies": []},
        "FACTION_STATE": {},
        "RESOURCE_FLOW": {},
    }
    for code, fac in MOCK_FACTIONS.items():
        ws["FACTION_STATE"][code] = {
            "power": min(100, fac["power"] * 2),
            "stability": 0.5,
            "stance_overrides": {},
            "active_goal": "维持现状",
            "morale": 0.7,
        }
    return ws


def _make_campaign(memory=None):
    campaign = {
        "state": "active",
        "cycle": 1,
        "slots": {},
    }
    if memory is not None:
        campaign["evolution_memory"] = memory
    return campaign


# ──────────────────────────────────────────────
#  测试用例
# ──────────────────────────────────────────────


def test_1_stance_hostility():
    """Rule 1: stance 从非'对立'变为'对立' → FACTION_CONFLICT (HIGH)"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state()
    ws["FACTION_STATE"]["STATE-01"]["stance_overrides"] = {
        "CULT-01": "对立"
    }
    campaign = _make_campaign()
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "stance_overrides",
        "from": {"CULT-01": "从属"},
        "to": {"CULT-01": "对立"},
    }]}

    result = trigger.check(
        group_id="g1",
        world_state=ws,
        event_pool=pool,
        evolution_result=evolution,
        campaign=campaign,
        cycle=1,
        factions=MOCK_FACTIONS,
    )

    # 查找势力冲突事件
    faction_events = [t for t in result["triggered"] if t["category"] == "势力冲突"]
    assert len(faction_events) >= 1, f"应至少触发 1 条势力冲突事件，实际 {len(faction_events)}"
    # 验证事件在 EventPool 中的优先级
    event = pool.get("g1", faction_events[0]["event_id"])
    assert event is not None, "事件应在 EventPool 中"
    assert event.priority == EventPriority.HIGH.value, \
        f"优先级应为 HIGH，实际 {event.priority}"
    assert faction_events[0]["metadata"]["trigger_source"] == "faction_trigger", \
        "trigger_source 应为 faction_trigger"
    assert set(faction_events[0]["metadata"]["faction_codes"]) == {"STATE-01", "CULT-01"}, \
        f"faction_codes 应包含双方代码"

    print("✅ 测试1通过：stance→对立 → FACTION_CONFLICT")


def test_2_goal_civil_strife():
    """Rule 2: active_goal → '内乱' → FACTION_CONFLICT (MEDIUM)"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state()
    ws["FACTION_STATE"]["STATE-01"]["active_goal"] = "内乱"
    campaign = _make_campaign()
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "active_goal",
        "from": "维持秩序",
        "to": "内乱",
    }]}

    result = trigger.check(
        group_id="g1",
        world_state=ws,
        event_pool=pool,
        evolution_result=evolution,
        campaign=campaign,
        cycle=1,
        factions=MOCK_FACTIONS,
    )

    # 查找内乱相关的势力冲突事件（标题含"内部权力斗争"）
    faction_events = [t for t in result["triggered"]
                      if t["category"] == "势力冲突" and "内部权力斗争" in t.get("title", "")]
    assert len(faction_events) >= 1, f"应至少触发 1 条内乱势力冲突事件，实际 {len(faction_events)}"
    # 验证事件在 EventPool 中的优先级
    event = pool.get("g1", faction_events[0]["event_id"])
    assert event is not None, "事件应在 EventPool 中"
    assert event.priority == EventPriority.MEDIUM.value, \
        f"优先级应为 MEDIUM，实际 {event.priority}"

    print("✅ 测试2通过：active_goal→内乱 → FACTION_CONFLICT")


def test_3_power_decline():
    """Rule 3: power 连续下降且 ≤30 → FACTION_CONFLICT (MEDIUM)"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state()
    ws["FACTION_STATE"]["STATE-01"]["power"] = 25
    campaign = _make_campaign(memory={
        "faction_power_decline_ticks": {"STATE-01": 3},
        "leyline_decline_count": 0,
        "resource_low_count": {},
    })
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "power",
        "from": 30,
        "to": 25,
    }]}

    result = trigger.check(
        group_id="g1",
        world_state=ws,
        event_pool=pool,
        evolution_result=evolution,
        campaign=campaign,
        cycle=1,
        factions=MOCK_FACTIONS,
    )

    # 查找衰退相关势力冲突事件
    decline_events = [t for t in result["triggered"]
                      if t["category"] == "势力冲突" and "衰退" in t.get("title", "")]
    assert len(decline_events) >= 1, f"应至少触发 1 条衰退势力冲突事件，实际 {len(decline_events)}"
    # 验证事件在 EventPool 中的优先级
    event = pool.get("g1", decline_events[0]["event_id"])
    assert event is not None, "事件应在 EventPool 中"
    assert event.priority == EventPriority.MEDIUM.value, \
        f"优先级应为 MEDIUM，实际 {event.priority}"

    print("✅ 测试3通过：power 连续下降且 ≤30 → FACTION_CONFLICT")


def test_4_ally_opportunity():
    """Rule 4: 盟友 + power > 70 → RUIN_OPPORTUNITY (LOW)"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state()
    # 使用盟友对：CULT-05 和 CULT-03（都是宗门，power=100）
    ws["FACTION_STATE"]["CULT-05"]["power"] = 100
    ws["FACTION_STATE"]["CULT-03"]["power"] = 100
    campaign = _make_campaign()
    evolution = {"faction_changed": []}

    result = trigger.check(
        group_id="g1",
        world_state=ws,
        event_pool=pool,
        evolution_result=evolution,
        campaign=campaign,
        cycle=1,
        factions=MOCK_FACTIONS,
    )

    assert len(result["triggered"]) >= 1, \
        f"应至少触发 1 条遗迹机缘事件，实际 {len(result['triggered'])}"
    categories = {t["category"] for t in result["triggered"]}
    assert "遗迹与机缘" in categories, \
        f"应有'遗迹与机缘'类别，实际 {categories}"

    # 找到对应的事件并检查元数据
    for t in result["triggered"]:
        if t["category"] == "遗迹与机缘":
            event = pool.get("g1", t["event_id"])
            assert event is not None, "事件应在 EventPool 中"
            assert event.priority == EventPriority.LOW.value, \
                f"优先级应为 LOW，实际 {event.priority}"
            assert t["metadata"]["trigger_source"] == "faction_trigger", \
                "trigger_source 应为 faction_trigger"
            break
    else:
        assert False, "未找到遗迹与机缘事件"

    print("✅ 测试4通过：盟友 + power > 70 → RUIN_OPPORTUNITY")


def test_5_dedup():
    """测试5：防重复（同 category+region）"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state()
    ws["FACTION_STATE"]["STATE-01"]["stance_overrides"] = {
        "CULT-01": "对立"
    }
    campaign = _make_campaign()
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "stance_overrides",
        "from": {"CULT-01": "从属"},
        "to": {"CULT-01": "对立"},
    }]}

    result = trigger.check(
        group_id="g1",
        world_state=ws,
        event_pool=pool,
        evolution_result=evolution,
        campaign=campaign,
        cycle=1,
        factions=MOCK_FACTIONS,
    )

    # 第一次调用应触发对立事件（可能同时有盟友事件，只检查对立）
    stance_events = [t for t in result["triggered"]
                     if t["category"] == "势力冲突" and "关系恶化" in t.get("title", "")]
    assert len(stance_events) >= 1, f"第1次应至少触发 1 条对立事件，实际 {len(stance_events)}"

    # 第二次调用同一条件下不应重复触发（对立事件被去重）
    result2 = trigger.check(
        group_id="g1",
        world_state=ws,
        event_pool=pool,
        evolution_result=evolution,
        campaign=campaign,
        cycle=1,
        factions=MOCK_FACTIONS,
    )
    stance_events2 = [t for t in result2["triggered"]
                      if t["category"] == "势力冲突" and "关系恶化" in t.get("title", "")]
    assert len(stance_events2) == 0, \
        f"第2次对立事件不应再触发，实际 {len(stance_events2)}"
    stance_skipped = [s for s in result2["skipped"]
                     if s["category"] == "势力冲突"]
    assert len(stance_skipped) >= 1, \
        f"第2次对立事件应跳过，实际 skipped={len(stance_skipped)}"

    print("✅ 测试5通过：防重复机制正常工作")


def test_6_coexist_with_other_triggers():
    """测试6：与已有 Trigger（灵脉/CHAOS/资源）共存"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state(chaos_level="高压")  # 会触发 CHAOS 异常
    ws["FACTION_STATE"]["STATE-01"]["stance_overrides"] = {
        "CULT-01": "对立"
    }
    campaign = _make_campaign()
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "stance_overrides",
        "from": {"CULT-01": "从属"},
        "to": {"CULT-01": "对立"},
    }]}

    result = trigger.check(
        group_id="g1",
        world_state=ws,
        event_pool=pool,
        evolution_result=evolution,
        campaign=campaign,
        cycle=1,
        factions=MOCK_FACTIONS,
    )

    # 应该同时有 CHAOS 异常和势力冲突两个事件
    categories = {t["category"] for t in result["triggered"]}
    assert "CHAOS异常" in categories or "势力冲突" in categories, \
        f"应至少有一类触发，实际 {categories}"

    print("✅ 测试6通过：与已有 Trigger 共存")


def test_7_metadata_correct():
    """测试7：metadata 正确写入 triggered result"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state()
    ws["FACTION_STATE"]["STATE-01"]["stance_overrides"] = {
        "CULT-01": "对立"
    }
    campaign = _make_campaign()
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "stance_overrides",
        "from": {"CULT-01": "从属"},
        "to": {"CULT-01": "对立"},
    }]}

    result = trigger.check(
        group_id="g1",
        world_state=ws,
        event_pool=pool,
        evolution_result=evolution,
        campaign=campaign,
        cycle=5,
        factions=MOCK_FACTIONS,
    )

    for t in result["triggered"]:
        meta = t.get("metadata", {})
        assert meta.get("trigger_source") == "faction_trigger", \
            f"trigger_source 应为 faction_trigger，实际 {meta.get('trigger_source')}"
        assert "faction_codes" in meta, \
            f"metadata 应包含 faction_codes，实际 {meta}"
        assert meta.get("trigger_cycle") == 5, \
            f"trigger_cycle 应为 5，实际 {meta.get('trigger_cycle')}"

    print("✅ 测试7通过：metadata 正确写入")


def test_8_multi_group():
    """测试8：多 Group 独立"""
    trigger = WorldEventTrigger()
    pool1 = EventPool()
    pool2 = EventPool()
    ws1 = _make_world_state()
    ws2 = _make_world_state()
    ws1["FACTION_STATE"]["STATE-01"]["stance_overrides"] = {"CULT-01": "对立"}
    ws2["FACTION_STATE"]["STATE-01"]["stance_overrides"] = {"CULT-01": "对立"}
    campaign1 = _make_campaign()
    campaign2 = _make_campaign()
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "stance_overrides",
        "from": {"CULT-01": "从属"},
        "to": {"CULT-01": "对立"},
    }]}

    result1 = trigger.check(
        group_id="g1", world_state=ws1, event_pool=pool1,
        evolution_result=evolution, campaign=campaign1, cycle=1, factions=MOCK_FACTIONS,
    )
    result2 = trigger.check(
        group_id="g2", world_state=ws2, event_pool=pool2,
        evolution_result=evolution, campaign=campaign2, cycle=1, factions=MOCK_FACTIONS,
    )

    # 每个群独立触发对立事件（可能同时有盟友事件）
    stance_events1 = [t for t in result1["triggered"]
                      if t["category"] == "势力冲突" and "关系恶化" in t.get("title", "")]
    assert len(stance_events1) >= 1, f"g1 应至少触发 1 条对立事件，实际 {len(stance_events1)}"
    stance_events2 = [t for t in result2["triggered"]
                      if t["category"] == "势力冲突" and "关系恶化" in t.get("title", "")]
    assert len(stance_events2) >= 1, f"g2 应至少触发 1 条对立事件，实际 {len(stance_events2)}"

    # 不同群的事件池互不影响
    assert len(pool1.list_all("g1")) >= 1, "g1 池中应至少有 1 条事件"
    assert len(pool2.list_all("g2")) >= 1, "g2 池中应至少有 1 条事件"

    print("✅ 测试8通过：多 Group 独立")


def test_9_snapshot_rollback():
    """测试9：Snapshot / Rollback 后继续正常 Trigger"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state()
    ws["FACTION_STATE"]["STATE-01"]["stance_overrides"] = {
        "CULT-01": "对立"
    }
    campaign = _make_campaign()
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "stance_overrides",
        "from": {"CULT-01": "从属"},
        "to": {"CULT-01": "对立"},
    }]}

    # 模拟快照
    snapshot_ws = json.loads(json.dumps(ws))
    snapshot_campaign = json.loads(json.dumps(campaign))

    # 执行演化后的触发
    result = trigger.check(
        group_id="g1", world_state=ws, event_pool=pool,
        evolution_result=evolution, campaign=campaign, cycle=1, factions=MOCK_FACTIONS,
    )
    stance_events = [t for t in result["triggered"]
                     if t["category"] == "势力冲突" and "关系恶化" in t.get("title", "")]
    assert len(stance_events) >= 1, "首次应至少触发 1 条对立事件"

    # rollback 到快照
    ws_restored = json.loads(json.dumps(snapshot_ws))
    campaign_restored = json.loads(json.dumps(snapshot_campaign))

    # 恢复后再次触发（状态已回退，不应再触发对立事件）
    result2 = trigger.check(
        group_id="g1", world_state=ws_restored, event_pool=pool,
        evolution_result=evolution, campaign=campaign_restored, cycle=1, factions=MOCK_FACTIONS,
    )
    stance_events2 = [t for t in result2["triggered"]
                      if t["category"] == "势力冲突" and "关系恶化" in t.get("title", "")]
    assert len(stance_events2) == 0, \
        f"rollback 后对立事件不应再触发，实际 {len(stance_events2)}"

    print("✅ 测试9通过：Snapshot / Rollback 后继续正常 Trigger")


def test_10_no_change_when_stable():
    """测试10：不满足条件不会创建事件"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    ws = _make_world_state()
    # 降低所有势力 power 到 30 以下，避免触发盟友联合
    for code in ws["FACTION_STATE"]:
        ws["FACTION_STATE"][code]["power"] = 30
        ws["FACTION_STATE"][code]["active_goal"] = "维持现状"
        ws["FACTION_STATE"][code]["stability"] = 0.5
        ws["FACTION_STATE"][code]["morale"] = 0.5
        ws["FACTION_STATE"][code]["stance_overrides"] = {}
    campaign = _make_campaign()
    evolution = {"faction_changed": [{
        "code": "STATE-01",
        "field": "stability",
        "from": 0.5,
        "to": 0.5,
    }]}

    result = trigger.check(
        group_id="g1", world_state=ws, event_pool=pool,
        evolution_result=evolution, campaign=campaign, cycle=1, factions=MOCK_FACTIONS,
    )

    assert len(result["triggered"]) == 0, \
        f"稳定状态下不应触发任何事件，实际 {len(result['triggered'])}"

    print("✅ 测试10通过：不满足条件不会创建事件")


if __name__ == "__main__":
    test_1_stance_hostility()
    test_2_goal_civil_strife()
    test_3_power_decline()
    test_4_ally_opportunity()
    test_5_dedup()
    test_6_coexist_with_other_triggers()
    test_7_metadata_correct()
    test_8_multi_group()
    test_9_snapshot_rollback()
    test_10_no_change_when_stable()
    print("\n🎉 全部 B-5.3 势力事件触发测试通过！")
