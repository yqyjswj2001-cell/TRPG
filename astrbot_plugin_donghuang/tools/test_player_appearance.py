"""
test_player_appearance.py — B-8 玩家角色外观与身份系统 测试

覆盖：
  1. 新角色生成 appearance
  2. to_dict/from_dict 一致
  3. 旧存档没有 appearance 可以加载
  4. WorldContext 可以读取 appearance
  5. NPC 不同身份返回不同观察
  6. Snapshot 后修改外貌，再 rollback 可以恢复
  7. 多玩家隔离
  8. AppearanceGenerator 确定性（同种子同结果）
  9. appearance_modifier 构造合法 profile_delta
  10. OutcomeApplier 可以写入 appearance 字段
"""

import json
import sys
from pathlib import Path

# 确保可以 import 插件模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from player_appearance import PlayerAppearance, AppearanceGenerator
from npc_perception import perceive_player, _determine_perception_depth
from appearance_modifier import (
    modify_appearance_delta,
    apply_appearance_to_profile,
    CHANGE_TYPE_BATTLE,
    CHANGE_TYPE_BREAKTHROUGH,
    CHANGE_TYPE_SPECIAL,
)


# ──────────────────────────────────────────────
#  测试 1：新角色生成 appearance
# ──────────────────────────────────────────────

def test_b81_new_character_appearance():
    """新角色生成 appearance：所有字段非空（marks 可能为空列表）。"""
    gen = AppearanceGenerator()
    appearance = gen.generate(
        identity="剑修弟子",
        cultivation_path="剑修",
        faction="CULT-01",
        element="金",
        gender="男",
        seed=42,
    )

    # face 必须有内容
    assert appearance.face.get("age"), "face.age 不应为空"
    assert appearance.face.get("features"), "face.features 不应为空"
    assert appearance.face.get("expression"), "face.expression 不应为空"

    # body 必须有内容
    assert appearance.body.get("height"), "body.height 不应为空"
    assert appearance.body.get("build"), "body.build 不应为空"

    # hair 必须有内容
    assert appearance.hair.get("color"), "hair.color 不应为空"
    assert appearance.hair.get("style"), "hair.style 不应为空"

    # eyes 必须有内容
    assert appearance.eyes.get("color"), "eyes.color 不应为空"

    # clothing 必须有内容
    assert appearance.clothing.get("style"), "clothing.style 不应为空"
    assert appearance.clothing.get("origin"), "clothing.origin 不应为空"

    # aura 必须有内容
    assert appearance.aura.get("feeling"), "aura.feeling 不应为空"

    # first_impression 必须有内容
    assert appearance.first_impression, "first_impression 不应为空"

    # marks 是 list（可能为空）
    assert isinstance(appearance.marks, list), "marks 应为 list"

    print("✅ B-8 测试1通过：新角色生成 appearance")


# ──────────────────────────────────────────────
#  测试 2：to_dict/from_dict 一致
# ──────────────────────────────────────────────

def test_b82_to_dict_from_dict_roundtrip():
    """to_dict → from_dict → to_dict 应完全一致。"""
    gen = AppearanceGenerator()
    original = gen.generate(
        identity="医修弟子",
        cultivation_path="医修",
        element="木",
        gender="女",
        seed=99,
    )

    d = original.to_dict()
    restored = PlayerAppearance.from_dict(d)
    d2 = restored.to_dict()

    assert d == d2, f"roundtrip 不一致：{d} vs {d2}"

    # 验证 JSON 序列化也一致
    json_str = json.dumps(d, ensure_ascii=False)
    d3 = json.loads(json_str)
    restored3 = PlayerAppearance.from_dict(d3)
    assert restored3.to_dict() == d, "JSON 序列化后 roundtrip 不一致"

    print("✅ B-8 测试2通过：to_dict/from_dict 一致")


# ──────────────────────────────────────────────
#  测试 3：旧存档没有 appearance 可以加载
# ──────────────────────────────────────────────

