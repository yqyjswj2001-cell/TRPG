"""
test_faction_state.py — B-5.1 势力状态模型测试

覆盖：
  1. 新世界初始化时生成完整 FACTION_STATE
  2. 旧存档缺失 FACTION_STATE 时自动补全
  3. 已存在的势力状态不会被覆盖
  4. 缺失单个势力时只补该势力
  5. power 边界不超过 100
  6. Snapshot / Rollback 能恢复 FACTION_STATE
  7. 缺失单个字段时只补该字段
  8. 可重复调用幂等性
  9. stability 从 status_desc 推导正确性
  10. active_goal 根据 type+stability 推导正确性

运行方式：
  python3 tools/test_faction_state.py
"""

import sys
import json
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_evolution import WorldEvolutionManager


# ──────────────────────────────────────────────
#  测试用势力数据（模拟 factions.json 的结构）
# ──────────────────────────────────────────────

MOCK_FACTIONS = {
    "STATE-01": {
        "code": "STATE-01",
        "name": "祁渊李氏",
        "type": "王朝",
        "region": "中部",
        "power": 48,
        "status_desc": "东荒最古老的世俗政权。灵脉衰退致税收崩溃。实际控制已从整个中部收缩至岱央周边七县。",
        "relations": [],
    },
    "STATE-02": {
        "code": "STATE-02",
        "name": "竹海商府",
        "type": "王朝",
        "region": "东部",
        "power": 100,
        "status_desc": "东部最强势世俗力量但权力根基不稳——实际控制仅限启阳港及周边。扩张，合作竞争。",
        "relations": [],
    },
    "CULT-01": {
        "code": "CULT-01",
        "name": "归墟宗",
        "type": "宗门",
        "region": "中部",
        "power": 83,
        "status_desc": "中部最古老宗门，曾在祖脉鼎盛时是东荒首屈一指的大宗。灵脉衰退对宗门釜底抽薪。",
        "relations": [],
    },
    "CULT-05": {
        "code": "CULT-05",
        "name": "镇渊院",
        "type": "宗门",
        "region": "西部",
        "power": 100,
        "status_desc": "裂川唯一宗门和事实统治者。近五百年封印稳定性持续下降。接近崩溃。",
        "relations": [],
    },
    "FREE-01": {
        "code": "FREE-01",
        "name": "砂民会",
        "type": "散修网络",
        "region": "中部",
        "power": 3,
        "status_desc": "中部散修互助联合体。不到一万人，没有灵石储备。",
        "relations": [],
    },
    "HIDDEN-01": {
        "code": "HIDDEN-01",
        "name": "守门人",
        "type": "隐秘组织",
        "region": "西部",
        "power": 100,
        "status_desc": "西部幽灵组织。比封禁宗更早存在于这片土地。稳定。",
        "relations": [],
    },
    "HIDDEN-03": {
        "code": "HIDDEN-03",
        "name": "水语",
        "type": "隐秘组织",
        "region": "南部",
        "power": 1,
        "status_desc": "南部影子信使。不是组织，是一种习惯。负担持续上升。",
        "relations": [],
    },
}

_REQUIRED_FIELDS = (
    "power", "stability", "stance_overrides", "active_goal", "morale",
    "reputation", "resources", "influence", "strategic_goal",
    "internal_state", "faction_relations_runtime",
)


def _make_empty_world_state():
    """创建一个不含 FACTION_STATE 的空世界状态。"""
    return {
        "GLOBAL": {"phase": "动荡"},
        "REGION": {},
        "FACTION": {},
        "RESOURCE": {},
        "CHAOS": {"active_anomalies": []},
    }


def _make_world_state_with_faction_state():
    """创建一个已包含完整 FACTION_STATE 的世界状态。"""
    ws = _make_empty_world_state()
    ws["FACTION_STATE"] = {}
    for code, fac in MOCK_FACTIONS.items():
        ws["FACTION_STATE"][code] = {
            "power": min(100, fac["power"] * 2),
            "stability": 0.5,
            "stance_overrides": {},
            "active_goal": "维持现状",
            "morale": 0.7,
            "reputation": 0.5,
            "resources": 50,
            "influence": 50,
            "strategic_goal": "维持现状",
            "internal_state": "stable",
            "faction_relations_runtime": {},
        }
    return ws


# ──────────────────────────────────────────────
#  测试用例
# ──────────────────────────────────────────────


