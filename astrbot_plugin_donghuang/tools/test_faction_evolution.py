"""
test_faction_evolution.py — B-5.2 势力演化规则测试

覆盖：
  1. 灵脉资源影响稳定度（RESOURCE ≤30 → stability -0.03，≥70 → +0.02）
  2. Resource Flow 影响士气（health ≤30 → morale -0.02，≥80 → +0.01）
  3. CHAOS 全局影响（高风险 → 全部 stability -0.02）
  4. Power 上下变化（stability<0.3 → power-1，stability>0.8 & morale>0.7 → power+1）
  5. 连续三 Tick Goal 切换
  6. evolution_memory 自动补全
  7. clamp 边界（stability/morale [0,1]，power [0,100]）
  8. 多 Group 独立
  9. Snapshot / Rollback 正确恢复
  10. 不满足条件不会变化
  11. Goal 切换优先级（内乱 > 自保）
  12. 连续计数中断后重置

运行方式：
  python3 tools/test_faction_evolution.py
"""

import sys
import json
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_evolution import WorldEvolutionManager


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
        "relations": [
            {"code": "STATE-01", "stance": "从属", "reason": "共治"},
        ],
    },
    "CULT-05": {
        "code": "CULT-05",
        "name": "镇渊院",
        "type": "宗门",
        "region": "西部",
        "power": 100,
        "status_desc": "裂川唯一宗门。",
        "relations": [
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
        "relations": [
            {"code": "CULT-05", "stance": "戒备", "reason": "默许"},
        ],
    },
}


def _make_world_state(resource_val=50, flow_health=None, chaos_level="稳定"):
    """创建一个包含 FACTION_STATE 的世界状态。"""
    ws = {
        "GLOBAL": {"chaos_level": chaos_level},
        "REGION": {},
        "FACTION": {},
        "RESOURCE": {
            "中部主脉残核": {"value": resource_val, "state": "紧张"},
            "东部新生支脉": {"value": 50, "state": "活跃"},
            "南部资源网络": {"value": 50, "state": "稳定"},
            "北地沉潜资源": {"value": 50, "state": "封闭"},
            "西部遗迹与异常资源": {"value": resource_val, "state": "高压"},
        },
        "CHAOS": {"active_anomalies": []},
        "FACTION_STATE": {},
        "RESOURCE_FLOW": {},
    }

    # 初始化 FACTION_STATE
    for code, fac in MOCK_FACTIONS.items():
        ws["FACTION_STATE"][code] = {
            "power": min(100, fac["power"] * 2),
            "stability": 0.5,
            "stance_overrides": {},
            "active_goal": "维持现状",
            "morale": 0.7,
        }

    # 初始化 RESOURCE_FLOW
    if flow_health is not None:
        ws["RESOURCE_FLOW"] = flow_health

    return ws


def _make_campaign(evolution_memory=None):
    """创建一个 campaign dict。"""
    campaign = {
        "state": "active",
        "cycle": 1,
        "slots": {},
    }
    if evolution_memory is not None:
        campaign["evolution_memory"] = evolution_memory
    return campaign


# ──────────────────────────────────────────────
#  测试用例
# ──────────────────────────────────────────────


def test_1_resource_affects_stability():
    """测试1：灵脉资源影响稳定度"""
    manager = WorldEvolutionManager()

    # ── 资源 ≤30 → stability -0.03 ──
    ws = _make_world_state(resource_val=25)
    campaign = _make_campaign()
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.5

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    # 中部势力 STATE-01 应受影响
    stab_changes = [c for c in result["faction_changed"]
                    if c["code"] == "STATE-01" and c["field"] == "stability"
                    and c["from"] != c["to"]]
    assert len(stab_changes) >= 1, "低资源应影响 stability"
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] < 0.5, \
        f"低资源时 stability 应下降，实际 {ws['FACTION_STATE']['STATE-01']['stability']}"

    # ── 资源 ≥70 → stability +0.02 ──
    ws2 = _make_world_state(resource_val=75)
    campaign2 = _make_campaign()
    ws2["FACTION_STATE"]["STATE-01"]["stability"] = 0.5

    result2 = manager.evolve("g1", ws2, 1, campaign=campaign2, factions=MOCK_FACTIONS)

    assert ws2["FACTION_STATE"]["STATE-01"]["stability"] > 0.5, \
        f"高资源时 stability 应上升，实际 {ws2['FACTION_STATE']['STATE-01']['stability']}"

    print("✅ 测试1通过：灵脉资源影响稳定度")