def test_b83_old_save_no_appearance():
    """旧存档没有 appearance 字段时，from_dict 应正常返回空外观。"""
    # 模拟旧存档 profile（没有 appearance 键）
    old_profile = {
        "name": "测试角色",
        "cultivation_realm": "炼气三层",
        "CORE_STATE": {"spirit_root_tier": 1, "spirit_root_element": "金"},
    }

    # from_dict 对空 dict 应正常工作
    empty_appearance = PlayerAppearance.from_dict({})
    assert empty_appearance.face == {}
    assert empty_appearance.marks == []
    assert empty_appearance.first_impression == ""

    # 模拟 main.py 的旧存档兼容逻辑
    if "appearance" not in old_profile:
        old_profile["appearance"] = {}

    # 空外观不应导致加载失败
    appearance = PlayerAppearance.from_dict(old_profile["appearance"])
    assert appearance.face == {}
    assert appearance.marks == []

    # format_brief 对空外观不应崩溃
    brief = appearance.format_brief()
    assert isinstance(brief, str)

    # format_short 对空外观不应崩溃
    short = appearance.format_short()
    assert isinstance(short, str)

    print("✅ B-8 测试3通过：旧存档没有 appearance 可以加载")


# ──────────────────────────────────────────────
#  测试 4：WorldContext 可以读取 appearance
# ──────────────────────────────────────────────

def test_b84_world_context_reads_appearance():
    """WorldContext._extract_player_appearance 可以正确提取外貌信息。"""
    from world_context import WorldContextBuilder

    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    # 构造有外观的 profile
    gen = AppearanceGenerator()
    appearance = gen.generate(
        identity="剑修",
        cultivation_path="剑修",
        element="金",
        gender="男",
        seed=42,
    )

    profiles = {
        "PLAYER-A": {
            "name": "沈砚",
            "appearance": appearance.to_dict(),
        }
    }

    # 完整展示模式
    result_full = builder._extract_player_appearance(profiles, "PLAYER-A", full_display=True)
    assert "【玩家外貌】" in result_full, "应包含【玩家外貌】标题"
    assert "外貌：" in result_full or "衣着：" in result_full, "完整模式应包含外貌或衣着"

    # 压缩模式
    result_short = builder._extract_player_appearance(profiles, "PLAYER-A", full_display=False)
    assert "【玩家外貌】" in result_short, "压缩模式应包含标题"
    # 压缩模式应只保留印象
    if appearance.first_impression:
        assert "外貌印象：" in result_short, "压缩模式应包含外貌印象"

    # 无 slot_id 时返回空
    result_none = builder._extract_player_appearance(profiles, None)
    assert result_none == "", "无 slot_id 应返回空"

    # 空 appearance 时返回空
    profiles_empty = {"PLAYER-A": {"name": "测试", "appearance": {}}}
    result_empty = builder._extract_player_appearance(profiles_empty, "PLAYER-A", full_display=True)
    assert result_empty == "", "空外观应返回空"

    print("✅ B-8 测试4通过：WorldContext 可以读取 appearance")


# ──────────────────────────────────────────────
#  测试 5：NPC 不同身份返回不同观察
# ──────────────────────────────────────────────

def test_b85_npc_different_perception():
    """不同修为的 NPC 对同一玩家返回不同感知深度。"""
    gen = AppearanceGenerator()
    appearance = gen.generate(
        identity="剑修",
        cultivation_path="剑修",
        element="金",
        gender="男",
        seed=42,
    )

    player_profile = {
        "name": "沈砚",
        "gender": "男",
        "CORE_STATE": {"spirit_root_tier": 1, "spirit_root_element": "金"},
        "METHOD_STATE": {"primary_path": "剑修", "growth_stage": "练气", "progress": 30},
        "appearance": appearance.to_dict(),
    }

    # 凡人 NPC（低修为）
    npc_mortal = {"name": "老农", "cultivation": 0, "type": "百姓"}
    result_mortal = perceive_player(player_profile, npc_mortal)
    assert result_mortal.npc_name == "老农"
    assert result_mortal.perception_depth in ("normal", "subtle", "keen", "insightful")
    # 凡人应该只能看到衣着
    assert any("身着" in obs for obs in result_mortal.observations), \
        f"凡人应能看到衣着，实际观察：{result_mortal.observations}"

    # 高阶修士 NPC
    npc_master = {"name": "宗主", "cultivation": 80, "type": "宗主"}
    result_master = perceive_player(player_profile, npc_master)
    assert result_master.perception_depth in ("keen", "insightful"), \
        f"高阶修士应有更深层感知，实际：{result_master.perception_depth}"
    # 高阶修士应能看到更多细节
    assert len(result_master.observations) >= len(result_mortal.observations), \
        "高阶修士应比凡人看到更多"

    # 感知深度判断
    depth_low = _determine_perception_depth(0, 30)
    depth_high = _determine_perception_depth(80, 30)
    assert depth_high in ("keen", "insightful"), f"高修为NPC应有更深层感知，实际：{depth_high}"
    assert depth_low in ("normal", "subtle"), f"低修为NPC应有浅层感知，实际：{depth_low}"

    print("✅ B-8 测试5通过：NPC 不同身份返回不同观察")


