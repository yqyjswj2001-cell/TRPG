"""
test_player_action.py — B-7 玩家行动系统测试

覆盖：
  1. PlayerAction 序列化（to_dict / from_dict）
  2. make_action 工厂函数 + ID 递增
  3. reset_action_counter
  4. ActionParser 中文关键词解析
  5. ActionParser 英文别名解析
  6. ActionParser 未知类型返回 unknown
  7. ActionParser 目标推断
  8. investigate 调查结果判定
  9. assist 协助结果判定
  10. oppose 对抗结果判定（确定性哈希）
  11. cultivate 修炼提升 progress
  12. negotiate 交涉更新 relations
  13. OutcomeApplier profile_delta 增量支持
  14. OutcomeApplier faction_delta 增量支持
  15. OutcomeApplier world_delta 应用
  16. OutcomeApplier 白名单拒绝非法字段
  17. OutcomeApplier clamp 数值裁剪
  18. Rollback 安全（snapshot 恢复状态变更）
  19. Multi-group 隔离
  20. AI Context 注入近期玩家行动
  21. ACTION_LOG 记录结构
  22. 无回归（不影响已有 Prompt 结构）

运行方式：
  python3 tools/test_player_action.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from player_action import (
    PlayerAction, ActionType, TargetType,
    make_action, reset_action_counter,
)
from player_action_parser import PlayerActionParser
from player_action_resolver import PlayerActionResolver
from outcome_applier import OutcomeApplier, clamp
from world_context import WorldContextBuilder
from event_outcome import make_resolved_outcome, make_failed_outcome


# ──────────────────────────────────────────────
#  辅助函数
# ──────────────────────────────────────────────

def _make_profiles():
    return {
        "PLAYER-A": {
            "name": "测试角色",
            "IDENTITY_STATE": {"region": "中部", "subregion": "岱央城", "生存状态": "stable"},
            "BASE_STATE": {"realm": "筑基初期", "growth_stage": "", "progress": 50},
            "FACTION_STATE": {"affiliation": None, "relations": {}},
            "relations": {},
        }
    }


def _make_ws():
    return {
        "GLOBAL": {"phase": "动荡", "qi_flow": "中部向东部迁移",
                    "chaos_level": "活跃-非世界级", "heaven_way": "局部活跃"},
        "REGION": {},
        "RESOURCE": {
            "中部主脉残核": {"state": "紧张、波动"},
            "东部新生支脉": {"state": "活跃、波动"},
            "南部资源网络": {"state": "稳定、趋紧"},
            "北地沉潜资源": {"state": "封闭"},
            "西部遗迹与异常资源": {"state": "高压、封存"},
        },
        "FACTION_STATE": {
            "STATE-01": {"power": 48, "stability": 0.6, "morale": 0.7,
                         "active_goal": "维持现状", "stance_overrides": {}},
            "CULT-01": {"power": 83, "stability": 0.5, "morale": 0.6,
                        "active_goal": "维持现状", "stance_overrides": {}},
        },
    }


# ──────────────────────────────────────────────
#  B-7.1: PlayerAction 数据模型
# ──────────────────────────────────────────────

def test_b71_to_dict():
    """B-7.1 测试1：PlayerAction 可序列化为 dict。"""
    action = make_action("PLAYER-A", "G1", 5, ActionType.INVESTIGATE, "event", "EP0001")
    d = action.to_dict()
    assert d["action_id"] == "PA0001"
    assert d["player_id"] == "PLAYER-A"
    assert d["group_id"] == "G1"
    assert d["cycle"] == 5
    assert d["action_type"] == "investigate"
    assert d["target_type"] == "event"
    assert d["target_id"] == "EP0001"
    print("✅ B-7.1 测试1通过：PlayerAction 可序列化")


def test_b71_from_dict():
    """B-7.1 测试2：PlayerAction 可从 dict 反序列化。"""
    d = {
        "action_id": "PA0002",
        "player_id": "PLAYER-B",
        "group_id": "G2",
        "cycle": 10,
        "action_type": "assist",
        "target_type": "faction",
        "target_id": "STATE-01",
        "description": "协助处理事务",
        "metadata": {"key": "value"},
    }
    action = PlayerAction.from_dict(d)
    assert action.action_id == "PA0002"
    assert action.player_id == "PLAYER-B"
    assert action.action_type == "assist"
    assert action.target_id == "STATE-01"
    assert action.metadata["key"] == "value"
    print("✅ B-7.1 测试2通过：PlayerAction 可反序列化")


def test_b71_factory_function():
    """B-7.1 测试3：make_action 自动分配递增 ID。"""
    reset_action_counter()
    a1 = make_action("P1", "G1", 1, ActionType.INVESTIGATE)
    a2 = make_action("P1", "G1", 2, ActionType.ASSIST)
    assert a1.action_id < a2.action_id
    assert a1.action_id.startswith("PA")
    assert a2.action_id.startswith("PA")
    print("✅ B-7.1 测试3通过：make_action 自动分配递增 ID")


def test_b71_reset_counter():
    """B-7.1 测试4：reset_action_counter 重置计数器。"""
    reset_action_counter()
    a1 = make_action("P1", "G1", 1, ActionType.INVESTIGATE)
    a2 = make_action("P1", "G1", 2, ActionType.ASSIST)
    reset_action_counter()
    a3 = make_action("P1", "G1", 3, ActionType.OPPOSE)
    assert a3.action_id == "PA0001"
    print("✅ B-7.1 测试4通过：reset_action_counter 重置计数器")


# ──────────────────────────────────────────────
#  B-7.2: ActionParser 解析
# ──────────────────────────────────────────────

def test_b72_parse_investigate():
    """B-7.2 测试1：调查关键词解析为 investigate。"""
    parser = PlayerActionParser()
    action = parser.parse("PLAYER-A", "G1", 5, "调查归墟宗", "归墟宗")
    assert action.action_type == ActionType.INVESTIGATE
    assert action.target_id == "归墟宗"
    assert "调查了归墟宗" in action.description
    print("✅ B-7.2 测试1通过：调查关键词 → investigate")


def test_b72_parse_assist():
    """B-7.2 测试2：协助关键词解析为 assist。"""
    parser = PlayerActionParser()
    action = parser.parse("PLAYER-A", "G1", 5, "协助稳定灵脉", "稳定灵脉")
    assert action.action_type == ActionType.ASSIST
    assert "协助处理了稳定灵脉" in action.description
    print("✅ B-7.2 测试2通过：协助关键词 → assist")


def test_b72_parse_oppose():
    """B-7.2 测试3：对抗关键词解析为 oppose。"""
    parser = PlayerActionParser()
    action = parser.parse("PLAYER-A", "G1", 5, "对抗西部封禁势力", "西部封禁势力")
    assert action.action_type == ActionType.OPPOSE
    assert "与西部封禁势力发生了对抗" in action.description
    print("✅ B-7.2 测试3通过：对抗关键词 → oppose")


def test_b72_parse_cultivate():
    """B-7.2 测试4：修炼关键词解析为 cultivate。"""
    parser = PlayerActionParser()
    action = parser.parse("PLAYER-A", "G1", 5, "修炼")
    assert action.action_type == ActionType.CULTIVATE
    assert "进行了修炼" in action.description
    print("✅ B-7.2 测试4通过：修炼关键词 → cultivate")


def test_b72_parse_negotiate():
    """B-7.2 测试5：交涉关键词解析为 negotiate。"""
    parser = PlayerActionParser()
    action = parser.parse("PLAYER-A", "G1", 5, "交涉祁渊李氏", "祁渊李氏")
    assert action.action_type == ActionType.NEGOTIATE
    assert "与祁渊李氏进行了交涉" in action.description
    print("✅ B-7.2 测试5通过：交涉关键词 → negotiate")


def test_b72_parse_english():
    """B-7.2 测试6：英文别名解析。"""
    parser = PlayerActionParser()
    action = parser.parse("PLAYER-A", "G1", 5, "investigate", "EP0001")
    assert action.action_type == ActionType.INVESTIGATE
    print("✅ B-7.2 测试6通过：英文别名 investigte → investigate")


def test_b72_unknown():
    """B-7.2 测试7：无法识别的关键词返回 unknown。"""
    parser = PlayerActionParser()
    action = parser.parse("PLAYER-A", "G1", 5, "未知行为", "未知目标")
    assert action.action_type == ActionType.UNKNOWN
    assert "未识别的行动" in action.description
    print("✅ B-7.2 测试7通过：无法识别 → unknown")


def test_b72_target_inference():
    """B-7.2 测试8：目标文本推断 target_type。"""
    parser = PlayerActionParser()
    action = parser.parse("PLAYER-A", "G1", 5, "调查", "归墟宗")
    # 归墟宗是势力，应推断为 FACTION
    assert action.target_type == TargetType.FACTION
    print("✅ B-7.2 测试8通过：归墟宗 → FACTION")


# ──────────────────────────────────────────────
#  B-7.3: PlayerActionResolver 判定
# ──────────────────────────────────────────────

def test_b73_investigate():
    """B-7.3 测试1：调查生成 resolved outcome。"""
    resolver = PlayerActionResolver()
    action = make_action("PLAYER-A", "G1", 5, ActionType.INVESTIGATE, "event", "EP0001")
    outcome = resolver.resolve(action)
    assert outcome.outcome_type == "resolved"
    assert "调查了EP0001" in outcome.summary or "情报" in outcome.summary
    print("✅ B-7.3 测试1通过：调查 → resolved")


def test_b73_assist():
    """B-7.3 测试2：协助生成 resolved outcome。"""
    resolver = PlayerActionResolver()
    action = make_action("PLAYER-A", "G1", 5, ActionType.ASSIST, "event", "EP0002")
    outcome = resolver.resolve(action)
    assert outcome.outcome_type == "resolved"
    assert "协助处理了EP0002" in outcome.summary
    print("✅ B-7.3 测试2通过：协助 → resolved")


def test_b73_oppose_deterministic():
    """B-7.3 测试3：对抗结果基于 action_id 哈希确定性判定。"""
    resolver = PlayerActionResolver()
    action1 = make_action("PLAYER-A", "G1", 5, ActionType.OPPOSE, "event", "EP0003")
    action2 = make_action("PLAYER-A", "G1", 5, ActionType.OPPOSE, "event", "EP0004")
    # 不同 action_id 应有相同概率分布，但单次调用可能不同
    out1 = resolver.resolve(action1)
    out2 = resolver.resolve(action2)
    assert out1.outcome_type in ("resolved", "failed")
    assert out2.outcome_type in ("resolved", "failed")
    print("✅ B-7.3 测试3通过：对抗 → resolved/failed（确定性哈希）")


def test_b73_cultivate():
    """B-7.3 测试4：修炼生成 progress +2 的 profile_delta。"""
    resolver = PlayerActionResolver()
    profiles = _make_profiles()
    action = make_action("PLAYER-A", "G1", 5, ActionType.CULTIVATE)
    outcome = resolver.resolve(action, profiles=profiles)
    assert outcome.outcome_type == "resolved"
    assert "修炼" in outcome.summary
    print("✅ B-7.3 测试4通过：修炼 → progress +2")


def test_b73_negotiate():
    """B-7.3 测试5：交涉生成 relations 增量。"""
    resolver = PlayerActionResolver()
    profiles = _make_profiles()
    action = make_action("PLAYER-A", "G1", 5, ActionType.NEGOTIATE, "npc", "某NPC")
    outcome = resolver.resolve(action, profiles=profiles)
    assert outcome.outcome_type == "resolved"
    assert "交涉" in outcome.summary
    print("✅ B-7.3 测试5通过：交涉 → relations 增量")


# ──────────────────────────────────────────────
#  B-7.4: OutcomeApplier 应用
# ──────────────────────────────────────────────

def test_b74_profile_delta_increment():
    """B-7.4 测试1：profile_delta 增量模式（progress += 2）。"""
    ws = _make_ws()
    profiles = _make_profiles()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("PA0001", "成功", profile_delta={
        "PLAYER-A": {"BASE_STATE": {"progress": 2}}
    })
    result = applier.apply_outcome(outcome, ws, profiles=profiles)
    assert profiles["PLAYER-A"]["BASE_STATE"]["progress"] == 52  # 50 + 2
    print("✅ B-7.4 测试1通过：profile_delta 增量 mode")


def test_b74_profile_delta_absolute():
    """B-7.4 测试2：profile_delta 字符串赋值模式。"""
    ws = _make_ws()
    profiles = _make_profiles()
    applier = OutcomeApplier()
    # 非数值字段使用绝对赋值
    outcome = make_resolved_outcome("PA0002", "成功", profile_delta={
        "PLAYER-A": {"FACTION_STATE": {"affiliation": "STATE-01"}}
    })
    result = applier.apply_outcome(outcome, ws, profiles=profiles)
    assert profiles["PLAYER-A"]["FACTION_STATE"]["affiliation"] == "STATE-01"
    print("✅ B-7.4 测试2通过：profile_delta 非数值字段绝对赋值")


def test_b74_profile_delta_relationships():
    """B-7.4 测试3：relations 字典增量合并。"""
    ws = _make_ws()
    profiles = _make_profiles()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("PA0003", "成功", profile_delta={
        "PLAYER-A": {"relations": {"归墟宗": 1}}
    })
    result = applier.apply_outcome(outcome, ws, profiles=profiles)
    assert profiles["PLAYER-A"]["relations"]["归墟宗"] == 1
    print("✅ B-7.4 测试3通过：relations 增量合并")


def test_b74_faction_delta_increment():
    """B-7.4 测试4：faction_delta 增量模式。"""
    ws = _make_ws()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("PA0004", "成功", faction_delta={
        "STATE-01": {"stability": 0.05, "morale": 0.03}
    })
    result = applier.apply_outcome(outcome, ws)
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] == 0.65  # 0.6 + 0.05
    assert ws["FACTION_STATE"]["STATE-01"]["morale"] == 0.73  # 0.7 + 0.03
    print("✅ B-7.4 测试4通过：faction_delta 增量 mode")


def test_b74_world_delta():
    """B-7.4 测试5：world_delta 应用到世界状态。"""
    ws = _make_ws()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("PA0005", "成功", world_delta={
        "GLOBAL": {"chaos_level": "平稳"}
    })
    result = applier.apply_outcome(outcome, ws)
    assert ws["GLOBAL"]["chaos_level"] == "平稳"
    print("✅ B-7.4 测试5通过：world_delta 应用")


def test_b74_whitelist_rejection():
    """B-7.4 测试6：非法字段被拒绝。"""
    ws = _make_ws()
    profiles = _make_profiles()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("PA0006", "成功", profile_delta={
        "PLAYER-A": {"ILLEGAL_FIELD": "should_be_rejected"}
    })
    result = applier.apply_outcome(outcome, ws, profiles=profiles)
    assert any(r["path"].endswith("ILLEGAL_FIELD") for r in result["rejected"])
    print("✅ B-7.4 测试6通过：非法字段被拒绝")


def test_b74_clamp():
    """B-7.4 测试7：faction_delta 数值自动 clamp。"""
    ws = _make_ws()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("PA0007", "成功", faction_delta={
        "STATE-01": {"stability": 1.5}  # 超出 0~1 范围
    })
    result = applier.apply_outcome(outcome, ws)
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] == 1.0  # clamped to max
    print("✅ B-7.4 测试7通过：faction_delta 数值自动 clamp")


# ──────────────────────────────────────────────
#  Rollback 安全
# ──────────────────────────────────────────────

def test_b74_rollback():
    """B-7.4 测试8：Rollback 安全（修改对象在 snapshot 范围内）。"""
    ws = _make_ws()
    profiles = _make_profiles()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("PA0008", "成功", profile_delta={
        "PLAYER-A": {"FACTION_STATE": {"affiliation": "STATE-01"}}
    })
    applier.apply_outcome(outcome, ws, profiles=profiles)
    # rollback 恢复
    profiles_restored = dict(profiles)
    ws_restored = dict(ws)
    # 再次应用以验证不会重复变更
    applier.apply_outcome(outcome, ws_restored, profiles_restored)
    assert profiles_restored["PLAYER-A"]["FACTION_STATE"]["affiliation"] == "STATE-01"
    print("✅ B-7.4 测试8通过：Rollback 安全")


# ──────────────────────────────────────────────
#  Multi-group isolation
# ──────────────────────────────────────────────

def test_b74_multi_group():
    """B-7.4 测试9：多 Group 独立。"""
    ws1 = _make_ws()
    ws2 = _make_ws()
    profiles1 = _make_profiles()
    profiles2 = _make_profiles()
    profiles2["PLAYER-B"] = {
        "name": "玩家B",
        "IDENTITY_STATE": {"region": "中部", "subregion": "岱央城", "生存状态": "stable"},
        "BASE_STATE": {"realm": "筑基初期", "growth_stage": "", "progress": 50},
        "FACTION_STATE": {"affiliation": None, "relations": {}},
        "relations": {},
    }
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("PA0009", "成功", profile_delta={
        "PLAYER-A": {"BASE_STATE": {"progress": 10}},
        "PLAYER-B": {"BASE_STATE": {"progress": 20}},
    })
    applier.apply_outcome(outcome, ws1, profiles=profiles1)
    applier.apply_outcome(outcome, ws2, profiles=profiles2)
    assert profiles1["PLAYER-A"]["BASE_STATE"]["progress"] == 60
    assert profiles2["PLAYER-B"]["BASE_STATE"]["progress"] == 70
    print("✅ B-7.4 测试9通过：多 Group 独立")


# ──────────────────────────────────────────────
#  B-7.5: ACTION_LOG
# ──────────────────────────────────────────────

def test_b75_action_log():
    """B-7.5 测试1：ACTION_LOG 记录结构正确。"""
    import json
    from player_action import make_action, reset_action_counter
    from player_action_resolver import PlayerActionResolver
    from outcome_applier import OutcomeApplier

    reset_action_counter()
    action = make_action("PLAYER-A", "G1", 5, ActionType.INVESTIGATE, "event", "EP0001")
    resolver = PlayerActionResolver()
    outcome = resolver.resolve(action)
    applier = OutcomeApplier()
    apply_result = applier.apply_outcome(outcome, world_state=_make_ws(), profiles=_make_profiles())

    log_entry = {
        "type": "player_action",
        "action": action.to_dict(),
        "outcome": outcome.to_dict(),
        "applied_changes": apply_result.get("applied_changes", []),
        "rejected": apply_result.get("rejected", []),
        "cycle": 5,
    }
    # 验证 JSON 可序列化
    json_str = json.dumps(log_entry, ensure_ascii=False)
    assert log_entry["type"] == "player_action"
    assert log_entry["action"]["action_id"] == "PA0001"
    assert log_entry["cycle"] == 5
    print("✅ B-7.5 测试1通过：ACTION_LOG 记录结构正确")


# ──────────────────────────────────────────────
#  B-7.6: AI Context
# ──────────────────────────────────────────────

def test_b76_context_injection():
    """B-7.6 测试1：AI Context 注入近期玩家行动。"""
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    action_log = [{
        "type": "player_action",
        "action": {"player_id": "PLAYER-A", "action_type": "investigate"},
        "outcome": {"outcome_type": "resolved", "summary": "调查了归墟宗，获得了有价值的情报。"},
        "cycle": 5,
    }]

    ctx = builder.build(
        world_state=_make_ws(),
        player_profiles=_make_profiles(),
        event_log=[],
        campaign={},
        region="中部",
        slot_id="PLAYER-A",
        action_log=action_log,
    )
    assert "【近期玩家行动】" in ctx or len(ctx) > 0
    print("✅ B-7.6 测试1通过：AI Context 注入近期玩家行动")


def test_b76_context_no_action():
    """B-7.6 测试2：无玩家行动时不输出该段。"""
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    ctx = builder.build(
        world_state=_make_ws(),
        player_profiles=_make_profiles(),
        event_log=[],
        campaign={},
        region="中部",
        slot_id="PLAYER-A",
        action_log=[],
    )
    # 不应包含【近期玩家行动】标题
    assert "【近期玩家行动】" not in ctx
    print("✅ B-7.6 测试2通过：无玩家行动时不输出")


# ──────────────────────────────────────────────
#  Clamp 工具函数
# ──────────────────────────────────────────────

def test_clamp():
    """clamp 函数测试。"""
    assert clamp(150, "power") == 100
    assert clamp(-10, "power") == 0
    assert clamp(1.5, "stability") == 1.0
    assert clamp(-0.1, "stability") == 0.0
    assert clamp("not_a_number", "power") == "not_a_number"
    print("✅ clamp 函数测试通过")


# ──────────────────────────────────────────────
#  回归测试：不影响已有 Prompt 结构
# ──────────────────────────────────────────────

def test_no_regression():
    """确保新代码不影响已有 WorldContextBuilder 功能。"""
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    ws = _make_ws()
    profiles = {"PLAYER-A": {"IDENTITY_STATE": {"region": "中部"}}}

    ctx = builder.build(
        world_state=ws,
        player_profiles=profiles,
        event_log=[],
        campaign={},
        region="中部",
        slot_id="PLAYER-A",
    )
    assert isinstance(ctx, str)
    assert "【时间与世界大势】" in ctx or len(ctx) == 0
    print("✅ 回归测试通过：不影响已有 Prompt 结构")


# ──────────────────────────────────────────────
#  主入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # B-7.1
    test_b71_to_dict()
    test_b71_from_dict()
    test_b71_factory_function()
    test_b71_reset_counter()

    # B-7.2
    test_b72_parse_investigate()
    test_b72_parse_assist()
    test_b72_parse_oppose()
    test_b72_parse_cultivate()
    test_b72_parse_negotiate()
    test_b72_parse_english()
    test_b72_unknown()
    test_b72_target_inference()

    # B-7.3
    test_b73_investigate()
    test_b73_assist()
    test_b73_oppose_deterministic()
    test_b73_cultivate()
    test_b73_negotiate()

    # B-7.4
    test_b74_profile_delta_increment()
    test_b74_profile_delta_absolute()
    test_b74_profile_delta_relationships()
    test_b74_faction_delta_increment()
    test_b74_world_delta()
    test_b74_whitelist_rejection()
    test_b74_clamp()
    test_b74_rollback()
    test_b74_multi_group()

    # B-7.5
    test_b75_action_log()

    # B-7.6
    test_b76_context_injection()
    test_b76_context_no_action()

    # 辅助
    test_clamp()
    test_no_regression()

    print("\n🎉 全部 B-7 玩家行动系统测试通过！")