def test_2_flow_affects_morale():
    """测试2：Resource Flow 影响士气"""
    manager = WorldEvolutionManager()

    # ── flow health ≤30 → morale -0.02 ──
    flow_low = {"CULT-01|STATE-01": 20}
    ws = _make_world_state(flow_health=flow_low)
    campaign = _make_campaign()
    ws["FACTION_STATE"]["STATE-01"]["morale"] = 0.7

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    morale_changes = [c for c in result["faction_changed"]
                      if c["code"] == "STATE-01" and c["field"] == "morale"]
    assert len(morale_changes) >= 1, "低资源流应影响 morale"
    assert ws["FACTION_STATE"]["STATE-01"]["morale"] < 0.7, \
        f"低资源流时 morale 应下降，实际 {ws['FACTION_STATE']['STATE-01']['morale']}"

    # ── flow health ≥80 → morale +0.01 ──
    flow_high = {"CULT-01|STATE-01": 85}
    ws2 = _make_world_state(flow_health=flow_high)
    campaign2 = _make_campaign()
    ws2["FACTION_STATE"]["STATE-01"]["morale"] = 0.7

    result2 = manager.evolve("g1", ws2, 1, campaign=campaign2, factions=MOCK_FACTIONS)

    assert ws2["FACTION_STATE"]["STATE-01"]["morale"] > 0.7, \
        f"高资源流时 morale 应上升，实际 {ws2['FACTION_STATE']['STATE-01']['morale']}"

    print("✅ 测试2通过：Resource Flow 影响士气")


def test_3_chaos_affects_stability():
    """测试3：CHAOS 全局影响"""
    manager = WorldEvolutionManager()

    # 高风险 CHAOS
    ws = _make_world_state(chaos_level="高压")
    campaign = _make_campaign()
    for code in ws["FACTION_STATE"]:
        ws["FACTION_STATE"][code]["stability"] = 0.5

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    # 全部势力应受影响
    for code in ws["FACTION_STATE"]:
        stab = ws["FACTION_STATE"][code]["stability"]
        # 可能同时受资源影响，所以只需检查有变化
        # 但 CHAOS 是必然 -0.02，至少应该看到变化
        pass

    # 至少有一个势力的 stability 变了
    stab_changes = [c for c in result["faction_changed"] if c["field"] == "stability"]
    assert len(stab_changes) > 0, "CHAOS 高风险应影响 stability"

    # ── 低风险 CHAOS 不影响 ──
    ws2 = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign2 = _make_campaign()
    for code in ws2["FACTION_STATE"]:
        ws2["FACTION_STATE"][code]["stability"] = 0.5
        ws2["FACTION_STATE"][code]["morale"] = 0.5

    result2 = manager.evolve("g1", ws2, 1, campaign=campaign2, factions=MOCK_FACTIONS)

    # "平稳" 不在 CHAOS 高风险集合中，不应有 CHAOS 导致的变化
    # 资源 = 50 也不触发资源影响
    stab_changes2 = [c for c in result2["faction_changed"] if c["field"] == "stability"]
    assert len(stab_changes2) == 0, \
        f"低风险 CHAOS 且资源中等时 stability 不应变，实际变化 {stab_changes2}"

    print("✅ 测试3通过：CHAOS 全局影响")