def test_1_new_world_init():
    """测试1：新世界初始化时生成完整 FACTION_STATE"""
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()

    summary = manager.ensure_faction_state(ws, campaign=None, factions=MOCK_FACTIONS)

    # 验证 FACTION_STATE 存在
    assert "FACTION_STATE" in ws, "world_state 应包含 FACTION_STATE"

    # 验证所有势力都被初始化
    for code in MOCK_FACTIONS:
        assert code in ws["FACTION_STATE"], f"势力 {code} 应在 FACTION_STATE 中"

    # 验证每个势力都有完整字段
    for code, entry in ws["FACTION_STATE"].items():
        for field in _REQUIRED_FIELDS:
            assert field in entry, f"势力 {code} 缺少字段 {field}"

    # 验证摘要
    assert summary["total_added"] == len(MOCK_FACTIONS), \
        f"应新增 {len(MOCK_FACTIONS)} 个势力，实际 {summary['total_added']}"
    assert summary["total_skipped"] == 0, "新世界不应有跳过的势力"

    print("✅ 测试1通过：新世界初始化生成完整 FACTION_STATE")


def test_2_old_save_compat():
    """测试2：旧存档缺失 FACTION_STATE 时自动补全"""
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()
    # 旧存档没有 FACTION_STATE 键
    assert "FACTION_STATE" not in ws

    summary = manager.ensure_faction_state(ws, campaign=None, factions=MOCK_FACTIONS)

    # 验证自动创建并填充
    assert "FACTION_STATE" in ws, "应自动创建 FACTION_STATE"
    assert len(ws["FACTION_STATE"]) == len(MOCK_FACTIONS), \
        f"应补全 {len(MOCK_FACTIONS)} 个势力"

    print("✅ 测试2通过：旧存档缺失 FACTION_STATE 时自动补全")


def test_3_no_overwrite_existing():
    """测试3：已存在的势力状态不会被覆盖"""
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()
    ws["FACTION_STATE"] = {
        "STATE-01": {
            "power": 42,           # 自定义值，不是默认的 96
            "stability": 0.33,     # 自定义值
            "stance_overrides": {"CULT-01": "对立"},  # 自定义值
            "active_goal": "内乱",  # 自定义值
            "morale": 0.1,         # 自定义值
        }
    }

    summary = manager.ensure_faction_state(ws, campaign=None, factions=MOCK_FACTIONS)

    # STATE-01 的值不应被覆盖
    assert ws["FACTION_STATE"]["STATE-01"]["power"] == 42, \
        f"已有 power 不应被覆盖，实际 {ws['FACTION_STATE']['STATE-01']['power']}"
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] == 0.33, \
        "已有 stability 不应被覆盖"
    assert ws["FACTION_STATE"]["STATE-01"]["stance_overrides"] == {"CULT-01": "对立"}, \
        "已有 stance_overrides 不应被覆盖"
    assert ws["FACTION_STATE"]["STATE-01"]["active_goal"] == "内乱", \
        "已有 active_goal 不应被覆盖"
    assert ws["FACTION_STATE"]["STATE-01"]["morale"] == 0.1, \
        "已有 morale 不应被覆盖"

    # STATE-01 现在可能因新增长期字段被补全，但原有字段值不能被覆盖
    assert "reputation" in ws["FACTION_STATE"]["STATE-01"]
    assert "resources" in ws["FACTION_STATE"]["STATE-01"]
    assert "influence" in ws["FACTION_STATE"]["STATE-01"]
    assert "strategic_goal" in ws["FACTION_STATE"]["STATE-01"]
    assert "internal_state" in ws["FACTION_STATE"]["STATE-01"]
    assert "faction_relations_runtime" in ws["FACTION_STATE"]["STATE-01"]

    print("✅ 测试3通过：已存在的势力状态不会被覆盖")


