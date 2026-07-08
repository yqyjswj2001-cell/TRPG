"""
test_b41_stability.py — B-4.1 稳定性修补专项测试

覆盖：
  1. 连续下降被中断时重置计数（48→47→48→47 不应触发）
  2. Rollback 恢复 evolution_memory（计数回退）
  3. 修复后原有触发仍正常工作

运行方式：
  python tools/test_b41_stability.py
"""

import sys
import json
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_event_pool import EventPool, EventCategory
from world_event_trigger import WorldEventTrigger


def make_campaign():
    return {
        "state": "active",
        "cycle": 1,
    }


def test_decline_interrupted_resets_count():
    """测试1：连续下降被中断时重置计数，不应触发事件。

    序列：50→49→48→48(不变,重置)→47→46→45
    最后连续只有2次下降(47→46→45)，不应触发。
    """
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g1"
    campaign = make_campaign()

    world_state = {
        "GLOBAL": {"leyline_flow_value": 50, "chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {},
    }

    # Tick 1: 50→49（下降，count=1）
    result1 = trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 50, "leyline_flow_to": 49,
    }, campaign, 1)
    assert len(result1["triggered"]) == 0

    # Tick 2: 49→48（下降，count=2）
    result2 = trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 49, "leyline_flow_to": 48,
    }, campaign, 2)
    assert len(result2["triggered"]) == 0

    # Tick 3: 48→48（不变，leyline_flow_changed=False → count 重置为 0）
    result3 = trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": False,
    }, campaign, 3)
    assert len(result3["triggered"]) == 0
    assert campaign["evolution_memory"]["leyline_decline_count"] == 0, \
        f"中断后计数应重置为0，实际={campaign['evolution_memory']['leyline_decline_count']}"

    # Tick 4: 48→47（下降，count=1）
    result4 = trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 48, "leyline_flow_to": 47,
    }, campaign, 4)
    assert len(result4["triggered"]) == 0

    # Tick 5: 47→46（下降，count=2）
    result5 = trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 47, "leyline_flow_to": 46,
    }, campaign, 5)
    assert len(result5["triggered"]) == 0, \
        f"连续下降仅2次，不应触发，但触发了{len(result5['triggered'])}条"

    print("✅ 测试1通过：连续下降被中断后重新计数，2次下降不触发")


def test_decline_three_consecutive_triggers():
    """测试1b：真正的连续3次下降仍能触发（确认修复没破坏正常路径）。"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g1b"
    campaign = make_campaign()

    world_state = {
        "GLOBAL": {"leyline_flow_value": 50, "chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {},
    }

    # 连续3次下降
    for i in range(3):
        result = trigger.check(group_id, world_state, pool, {
            "weather_changed": [], "region_changed": [], "resource_changed": [],
            "leyline_flow_changed": True,
            "leyline_flow_from": 50 - i,
            "leyline_flow_to": 50 - i - 1,
        }, campaign, i + 1)

    assert len(result["triggered"]) == 1
    assert result["triggered"][0]["category"] == "灵脉资源"

    print("✅ 测试1b通过：连续3次下降正常触发灵脉资源事件")


def test_rollback_restores_evolution_memory():
    """测试2：Rollback 恢复 evolution_memory。

    流程：
      1. Tick 后 decline_count=2
      2. 拍快照（含 campaign → 含 evolution_memory）
      3. 继续 Tick，decline_count=3（触发事件）
      4. Rollback 到快照
      5. 验证 decline_count 恢复到 2
      6. 再 Tick 1次后 decline_count=3，可再次触发
    """
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g2"
    campaign = make_campaign()

    world_state = {
        "GLOBAL": {"leyline_flow_value": 50, "chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {},
    }

    # Tick 1: 50→49（count=1）
    trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 50, "leyline_flow_to": 49,
    }, campaign, 1)

    # Tick 2: 49→48（count=2）
    trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 49, "leyline_flow_to": 48,
    }, campaign, 2)

    assert campaign["evolution_memory"]["leyline_decline_count"] == 2

    # 拍快照
    snapshot_campaign = json.loads(json.dumps(campaign))

    # Tick 3: 48→47（count=3，触发事件）
    result3 = trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 48, "leyline_flow_to": 47,
    }, campaign, 3)

    assert len(result3["triggered"]) == 1, "第3次下降应触发"
    assert campaign["evolution_memory"]["leyline_decline_count"] == 0, "触发后计数重置"

    # Rollback：从快照恢复 campaign
    campaign.clear()
    campaign.update(snapshot_campaign)

    # 验证 evolution_memory 恢复
    assert campaign["evolution_memory"]["leyline_decline_count"] == 2, \
        f"Rollback 后计数应恢复到2，实际={campaign['evolution_memory']['leyline_decline_count']}"

    # 再 Tick 1次：48→47（count=3，可再次触发）
    result4 = trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 48, "leyline_flow_to": 47,
    }, campaign, 4)

    # 注意：此时池中已有之前的灵脉资源事件（pool 未回滚），所以应被 skipped
    # 这是正确行为——rollback 只恢复了 campaign，没恢复 EventPool
    # 在真实系统中，main.py rollback 会同时恢复 EventPool
    # 此处我们验证的是 evolution_memory 恢复后的计数逻辑正确
    assert campaign["evolution_memory"]["leyline_decline_count"] == 3, \
        f"再1次下降后计数应为3，实际={campaign['evolution_memory']['leyline_decline_count']}"

    print("✅ 测试2通过：Rollback 恢复 evolution_memory，后续 Tick 行为正确")


def test_decline_rising_resets_count():
    """测试3：灵气上升时重置计数（补充覆盖）。"""
    trigger = WorldEventTrigger()
    pool = EventPool()
    group_id = "g3"
    campaign = make_campaign()

    world_state = {
        "GLOBAL": {"leyline_flow_value": 50, "chaos_level": "沉寂"},
        "weather": {},
        "RESOURCE": {},
    }

    # 2次下降
    for i in range(2):
        trigger.check(group_id, world_state, pool, {
            "weather_changed": [], "region_changed": [], "resource_changed": [],
            "leyline_flow_changed": True,
            "leyline_flow_from": 50 - i,
            "leyline_flow_to": 50 - i - 1,
        }, campaign, i + 1)

    assert campaign["evolution_memory"]["leyline_decline_count"] == 2

    # 灵气上升：48→49（重置）
    trigger.check(group_id, world_state, pool, {
        "weather_changed": [], "region_changed": [], "resource_changed": [],
        "leyline_flow_changed": True, "leyline_flow_from": 48, "leyline_flow_to": 49,
    }, campaign, 3)

    assert campaign["evolution_memory"]["leyline_decline_count"] == 0, \
        "灵气上升后计数应重置为0"

    print("✅ 测试3通过：灵气上升时重置计数")


if __name__ == "__main__":
    test_decline_interrupted_resets_count()
    test_decline_three_consecutive_triggers()
    test_rollback_restores_evolution_memory()
    test_decline_rising_resets_count()
    print("\n🎉 全部 B-4.1 稳定性修补测试通过！")