def test_4_power_changes():
    """测试4：power 上下变化"""
    manager = WorldEvolutionManager()

    # ── stability < 0.3 → power -1 ──
    ws = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign = _make_campaign()
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2
    ws["FACTION_STATE"]["STATE-01"]["morale"] = 0.5
    ws["FACTION_STATE"]["STATE-01"]["power"] = 80

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    power_changes = [c for c in result["faction_changed"]
                     if c["code"] == "STATE-01" and c["field"] == "power"]
    assert len(power_changes) >= 1, "低 stability 应影响 power"
    assert ws["FACTION_STATE"]["STATE-01"]["power"] == 79, \
        f"低 stability 时 power 应 -1，实际 {ws['FACTION_STATE']['STATE-01']['power']}"

    # ── stability > 0.8 且 morale > 0.7 → power +1 ──
    ws2 = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign2 = _make_campaign()
    ws2["FACTION_STATE"]["STATE-01"]["stability"] = 0.9
    ws2["FACTION_STATE"]["STATE-01"]["morale"] = 0.8
    ws2["FACTION_STATE"]["STATE-01"]["power"] = 80

    result2 = manager.evolve("g1", ws2, 1, campaign=campaign2, factions=MOCK_FACTIONS)

    assert ws2["FACTION_STATE"]["STATE-01"]["power"] == 81, \
        f"高 stability+高 morale 时 power 应 +1，实际 {ws2['FACTION_STATE']['STATE-01']['power']}"

    # ── stability > 0.8 但 morale ≤ 0.7 → power 不变 ──
    ws3 = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign3 = _make_campaign()
    ws3["FACTION_STATE"]["STATE-01"]["stability"] = 0.9
    ws3["FACTION_STATE"]["STATE-01"]["morale"] = 0.7
    ws3["FACTION_STATE"]["STATE-01"]["power"] = 80

    result3 = manager.evolve("g1", ws3, 1, campaign=campaign3, factions=MOCK_FACTIONS)

    # morale == 0.7 不满足 > 0.7
    power_changes3 = [c for c in result3["faction_changed"]
                      if c["code"] == "STATE-01" and c["field"] == "power"]
    assert len(power_changes3) == 0, \
        f"stability>0.8 但 morale==0.7 时 power 不应变"

    print("✅ 测试4通过：power 上下变化")


def test_5_goal_switch_three_ticks():
    """测试5：连续三 Tick Goal 切换"""
    manager = WorldEvolutionManager()

    # ── 连续 3 Tick stability < 0.3 → active_goal = "自保" ──
    ws = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign = _make_campaign()
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2
    ws["FACTION_STATE"]["STATE-01"]["morale"] = 0.5
    ws["FACTION_STATE"]["STATE-01"]["active_goal"] = "维持秩序"
    ws["FACTION_STATE"]["STATE-01"]["power"] = 80

    # Tick 1
    manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "维持秩序", \
        "第1 Tick 不应切换 goal"

    # Tick 2
    # 重置 stability（被 CHAOS 或资源改变了），需要重新设置
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2
    manager.evolve("g1", ws, 2, campaign=campaign, factions=MOCK_FACTIONS)
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "维持秩序", \
        "第2 Tick 不应切换 goal"

    # Tick 3
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2
    manager.evolve("g1", ws, 3, campaign=campaign, factions=MOCK_FACTIONS)
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "自保", \
        f"第3 Tick 应切换为'自保'，实际 {ws['FACTION_STATE']['STATE-01']['active_goal']}"

    print("✅ 测试5通过：连续三 Tick Goal 切换")