# ──────────────────────────────────────────────
#  测试 6：Snapshot 后修改外貌，再 rollback 可以恢复
# ──────────────────────────────────────────────

def test_b86_snapshot_rollback_appearance():
    """Snapshot 包含 appearance，rollback 可以恢复外貌变化。"""
    gen = AppearanceGenerator()
    appearance = gen.generate(
        identity="剑修",
        cultivation_path="剑修",
        element="金",
        gender="男",
        seed=42,
    )

    # 模拟 profile
    profile = {
        "name": "沈砚",
        "appearance": appearance.to_dict(),
    }

    # 拍快照（深拷贝）
    snapshot = json.loads(json.dumps(profile))

    # 修改外貌（通过 apply_appearance_to_profile）
    changes = apply_appearance_to_profile(profile, {
        "marks": ["左臂新伤"],
        "aura": {"feeling": "战意凌厉"},
    })

    # 验证修改已生效
    assert "左臂新伤" in profile["appearance"]["marks"], "伤痕应已追加"
    assert profile["appearance"]["aura"]["feeling"] == "战意凌厉", "气质应已改变"

    # rollback（从快照恢复）
    profile = json.loads(json.dumps(snapshot))

    # 验证恢复
    assert "左臂新伤" not in profile["appearance"].get("marks", []), "rollback 后伤痕应消失"
    assert profile["appearance"]["aura"]["feeling"] == appearance.aura["feeling"], \
        "rollback 后气质应恢复"

    print("✅ B-8 测试6通过：Snapshot 后修改外貌，rollback 可以恢复")


# ──────────────────────────────────────────────
#  测试 7：多玩家隔离
# ──────────────────────────────────────────────

def test_b87_multi_player_isolation():
    """不同玩家的外观互不影响。"""
    gen = AppearanceGenerator()

    # 两个不同角色
    app1 = gen.generate(identity="剑修", cultivation_path="剑修", element="金", gender="男", seed=1)
    app2 = gen.generate(identity="医修", cultivation_path="医修", element="木", gender="女", seed=2)

    # 外观应不同
    d1 = app1.to_dict()
    d2 = app2.to_dict()

    # 至少某些字段应不同（不同种子、不同路径）
    assert d1 != d2, "不同角色外观应不同"

    # 剑修应有剑修衣着
    assert "剑" in app1.clothing.get("style", "") or "剑" in str(app1.clothing), \
        f"剑修应有剑修衣着，实际：{app1.clothing}"

    # 医修应有医修衣着
    assert "药" in app2.clothing.get("style", "") or "药" in str(app2.clothing) or "医" in str(app2.clothing), \
        f"医修应有医修衣着，实际：{app2.clothing}"

    # 修改一个不影响另一个
    profile1 = {"name": "角色1", "appearance": d1}
    profile2 = {"name": "角色2", "appearance": d2}

    apply_appearance_to_profile(profile1, {"marks": ["新伤痕"]})
    assert "新伤痕" not in profile2["appearance"].get("marks", []), "修改角色1不应影响角色2"

    print("✅ B-8 测试7通过：多玩家隔离")


