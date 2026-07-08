"""
test_faction_context_injection.py — B-5.5 势力上下文注入测试

覆盖：
  1. 有所属势力时注入所属势力摘要（含稳定度、士气）
  2. 无所属势力时不输出所属势力段
  3. 当前地区势力动态最多3个
  4. stance_overrides 生成关系变化摘要
  5. 无 stance_overrides 时不输出关系变化段
  6. 衰退/动荡提示
  7. 强盛/扩张提示
  8. 缺失 FACTION_STATE 时不报错
  9. 缺失 factions 静态数据时优雅降级
  10. max_chars 裁剪后仍优先保留所属势力或本地势力
  11. 不影响已有 Prompt 结构

运行方式：
  python3 tools/test_faction_context_injection.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_context import WorldContextBuilder

# ──────────────────────────────────────────────
#  测试用势力静态数据
# ──────────────────────────────────────────────

MOCK_FACTIONS = {
    "STATE-01": {
        "code": "STATE-01", "name": "祁渊李氏", "type": "王朝",
        "region": "中部", "power": 48, "status_desc": "",
        "stronghold": "岱央城——灵漏塔",
        "relations": [{"code": "CULT-01", "stance": "从属", "reason": "共治岱央千年"},
                      {"code": "HIDDEN-02", "stance": "戒备", "reason": "资助观测会但恐惧其报告内容"},
                      {"code": "STATE-02", "stance": "对立", "reason": "新域统合府欢迎东迁者"}],
        "leader": {"name": "李承渊", "title": "岱央第十八代守脉王", "desc": "守脉王"},
    },
    "CULT-01": {
        "code": "CULT-01", "name": "归墟宗", "type": "宗门",
        "region": "中部", "power": 83, "status_desc": "",
        "stronghold": "祖脉余山",
        "relations": [{"code": "STATE-01", "stance": "从属", "reason": "与李氏王朝共治岱央"}],
        "leader": {"name": "归尘真人", "title": "守脉宗第七代宗主", "desc": "宗主"},
    },
    "CULT-02": {
        "code": "CULT-02", "name": "青竹脉", "type": "宗门",
        "region": "东部", "power": 100, "status_desc": "",
        "stronghold": "新灵山脉",
        "relations": [{"code": "STATE-02", "stance": "合作竞争", "reason": "灵石开采合作"},
                      {"code": "FREE-02", "stance": "从属", "reason": "勘察团是拓脉宗最重要外围弟子来源"}],
        "leader": {"name": "林竹心", "title": "拓脉宗首任宗主", "desc": "宗主"},
    },
    "CULT-03": {
        "code": "CULT-03", "name": "永寂殿", "type": "宗门",
        "region": "北地", "power": 100, "status_desc": "",
        "stronghold": "玄冰崖",
        "relations": [{"code": "STATE-04", "stance": "戒备", "reason": "世俗权力持有者不得踏入第二道冰门"}],
        "leader": {"name": "冰渊子", "title": "守护宗第十一代宗主", "desc": "宗主"},
    },
    "FREE-01": {
        "code": "FREE-01", "name": "砂民会", "type": "散修网络",
        "region": "中部", "power": 3, "status_desc": "",
        "stronghold": "岱央城——废弃祠堂",
        "relations": [{"code": "STATE-01", "stance": "中立观望", "reason": "王朝给市盟微额税收减免"}],
        "leader": {"name": "石老六", "title": "市盟轮值盟长", "desc": "盟长"},
    },
    "FREE-02": {
        "code": "FREE-02", "name": "寻脉人", "type": "散修网络",
        "region": "东部", "power": 100, "status_desc": "",
        "stronghold": "新灵山脉——野外无固定据点",
        "relations": [],
        "leader": {"name": "无固定首领", "title": "三支勘察队队长轮流主事", "desc": ""},
    },
}

# ──────────────────────────────────────────────
#  辅助函数
# ──────────────────────────────────────────────

def _make_ws():
    return {
        "GLOBAL": {"phase": "中平期", "chaos_level": "平稳", "leyline_flow": "缓慢衰减", "tiandao_activity": "沉寂"},
        "REGION": {},
        "FACTION_STATE": {
            "STATE-01": {"power": 48, "stability": 0.6, "morale": 0.7, "active_goal": "维持现状", "stance_overrides": {}},
            "CULT-01": {"power": 83, "stability": 0.5, "morale": 0.6, "active_goal": "维持现状", "stance_overrides": {}},
            "CULT-02": {"power": 100, "stability": 0.9, "morale": 0.8, "active_goal": "扩张领土", "stance_overrides": {}},
            "CULT-03": {"power": 100, "stability": 0.85, "morale": 0.75, "active_goal": "维持现状", "stance_overrides": {}},
            "FREE-01": {"power": 3, "stability": 0.2, "morale": 0.3, "active_goal": "自保", "stance_overrides": {}},
            "FREE-02": {"power": 100, "stability": 0.95, "morale": 0.85, "active_goal": "扩张领土", "stance_overrides": {}},
        },
    }


def _make_profile(affiliation=None):
    profile = {
        "name": "测试角色",
        "IDENTITY_STATE": {"region": "中部", "subregion": "岱央城", "生存状态": "stable"},
        "FACTION_STATE": {"affiliation": affiliation, "relations": {}},
        "hp": {"current": 20, "max": 20},
        "mp": {"current": 15, "max": 15},
    }
    if affiliation:
        profile["FACTION_METADATA"] = {"static": {}}
    return profile


# ──────────────────────────────────────────────
#  测试用例
# ──────────────────────────────────────────────

def test_1_affiliation_with_stability_and_morale():
    """测试1：有所属势力时注入所属势力摘要（含稳定度、士气）"""
    ws = _make_ws()
    profile = _make_profile(affiliation="STATE-01")
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS)

    assert "【所属势力：" in result, f"应包含'所属势力'标记，实际 {result}"
    assert "祁渊李氏" in result, f"应含势力名称，实际 {result}"
    assert "王朝" in result, f"应含势力类型，实际 {result}"
    assert "0.6" in result, f"应含稳定度，实际 {result}"
    assert "0.7" in result, f"应含士气，实际 {result}"
    print("✅ 测试1通过：所属势力摘要含稳定度和士气")


def test_2_no_affiliation():
    """测试2：无所属势力时不输出所属势力段"""
    ws = _make_ws()
    profile = _make_profile(affiliation=None)
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS)

    # 不应包含所属势力段
    assert "【所属势力：" not in result, f"无 affiliation 时不应有所属势力段，实际 {result}"
    print("✅ 测试2通过：无所属势力时不输出所属势力段")


def test_3_local_factions_max_3():
    """测试3：当前地区势力动态最多3个"""
    ws = _make_ws()
    profile = _make_profile(affiliation=None)
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS, region="中部")

    # 提取本地势力动态段中的条目数
    assert "【本地势力动态】" in result, f"应有本地势力动态段，实际 {result}"
    local_start = result.index("【本地势力动态】")
    # 找下一个段标题或结尾
    next_section = result.find("【", local_start + 1)
    local_section = result[local_start:next_section] if next_section != -1 else result[local_start:]
    count = local_section.count("- ")
    assert count <= 3, f"本地势力动态应不超过3个，实际 {count} 个"
    print(f"✅ 测试3通过：本地势力动态{count}个（≤3）")


def test_4_stance_changes():
    """测试4：stance_overrides 生成关系变化摘要"""
    ws = _make_ws()
    ws["FACTION_STATE"]["STATE-01"]["stance_overrides"] = {
        "CULT-01": "敌对"  # 默认是从属 → 敌对
    }
    profile = _make_profile(affiliation=None)
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS, region="中部")

    assert "【势力关系变化】" in result, f"应有关系变化段，实际 {result}"
    assert "STATE-01" in result and "归墟宗" in result, f"应含 STATE-01→归墟宗 关系变化，实际 {result}"
    assert "从属" in result and "敌对" in result, f"应含从属→敌对变化，实际 {result}"
    print("✅ 测试4通过：stance_overrides 生成关系变化摘要")


def test_5_no_stance_overrides():
    """测试5：无 stance_overrides 时不输出关系变化段"""
    ws = _make_ws()
    del ws["FACTION_STATE"]["STATE-01"]["stance_overrides"]
    profile = _make_profile(affiliation=None)
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS, region="中部")

    assert "【势力关系变化】" not in result, f"无 override 时不应有关系变化段，实际 {result}"
    print("✅ 测试5通过：无 stance_overrides 时不输出关系变化段")


def test_6_decline_hint():
    """测试6：衰退/动荡提示"""
    ws = _make_ws()
    ws["FACTION_STATE"]["FREE-01"]["power"] = 3
    ws["FACTION_STATE"]["FREE-01"]["stability"] = 0.2
    profile = _make_profile(affiliation=None)
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS, region="中部")

    assert "【势力衰退/崛起提示】" in result, f"应有衰退提示段，实际 {result}"
    assert "砂民会" in result, f"应含砂民会，实际 {result}"
    assert "衰退" in result, f"应含'衰退'，实际 {result}"
    print("✅ 测试6通过：衰退/动荡提示")


def test_7_rise_hint():
    """测试7：强盛/扩张提示"""
    ws = _make_ws()
    ws["FACTION_STATE"]["CULT-02"]["power"] = 100
    ws["FACTION_STATE"]["CULT-02"]["stability"] = 0.9
    profile = _make_profile(affiliation=None)
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS, region="东部")

    assert "【势力衰退/崛起提示】" in result, f"应有崛起提示段，实际 {result}"
    assert "青竹脉" in result, f"应含青竹脉，实际 {result}"
    assert "强盛" in result or "扩张" in result, f"应含强盛/扩张，实际 {result}"
    print("✅ 测试7通过：强盛/扩张提示")


def test_8_missing_faction_state():
    """测试8：缺失 FACTION_STATE 时不报错"""
    ws = {"GLOBAL": {"phase": "中平期", "chaos_level": "平稳"}}
    profile = _make_profile(affiliation="STATE-01")
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    # 不应抛异常
    try:
        result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS)
        print("✅ 测试8通过：缺失 FACTION_STATE 时不报错")
    except Exception as e:
        assert False, f"不应抛异常，实际 {e}"


def test_9_missing_factions():
    """测试9：缺失 factions 静态数据时优雅降级"""
    ws = _make_ws()
    profile = _make_profile(affiliation="STATE-01")
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    # factions=None 时应正常处理
    result = builder._extract_faction_dynamics(ws, profile, None)

    # 不应崩溃，所属势力信息可能缺失但不会报错
    assert isinstance(result, str), f"结果应为字符串，实际 {type(result)}"
    print("✅ 测试9通过：缺失 factions 静态数据时优雅降级")


def test_10_trim_priority():
    """测试10：max_chars 裁剪后仍优先保留所属势力或本地势力"""
    ws = _make_ws()
    profile = _make_profile(affiliation="STATE-01")
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 200  # 很小的限制

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS, region="中部")

    # 即使裁剪后，所属势力段应该还在（优先级最高）
    assert "【所属势力：" in result, f"裁剪后所属势力段应保留，实际 {result}"
    print("✅ 测试10通过：裁剪后优先保留所属势力")


def test_11_prompt_structure():
    """测试11：不影响已有 Prompt 结构"""
    ws = _make_ws()
    profile = _make_profile(affiliation="STATE-01")
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    result = builder._extract_faction_dynamics(ws, profile, MOCK_FACTIONS, region="中部")

    # 验证格式正确
    assert result.startswith("【势力动态】"), f"应以'【势力动态】'开头，实际 {result[:50]}"
    # 验证各段标题存在
    assert "【所属势力：" in result
    assert "【本地势力动态】" in result
    # 关系变化或衰退/崛起提示至少有一个
    has_extra = "【势力关系变化】" in result or "【势力衰退/崛起提示】" in result
    assert has_extra, f"应至少有关系变化或衰退/崛起提示段，实际 {result}"
    print("✅ 测试11通过：Prompt 结构完整")


if __name__ == "__main__":
    test_1_affiliation_with_stability_and_morale()
    test_2_no_affiliation()
    test_3_local_factions_max_3()
    test_4_stance_changes()
    test_5_no_stance_overrides()
    test_6_decline_hint()
    test_7_rise_hint()
    test_8_missing_faction_state()
    test_9_missing_factions()
    test_10_trim_priority()
    test_11_prompt_structure()
    print("\n🎉 全部 B-5.5 势力上下文注入测试通过！")