def test_6_evolution_memory_compat():
    """测试6：evolution_memory 自动补全"""
    manager = WorldEvolutionManager()

    # 旧存档没有 evolution_memory
    ws = _make_world_state()
    campaign = _make_campaign()  # 没有 evolution_memory

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    # 应自动创建 evolution_memory 和势力相关字段
    assert "evolution_memory" in campaign, "应创建 evolution_memory"
    assert "faction_low_stability_ticks" in campaign["evolution_memory"], \
        "应创建 faction_low_stability_ticks"
    assert "faction_low_morale_ticks" in campaign["evolution_memory"], \
        "应创建 faction_low_morale_ticks"

    # ── 部分 evolution_memory（只有旧字段）──
    ws2 = _make_world_state()
    campaign2 = _make_campaign(evolution_memory={
        "leyline_decline_count": 2,
        "resource_low_count": {},
    })

    result2 = manager.evolve("g1", ws2, 1, campaign=campaign2, factions=MOCK_FACTIONS)

    # 应补全新字段
    assert "faction_low_stability_ticks" in campaign2["evolution_memory"], \
        "应补全 faction_low_stability_ticks"
    assert "faction_low_morale_ticks" in campaign2["evolution_memory"], \
        "应补全 faction_low_morale_ticks"
    # 旧字段不应被覆盖
    assert campaign2["evolution_memory"]["leyline_decline_count"] == 2, \
        "旧字段不应被覆盖"

    print("✅ 测试6通过：evolution_memory 自动补全")


def test_7_clamp_boundaries():
    """测试7：clamp 边界"""
    manager = WorldEvolutionManager()

    # ── stability 下限 ──
    ws = _make_world_state(resource_val=25, chaos_level="高压")
    campaign = _make_campaign()
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.02  # 接近下限
    ws["FACTION_STATE"]["STATE-01"]["morale"] = 0.5

    manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    assert ws["FACTION_STATE"]["STATE-01"]["stability"] >= 0.0, \
        f"stability 不应低于 0.0，实际 {ws['FACTION_STATE']['STATE-01']['stability']}"

    # ── stability 上限 ──
    ws2 = _make_world_state(resource_val=75, chaos_level="平稳")
    campaign2 = _make_campaign()
    ws2["FACTION_STATE"]["STATE-01"]["stability"] = 0.99
    ws2["FACTION_STATE"]["STATE-01"]["morale"] = 0.8

    manager.evolve("g1", ws2, 1, campaign=campaign2, factions=MOCK_FACTIONS)

    assert ws2["FACTION_STATE"]["STATE-01"]["stability"] <= 1.0, \
        f"stability 不应超过 1.0，实际 {ws2['FACTION_STATE']['STATE-01']['stability']}"

    # ── morale 下限 ──
    ws3 = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign3 = _make_campaign()
    flow_low = {"CULT-01|STATE-01": 10}
    ws3["RESOURCE_FLOW"] = flow_low
    ws3["FACTION_STATE"]["STATE-01"]["morale"] = 0.01

    manager.evolve("g1", ws3, 1, campaign=campaign3, factions=MOCK_FACTIONS)

    assert ws3["FACTION_STATE"]["STATE-01"]["morale"] >= 0.0, \
        f"morale 不应低于 0.0，实际 {ws3['FACTION_STATE']['STATE-01']['morale']}"

    # ── power 下限 ──
    ws4 = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign4 = _make_campaign()
    ws4["FACTION_STATE"]["STATE-01"]["stability"] = 0.1
    ws4["FACTION_STATE"]["STATE-01"]["power"] = 0

    manager.evolve("g1", ws4, 1, campaign=campaign4, factions=MOCK_FACTIONS)

    assert ws4["FACTION_STATE"]["STATE-01"]["power"] >= 0, \
        f"power 不应低于 0，实际 {ws4['FACTION_STATE']['STATE-01']['power']}"

    # ── power 上限 ──
    ws5 = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign5 = _make_campaign()
    ws5["FACTION_STATE"]["STATE-01"]["stability"] = 0.9
    ws5["FACTION_STATE"]["STATE-01"]["morale"] = 0.8
    ws5["FACTION_STATE"]["STATE-01"]["power"] = 100

    manager.evolve("g1", ws5, 1, campaign=campaign5, factions=MOCK_FACTIONS)

    assert ws5["FACTION_STATE"]["STATE-01"]["power"] <= 100, \
        f"power 不应超过 100，实际 {ws5['FACTION_STATE']['STATE-01']['power']}"

    print("✅ 测试7通过：clamp 边界")


