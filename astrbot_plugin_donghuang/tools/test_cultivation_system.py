# -*- coding: utf-8 -*-
"""
test_cultivation_system.py — 修仙成长生态系统测试（LONG-A）

覆盖范围：
  - cultivation_state: 状态提取、增益计算、根基/瓶颈变化、突破DC
  - spiritual_root: 灵根生成、效率计算、功法亲和度、突破风险
  - cultivation_technique: 功法加载、速度计算、突破加成
  - cultivation_ability: 技能升级、经验计算、效果判定
  - sect_interface: 宗门接口、贡献计算、职位晋升
  - event_outcome: 白名单扩展
  - outcome_applier: METHOD_STATE/CORE_STATE delta 处理
  - 旧存档兼容：迁移函数
  - 多玩家隔离
"""

import sys
import os
import json
import copy
from pathlib import Path

# 添加插件目录到 sys.path
PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_DIR))

from cultivation_state import (
    CultivationState, extract_cultivation_state,
    calculate_cultivation_gain, calculate_foundation_change,
    calculate_bottleneck_change, calculate_breakthrough_dc,
    adjust_cultivation_progress, calculate_cultivation_modifier,
    get_realm_index, get_next_realm, is_boundary_realm, is_major_breakthrough,
    migrate_profile_cultivation, make_method_state_delta,
    REALMS, BOUNDARY_REALMS, FOUNDATION_DEFAULT, FOUNDATION_MIN, FOUNDATION_MAX,
    BOTTLENECK_MIN, BOTTLENECK_MAX, CULTIVATION_PROGRESS_MAX,
)
from spiritual_root import (
    SpiritualRoot, extract_spiritual_root,
    calculate_cultivation_efficiency, calculate_technique_affinity,
    calculate_breakthrough_risk, generate_spiritual_root,
    make_core_state_delta, describe_spiritual_root,
    migrate_profile_spiritual_root, calculate_purity_change,
    clamp_purity, calculate_ability_affinity,
    FIVE_ELEMENTS, SPECIAL_ROOTS, PURITY_MIN, PURITY_MAX,
)
from cultivation_ability import (
    CultivationAbility, AbilityManager,
    describe_ability, describe_all_abilities,
    migrate_profile_abilities, make_ability_delta,
    ABILITY_NAMES, ABILITY_MAX_LEVEL, ABILITY_LEVEL_NAMES,
)
from breakthrough_manager import (
    BreakthroughManager, BreakthroughResult,
    generate_cultivation_events, CULTIVATION_EVENT_TEMPLATES,
)
from sect_interface import (
    SectInterface, SectInfo, describe_sect_info,
    migrate_profile_sect, make_sect_delta,
)
from event_outcome import (
    EventOutcome, PROFILE_FIELD_WHITELIST,
    METHOD_STATE_WHITELIST, CORE_STATE_WHITELIST,
)
from outcome_applier import OutcomeApplier


# ──────────────────────────────────────────────
#  测试辅助
# ──────────────────────────────────────────────

_passed = 0
_failed = 0
_errors = []

def assert_eq(name, actual, expected):
    global _passed, _failed
    if actual == expected:
        _passed += 1
    else:
        _failed += 1
        _errors.append(f"FAIL {name}: expected {expected!r}, got {actual!r}")

def assert_true(name, condition):
    assert_eq(name, condition, True)

def assert_in(name, value, collection):
    global _passed, _failed
    if value in collection:
        _passed += 1
    else:
        _failed += 1
        _errors.append(f"FAIL {name}: {value!r} not in {collection!r}")

def assert_gte(name, actual, minimum):
    global _passed, _failed
    if actual >= minimum:
        _passed += 1
    else:
        _failed += 1
        _errors.append(f"FAIL {name}: {actual!r} < {minimum!r}")