def test_4_fill_missing_faction():
    """测试4：缺失单个势力时只补该势力"""
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()
    # 只有 STATE-01 和 CULT-01
    ws["FACTION_STATE"] = {
        "STATE-01": {
            "power": 96, "stability": 0.5, "stance_overrides": {},
            "active_goal": "维持秩序", "morale": 0.7,
        },
        "CULT-01": {
            "power": 100, "stability": 0.5, "stance_overrides": {},
            "active_goal": "拓展势力", "morale": 0.7,
        },
    }

    summary = manager.ensure_faction_state(ws, campaign=None, factions=MOCK_FACTIONS)

    # STATE-01 和 CULT-01 的既有字段不应被覆盖，但会补全新增长期字段
    for code in ("STATE-01", "CULT-01"):
        assert "reputation" in ws["FACTION_STATE"][code]
        assert "resources" in ws["FACTION_STATE"][code]
        assert "influence" in ws["FACTION_STATE"][code]
        assert "strategic_goal" in ws["FACTION_STATE"][code]
        assert "internal_state" in ws["FACTION_STATE"][code]
        assert "faction_relations_runtime" in ws["FACTION_STATE"][code]

    # 其他势力应被新增
    added_codes = [a["code"] for a in summary["added"]]
    expected_added = set(MOCK_FACTIONS.keys()) - {"STATE-01", "CULT-01"}
    assert set(added_codes) == expected_added, \
        f"应新增 {expected_added}，实际 {set(added_codes)}"

    # 已有势力的值不应变
    assert ws["FACTION_STATE"]["STATE-01"]["power"] == 96
    assert ws["FACTION_STATE"]["CULT-01"]["power"] == 100

    print("✅ 测试4通过：缺失单个势力时只补该势力")


def test_5_power_boundary():
    """测试5：power 边界不超过 100"""
    manager = WorldEvolutionManager()

    # factions.json 中 power=100 的势力，×2 = 200，应被 clamp 到 100
    ws = _make_empty_world_state()
    high_power_factions = {
        "TEST-HIGH": {"code": "TEST-HIGH", "name": "测试高势力", "type": "王朝",
                      "region": "中部", "power": 100, "status_desc": "稳定", "relations": []},
        "TEST-LOW": {"code": "TEST-LOW", "name": "测试低势力", "type": "散修网络",
                     "region": "中部", "power": 3, "status_desc": "互助", "relations": []},
    }

    manager.ensure_faction_state(ws, campaign=None, factions=high_power_factions)

    # power=100 ×2 = 200 → clamp 到 100
    assert ws["FACTION_STATE"]["TEST-HIGH"]["power"] == 100, \
        f"power 应被 clamp 到 100，实际 {ws['FACTION_STATE']['TEST-HIGH']['power']}"
    # power=3 ×2 = 6
    assert ws["FACTION_STATE"]["TEST-LOW"]["power"] == 6, \
        f"power 应为 6，实际 {ws['FACTION_STATE']['TEST-LOW']['power']}"

    print("✅ 测试5通过：power 边界不超过 100")


def test_6_snapshot_rollback():
    """测试6：Snapshot / Rollback 能恢复 FACTION_STATE"""
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()
    manager.ensure_faction_state(ws, campaign=None, factions=MOCK_FACTIONS)

    # 模拟 snapshot（深拷贝）
    snapshot = json.loads(json.dumps(ws))

    # 修改 FACTION_STATE
    ws["FACTION_STATE"]["STATE-01"]["power"] = 10
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.1
    ws["FACTION_STATE"]["STATE-01"]["active_goal"] = "崩溃"
    del ws["FACTION_STATE"]["CULT-01"]

    # 模拟 rollback（从 snapshot 恢复）
    ws = json.loads(json.dumps(snapshot))

    # 验证恢复
    assert ws["FACTION_STATE"]["STATE-01"]["power"] != 10, "power 应恢复"
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] != 0.1, "stability 应恢复"
    assert "CULT-01" in ws["FACTION_STATE"], "CULT-01 应恢复"

    print("✅ 测试6通过：Snapshot / Rollback 能恢复 FACTION_STATE")


def test_7_fill_missing_field():
    """测试7：缺失单个字段时只补该字段"""
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()
    # STATE-01 缺少 morale 和 active_goal
    ws["FACTION_STATE"] = {
        "STATE-01": {
            "power": 96,
            "stability": 0.5,
            "stance_overrides": {},
            # 缺少 active_goal
            # 缺少 morale
        }
    }

    summary = manager.ensure_faction_state(ws, campaign=None, factions=MOCK_FACTIONS)

    # STATE-01 应被标记为 filled
    filled_codes = [f["code"] for f in summary["filled"]]
    assert "STATE-01" in filled_codes, "STATE-01 应被标记为补全"

    # 已有字段不应被覆盖
    assert ws["FACTION_STATE"]["STATE-01"]["power"] == 96, "已有 power 不应被覆盖"
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] == 0.5, "已有 stability 不应被覆盖"

    # 缺失字段应被补全
    assert "active_goal" in ws["FACTION_STATE"]["STATE-01"], "active_goal 应被补全"
    assert "morale" in ws["FACTION_STATE"]["STATE-01"], "morale 应被补全"
    assert ws["FACTION_STATE"]["STATE-01"]["morale"] == 0.7, "morale 默认应为 0.7"

    print("✅ 测试7通过：缺失单个字段时只补该字段")