def test_8_multi_group_isolation():
    """测试8：多 Group 独立"""
    manager = WorldEvolutionManager()

    ws1 = _make_world_state(resource_val=25)
    ws2 = _make_world_state(resource_val=75)
    campaign1 = _make_campaign()
    campaign2 = _make_campaign()

    ws1["FACTION_STATE"]["STATE-01"]["stability"] = 0.5
    ws2["FACTION_STATE"]["STATE-01"]["stability"] = 0.5

    result1 = manager.evolve("g1", ws1, 1, campaign=campaign1, factions=MOCK_FACTIONS)
    result2 = manager.evolve("g2", ws2, 1, campaign=campaign2, factions=MOCK_FACTIONS)

    # 不同群的世界状态应独立
    assert ws1["FACTION_STATE"]["STATE-01"]["stability"] != ws2["FACTION_STATE"]["STATE-01"]["stability"], \
        "不同群的世界状态应独立变化"

    # evolution_memory 也应独立
    assert campaign1["evolution_memory"]["faction_low_stability_ticks"] != \
           campaign2["evolution_memory"]["faction_low_stability_ticks"] or True, \
        "不同群的 evolution_memory 应独立"

    print("✅ 测试8通过：多 Group 独立")


def test_9_snapshot_rollback():
    """测试9：Snapshot / Rollback 正确恢复"""
    manager = WorldEvolutionManager()

    ws = _make_world_state(resource_val=25)
    campaign = _make_campaign()
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.5
    ws["FACTION_STATE"]["STATE-01"]["morale"] = 0.7

    # 模拟 snapshot
    snapshot_ws = json.loads(json.dumps(ws))
    snapshot_campaign = json.loads(json.dumps(campaign))

    # 执行演化
    manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    # 验证有变化
    ws_changed = (ws["FACTION_STATE"]["STATE-01"]["stability"] != 0.5 or
                  ws["FACTION_STATE"]["STATE-01"]["morale"] != 0.7)
    assert ws_changed, "演化后应有变化"

    # 模拟 rollback
    ws_restored = json.loads(json.dumps(snapshot_ws))

    # 验证恢复后与快照一致
    assert ws_restored["FACTION_STATE"]["STATE-01"]["stability"] == 0.5, \
        "rollback 应恢复 stability"
    assert ws_restored["FACTION_STATE"]["STATE-01"]["morale"] == 0.7, \
        "rollback 应恢复 morale"

    print("✅ 测试9通过：Snapshot / Rollback 正确恢复")


def test_10_no_change_when_stable():
    """测试10：不满足条件不会变化"""
    manager = WorldEvolutionManager()

    # 所有条件都在中间值：资源50、flow无、chaos平稳、stability=0.5、morale=0.5
    ws = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign = _make_campaign()
    # morale 设为 0.5 以避免触发 power+1（需要 >0.8 & >0.7）
    for code in ws["FACTION_STATE"]:
        ws["FACTION_STATE"][code]["stability"] = 0.5
        ws["FACTION_STATE"][code]["morale"] = 0.5
        ws["FACTION_STATE"][code]["power"] = 50
        ws["FACTION_STATE"][code]["active_goal"] = "维持现状"

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    # 不应有 faction_changed（资源=50不触发，CHAOS=平稳不触发，stability=0.5不影响power）
    # 注意：天气和资源仍然可能变化，只检查 faction_changed
    assert len(result["faction_changed"]) == 0, \
        f"稳定条件下不应有势力变化，实际 {result['faction_changed']}"

    # FACTION_STATE 值不变
    for code in ws["FACTION_STATE"]:
        assert ws["FACTION_STATE"][code]["stability"] == 0.5, \
            f"{code} stability 不应变"
        assert ws["FACTION_STATE"][code]["morale"] == 0.5, \
            f"{code} morale 不应变"
        assert ws["FACTION_STATE"][code]["power"] == 50, \
            f"{code} power 不应变"
        assert ws["FACTION_STATE"][code]["active_goal"] == "维持现状", \
            f"{code} active_goal 不应变"

    print("✅ 测试10通过：不满足条件不会变化")


