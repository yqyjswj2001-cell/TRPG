"""
test_world_event_trigger.py — 世界变化 → 事件触发测试

覆盖：
  1. 灵气连续下降触发事件
  2. CHAOS 超阈值触发事件
  3. 资源不足触发事件
  4. 已存在事件不会重复创建
  5. 正常环境不会触发
  6. 多 group 隔离

运行方式：
  python tools/test_world_event_trigger.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_event_pool import EventPool, EventCategory
from world_event_trigger import WorldEventTrigger


def make_campaign():
    return {
        "state": "active",
        "cycle": 1,
    }


def test_leyline_decline_triggers_event():
    """测试1：灵气连续下降 3 次 → 触发灵脉资源事件"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g1"
    campaign = make_campaign()

    world_state = {
        "GLOBAL": {"leyline_flow_value": 50, "chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {},
    }

    # 模拟 3 次灵气下降
    for i in range(3):
        evolution_result = {
            "weather_changed": [],
            "region_changed": [],
            "resource_changed": [],
            "leyline_flow_changed": True,
            "leyline_flow_from": 50 - i,
            "leyline_flow_to": 50 - i - 1,
        }
        result = trigger.check(group_id, world_state, pool, evolution_result, campaign, 1)

    # 应该触发了 1 条灵脉资源事件
    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["category"] == "灵脉资源"
    assert result["triggered"][0]["title"] == "灵脉流向异常"

    # 确认事件已在池中
    events = pool.query_by_category(group_id, "灵脉资源")
    assert len(events) == 1

    print("✅ 测试1通过：灵气连续下降触发灵脉资源事件")


def test_chaos_threshold_triggers_event():
    """测试2：CHAOS 活跃度超阈值 → 触发 CHAOS 异常事件"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g2"
    campaign = make_campaign()

    world_state = {
        "GLOBAL": {"chaos_level": "活跃"},
        "weather": {},
        "RESOURCE": {},
    }

    evolution_result = {
        "weather_changed": [],
        "region_changed": [],
        "resource_changed": [],
        "leyline_flow_changed": False,
    }

    result = trigger.check(group_id, world_state, pool, evolution_result, campaign, 1)

    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["category"] == "CHAOS异常"
    assert result["triggered"][0]["title"] == "CHAOS活跃度异常升高"

    # 确认事件已在池中
    events = pool.query_by_category(group_id, "CHAOS异常")
    assert len(events) == 1

    print("✅ 测试2通过：CHAOS 超阈值触发 CHAOS 异常事件")


def test_resource_low_triggers_event():
    """测试3：资源值连续低值 → 触发灵脉资源/日常事件"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g3"
    campaign = make_campaign()

    world_state = {
        "GLOBAL": {"chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {
            "中部主脉残核": {"value": 15},  # 低于阈值 20
        },
    }

    evolution_result = {
        "weather_changed": [],
        "region_changed": [],
        "resource_changed": [],
        "leyline_flow_changed": False,
    }

    # 第一次：计数 1
    result1 = trigger.check(group_id, world_state, pool, evolution_result, campaign, 1)
    assert len(result1["triggered"]) == 0, "第一次不应触发"

    # 第二次：计数 2 → 达到阈值
    result2 = trigger.check(group_id, world_state, pool, evolution_result, campaign, 2)
    assert len(result2["triggered"]) == 1
    assert result2["triggered"][0]["category"] in ("灵脉资源", "日常")

    print("✅ 测试3通过：资源低值触发事件")


def test_no_duplicate_events():
    """测试4：已有同类别事件时不会重复创建"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g4"
    campaign = make_campaign()

    # 手动添加一条灵脉资源事件
    pool.add(
        group_id=group_id,
        title="已有灵脉事件",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="",
    )

    world_state = {
        "GLOBAL": {"leyline_flow_value": 50, "chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {},
    }

    # 模拟 3 次灵气下降
    for i in range(3):
        evolution_result = {
            "weather_changed": [],
            "region_changed": [],
            "resource_changed": [],
            "leyline_flow_changed": True,
            "leyline_flow_from": 50 - i,
            "leyline_flow_to": 50 - i - 1,
        }
        result = trigger.check(group_id, world_state, pool, evolution_result, campaign, 1)

    # 应该跳过（已有同类别事件）
    assert len(result["triggered"]) == 0
    assert len(result["skipped"]) >= 1
    assert result["skipped"][0]["reason"] == "已有同类别活跃事件"

    print("✅ 测试4通过：已有同类别事件时不会重复创建")


def test_normal_no_trigger():
    """测试5：正常环境不会触发事件"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g5"
    campaign = make_campaign()

    world_state = {
        "GLOBAL": {"leyline_flow_value": 50, "chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {
            "中部主脉残核": {"value": 60},  # 正常值
        },
    }

    evolution_result = {
        "weather_changed": [],
        "region_changed": [],
        "resource_changed": [],
        "leyline_flow_changed": True,
        "leyline_flow_from": 50,
        "leyline_flow_to": 51,  # 灵气上升，不触发
    }

    result = trigger.check(group_id, world_state, pool, evolution_result, campaign, 1)

    assert len(result["triggered"]) == 0
    assert len(result["skipped"]) == 0

    print("✅ 测试5通过：正常环境不会触发事件")


def test_multi_group_isolation():
    """测试6：多 group 隔离"""
    trigger = WorldEventTrigger()
    pool = EventPool()

    g1, g2 = "group_A", "group_B"
    c1, c2 = make_campaign(), make_campaign()

    # 群A：CHAOS 活跃
    ws1 = {
        "GLOBAL": {"chaos_level": "活跃"},
        "weather": {},
        "RESOURCE": {},
    }
    # 群B：正常
    ws2 = {
        "GLOBAL": {"chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {"中部主脉残核": {"value": 60}},
    }

    evo = {
        "weather_changed": [],
        "region_changed": [],
        "resource_changed": [],
        "leyline_flow_changed": False,
    }

    r1 = trigger.check(g1, ws1, pool, evo, c1, 1)
    r2 = trigger.check(g2, ws2, pool, evo, c2, 1)

    # 群A 触发 CHAOS 事件
    assert len(r1["triggered"]) == 1
    assert r1["triggered"][0]["category"] == "CHAOS异常"

    # 群B 不触发
    assert len(r2["triggered"]) == 0

    # 群A 有事件，群B 没有
    assert len(pool.list_all(g1)) == 1
    assert len(pool.list_all(g2)) == 0

    print("✅ 测试6通过：多 group 隔离正常")


if __name__ == "__main__":
    test_leyline_decline_triggers_event()
    test_chaos_threshold_triggers_event()
    test_resource_low_triggers_event()
    test_no_duplicate_events()
    test_normal_no_trigger()
    test_multi_group_isolation()
    print("\n🎉 全部 World Event Trigger 测试通过！")