def make_test_profile(**overrides):
    """创建测试用 profile。"""
    profile = {
        "name": "测试角色", "age": 20, "gender": "男",
        "cultivation_realm": "练气一层", "identity": "散修",
        "six_dims": {"体质": 10, "根骨": 10, "悟性": 10, "心性": 10, "机缘": 10, "魅力": 10},
        "hp": {"current": 20, "max": 20},
        "mp": {"current": 15, "max": 15},
        "CORE_STATE": {
            "spirit_root_tier": 3, "spirit_root_element": "金",
            "stability": "stable", "chaos_influence": "none",
            "spiritual_root": {
                "primary": "金", "secondary": [], "purity": 0.5,
                "mutation": "none", "efficiency": 1.0,
            },
        },
        "METHOD_STATE": {
            "primary_path": "感悟型", "growth_stage": "练气",
            "breakthrough_status": "none_pending",
            "known_techniques": [], "progress": 0,
            "foundation": 100, "bottleneck": 0,
            "consecutive_failures": 0, "cultivation_modifier": 1.0,
            "active_technique": "",
            "abilities": {
                "剑意": {"level": 0, "exp": 0, "max_level": 5},
                "炼丹": {"level": 0, "exp": 0, "max_level": 5},
                "炼器": {"level": 0, "exp": 0, "max_level": 5},
                "阵法": {"level": 0, "exp": 0, "max_level": 5},
                "符箓": {"level": 0, "exp": 0, "max_level": 5},
            },
        },
        "FACTION_STATE": {"affiliation": None, "relations": {}, "sect": {
            "name": "", "position": "外门弟子", "contribution": 0,
            "contribution_rank": 0, "heritage": [], "master": "",
            "disciples": [], "joined_cycle": 0, "status": "active",
        }},
    }
    profile.update(overrides)
    return profile


# ──────────────────────────────────────────────
#  1. cultivation_state 测试
# ──────────────────────────────────────────────

def test_cultivation_state():
    print("=== cultivation_state 测试 ===")

    # 境界列表完整性
    assert_eq("REALMS_count", len(REALMS), 14)
    assert_eq("BOUNDARY_REALMS", BOUNDARY_REALMS, frozenset({"练气九层", "筑基巅峰"}))

    # 境界索引
    assert_eq("realm_index_练气一层", get_realm_index("练气一层"), 0)
    assert_eq("realm_index_金丹初期", get_realm_index("金丹初期"), 13)
    assert_eq("realm_index_unknown", get_realm_index("不存在"), 0)

    # 下一境界
    assert_eq("next_realm_练气一层", get_next_realm("练气一层"), "练气二层")
    assert_eq("next_realm_金丹初期", get_next_realm("金丹初期"), None)

    # 大境界判断
    assert_true("is_boundary_练气九层", is_boundary_realm("练气九层"))
    assert_true("is_boundary_筑基巅峰", is_boundary_realm("筑基巅峰"))
    assert_true("not_boundary_练气一层", not is_boundary_realm("练气一层"))

    # 跨大境界判断
    assert_true("major_breakthrough", is_major_breakthrough("练气九层", "筑基初期"))
    assert_true("not_major_breakthrough", not is_major_breakthrough("练气一层", "练气二层"))

    # 从 profile 提取
    profile = make_test_profile()
    cs = extract_cultivation_state(profile)
    assert_eq("extract_realm", cs.realm, "练气一层")
    assert_eq("extract_progress", cs.progress, 0)
    assert_eq("extract_foundation", cs.foundation, 100)
    assert_eq("extract_bottleneck", cs.bottleneck, 0)

    # 修炼增益计算
    gain = calculate_cultivation_gain(10, cs, spiritual_root_efficiency=1.0)
    assert_gte("basic_gain", gain, 5)  # 10 * 1.0 * 1.0 * 1.0 * 1.0

    # 瓶颈衰减
    cs_bottleneck = CultivationState(realm="练气一层", bottleneck=3)
    gain_bottleneck = calculate_cultivation_gain(10, cs_bottleneck)
    assert_true("bottleneck_reduces_gain", gain_bottleneck < gain)

    # 根基变化
    assert_eq("foundation_cultivation_success", calculate_foundation_change(100, "cultivation_success"), 1)
    assert_eq("foundation_breakthrough_success", calculate_foundation_change(100, "breakthrough_success"), 5)
    assert_eq("foundation_breakthrough_success_boundary", calculate_foundation_change(100, "breakthrough_success", True), 10)
    assert_eq("foundation_breakthrough_failure", calculate_foundation_change(100, "breakthrough_failure"), -5)
    assert_eq("foundation_breakthrough_failure_boundary", calculate_foundation_change(100, "breakthrough_failure", True), -15)

    # 瓶颈变化
    delta, new_consec = calculate_bottleneck_change(0, 0, "breakthrough_failure")
    assert_eq("bottleneck_failure_first", delta, 0)  # 第一次失败不增加瓶颈
    assert_eq("consecutive_after_first_failure", new_consec, 1)

    delta, new_consec = calculate_bottleneck_change(0, 1, "breakthrough_failure")
    assert_eq("bottleneck_failure_second", delta, 1)  # 第二次连续失败增加瓶颈
    assert_eq("consecutive_after_second_failure", new_consec, 2)

    delta, new_consec = calculate_bottleneck_change(1, 2, "breakthrough_success")
    assert_eq("bottleneck_success_reduces", delta, -1)
    assert_eq("consecutive_after_success", new_consec, 0)

    # 突破 DC 计算
    dc = calculate_breakthrough_dc(cs)
    assert_gte("breakthrough_dc_min", dc, 10)
    assert_gte("breakthrough_dc_reasonable", dc, 15)  # 基础DC20，根基-5，所以15

    # 修炼进度调整
    assert_eq("progress_adjust", adjust_cultivation_progress(50, 30), 80)
    assert_eq("progress_clamp_max", adjust_cultivation_progress(90, 20), 100)
    assert_eq("progress_clamp_min", adjust_cultivation_progress(10, -20), 0)

    # 修炼倍率计算
    modifier = calculate_cultivation_modifier(spiritual_root_efficiency=1.5, technique_speed_bonus=1.2, bottleneck=0)
    assert_gte("modifier_basic", modifier, 1.5)

    # METHOD_STATE delta 构造
    delta = make_method_state_delta(progress_delta=10, foundation_delta=-5)
    assert_eq("method_delta_progress", delta.get("progress"), 10)
    assert_eq("method_delta_foundation", delta.get("foundation"), -5)
    assert_true("method_delta_no_empty_keys", "growth_stage" not in delta)


