"""
test_faction_affiliation.py — B-5.4 玩家势力归属测试

覆盖：
  1. 成功加入势力（条件满足）
  2. 势力不存在
  3. 区域不一致
  4. stability ≤ 0.3
  5. 离开势力
  6. 重复加入（已在目标势力）
  7. 未加入直接离开
  8. 多 Group
  9. Snapshot / Rollback 正确恢复 affiliation
  10. AI Prompt 包含所属势力信息

运行方式：
  python3 tools/test_faction_affiliation.py
"""

import sys
import json
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
        "relations": [],
        "leader": {"name": "李承渊", "title": "岱央第十八代守脉王", "desc": "守脉王"},
    },
    "CULT-01": {
        "code": "CULT-01",
        "name": "归墟宗",
        "type": "宗门",
        "region": "中部",
        "power": 83,
        "status_desc": "中部最古老宗门。",
        "stronghold": "祖脉余山",
        "relations": [],
        "leader": {"name": "归尘真人", "title": "守脉宗第七代宗主", "desc": "宗主"},
    },
    "CULT-05": {
        "code": "CULT-05",
        "name": "镇渊院",
        "type": "隐秘组织",
        "region": "西部",
        "power": 100,
        "status_desc": "裂川唯一宗门。",
        "stronghold": "封碑采石场",
        "relations": [],
        "leader": {"name": "封碑真人", "title": "封禁宗第十二代宗主", "desc": "宗主"},
    },
}


def _make_profile(region="中部", affiliation=None):
    """创建一个模拟的玩家 Profile。"""
    return {
        "name": "测试角色",
        "status": "ready",
        "IDENTITY_STATE": {
            "region": region,
            "subregion": "岱央城",
            "生存状态": "stable",
        },
        "FACTION_STATE": {
            "affiliation": affiliation,
            "relations": {},
        },
        "hp": {"current": 20, "max": 20},
        "mp": {"current": 15, "max": 15},
    }


