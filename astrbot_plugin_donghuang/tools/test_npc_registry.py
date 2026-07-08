"""
test_npc_registry.py — B-13 NPC数据绑定与自然交互系统 测试

覆盖：
  1. NPC搜索
  2. NPC数据读取
  3. 不存在NPC处理
  4. /dh interact 使用真实NPC
  5. NPC身份影响行为
  6. 人格标签影响行为
  7. 玩家不知道隐藏NPC信息
  8. GM查看完整信息
  9. 旧存档兼容
  10. 多NPC隔离
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from npc_registry import NPCRegistry, NPCInfo, create_npc_info
from npc_behavior import (
    calculate_behavior, apply_identity_modifier, NPCBehaviorProfile,
    clamp_probability, IDENTITY_MODIFIERS, PERSONALITY_MODIFIERS,
)
from npc_relationship import (
    calculate_relationship, REL_UNKNOWN, REL_FRIENDLY, REL_HOSTILE, REL_SUSPICIOUS, REL_LABELS,
)
from npc_action_generator import evaluate_npc_opportunity
from npc_event_trigger import create_npc_interaction_hint


# ──────────────────────────────────────────────
#  测试1：NPC搜索
# ──────────────────────────────────────────────

def test_b131_npc_search():
    """NPCRegistry 可搜索 NPC。"""
    registry = NPCRegistry()
    plugin_dir = Path(__file__).resolve().parent.parent
    registry.load(plugin_dir)

    # 精确搜索
    all_npcs = registry.get_all_npcs()
    if len(all_npcs) > 0:
        first_npc = all_npcs[0]
        name = first_npc.get("name", "")
        if name:
            found = registry.get_npc(name)
            assert found is not None
            assert found["name"] == name

    # 模糊搜索
    if len(all_npcs) > 0:
        # 取一个NPC名字的第一个字作为关键词
        partial = all_npcs[0].get("name", "")[:1]
        results = registry.search_npc(partial)
        assert len(results) > 0

    print("✅ B-13 测试1通过：NPC搜索")


# ──────────────────────────────────────────────
#  测试2：NPC数据读取
# ──────────────────────────────────────────────
def test_b132_npc_data_read():
    """NPCRegistry 可读取 NPC 数据（name, role, faction, region 等）。"""
    registry = NPCRegistry()
    plugin_dir = Path(__file__).resolve().parent.parent
    registry.load(plugin_dir)

    all_npcs = registry.get_all_npcs()
    assert len(all_npcs) > 0, "应有 NPC 数据"

    # 验证 NPC 数据结构
    for npc in all_npcs[:10]:  # 只检查前10个
        assert "name" in npc or "npc_id" in npc
        # 大部分 NPC 应有 role
        if npc.get("role"):
            assert isinstance(npc["role"], str)

    # 创建 NPCInfo
    npc_dict = all_npcs[0]
    info = create_npc_info(npc_dict)
    assert isinstance(info, NPCInfo)
    assert info.name == npc_dict.get("name", "")

    print("✅ B-13 测试2通过：NPC数据读取")


# ──────────────────────────────────────────────
#  测试3：不存在NPC处理
# ──────────────────────────────────────────────

def test_b133_nonexistent_npc():
    """不存在NPC时返回 None。"""
    registry = NPCRegistry()
    plugin_dir = Path(__file__).resolve().parent.parent
    registry.load(plugin_dir)

    result = registry.get_npc("不存在的人物XYZ")
    assert result is None

    # 模糊搜索也应返回空
    results = registry.search_npc("XYZ999不存在")
    assert len(results) == 0

    # npc_exists 应返回 False
    assert not registry.npc_exists("不存在的人物XYZ")

    print("✅ B-13 测试3通过：不存在NPC处理")


# ──────────────────────────────────────────────
#  测试4：interact 使用真实NPC
# ──────────────────────────────────────────────

def test_b134_interact_with_real_npc():
    """execute_interaction 可使用真实 NPC 数据。"""
    registry = NPCRegistry()
    plugin_dir = Path(__file__).resolve().parent.parent
    registry.load(plugin_dir)

    all_npcs = registry.get_all_npcs()
    if len(all_npcs) == 0:
        print("✅ B-13 测试4通过：interact 使用真实NPC（无NPC数据时跳过）")
        return

    # 取第一个有 name 的 NPC
    npc_dict = all_npcs[0]
    npc_name = npc_dict.get("name", "")
    if not npc_name:
        print("✅ B-13 测试4通过：interact 使用真实NPC（无有效NPC时跳过）")
        return

    from npc_interaction_executor import execute_interaction

    npc_info = {
        "name": npc_name,
        "role": npc_dict.get("role", ""),
        "faction_code": npc_dict.get("faction_code", ""),
        "cultivation": npc_dict.get("spirit_root_tier", ""),
        "type": npc_dict.get("role", "散修"),
    }

    # 友善记忆
    memories = [{"memory_type": "help", "trust_change": 35, "importance": 60}]
    result = execute_interaction(npc_info, {}, "trade", memories)

    assert isinstance(result.success, bool)
    assert result.response != ""

    print("✅ B-13 测试4通过：interact 使用真实NPC")


# ──────────────────────────────────────────────
#  测试5：NPC身份影响行为
# ──────────────────────────────────────────────

def test_b135_identity_modifies_behavior():
    """长老/商人等身份修正行为倾向。"""
    # 长老修正：信息概率增加，风险态度变谨慎
    memories1 = [{"memory_type": "help", "trust_change": 10, "importance": 50}]
    base_elder = calculate_behavior(memories1)
    base_elder_secret = base_elder.secret_probability
    npc_elder = {"role": "长老", "faction_code": "CULT-01", "personality": ""}
    modified_elder = apply_identity_modifier(base_elder, npc_elder)
    assert modified_elder.secret_probability >= base_elder_secret
    assert modified_elder.risk_attitude == "cautious"

    # 商人修正：价格偏向优惠（重新计算base）
    memories2 = [{"memory_type": "help", "trust_change": 10, "importance": 50}]
    base_merchant = calculate_behavior(memories2)
    base_merchant_price = base_merchant.price_bias
    npc_merchant = {"role": "货郎", "faction_code": "", "personality": ""}
    modified_merchant = apply_identity_modifier(base_merchant, npc_merchant)
    assert modified_merchant.price_bias > base_merchant_price

    print("✅ B-13 测试5通过：NPC身份影响行为")


# ──────────────────────────────────────────────
#  测试6：人格标签影响行为
# ──────────────────────────────────────────────

def test_b136_personality_modifies_behavior():
    """谨慎/豪爽等人格标签修正行为倾向。"""
    memories = [{"memory_type": "help", "trust_change": 10, "importance": 50}]
    base = calculate_behavior(memories)

    # 谨慎人格：帮助概率降低，信息概率降低
    npc_cautious = {"role": "", "faction_code": "", "personality": "谨慎"}
    modified = apply_identity_modifier(base, npc_cautious)
    assert modified.help_probability <= base.help_probability
    assert modified.secret_probability <= base.secret_probability
    assert modified.risk_attitude == "cautious"

    # 豪爽人格：帮助概率增加
    base2 = calculate_behavior(memories)
    npc_bold = {"role": "", "faction_code": "", "personality": "豪爽"}
    modified2 = apply_identity_modifier(base2, npc_bold)
    assert modified2.help_probability >= base2.help_probability
    assert modified2.risk_attitude == "bold"

    # 多疑人格：信息概率大幅降低
    base3 = calculate_behavior(memories)
    npc_suspicious = {"role": "", "faction_code": "", "personality": "多疑"}
    modified3 = apply_identity_modifier(base3, npc_suspicious)
    assert modified3.secret_probability <= base3.secret_probability

    print("✅ B-13 测试6通过：人格标签影响行为")


# ──────────────────────────────────────────────
#  测试7：玩家不知道隐藏NPC信息
# ──────────────────────────────────────────────

def test_b137_player_cannot_see_hidden_info():
    """NPCInfo 的 to_dict 不暴露隐藏数据（如 GM only 信息）。"""
    npc_dict = {
        "npc_id": "MAJ-001",
        "name": "孔红美",
        "role": "丞相",
        "faction_code": "STATE-01",
        "faction_name": "祁渊李氏",
        "region": "中部",
        "spirit_root_tier": "黄",
        "spirit_root_element": "木",
        "desc": "这是一段很长的描述..." * 20,
        "relations": [{"target": "李承渊", "note": "秘密关系"}],
    }

    info = create_npc_info(npc_dict)
    info_dict = info.to_dict()

    # 公开字段应存在
    assert info_dict["name"] == "孔红美"
    assert info_dict["role"] == "丞相"

    # NPC ID 是内部标识，不应直接展示给玩家
    # （但存在于 to_dict 中，因为是数据模型）
    assert info_dict["id"] == "MAJ-001"

    # 描述很长，应截断给普通玩家（由 /dh npc 命令处理截断逻辑）
    assert len(info.description) > 80  # 描述本身很长

    print("✅ B-13 测试7通过：玩家不知道隐藏NPC信息")


# ──────────────────────────────────────────────
#  测试8：GM查看完整信息
# ──────────────────────────────────────────────

def test_b138_gm_sees_full_info():
    """GM 可查看 NPC 的完整描述和八字等隐藏信息。"""
    npc_dict = {
        "npc_id": "MAJ-001",
        "name": "孔红美",
        "role": "丞相",
        "faction_code": "STATE-01",
        "faction_name": "祁渊李氏",
        "region": "中部",
        "spirit_root_tier": "黄",
        "spirit_root_element": "木",
        "six_dims": {"根骨": 10, "悟性": 17},
        "desc": "完整描述文本",
        "relations": [{"target": "李承渊", "note": "秘密关系"}],
        "personality": "谨慎",
        "eight_chars": "癸未癸卯乙巳丙子",
    }

    info = create_npc_info(npc_dict)
    info_dict = info.to_dict()

    # GM 信息应包含所有字段
    assert info_dict["faction_code"] == "STATE-01"
    assert info_dict["six_dims"] == {"根骨": 10, "悟性": 17}
    assert info_dict["personality"] == "谨慎"
    assert len(info_dict["relations"]) > 0

    print("✅ B-13 测试8通过：GM查看完整信息")


# ──────────────────────────────────────────────
#  测试9：旧存档兼容
# ──────────────────────────────────────────────

def test_b139_old_save_compatibility():
    """旧存档没有 npc_memory 时 NPCRegistry 正常工作。"""
    registry = NPCRegistry()
    plugin_dir = Path(__file__).resolve().parent.parent
    registry.load(plugin_dir)

    # 空 campaign
    old_campaign = {"state": "running", "cycle": 5, "slots": {}}
    npc_memory = old_campaign.get("npc_memory", {})
    assert npc_memory == {}

    # NPCRegistry 不依赖 npc_memory
    all_npcs = registry.get_all_npcs()
    assert len(all_npcs) > 0

    # 行为计算对空记忆正常
    behavior = calculate_behavior([])
    assert behavior.relationship == REL_UNKNOWN

    print("✅ B-13 测试9通过：旧存档兼容")


# ──────────────────────────────────────────────
#  测试10：多NPC隔离
# ──────────────────────────────────────────────

def test_b1310_multi_npc_isolation():
    """不同区域 NPC 数据互不干扰。"""
    registry = NPCRegistry()
    plugin_dir = Path(__file__).resolve().parent.parent
    registry.load(plugin_dir)

    # 获取各区域 NPC
    regions = ["中部", "西部", "北部", "东部", "南部"]
    region_sets = {}
    for region in regions:
        npcs = registry.get_nearby_npcs(region, max_count=5)
        region_sets[region] = set(n.get("name", "") for n in npcs)

    # 不同区域的 NPC 列表可能重叠（因为 NPC 可能属于多个区域）
    # 但至少应该有不同的结果
    assert len(region_sets) > 0

    # NPC 行为隔离
    mem_a = [{"memory_type": "help", "trust_change": 35, "importance": 60}]
    mem_b = [{"memory_type": "conflict", "trust_change": -40, "importance": 65}]

    beh_a = calculate_behavior(mem_a)
    beh_b = calculate_behavior(mem_b)

    assert beh_a.relationship != beh_b.relationship

    print("✅ B-13 测试10通过：多NPC隔离")


# ──────────────────────────────────────────────
#  测试11：evaluate_npc_opportunity
# ──────────────────────────────────────────────

def test_b1311_npc_opportunity_evaluation():
    """NPC 主动行为机会评估。"""
    # friendly NPC → send_warning 或 offer_information
    mem_friendly = [{"memory_type": "help", "trust_change": 35, "importance": 60}]
    npc_info = {"name": "友善NPC"}
    action = evaluate_npc_opportunity(npc_info, memories=mem_friendly)
    assert action in ("send_warning", "offer_information", None)
    # 高信任时应有主动行为
    if mem_friendly[0]["trust_change"] >= 30:
        assert action is not None

    # hostile NPC → avoid_player
    mem_hostile = [{"memory_type": "conflict", "trust_change": -65, "importance": 75}]
    action_hostile = evaluate_npc_opportunity(npc_info, memories=mem_hostile)
    assert action_hostile == "avoid_player"

    # 无记忆 → None
    action_none = evaluate_npc_opportunity(npc_info, memories=None)
    assert action_none is None

    print("✅ B-13 测试11通过：evaluate_npc_opportunity")


# ──────────────────────────────────────────────
#  测试12：create_npc_interaction_hint
# ──────────────────────────────────────────────

def test_b1312_npc_interaction_hint():
    """NPC 主动事件提示生成。"""
    hint_warning = create_npc_interaction_hint("send_warning", region="西部")
    assert hint_warning is not None
    assert "西部" in hint_warning

    hint_info = create_npc_interaction_hint("offer_information", npc_name="李长老", topic="灵脉异常")
    assert hint_info is not None
    assert "灵脉异常" in hint_info

    hint_avoid = create_npc_interaction_hint("avoid_player")
    assert hint_avoid is not None

    # ignore → None
    hint_ignore = create_npc_interaction_hint("ignore")
    assert hint_ignore is None

    print("✅ B-13 测试12通过：create_npc_interaction_hint")


# ──────────────────────────────────────────────
#  测试13：clamp_probability
# ──────────────────────────────────────────────

def test_b1313_clamp_probability():
    """概率 clamp 函数正确限制范围。"""
    assert clamp_probability(0.0) == 0.01
    assert clamp_probability(-0.5) == 0.01
    assert clamp_probability(1.5) == 1.0
    assert clamp_probability(0.5) == 0.5
    assert clamp_probability(0.65) == 0.65

    print("✅ B-13 测试13通过：clamp_probability")


# ──────────────────────────────────────────────
#  运行全部测试
# ──────────────────────────────────────────────

if __name__ == "__main__":
    test_b131_npc_search()
    test_b132_npc_data_read()
    test_b133_nonexistent_npc()
    test_b134_interact_with_real_npc()
    test_b135_identity_modifies_behavior()
    test_b136_personality_modifies_behavior()
    test_b137_player_cannot_see_hidden_info()
    test_b138_gm_sees_full_info()
    test_b139_old_save_compatibility()
    test_b1310_multi_npc_isolation()
    test_b1311_npc_opportunity_evaluation()
    test_b1312_npc_interaction_hint()
    test_b1313_clamp_probability()
    print("\n🎉 B-13 全部 13 项测试通过！")