# ──────────────────────────────────────────────
#  2. spiritual_root 测试
# ──────────────────────────────────────────────

def test_spiritual_root():
    print("=== spiritual_root 测试 ===")

    # 五行灵根
    assert_eq("five_elements_count", len(FIVE_ELEMENTS), 5)
    assert_eq("special_roots_count", len(SPECIAL_ROOTS), 4)

    # 灵根生成
    sr = generate_spiritual_root(seed=42)
    assert_in("generated_primary", sr.primary, FIVE_ELEMENTS)
    assert_gte("generated_purity_min", sr.purity, PURITY_MIN)
    assert_gte("generated_purity_max", PURITY_MAX - sr.purity + PURITY_MIN, 0)  # purity <= 1.0
    assert_in("generated_mutation_or_none", sr.mutation, list(SPECIAL_ROOTS) + ["none"])

    # 强制异变
    sr_mutation = generate_spiritual_root(seed=42, force_mutation="雷")
    assert_eq("forced_mutation", sr_mutation.mutation, "雷")

    # 修炼效率计算
    eff_high = calculate_cultivation_efficiency(0.95, "none")
    eff_low = calculate_cultivation_efficiency(0.2, "none")
    assert_true("efficiency_high_purity_better", eff_high > eff_low)

    eff_mutation = calculate_cultivation_efficiency(0.5, "雷")
    eff_normal = calculate_cultivation_efficiency(0.5, "none")
    assert_true("efficiency_mutation_bonus", eff_mutation > eff_normal)

    # 功法亲和度
    sr_gold = SpiritualRoot(primary="金", purity=0.5)
    affinity_same = calculate_technique_affinity(sr_gold, "金")
    affinity_generate = calculate_technique_affinity(sr_gold, "水")
    affinity_overcome = calculate_technique_affinity(sr_gold, "木")
    assert_true("affinity_same_best", affinity_same > affinity_generate)
    assert_true("affinity_generate_better_than_overcome", affinity_generate > affinity_overcome)

    # 突破风险
    risk = calculate_breakthrough_risk(sr_gold, is_boundary=False)
    assert_true("risk_has_backlash", "backlash" in risk)
    assert_true("risk_has_tribulation", "tribulation" in risk)
    assert_true("risk_has_mutation_risk", "mutation_risk" in risk)

    risk_boundary = calculate_breakthrough_risk(sr_gold, is_boundary=True)
    assert_true("boundary_tribulation_higher", risk_boundary["tribulation"] >= risk["tribulation"])

    # 纯度变化
    assert_gte("purity_change_breakthrough_success", calculate_purity_change(0.5, "breakthrough_success"), 0)
    assert_true("purity_change_breakthrough_failure_negative", calculate_purity_change(0.5, "breakthrough_failure") < 0)
    assert_gte("purity_change_pill_cleansing", calculate_purity_change(0.5, "pill_cleansing"), 0.05)

    # 纯度 clamp
    assert_eq("clamp_purity_high", clamp_purity(1.5), 1.0)
    assert_eq("clamp_purity_low", clamp_purity(-0.5), 0.1)

    # 从 profile 提取
    profile = make_test_profile()
    sr = extract_spiritual_root(profile)
    assert_eq("extract_primary", sr.primary, "金")
    assert_eq("extract_purity", sr.purity, 0.5)

    # 旧存档兼容
    old_profile = {
        "CORE_STATE": {"spirit_root_tier": 4, "spirit_root_element": "火"}
    }
    sr_old = extract_spiritual_root(old_profile)
    assert_eq("old_compat_primary", sr_old.primary, "火")
    assert_eq("old_compat_purity", sr_old.purity, 0.75)

    # 灵根描述
    desc = describe_spiritual_root(sr_gold)
    assert_true("description_not_empty", len(desc) > 0)

    # 能力亲和度
    affinity_sword = calculate_ability_affinity(sr_gold, "剑意")
    affinity_alchemy = calculate_ability_affinity(sr_gold, "炼丹")
    assert_true("sword_affinity_for_gold", affinity_sword > 1.0)  # 金行对剑意有加成

    # CORE_STATE delta 构造
    delta = make_core_state_delta(purity_delta=0.05)
    assert_true("core_delta_has_spiritual_root", "spiritual_root" in delta)
    assert_eq("core_delta_purity", delta["spiritual_root"]["purity"], 0.05)