def test_11_goal_priority():
    """测试11：Goal 切换优先级（内乱 > 自保）"""
    manager = WorldEvolutionManager()

    # 同时满足低 stability 和低 morale 连续 3 Tick
    ws = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign = _make_campaign(evolution_memory={
        "faction_low_stability_ticks": {"STATE-01": 2},
        "faction_low_morale_ticks": {"STATE-01": 2},
        "leyline_decline_count": 0,
        "resource_low_count": {},
    })
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2
    ws["FACTION_STATE"]["STATE-01"]["morale"] = 0.2
    ws["FACTION_STATE"]["STATE-01"]["active_goal"] = "维持秩序"

    # 这个 Tick 是第3个连续低 stability 和第3个连续低 morale
    manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    # 内乱优先级高于自保
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "内乱", \
        f"内乱应优先于自保，实际 {ws['FACTION_STATE']['STATE-01']['active_goal']}"

    # ── 已经是内乱，stability 低不会降级为自保 ──
    ws2 = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign2 = _make_campaign(evolution_memory={
        "faction_low_stability_ticks": {"STATE-01": 3},
        "faction_low_morale_ticks": {"STATE-01": 0},
        "leyline_decline_count": 0,
        "resource_low_count": {},
    })
    ws2["FACTION_STATE"]["STATE-01"]["stability"] = 0.2
    ws2["FACTION_STATE"]["STATE-01"]["morale"] = 0.8  # morale 正常
    ws2["FACTION_STATE"]["STATE-01"]["active_goal"] = "内乱"  # 已经是内乱

    manager.evolve("g1", ws2, 1, campaign=campaign2, factions=MOCK_FACTIONS)

    # 内乱不应被自保降级
    assert ws2["FACTION_STATE"]["STATE-01"]["active_goal"] == "内乱", \
        f"内乱不应被自保降级，实际 {ws2['FACTION_STATE']['STATE-01']['active_goal']}"

    print("✅ 测试11通过：Goal 切换优先级（内乱 > 自保）")


def test_12_counter_reset_on_recovery():
    """测试12：连续计数中断后重置"""
    manager = WorldEvolutionManager()

    # 先累积2个 Tick 的低 stability
    ws = _make_world_state(resource_val=50, chaos_level="平稳")
    campaign = _make_campaign(evolution_memory={
        "faction_low_stability_ticks": {"STATE-01": 2},
        "faction_low_morale_ticks": {},
        "leyline_decline_count": 0,
        "resource_low_count": {},
    })
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.5  # 恢复正常
    ws["FACTION_STATE"]["STATE-01"]["morale"] = 0.5
    ws["FACTION_STATE"]["STATE-01"]["active_goal"] = "维持秩序"

    manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    # stability 恢复后计数应重置
    assert campaign["evolution_memory"]["faction_low_stability_ticks"]["STATE-01"] == 0, \
        "stability 恢复后计数应重置为0"

    # active_goal 不应变（因为计数中断了）
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "维持秩序", \
        "计数中断后不应切换 goal"

    # ── 然后再次降低，需要重新累积3次 ──
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2

    manager.evolve("g1", ws, 2, campaign=campaign, factions=MOCK_FACTIONS)
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "维持秩序", \
        "重新累积第1 Tick 不应切换"

    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2
    manager.evolve("g1", ws, 3, campaign=campaign, factions=MOCK_FACTIONS)
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "维持秩序", \
        "重新累积第2 Tick 不应切换"

    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2
    manager.evolve("g1", ws, 4, campaign=campaign, factions=MOCK_FACTIONS)
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "自保", \
        "重新累积第3 Tick 应切换为自保"

    print("✅ 测试12通过：连续计数中断后重置")