# ──────────────────────────────────────────────
#  测试 8：AppearanceGenerator 确定性
# ──────────────────────────────────────────────

def test_b88_generator_deterministic():
    """同一种子生成相同结果。"""
    gen = AppearanceGenerator()

    app1 = gen.generate(identity="剑修", cultivation_path="剑修", element="金", gender="男", seed=42)
    app2 = gen.generate(identity="剑修", cultivation_path="剑修", element="金", gender="男", seed=42)

    assert app1.to_dict() == app2.to_dict(), "同种子应生成相同外观"

    # 不同种子应生成不同结果
    app3 = gen.generate(identity="剑修", cultivation_path="剑修", element="金", gender="男", seed=99)
    assert app1.to_dict() != app3.to_dict(), "不同种子应生成不同外观"

    print("✅ B-8 测试8通过：AppearanceGenerator 确定性")


# ──────────────────────────────────────────────
#  测试 9：appearance_modifier 构造合法 profile_delta
# ──────────────────────────────────────────────

def test_b89_appearance_modifier_delta():
    """appearance_modifier 构造的 profile_delta 格式正确。"""
    # 战斗变化
    delta_battle = modify_appearance_delta(
        "PLAYER-A",
        CHANGE_TYPE_BATTLE,
        {"marks": ["左臂新伤"], "clothing": {"style": "破损剑袍"}},
        current_appearance={"marks": ["旧剑伤"], "clothing": {"style": "青色剑修袍", "origin": "宗门制式"}},
    )

    # 验证格式：{slot_id: {"appearance": {...}}}
    assert "PLAYER-A" in delta_battle, "delta 应包含玩家 ID"
    assert "appearance" in delta_battle["PLAYER-A"], "delta 应包含 appearance 键"

    app_delta = delta_battle["PLAYER-A"]["appearance"]
    # marks 应为旧 + 新
    assert "旧剑伤" in app_delta["marks"], "旧印记应保留"
    assert "左臂新伤" in app_delta["marks"], "新伤痕应追加"
    # clothing 应为增量
    assert app_delta["clothing"]["style"] == "破损剑袍", "衣着应更新"

    # 突破变化
    delta_breakthrough = modify_appearance_delta(
        "PLAYER-A",
        CHANGE_TYPE_BREAKTHROUGH,
        {"aura": {"feeling": "锋锐内敛"}, "first_impression": "像一柄出鞘的剑"},
    )
    assert "appearance" in delta_breakthrough["PLAYER-A"]
    app_delta2 = delta_breakthrough["PLAYER-A"]["appearance"]
    assert app_delta2["aura"]["feeling"] == "锋锐内敛"
    assert app_delta2["first_impression"] == "像一柄出鞘的剑"

    # 特殊事件变化
    delta_special = modify_appearance_delta(
        "PLAYER-B",
        CHANGE_TYPE_SPECIAL,
        {"marks": ["额头封印"], "face": {"expression": "肃穆"}},
    )
    assert "PLAYER-B" in delta_special
    assert "额头封印" in delta_special["PLAYER-B"]["appearance"]["marks"]

    # 未知变化类型返回空
    delta_unknown = modify_appearance_delta("PLAYER-A", "unknown", {})
    assert delta_unknown == {}

    print("✅ B-8 测试9通过：appearance_modifier 构造合法 profile_delta")


# ──────────────────────────────────────────────
#  测试 10：OutcomeApplier 可以写入 appearance 字段
# ──────────────────────────────────────────────