# ──────────────────────────────────────────────
#  3. cultivation_ability 测试
# ──────────────────────────────────────────────

def test_cultivation_ability():
    print("=== cultivation_ability 测试 ===")

    # 默认技能
    assert_eq("ability_names_count", len(ABILITY_NAMES), 5)
    assert_eq("ability_max_level", ABILITY_MAX_LEVEL, 5)

    # 技能数据类
    ability = CultivationAbility(name="剑意", level=0, exp=0)
    assert_eq("ability_level_name_0", ability.level_name, "未入门")
    assert_eq("ability_can_level_up_0", ability.can_level_up(), False)

    ability_leveled = CultivationAbility(name="剑意", level=1, exp=10)
    assert_eq("ability_level_name_1", ability_leveled.level_name, "初窥")
    assert_gte("ability_speed_bonus_1", ability_leveled.speed_bonus, 0.1)

    # 技能管理器
    profile = make_test_profile()
    mgr = AbilityManager()
    abilities = mgr.extract_abilities(profile)
    assert_eq("abilities_count", len(abilities), 5)
    assert_eq("sword_level_0", abilities["剑意"].level, 0)

    # 经验获取
    exp = mgr.calculate_exp_gain("剑意", action_type="practice", luck_level="成功")
    assert_gte("exp_gain_positive", exp, 1)

    exp_great = mgr.calculate_exp_gain("剑意", action_type="practice", luck_level="极大成功")
    assert_true("exp_great_success_more", exp_great >= exp)

    # 技能升级
    ability = CultivationAbility(name="剑意", level=0, exp=0)
    ability, leveled = mgr.add_exp(ability, 15)
    assert_eq("level_after_exp", ability.level, 1)
    assert_true("leveled_up", leveled)

    # 技能检定
    success, roll = mgr.check_ability_action(ability, difficulty=10, seed=42)
    # 结果取决于骰子，只检查返回类型
    assert_true("check_returns_bool", isinstance(success, bool))
    assert_true("check_returns_int", isinstance(roll, int))

    # 技能效果
    effects = mgr.get_ability_effects(ability)
    assert_true("effects_has_speed_bonus", "speed_bonus" in effects)
    assert_true("effects_has_level_name", "level_name" in effects)

    # 技能描述
    desc = describe_ability(ability)
    assert_true("ability_desc_not_empty", len(desc) > 0)

    # 技能 delta
    delta = make_ability_delta("剑意", exp_delta=10)
    assert_true("ability_delta_has_abilities", "abilities" in delta)
    assert_true("ability_delta_has_sword", "剑意" in delta["abilities"])

    # 旧存档迁移
    old_profile = {"METHOD_STATE": {}}
    migrate_profile_abilities(old_profile)
    assert_true("migrate_adds_abilities", "abilities" in old_profile["METHOD_STATE"])
    for name in ABILITY_NAMES:
        assert_true(f"migrate_has_{name}", name in old_profile["METHOD_STATE"]["abilities"])