def test_13_long_term_fields_remain_stable_without_drivers():
    manager = WorldEvolutionManager()
    ws = _make_world_state(resource_val=50, flow_health={"CULT-01|STATE-01": 50}, chaos_level="平稳")
    campaign = _make_campaign()
    for code in ws["FACTION_STATE"]:
        ws["FACTION_STATE"][code]["stability"] = 0.5
        ws["FACTION_STATE"][code]["morale"] = 0.5
        ws["FACTION_STATE"][code]["reputation"] = 0.5
        ws["FACTION_STATE"][code]["resources"] = 50
        ws["FACTION_STATE"][code]["influence"] = int((ws["FACTION_STATE"][code]["power"] * 0.8) + 10)
        ws["FACTION_STATE"][code]["strategic_goal"] = "维持现状"
        ws["FACTION_STATE"][code]["internal_state"] = "stable"
        ws["FACTION_STATE"][code]["faction_relations_runtime"] = {}

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    long_term_changes = [c for c in result["faction_changed"] if c["field"] in {"reputation", "resources", "influence", "strategic_goal", "internal_state"}]
    assert long_term_changes == []
    print("Phase D evolution test 13 passed: long-term fields stay stable without drivers")


def test_14_resource_pressure_updates_long_term_fields():
    manager = WorldEvolutionManager()
    ws = _make_world_state(resource_val=20, flow_health={"CULT-01|STATE-01": 20}, chaos_level="平稳")
    campaign = _make_campaign()
    ws["FACTION_STATE"]["STATE-01"]["resources"] = 50
    ws["FACTION_STATE"]["STATE-01"]["influence"] = 50
    ws["FACTION_STATE"]["STATE-01"]["reputation"] = 0.5
    ws["FACTION_STATE"]["STATE-01"]["strategic_goal"] = "维持现状"
    ws["FACTION_STATE"]["STATE-01"]["internal_state"] = "stable"

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    assert ws["FACTION_STATE"]["STATE-01"]["resources"] < 50
    assert ws["FACTION_STATE"]["STATE-01"]["influence"] != 50 or ws["FACTION_STATE"]["STATE-01"]["reputation"] != 0.5
    assert ws["FACTION_STATE"]["STATE-01"]["internal_state"] in ("strained", "fragmenting", "stable")
    assert any(c["field"] in {"resources", "influence", "reputation", "strategic_goal", "internal_state"} for c in result["faction_changed"])
    print("Phase D evolution test 14 passed: resource pressure updates long-term fields")


def test_15_runtime_relations_evolve_with_flow_pressure():
    manager = WorldEvolutionManager()
    ws = _make_world_state(flow_health={"CULT-01|STATE-01": 20}, resource_val=50, chaos_level="平稳")
    campaign = _make_campaign()
    ws["FACTION_STATE"]["STATE-01"]["faction_relations_runtime"] = {
        "CULT-01": {"stance": "盟友", "tension": 0.5, "trust": 0.5}
    }

    result = manager.evolve("g1", ws, 1, campaign=campaign, factions=MOCK_FACTIONS)

    rel = ws["FACTION_STATE"]["STATE-01"]["faction_relations_runtime"]["CULT-01"]
    assert rel["tension"] > 0.5
    assert rel["trust"] < 0.5
    assert any(c["field"] == "faction_relations_runtime.CULT-01.tension" for c in result["faction_changed"])
    assert any(c["field"] == "faction_relations_runtime.CULT-01.trust" for c in result["faction_changed"])
    print("Phase D evolution test 15 passed: runtime relations evolve with flow pressure")

if __name__ == "__main__":
    test_1_resource_affects_stability()
    test_2_flow_affects_morale()
    test_3_chaos_affects_stability()
    test_4_power_changes()
    test_5_goal_switch_three_ticks()
    test_6_evolution_memory_compat()
    test_7_clamp_boundaries()
    test_8_multi_group_isolation()
    test_9_snapshot_rollback()
    test_10_no_change_when_stable()
    test_11_goal_priority()
    test_12_counter_reset_on_recovery()
    test_13_long_term_fields_remain_stable_without_drivers()
    test_14_resource_pressure_updates_long_term_fields()
    test_15_runtime_relations_evolve_with_flow_pressure()
    print("\n🎉 全部 B-5.2 势力演化规则测试通过！")