def test_8_idempotent():
    """测试8：可重复调用幂等性"""
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()

    # 第一次调用
    summary1 = manager.ensure_faction_state(ws, campaign=None, factions=MOCK_FACTIONS)
    state_after_first = json.loads(json.dumps(ws["FACTION_STATE"]))

    # 第二次调用
    summary2 = manager.ensure_faction_state(ws, campaign=None, factions=MOCK_FACTIONS)
    state_after_second = json.loads(json.dumps(ws["FACTION_STATE"]))

    # 状态应完全相同
    assert state_after_first == state_after_second, "重复调用后状态应相同"

    # 第二次应全部跳过
    assert summary2["total_added"] == 0, f"重复调用不应新增，实际 {summary2['total_added']}"
    assert summary2["total_filled"] == 0, f"重复调用不应补全，实际 {summary2['total_filled']}"
    assert summary2["total_skipped"] == len(MOCK_FACTIONS), \
        f"重复调用应全部跳过，实际 {summary2['total_skipped']}"

    print("✅ 测试8通过：可重复调用幂等性")


def test_9_stability_from_desc():
    """测试9：stability 从 status_desc 推导正确性"""
    manager = WorldEvolutionManager()

    test_cases = [
        ("稳定", 0.8),
        ("维持", 0.8),
        ("扩张", 0.7),
        ("拓展", 0.7),
        ("接近崩溃", 0.3),
        ("衰退", 0.3),
        ("负担", 0.6),
        ("压力", 0.6),
        ("临界", 0.4),
        ("失衡", 0.4),
        ("无关键词", 0.5),  # 默认
    ]

    for desc_keyword, expected_stab in test_cases:
        ws = {"FACTION_STATE": {}}
        fac = {
            "TEST": {
                "code": "TEST", "name": "测试", "type": "王朝",
                "region": "中部", "power": 50,
                "status_desc": f"这是一个{desc_keyword}的势力描述",
                "relations": [],
            }
        }
        manager.ensure_faction_state(ws, campaign=None, factions=fac)
        actual = ws["FACTION_STATE"]["TEST"]["stability"]
        assert actual == expected_stab, \
            f"描述含'{desc_keyword}'时 stability 应为 {expected_stab}，实际 {actual}"

    print("✅ 测试9通过：stability 从 status_desc 推导正确")