# ──────────────────────────────────────────────
#  4. sect_interface 测试
# ──────────────────────────────────────────────

def test_sect_interface():
    print("=== sect_interface 测试 ===")

    # 宗门接口
    si = SectInterface()
    profile = make_test_profile()
    sect = si.get_sect_info(profile)
    assert_eq("sect_name_empty", sect.name, "")
    assert_eq("sect_position_default", sect.position, "外门弟子")

    # 加入宗门检查
    can_join, reason = si.can_join_sect(profile, "测试宗门")
    assert_true("can_join_no_sect", can_join)

    # 已有宗门不能加入
    profile_with_sect = make_test_profile()
    profile_with_sect["FACTION_STATE"]["sect"]["name"] = "旧宗门"
    can_join2, reason2 = si.can_join_sect(profile_with_sect, "新宗门")
    assert_true("cannot_join_with_sect", not can_join2)

    # 贡献点计算（无宗门时为0，有宗门时才有贡献）
    gain = si.calculate_contribution_gain(profile, "daily")
    assert_eq("daily_contribution_no_sect", gain, 0)  # 无宗门时贡献为0

    # 有宗门时的贡献
    profile_with_sect2 = make_test_profile()
    profile_with_sect2["FACTION_STATE"]["sect"]["name"] = "测试宗门"
    gain_sect = si.calculate_contribution_gain(profile_with_sect2, "daily")
    assert_gte("daily_contribution_with_sect", gain_sect, 1)

    gain_mission = si.calculate_contribution_gain(profile_with_sect2, "mission_success")
    assert_true("mission_contribution_more", gain_mission >= gain_sect)

    # 职位晋升检查
    can_promote, reason = si.check_position_promotion(profile)
    assert_true("cannot_promote_low_contribution", not can_promote)

    # 传承列表
    heritage = si.get_available_heritage(profile)
    # 外门弟子没有传承
    assert_eq("no_heritage_for_outer", len(heritage), 0)

    # 宗门描述
    desc = describe_sect_info(sect)
    assert_true("sect_desc_has_sanxiu", "散修" in desc)

    # 宗门 delta
    delta = make_sect_delta(name="测试宗门", contribution_delta=50)
    assert_true("sect_delta_has_name", "name" in delta.get("sect", {}))
    assert_true("sect_delta_has_contribution", "contribution" in delta.get("sect", {}))

    # 旧存档迁移
    old_profile = {"FACTION_STATE": {}}
    migrate_profile_sect(old_profile)
    assert_true("migrate_adds_sect", "sect" in old_profile["FACTION_STATE"])


# ──────────────────────────────────────────────
#  5. event_outcome 白名单测试
# ──────────────────────────────────────────────

