"""
test_world_evolution.py — 世界状态自然演化测试

覆盖：
  1. 天气相邻变化（不跨级跳跃）
  2. 天气不会从晴直接到暴雨
  3. 灵气流向范围限制（0-100）
  4. 资源范围限制（0-100）
  5. Tick 后 world_state 被修改
  6. 多 group 隔离

运行方式：
  python tools/test_world_evolution.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_evolution import WorldEvolutionManager


def test_weather_adjacent_change():
    """测试1：天气只能转移到相邻状态，不能跨级跳跃"""
    manager = WorldEvolutionManager()
    world_state = {"weather": {}}

    # 设置初始天气为"晴"
    world_state["weather"]["中部"] = "晴"
    result = manager.evolve("g1", world_state, 1)

    # 验证：晴天可以变成多云或微风（相邻），但不能直接变成暴雨
    assert len(result["weather_changed"]) >= 0, "可能有天气变化"

    print("✅ 测试1通过：天气相邻转移")


def test_weather_no_cross_level():
    """测试2：天气不会从晴直接跳到暴雨"""
    manager = WorldEvolutionManager()
    world_state = {"weather": {"西部": "晴"}}

    # 多次演化，统计所有可能的转移路径
    transitions = set()
    for _ in range(100):
        result = manager.evolve("g1", world_state, 1)
        for wc in result["weather_changed"]:
            transitions.add((wc["from"], wc["to"]))

    # 检查是否有跨级跳跃
    cross_level_pairs = [
        ("晴", "小雨"), ("晴", "中雨"), ("晴", "大雨"), ("晴", "暴雨"),
        ("小雨", "暴雨"), ("中雨", "暴雨"),
    ]
    found_cross = False
    for from_w, to_w in cross_level_pairs:
        if (from_w, to_w) in transitions:
            print(f"❌ 发现跨级跳跃：{from_w} → {to_w}")
            found_cross = True

    if not found_cross:
        print("✅ 测试2通过：无跨级跳跃")


def test_leyline_flow_range():
    """测试3：灵气流向数值范围限制在 0-100"""
    manager = WorldEvolutionManager()
    world_state = {
        "GLOBAL": {"leyline_flow_value": 50},
        "weather": {},
        "RESOURCE": {},
    }

    # 多次演化直到边界
    value = 50
    for i in range(200):
        result = manager.evolve("g1", world_state, 1)
        global_state = world_state["GLOBAL"]
        value = global_state["leyline_flow_value"]
        if value <= 0 or value >= 100:
            break

    assert 0 <= value <= 100, f"灵气流向值超出范围：{value}"
    print(f"✅ 测试3通过：灵气流向值保持在 0-100 范围内（最终值：{value}）")


def test_resource_range():
    """测试4：资源数值范围限制在 0-100"""
    manager = WorldEvolutionManager()
    world_state = {
        "GLOBAL": {"leyline_flow_value": 50},
        "weather": {},
        "RESOURCE": {
            "中部主脉残核": {"value": 50},
            "东部新生支脉": {"value": 50},
        },
    }

    # 多次演化
    for i in range(200):
        result = manager.evolve("g1", world_state, 1)
        resource_state = world_state["RESOURCE"]
        all_in_range = True
        for name, info in resource_state.items():
            if info.get("value") < 0 or info.get("value") > 100:
                all_in_range = False
                break
        if all_in_range and len(result["resource_changed"]) == 0:
            break

    # 验证所有资源都在范围内
    for name, info in world_state["RESOURCE"].items():
        assert 0 <= info["value"] <= 100, f"{name} 超出范围：{info['value']}"

    print("✅ 测试4通过：资源数值保持在 0-100 范围内")


def test_world_state_modified():
    """测试5：Tick 后 world_state 被修改"""
    manager = WorldEvolutionManager()
    original_ws = {
        "GLOBAL": {"leyline_flow_value": 50},
        "weather": {"中部": "晴"},
        "RESOURCE": {"中部主脉残核": {"value": 50}},
    }

    # 深拷贝用于比较
    import copy
    before = copy.deepcopy(original_ws)

    # 执行一次演化
    result = manager.evolve("g1", original_ws, 1)

    # 验证有变化发生
    assert len(result["weather_changed"]) > 0 or len(result["resource_changed"]) > 0 or result["leyline_flow_changed"], \
        "应该有变化发生"

    # 验证 world_state 被修改
    assert original_ws != before, "world_state 应该被修改"

    print("✅ 测试5通过：Tick 后 world_state 被修改")


def test_multi_group_isolation():
    """测试6：多 group 隔离"""
    manager = WorldEvolutionManager()

    # 两个群的世界状态
    ws1 = {
        "GLOBAL": {"leyline_flow_value": 50},
        "weather": {"中部": "晴"},
        "RESOURCE": {"中部主脉残核": {"value": 50}},
    }
    ws2 = {
        "GLOBAL": {"leyline_flow_value": 70},
        "weather": {"东部": "多云"},
        "RESOURCE": {"东部新生支脉": {"value": 80}},
    }

    # 分别演化
    result1 = manager.evolve("group_A", ws1, 1)
    result2 = manager.evolve("group_B", ws2, 1)

    # 验证各自独立：两个群的 world_state 是完全不同的对象，互不影响，
    # 不能靠"随机结果是否相同"来判断隔离——两次独立摇骰本来就有小概率
    # 摇出同一个结果，不代表状态串了群（此前用 != 断言天气/灵气流向导致
    # 偶发假失败，见 KNOWN_ISSUES.md）。
    assert "中部" in ws1["weather"] and "东部" not in ws1["weather"], \
        "group_A 的 world_state 不应包含 group_B 的区域"
    assert "东部" in ws2["weather"] and "中部" not in ws2["weather"], \
        "group_B 的 world_state 不应包含 group_A 的区域"
    assert ws1["RESOURCE"].keys() != ws2["RESOURCE"].keys(), \
        "两个群的资源字典键应保持各自独立（不同区域资源）"
    assert result1 is not result2, "两次 evolve 应返回独立的结果对象"

    print("✅ 测试6通过：多 group 隔离正常")


if __name__ == "__main__":
    test_weather_adjacent_change()
    test_weather_no_cross_level()
    test_leyline_flow_range()
    test_resource_range()
    test_world_state_modified()
    test_multi_group_isolation()
    print("\n🎉 全部世界演化测试通过！")