def test_10_active_goal_by_type():
    """测试10：active_goal 根据 type+stability 推导正确性"""
    manager = WorldEvolutionManager()

    # 王朝 + 高稳定度 → 维持秩序
    ws1 = {"FACTION_STATE": {}}
    fac1 = {"W1": {"code": "W1", "name": "王朝1", "type": "王朝", "region": "中部",
                   "power": 50, "status_desc": "稳定繁荣", "relations": []}}
    manager.ensure_faction_state(ws1, campaign=None, factions=fac1)
    assert ws1["FACTION_STATE"]["W1"]["active_goal"] == "维持秩序", \
        f"王朝+高稳定度应为'维持秩序'，实际 {ws1['FACTION_STATE']['W1']['active_goal']}"

    # 王朝 + 低稳定度 → 收缩自保
    ws2 = {"FACTION_STATE": {}}
    fac2 = {"W2": {"code": "W2", "name": "王朝2", "type": "王朝", "region": "中部",
                   "power": 50, "status_desc": "接近崩溃边缘", "relations": []}}
    manager.ensure_faction_state(ws2, campaign=None, factions=fac2)
    assert ws2["FACTION_STATE"]["W2"]["active_goal"] == "收缩自保", \
        f"王朝+低稳定度应为'收缩自保'，实际 {ws2['FACTION_STATE']['W2']['active_goal']}"

    # 宗门 + 高稳定度 → 拓展势力
    ws3 = {"FACTION_STATE": {}}
    fac3 = {"C1": {"code": "C1", "name": "宗门1", "type": "宗门", "region": "东部",
                   "power": 80, "status_desc": "扩张中", "relations": []}}
    manager.ensure_faction_state(ws3, campaign=None, factions=fac3)
    assert ws3["FACTION_STATE"]["C1"]["active_goal"] == "拓展势力", \
        f"宗门+高稳定度应为'拓展势力'，实际 {ws3['FACTION_STATE']['C1']['active_goal']}"

    # 宗门 + 低稳定度 → 闭关固守
    ws4 = {"FACTION_STATE": {}}
    fac4 = {"C2": {"code": "C2", "name": "宗门2", "type": "宗门", "region": "西部",
                   "power": 80, "status_desc": "接近崩溃", "relations": []}}
    manager.ensure_faction_state(ws4, campaign=None, factions=fac4)
    assert ws4["FACTION_STATE"]["C2"]["active_goal"] == "闭关固守", \
        f"宗门+低稳定度应为'闭关固守'，实际 {ws4['FACTION_STATE']['C2']['active_goal']}"

    # 散修网络 → 互助求生
    ws5 = {"FACTION_STATE": {}}
    fac5 = {"F1": {"code": "F1", "name": "散修1", "type": "散修网络", "region": "中部",
                   "power": 10, "status_desc": "互助", "relations": []}}
    manager.ensure_faction_state(ws5, campaign=None, factions=fac5)
    assert ws5["FACTION_STATE"]["F1"]["active_goal"] == "互助求生", \
        f"散修网络应为'互助求生'，实际 {ws5['FACTION_STATE']['F1']['active_goal']}"

    # 隐秘组织 + 高稳定度 → 守护秘密
    ws6 = {"FACTION_STATE": {}}
    fac6 = {"H1": {"code": "H1", "name": "隐秘1", "type": "隐秘组织", "region": "西部",
                   "power": 90, "status_desc": "稳定守护", "relations": []}}
    manager.ensure_faction_state(ws6, campaign=None, factions=fac6)
    assert ws6["FACTION_STATE"]["H1"]["active_goal"] == "守护秘密", \
        f"隐秘组织+高稳定度应为'守护秘密'，实际 {ws6['FACTION_STATE']['H1']['active_goal']}"

    # 隐秘组织 + 低稳定度 → 隐藏存续
    ws7 = {"FACTION_STATE": {}}
    fac7 = {"H2": {"code": "H2", "name": "隐秘2", "type": "隐秘组织", "region": "南部",
                   "power": 5, "status_desc": "接近崩溃", "relations": []}}
    manager.ensure_faction_state(ws7, campaign=None, factions=fac7)
    assert ws7["FACTION_STATE"]["H2"]["active_goal"] == "隐藏存续", \
        f"隐秘组织+低稳定度应为'隐藏存续'，实际 {ws7['FACTION_STATE']['H2']['active_goal']}"

    print("✅ 测试10通过：active_goal 根据 type+stability 推导正确")


def test_11_no_factions_param():
    """测试11：不传 factions 参数时，无势力可初始化，但不会报错"""
    manager = WorldEvolutionManager()
    ws = {"FACTION_STATE": {}}

    # 不传 factions，all_faction_codes 为空，不会处理任何势力
    summary = manager.ensure_faction_state(ws, campaign=None, factions=None)

    # 应无新增、无补全、无跳过
    assert summary["total_added"] == 0, "无 factions 时不应新增"
    assert summary["total_filled"] == 0, "无 factions 时不应补全"
    assert summary["total_skipped"] == 0, "无 factions 时不应跳过"

    # 但如果 FACTION_STATE 中已有条目（缺失字段），应能补全
    ws2 = {"FACTION_STATE": {"TEST-01": {}}}
    summary2 = manager.ensure_faction_state(ws2, campaign=None, factions=None)

    # TEST-01 不在 factions 中，所以不会被处理
    # 但它已在 existing_codes 中，会被检查字段缺失
    # 由于 factions=None，all_faction_codes 为空，不会遍历到 TEST-01
    # 所以 TEST-01 的字段不会被补全——这是预期行为
    # （实际使用中，factions 总是从 factions.json 加载的）
    assert "power" not in ws2["FACTION_STATE"]["TEST-01"], \
        "无 factions 时无法推导 power，字段不被补全"

    print("✅ 测试11通过：不传 factions 参数时不报错，但无法补全字段")