def test_b810_outcome_applier_writes_appearance():
    """OutcomeApplier 可以通过 profile_delta 写入 appearance 字段。"""
    from outcome_applier import OutcomeApplier
    from event_outcome import make_resolved_outcome

    gen = AppearanceGenerator()
    appearance = gen.generate(
        identity="剑修", cultivation_path="剑修", element="金", gender="男", seed=42,
    )

    profiles = {
        "PLAYER-A": {
            "name": "沈砚",
            "BASE_STATE": {"progress": 50},
            "FACTION_STATE": {"affiliation": None},
            "relations": {},
            "appearance": appearance.to_dict(),
        }
    }

    applier = OutcomeApplier()

    # 构造包含 appearance 变更的 outcome
    outcome = make_resolved_outcome("E1", "战斗胜利", profile_delta={
        "PLAYER-A": {
            "appearance": {
                "marks": appearance.marks + ["左臂新伤"],
                "aura": {"feeling": "战意凌厉"},
            },
        }
    })

    result = applier.apply_outcome(outcome, world_state={}, profiles=profiles)

    # appearance 应被写入
    assert "左臂新伤" in profiles["PLAYER-A"]["appearance"]["marks"], \
        f"伤痕应已追加，实际：{profiles['PLAYER-A']['appearance']['marks']}"
    assert profiles["PLAYER-A"]["appearance"]["aura"]["feeling"] == "战意凌厉", \
        "气质应已更新"

    # applied_changes 应包含 appearance 变更
    app_changes = [c for c in result["applied_changes"] if "appearance" in c["path"]]
    assert len(app_changes) > 0, "应有 appearance 变更记录"

    print("✅ B-8 测试10通过：OutcomeApplier 可以写入 appearance 字段")


# ──────────────────────────────────────────────
#  测试 11：format_brief / format_short 输出合理
# ──────────────────────────────────────────────

def test_b811_format_methods():
    """format_brief 和 format_short 输出合理。"""
    gen = AppearanceGenerator()
    appearance = gen.generate(
        identity="剑修", cultivation_path="剑修", element="金", gender="男", seed=42,
    )

    brief = appearance.format_brief()
    assert isinstance(brief, str)
    assert len(brief) > 0, "format_brief 不应为空"

    short = appearance.format_short()
    assert isinstance(short, str)
    # short 应比 brief 短或相等
    assert len(short) <= len(brief) or short == "", \
        f"format_short 应比 format_brief 短，实际 short={len(short)} brief={len(brief)}"

    # 空 appearance 的 format 方法不应崩溃
    empty = PlayerAppearance()
    assert isinstance(empty.format_brief(), str)
    assert isinstance(empty.format_short(), str)

    print("✅ B-8 测试11通过：format_brief / format_short 输出合理")


# ──────────────────────────────────────────────
#  测试 12：修为路径影响外观
# ──────────────────────────────────────────────

def test_b812_path_influences_appearance():
    """不同修为路径生成不同风格的外观。"""
    gen = AppearanceGenerator()

    # 剑修
    sword = gen.generate(cultivation_path="剑修", gender="男", seed=42)
    assert "剑" in sword.clothing["style"] or "剑" in sword.hair["style"], \
        f"剑修衣着/发型应含'剑'，实际：clothing={sword.clothing} hair={sword.hair}"

    # 医修
    med = gen.generate(cultivation_path="医修", gender="女", seed=42)
    assert "药" in med.clothing["style"] or "药" in med.aura.get("feeling", ""), \
        f"医修衣着/气质应含'药'，实际：clothing={med.clothing} aura={med.aura}"

    # 魔修
    demon = gen.generate(cultivation_path="魔修", gender="男", seed=42)
    assert "暗" in demon.clothing["style"] or "危险" in demon.aura.get("feeling", "") or "诡" in demon.aura.get("feeling", ""), \
        f"魔修衣着/气质应含暗色/危险，实际：clothing={demon.clothing} aura={demon.aura}"

    print("✅ B-8 测试12通过：修为路径影响外观")


# ──────────────────────────────────────────────
#  运行所有测试
# ──────────────────────────────────────────────

if __name__ == "__main__":
    test_b81_new_character_appearance()
    test_b82_to_dict_from_dict_roundtrip()
    test_b83_old_save_no_appearance()
    test_b84_world_context_reads_appearance()
    test_b85_npc_different_perception()
    test_b86_snapshot_rollback_appearance()
    test_b87_multi_player_isolation()
    test_b88_generator_deterministic()
    test_b89_appearance_modifier_delta()
    test_b810_outcome_applier_writes_appearance()
    test_b811_format_methods()
    test_b812_path_influences_appearance()
    print("\n🎉 B-8 全部 12 项测试通过！")