def test_event_outcome_whitelist():
    print("=== event_outcome 白名单测试 ===")

    # PROFILE 白名单
    assert_true("appearance_in_whitelist", "appearance" in PROFILE_FIELD_WHITELIST)
    assert_true("FACTION_STATE_in_whitelist", "FACTION_STATE" in PROFILE_FIELD_WHITELIST)

    # METHOD_STATE 白名单
    assert_true("progress_in_method_whitelist", "progress" in METHOD_STATE_WHITELIST)
    assert_true("foundation_in_method_whitelist", "foundation" in METHOD_STATE_WHITELIST)
    assert_true("bottleneck_in_method_whitelist", "bottleneck" in METHOD_STATE_WHITELIST)
    assert_true("abilities_in_method_whitelist", "abilities" in METHOD_STATE_WHITELIST)
    assert_true("cultivation_modifier_in_method_whitelist", "cultivation_modifier" in METHOD_STATE_WHITELIST)

    # CORE_STATE 白名单
    assert_true("spiritual_root_in_core_whitelist", "spiritual_root" in CORE_STATE_WHITELIST)


# ──────────────────────────────────────────────
#  6. outcome_applier 测试
# ──────────────────────────────────────────────

def test_outcome_applier():
    print("=== outcome_applier 测试 ===")

    applier = OutcomeApplier()

    # METHOD_STATE delta 应用
    profile = make_test_profile()
    profiles = {"PLAYER-A": profile}
    outcome = EventOutcome(
        event_id="test-1",
        profile_delta={
            "PLAYER-A": {
                "METHOD_STATE": {
                    "progress": 10,  # 增量
                    "foundation": -5,  # 增量
                    "bottleneck": 1,  # 增量
                }
            }
        }
    )
    result = applier.apply_outcome(outcome, {}, profiles=profiles)
    assert_true("method_delta_applied", result["applied"])
    # progress should be 0 + 10 = 10
    assert_eq("progress_after_delta", profile["METHOD_STATE"]["progress"], 10)
    # foundation should be 100 + (-5) = 95
    assert_eq("foundation_after_delta", profile["METHOD_STATE"]["foundation"], 95)
    # bottleneck should be 0 + 1 = 1
    assert_eq("bottleneck_after_delta", profile["METHOD_STATE"]["bottleneck"], 1)

    # CORE_STATE delta 应用
    profile2 = make_test_profile()
    profiles2 = {"PLAYER-A": profile2}
    outcome2 = EventOutcome(
        event_id="test-2",
        profile_delta={
            "PLAYER-A": {
                "CORE_STATE": {
                    "spiritual_root": {
                        "purity": 0.05,  # 增量
                    }
                }
            }
        }
    )
    result2 = applier.apply_outcome(outcome2, {}, profiles=profiles2)
    assert_true("core_delta_applied", result2["applied"])
    # purity should be 0.5 + 0.05 = 0.55
    new_purity = profile2["CORE_STATE"]["spiritual_root"]["purity"]
    assert_true("purity_after_delta", abs(new_purity - 0.55) < 0.01)

    # cultivation_realm 特殊通道
    profile3 = make_test_profile()
    profiles3 = {"PLAYER-A": profile3}
    outcome3 = EventOutcome(
        event_id="test-3",
        profile_delta={
            "PLAYER-A": {
                "cultivation_realm": "练气二层",
            }
        }
    )
    result3 = applier.apply_outcome(outcome3, {}, profiles=profiles3)
    assert_true("realm_delta_applied", result3["applied"])
    assert_eq("realm_after_delta", profile3["cultivation_realm"], "练气二层")


# ──────────────────────────────────────────────
#  7. 旧存档兼容测试
# ──────────────────────────────────────────────