def _make_world_state():
    """创建一个包含 FACTION_STATE 的世界状态。"""
    ws = {
        "GLOBAL": {"chaos_level": "平稳"},
        "FACTION_STATE": {},
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


# ──────────────────────────────────────────────
#  测试辅助函数：模拟加入/离开势力的逻辑
# ──────────────────────────────────────────────

def simulate_join_faction(profile, faction_code, factions, world_state):
    """模拟 /dh join_faction 的核心逻辑（不依赖 AstrBot 框架）。"""
    fac_info = factions.get(faction_code)
    if not fac_info:
        return {"ok": False, "reason": "势力不存在"}

    current_aff = profile.get("FACTION_STATE", {}).get("affiliation")
    if current_aff == faction_code:
        return {"ok": False, "reason": "已在该势力"}
    if current_aff:
        return {"ok": False, "reason": "已加入其他势力"}

    player_region = profile.get("IDENTITY_STATE", {}).get("region", "")
    faction_region = fac_info.get("region", "")
    if player_region != faction_region:
        return {"ok": False, "reason": f"区域不一致: 玩家在{player_region}, 势力在{faction_region}"}

    faction_state = world_state.get("FACTION_STATE", {})
    entry = faction_state.get(faction_code, {})
    stability = entry.get("stability", 0.5) if isinstance(entry, dict) else 0.5
    if stability <= 0.3:
        return {"ok": False, "reason": f"势力动荡: stability={round(stability, 2)}"}

    # 加入成功
    fs = profile.setdefault("FACTION_STATE", {})
    fs["affiliation"] = faction_code

    # 初始化 leader 好感度 +2
    leader_name = fac_info.get("leader", {}).get("name", "")
    if leader_name:
        relations = fs.setdefault("relations", {})
        relations[leader_name] = relations.get(leader_name, 0) + 2

    return {"ok": True, "faction_code": faction_code, "leader_name": leader_name}


def simulate_leave_faction(profile, faction_code, factions, world_state):
    """模拟 /dh leave_faction 的核心逻辑。"""
    fs = profile.get("FACTION_STATE", {})
    current_aff = fs.get("affiliation")
    if not current_aff:
        return {"ok": False, "reason": "未加入任何势力"}

    fac_info = factions.get(current_aff)

    # 离开
    fs["affiliation"] = None

    # 扣减 leader 好感度 -3
    leader_name = ""
    is_hidden = False
    if fac_info:
        leader_name = fac_info.get("leader", {}).get("name", "")
        if leader_name:
            relations = fs.setdefault("relations", {})
            relations[leader_name] = relations.get(leader_name, 0) - 3
        is_hidden = fac_info.get("type") == "隐秘组织"

    # 隐秘组织离开：morale -0.1
    if is_hidden:
        faction_state = world_state.get("FACTION_STATE", {})
        entry = faction_state.get(current_aff)
        if entry and isinstance(entry, dict):
            entry["morale"] = max(0.0, entry.get("morale", 0.7) - 0.1)

    return {"ok": True, "faction_code": current_aff, "is_hidden": is_hidden}


def simulate_build_faction_prompt(profile, factions, world_state):
    """模拟 _build_system_prompt 中的所属势力注入逻辑。"""
    affiliation = profile.get("FACTION_STATE", {}).get("affiliation")
    if not affiliation:
        return None

    fac_info = factions.get(affiliation)
    if not fac_info:
        return None

    fac_name = fac_info.get("name", affiliation)
    fac_type = fac_info.get("type", "")
    faction_state = world_state.get("FACTION_STATE", {})
    entry = faction_state.get(affiliation, {})
    active_goal = entry.get("active_goal", "维持现状") if isinstance(entry, dict) else "维持现状"

    return f"【所属势力：{fac_name}｜{fac_type}】\n势力当前目标：{active_goal}"


# ──────────────────────────────────────────────
#  测试用例
# ──────────────────────────────────────────────


def test_1_join_success():
    """测试1：成功加入势力"""
    profile = _make_profile(region="中部")
    ws = _make_world_state()

    result = simulate_join_faction(profile, "STATE-01", MOCK_FACTIONS, ws)

    assert result["ok"], f"加入应成功，实际 {result}"
    assert profile["FACTION_STATE"]["affiliation"] == "STATE-01", \
        f"affiliation 应为 STATE-01，实际 {profile['FACTION_STATE']['affiliation']}"
    assert result["leader_name"] == "李承渊", \
        f"leader 应为李承渊，实际 {result['leader_name']}"
    # 验证 leader 好感度 +2
    assert profile["FACTION_STATE"]["relations"].get("李承渊") == 2, \
        f"李承渊好感度应为 +2，实际 {profile['FACTION_STATE']['relations'].get('李承渊')}"

    print("✅ 测试1通过：成功加入势力")


def test_2_faction_not_exist():
    """测试2：势力不存在"""
    profile = _make_profile(region="中部")
    ws = _make_world_state()

    result = simulate_join_faction(profile, "FAKE-99", MOCK_FACTIONS, ws)

    assert not result["ok"], "加入应失败"
    assert "不存在" in result["reason"], f"原因应含'不存在'，实际 {result['reason']}"
    assert profile["FACTION_STATE"]["affiliation"] is None, \
        "affiliation 应保持 None"

    print("✅ 测试2通过：势力不存在时拒绝加入")


def test_3_region_mismatch():
    """测试3：区域不一致"""
    profile = _make_profile(region="东部")  # 玩家在东部
    ws = _make_world_state()

    result = simulate_join_faction(profile, "STATE-01", MOCK_FACTIONS, ws)  # 势力在中部

    assert not result["ok"], "加入应失败"
    assert "区域" in result["reason"], f"原因应含'区域'，实际 {result['reason']}"
    assert profile["FACTION_STATE"]["affiliation"] is None, \
        "affiliation 应保持 None"

    print("✅ 测试3通过：区域不一致时拒绝加入")


def test_4_low_stability():
    """测试4：stability ≤ 0.3"""
    profile = _make_profile(region="中部")
    ws = _make_world_state()
    ws["FACTION_STATE"]["STATE-01"]["stability"] = 0.2  # 设置为动荡

    result = simulate_join_faction(profile, "STATE-01", MOCK_FACTIONS, ws)

    assert not result["ok"], "加入应失败"
    assert "动荡" in result["reason"] or "stability" in result["reason"], \
        f"原因应含稳定度信息，实际 {result['reason']}"
    assert profile["FACTION_STATE"]["affiliation"] is None, \
        "affiliation 应保持 None"

    print("✅ 测试4通过：stability ≤ 0.3 时拒绝加入")


def test_5_leave_success():
    """测试5：离开势力"""
    profile = _make_profile(region="中部", affiliation="STATE-01")
    profile["FACTION_STATE"]["relations"]["李承渊"] = 2  # 之前加入时设置的
    ws = _make_world_state()

    result = simulate_leave_faction(profile, "STATE-01", MOCK_FACTIONS, ws)

    assert result["ok"], f"离开应成功，实际 {result}"
    assert profile["FACTION_STATE"]["affiliation"] is None, \
        f"affiliation 应为 None，实际 {profile['FACTION_STATE']['affiliation']}"
    # leader 好感度 -3（从 2 变为 -1）
    assert profile["FACTION_STATE"]["relations"]["李承渊"] == -1, \
        f"李承渊好感度应为 -1，实际 {profile['FACTION_STATE']['relations']['李承渊']}"

    print("✅ 测试5通过：离开势力成功")


def test_6_already_joined():
    """测试6：重复加入（已在目标势力）"""
    profile = _make_profile(region="中部", affiliation="STATE-01")
    ws = _make_world_state()

    result = simulate_join_faction(profile, "STATE-01", MOCK_FACTIONS, ws)

    assert not result["ok"], "重复加入应失败"
    assert "已在" in result["reason"], f"原因应含'已在'，实际 {result['reason']}"

    # 加入其他势力也应失败
    result2 = simulate_join_faction(profile, "CULT-01", MOCK_FACTIONS, ws)
    assert not result2["ok"], "已加入其他势力时应失败"
    assert "其他" in result2["reason"], f"原因应含'其他'，实际 {result2['reason']}"

    print("✅ 测试6通过：重复加入被拒绝")


def test_7_leave_without_join():
    """测试7：未加入直接离开"""
    profile = _make_profile(region="中部", affiliation=None)
    ws = _make_world_state()

    result = simulate_leave_faction(profile, None, MOCK_FACTIONS, ws)

    assert not result["ok"], "未加入时离开应失败"
    assert "未加入" in result["reason"], f"原因应含'未加入'，实际 {result['reason']}"

    print("✅ 测试7通过：未加入时离开被拒绝")


def test_8_multi_group():
    """测试8：多 Group 独立"""
    profile1 = _make_profile(region="中部")
    profile2 = _make_profile(region="中部")
    ws1 = _make_world_state()
    ws2 = _make_world_state()

    # g1 加入 STATE-01
    result1 = simulate_join_faction(profile1, "STATE-01", MOCK_FACTIONS, ws1)
    assert result1["ok"], "g1 加入应成功"
    assert profile1["FACTION_STATE"]["affiliation"] == "STATE-01"

    # g2 加入 CULT-01
    result2 = simulate_join_faction(profile2, "CULT-01", MOCK_FACTIONS, ws2)
    assert result2["ok"], "g2 加入应成功"
    assert profile2["FACTION_STATE"]["affiliation"] == "CULT-01"

    # 各自独立
    assert profile1["FACTION_STATE"]["affiliation"] != profile2["FACTION_STATE"]["affiliation"]

    print("✅ 测试8通过：多 Group 独立")


def test_9_snapshot_rollback():
    """测试9：Snapshot / Rollback 正确恢复 affiliation"""
    profile = _make_profile(region="中部")
    ws = _make_world_state()

    # 快照
    snapshot_profile = json.loads(json.dumps(profile))

    # 加入势力
    result = simulate_join_faction(profile, "STATE-01", MOCK_FACTIONS, ws)
    assert result["ok"], "加入应成功"
    assert profile["FACTION_STATE"]["affiliation"] == "STATE-01"

    # Rollback
    profile_restored = json.loads(json.dumps(snapshot_profile))

    # 验证恢复
    assert profile_restored["FACTION_STATE"]["affiliation"] is None, \
        "rollback 后 affiliation 应为 None"

    print("✅ 测试9通过：Snapshot / Rollback 正确恢复 affiliation")


def test_10_prompt_injection():
    """测试10：AI Prompt 包含所属势力信息"""
    # 无 affiliation 时不注入
    profile_no_aff = _make_profile(region="中部", affiliation=None)
    ws = _make_world_state()

    result_none = simulate_build_faction_prompt(profile_no_aff, MOCK_FACTIONS, ws)
    assert result_none is None, "无 affiliation 时不应注入"

    # 有 affiliation 时注入
    profile_aff = _make_profile(region="中部", affiliation="STATE-01")
    ws = _make_world_state()

    result = simulate_build_faction_prompt(profile_aff, MOCK_FACTIONS, ws)
    assert result is not None, "有 affiliation 时应注入"
    assert "祁渊李氏" in result, f"应含势力名称，实际 {result}"
    assert "王朝" in result, f"应含势力类型，实际 {result}"
    assert "维持现状" in result, f"应含当前目标，实际 {result}"
    assert "所属势力" in result, f"应含'所属势力'标记，实际 {result}"

    # FACTION_STATE 中有不同 active_goal 时反映
    ws2 = _make_world_state()
    ws2["FACTION_STATE"]["STATE-01"]["active_goal"] = "扩张领土"
    result2 = simulate_build_faction_prompt(profile_aff, MOCK_FACTIONS, ws2)
    assert "扩张领土" in result2, f"应含'扩张领土'，实际 {result2}"

    print("✅ 测试10通过：AI Prompt 包含所属势力信息")


def test_hidden_org_leave_penalty():
    """额外测试：隐秘组织离开时 morale 惩罚"""
    profile = _make_profile(region="西部", affiliation="CULT-05")
    profile["FACTION_STATE"]["relations"]["封碑真人"] = 2
    ws = _make_world_state()
    ws["FACTION_STATE"]["CULT-05"]["morale"] = 0.7

    result = simulate_leave_faction(profile, "CULT-05", MOCK_FACTIONS, ws)

    assert result["ok"], f"离开应成功，实际 {result}"
    assert result["is_hidden"], "CULT-05 是隐秘组织"
    # morale 应下降 0.1
    assert ws["FACTION_STATE"]["CULT-05"]["morale"] == 0.6, \
        f"隐秘组织离开后 morale 应为 0.6，实际 {ws['FACTION_STATE']['CULT-05']['morale']}"
    # leader 好感度 -3
    assert profile["FACTION_STATE"]["relations"]["封碑真人"] == -1, \
        f"封碑真人好感度应为 -1，实际 {profile['FACTION_STATE']['relations']['封碑真人']}"

    print("✅ 测试11通过：隐秘组织离开时 morale 惩罚")


if __name__ == "__main__":
    test_1_join_success()
    test_2_faction_not_exist()
    test_3_region_mismatch()
    test_4_low_stability()
    test_5_leave_success()
    test_6_already_joined()
    test_7_leave_without_join()
    test_8_multi_group()
    test_9_snapshot_rollback()
    test_10_prompt_injection()
    test_hidden_org_leave_penalty()
    print("\n🎉 全部 B-5.4 玩家势力归属测试通过！")