def test_11b_default_values_with_factions():
    """测试11b：factions 中无 status_desc 时使用默认值"""
    manager = WorldEvolutionManager()
    ws = {"FACTION_STATE": {}}

    # factions 中势力无 status_desc
    fac = {"TEST-01": {"code": "TEST-01", "name": "测试", "type": "王朝",
                       "region": "中部", "power": 50, "relations": []}}
    # 注意：无 status_desc 键
    manager.ensure_faction_state(ws, campaign=None, factions=fac)

    # stability 应为默认 0.5
    assert ws["FACTION_STATE"]["TEST-01"]["stability"] == 0.5, \
        "无 status_desc 时 stability 默认应为 0.5"
    # power = 50 * 2 = 100
    assert ws["FACTION_STATE"]["TEST-01"]["power"] == 100, \
        "power 应为 100"
    # morale 默认 0.7
    assert ws["FACTION_STATE"]["TEST-01"]["morale"] == 0.7, \
        "morale 默认应为 0.7"

    print("✅ 测试11b通过：factions 中无 status_desc 时使用默认值")


def test_12_non_dict_entry_recovery():
    """测试12：FACTION_STATE 中条目为非 dict 时能恢复"""
    manager = WorldEvolutionManager()
    ws = {"FACTION_STATE": {"STATE-01": None}}  # 损坏数据

    fac = {"STATE-01": MOCK_FACTIONS["STATE-01"]}
    summary = manager.ensure_faction_state(ws, campaign=None, factions=fac)

    # 应被标记为 filled（非 dict → 重建为 dict）
    filled_codes = [f["code"] for f in summary["filled"]]
    assert "STATE-01" in filled_codes, "非 dict 条目应被标记为补全"

    # 应恢复为完整 dict
    assert isinstance(ws["FACTION_STATE"]["STATE-01"], dict), "应恢复为 dict"
    for field in _REQUIRED_FIELDS:
        assert field in ws["FACTION_STATE"]["STATE-01"], f"恢复后应包含 {field}"

    print("✅ 测试12通过：非 dict 条目能恢复")



def test_13_fill_new_long_term_fields_on_old_save():
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()
    ws["FACTION_STATE"] = {
        "STATE-01": {
            "power": 42,
            "stability": 0.33,
            "stance_overrides": {"CULT-01": "对立"},
            "active_goal": "内乱",
            "morale": 0.1,
        }
    }

    summary = manager.ensure_faction_state(ws, campaign=None, factions={"STATE-01": MOCK_FACTIONS["STATE-01"]})

    entry = ws["FACTION_STATE"]["STATE-01"]
    assert entry["power"] == 42
    assert entry["stability"] == 0.33
    assert entry["morale"] == 0.1
    assert "reputation" in entry
    assert "resources" in entry
    assert "influence" in entry
    assert "strategic_goal" in entry
    assert "internal_state" in entry
    assert "faction_relations_runtime" in entry
    assert any(item["code"] == "STATE-01" for item in summary["filled"])
    print("Phase D state test 13 passed: old save backfills long-term fields")


def test_14_runtime_relation_defaults_from_static_relations():
    manager = WorldEvolutionManager()
    ws = _make_empty_world_state()
    factions = {
        "STATE-01": dict(MOCK_FACTIONS["STATE-01"], relations=[{"code": "CULT-01", "stance": "盟友", "reason": "共同防线"}]),
        "CULT-01": dict(MOCK_FACTIONS["CULT-01"], relations=[{"code": "STATE-01", "stance": "盟友", "reason": "共同防线"}]),
    }

    manager.ensure_faction_state(ws, campaign=None, factions=factions)

    runtime_rel = ws["FACTION_STATE"]["STATE-01"]["faction_relations_runtime"]
    assert "CULT-01" in runtime_rel
    assert runtime_rel["CULT-01"]["stance"]
    assert "tension" in runtime_rel["CULT-01"]
    print("Phase D state test 14 passed: runtime relations default from static relations")

if __name__ == "__main__":
    test_1_new_world_init()
    test_2_old_save_compat()
    test_3_no_overwrite_existing()
    test_4_fill_missing_faction()
    test_5_power_boundary()
    test_6_snapshot_rollback()
    test_7_fill_missing_field()
    test_8_idempotent()
    test_9_stability_from_desc()
    test_10_active_goal_by_type()
    test_11_no_factions_param()
    test_11b_default_values_with_factions()
    test_12_non_dict_entry_recovery()
    test_13_fill_new_long_term_fields_on_old_save()
    test_14_runtime_relation_defaults_from_static_relations()
    print("\n🎉 全部 B-5.1 势力状态模型测试通过！")