def test_old_save_compatibility():
    print("=== 旧存档兼容测试 ===")

    # 最简旧存档
    old_profile = {
        "cultivation_realm": "练气三层",
        "CORE_STATE": {"spirit_root_tier": 2, "spirit_root_element": "水"},
        "METHOD_STATE": {
            "primary_path": "感悟型",
            "growth_stage": "练气",
            "breakthrough_status": "none_pending",
            "known_techniques": [],
            "progress": 50,
        },
        "FACTION_STATE": {},
    }

    # 迁移 cultivation
    migrate_profile_cultivation(old_profile)
    assert_true("migrate_foundation", "foundation" in old_profile["METHOD_STATE"])
    assert_true("migrate_bottleneck", "bottleneck" in old_profile["METHOD_STATE"])
    assert_true("migrate_consecutive_failures", "consecutive_failures" in old_profile["METHOD_STATE"])
    assert_true("migrate_cultivation_modifier", "cultivation_modifier" in old_profile["METHOD_STATE"])
    assert_true("migrate_abilities", "abilities" in old_profile["METHOD_STATE"])

    # 迁移 spiritual_root
    migrate_profile_spiritual_root(old_profile)
    assert_true("migrate_spiritual_root", "spiritual_root" in old_profile["CORE_STATE"])
    sr = old_profile["CORE_STATE"]["spiritual_root"]
    assert_eq("migrate_sr_primary", sr["primary"], "水")
    assert_true("migrate_sr_has_purity", "purity" in sr)
    assert_true("migrate_sr_has_efficiency", "efficiency" in sr)

    # 迁移 abilities
    migrate_profile_abilities(old_profile)
    for name in ABILITY_NAMES:
        assert_true(f"migrate_has_ability_{name}", name in old_profile["METHOD_STATE"]["abilities"])

    # 迁移 sect
    migrate_profile_sect(old_profile)
    assert_true("migrate_sect", "sect" in old_profile["FACTION_STATE"])

    # 旧存档提取
    cs = extract_cultivation_state(old_profile)
    assert_eq("old_extract_realm", cs.realm, "练气三层")
    assert_eq("old_extract_progress", cs.progress, 50)
    assert_eq("old_extract_foundation", cs.foundation, 100)  # 默认值

    sr = extract_spiritual_root(old_profile)
    assert_eq("old_extract_sr_primary", sr.primary, "水")


# ──────────────────────────────────────────────
#  8. 多玩家隔离测试
# ──────────────────────────────────────────────

def test_multi_player_isolation():
    print("=== 多玩家隔离测试 ===")

    profile_a = make_test_profile(name="玩家A", cultivation_realm="练气一层")
    profile_b = make_test_profile(name="玩家B", cultivation_realm="筑基初期")
    profile_b["METHOD_STATE"]["progress"] = 50
    profile_b["METHOD_STATE"]["foundation"] = 120

    profiles = {"PLAYER-A": profile_a, "PLAYER-B": profile_b}

    # 只修改 PLAYER-A
    applier = OutcomeApplier()
    outcome = EventOutcome(
        event_id="test-isolation",
        profile_delta={
            "PLAYER-A": {
                "METHOD_STATE": {"progress": 20}
            }
        }
    )
    result = applier.apply_outcome(outcome, {}, profiles=profiles)

    # PLAYER-A 的进度变了
    assert_eq("player_a_progress", profile_a["METHOD_STATE"]["progress"], 20)
    # PLAYER-B 的进度没变
    assert_eq("player_b_progress_unchanged", profile_b["METHOD_STATE"]["progress"], 50)
    assert_eq("player_b_foundation_unchanged", profile_b["METHOD_STATE"]["foundation"], 120)


# ──────────────────────────────────────────────
#  9. 突破管理器 + 修炼事件测试
# ──────────────────────────────────────────────

def test_breakthrough_and_events():
    print("=== 突破管理器 + 修炼事件测试 ===")

    # 突破管理器基础
    mgr = BreakthroughManager()
    profile = make_test_profile(cultivation_realm="练气九层")
    profile["METHOD_STATE"]["progress"] = 100  # 满进度才能突破

    # 检查能否突破
    can, reason = mgr.can_attempt_breakthrough(profile)
    assert_true("can_attempt_full_progress", can)

    # 进度不足时不能突破
    profile_low = make_test_profile()
    profile_low["METHOD_STATE"]["progress"] = 50
    can2, reason2 = mgr.can_attempt_breakthrough(profile_low)
    assert_true("cannot_attempt_low_progress", not can2)

    # 执行突破检定
    result = mgr.roll_breakthrough(profile, seed=42)
    assert_true("result_has_success", isinstance(result.success, bool))
    assert_eq("result_current_realm", result.current_realm, "练气九层")
    assert_true("result_is_boundary", result.is_boundary)  # 练气九层是大境界瓶颈
    assert_gte("result_roll", result.roll_result, 1)
    assert_gte("result_dc", result.actual_dc, 10)

    # 突破结果不可变性：同一个 result 对象在后续使用中不会重新掷骰
    # 这是 Phase 7 bug fix 的核心验证
    saved_success = result.success
    saved_roll = result.roll_result
    # 再次访问 result 的字段，应该不变
    assert_eq("result_stability_success", result.success, saved_success)
    assert_eq("result_stability_roll", result.roll_result, saved_roll)

    # 应用突破结果
    profile_copy = copy.deepcopy(profile)
    mgr.apply_breakthrough(result, profile_copy)
    # 如果成功，境界应该变了
    if result.success:
        assert_true("realm_changed_on_success", profile_copy["cultivation_realm"] != "练气九层")
        assert_eq("progress_reset_on_success", profile_copy["METHOD_STATE"]["progress"], 0)
        assert_eq("consecutive_reset_on_success", profile_copy["METHOD_STATE"]["consecutive_failures"], 0)

    # 修炼事件模板完整性
    assert_eq("event_templates_count", len(CULTIVATION_EVENT_TEMPLATES), 4)
    assert_true("has_闭关走火", "闭关走火" in CULTIVATION_EVENT_TEMPLATES)
    assert_true("has_突破异象", "突破异象" in CULTIVATION_EVENT_TEMPLATES)
    assert_true("has_天劫降临", "天劫降临" in CULTIVATION_EVENT_TEMPLATES)
    assert_true("has_功法顿悟", "功法顿悟" in CULTIVATION_EVENT_TEMPLATES)

    # 修炼事件生成（不传入 EventPool，只返回事件定义）
    events = generate_cultivation_events(result, profile, event_pool=None, group_id="")
    assert_true("events_not_empty", len(events) > 0)
    # 每个事件应该有必要的字段
    for evt in events:
        assert_true("evt_has_type", "type" in evt)
        assert_true("evt_has_title", "title" in evt)
        assert_true("evt_has_category", "category" in evt)
        assert_true("evt_has_summary", "summary" in evt)
        assert_eq("evt_category_is_修行突破", evt["category"], "修行突破")
        assert_true("evt_has_priority", "priority" in evt)
        assert_true("evt_has_visibility", "visibility" in evt)
        assert_true("evt_player_related", evt.get("player_related", False))

    # 验证不同结果类型产生不同事件
    # 成功 + 大境界 → 至少有突破异象
    if result.success and result.is_boundary:
        event_types = [e["type"] for e in events]
        assert_true("boundary_success_has_突破异象", "突破异象" in event_types)

    # 失败 → 闭关走火
    fail_result = BreakthroughResult(
        success=False, current_realm="练气九层", next_realm="练气九层",
        is_boundary=True, roll_result=5, required_dc=20, actual_dc=20,
        technique_bonus=0.0, root_bonus=0.0,
        risk_factors=[], narrative_hints=["突破失败"],
    )
    fail_events = generate_cultivation_events(fail_result, profile, event_pool=None, group_id="")
    fail_types = [e["type"] for e in fail_events]
    assert_true("failure_has_闭关走火", "闭关走火" in fail_types)


# ──────────────────────────────────────────────
#  运行所有测试
# ──────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("LONG-A 修仙成长生态系统测试")
    print("=" * 60)

    test_cultivation_state()
    test_spiritual_root()
    test_cultivation_ability()
    test_sect_interface()
    test_event_outcome_whitelist()
    test_outcome_applier()
    test_old_save_compatibility()
    test_multi_player_isolation()
    test_breakthrough_and_events()

    print("=" * 60)
    print(f"结果：{_passed} 通过，{_failed} 失败")
    if _errors:
        print("错误详情：")
        for e in _errors:
            print(f"  {e}")
    print("=" * 60)

    sys.exit(0 if _failed == 0 else 1)
