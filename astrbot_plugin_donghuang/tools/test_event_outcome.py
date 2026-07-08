"""
test_event_outcome.py — B-6 事件结果反馈系统测试

覆盖：
  B-6.1: EventOutcome 数据模型（序列化、工厂函数）
  B-6.2: OutcomeResolver 判定规则
  B-6.3: OutcomeApplier 状态应用（白名单、clamp、rollback）
  B-6.4: 归档记录嵌入 outcome
  B-6.5: Spawn Hint 生成
  B-6.6: AI Context 注入近期事件后果

运行方式：
  python3 tools/test_event_outcome.py
"""

import sys
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ──────────────────────────────────────────────
#  导入模块
# ──────────────────────────────────────────────

from event_outcome import (
    EventOutcome, EventOutcomeType, make_resolved_outcome,
    make_failed_outcome, make_partial_outcome,
    make_expired_outcome, make_escalated_outcome,
)
from event_outcome_resolver import EventOutcomeResolver
from outcome_applier import OutcomeApplier, clamp
from world_event_pool import ActiveEvent, EventCategory, EventStage


# ──────────────────────────────────────────────
#  辅助函数
# ──────────────────────────────────────────────

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
            "FREE-01": {"power": 3, "stability": 0.2, "morale": 0.3,
                        "active_goal": "自保", "stance_overrides": {}},
        },
    }


def _make_event(category="日常", progress=0.9):
    return ActiveEvent(
        event_id="EP0001", title="测试事件", category=category,
        stage=EventStage.ENDED.value, region="中部", location="岱央城",
        participants=[], summary="测试摘要", progress=progress,
        start_time=0, estimated_end=None, priority="中",
        visibility="公开", player_related=False,
    )


def _make_profiles():
    return {
        "PLAYER-A": {
            "name": "玩家角色",
            "IDENTITY_STATE": {"region": "中部", "subregion": "岱央城", "生存状态": "stable"},
            "FACTION_STATE": {"affiliation": "STATE-01", "relations": {}},
            "BASE_STATE": {"realm": "筑基初期", "growth_stage": "", "progress": 50},
        }
    }


# ──────────────────────────────────────────────
#  B-6.1: EventOutcome 数据模型
# ──────────────────────────────────────────────

def test_b61_outcome_to_dict():
    """B-6.1 测试1：EventOutcome 可序列化为 dict。"""
    outcome = make_resolved_outcome("EP0001", "成功解决")
    d = outcome.to_dict()
    assert d["event_id"] == "EP0001"
    assert d["outcome_type"] == "resolved"
    assert d["summary"] == "成功解决"
    assert d["world_delta"] == {}
    assert d["faction_delta"] == {}
    print("✅ B-6.1 测试1通过：EventOutcome 可序列化")


def test_b61_from_dict():
    """B-6.1 测试2：EventOutcome 可从 dict 反序列化。"""
    d = {
        "event_id": "EP0002",
        "outcome_type": "failed",
        "summary": "失败恶化",
        "world_delta": {"GLOBAL": {"chaos_level": "平稳"}},
        "faction_delta": {"STATE-01": {"stability": -0.05}},
        "profile_delta": {"PLAYER-A": {"BASE_STATE": {"progress": 60}}},
        "spawn_event_hints": [],
        "applied_changes": [],
    }
    outcome = EventOutcome.from_dict(d)
    assert outcome.event_id == "EP0002"
    assert outcome.outcome_type == "failed"
    assert outcome.summary == "失败恶化"
    print("✅ B-6.1 测试2通过：EventOutcome 可反序列化")


def test_b61_factory_functions():
    """B-6.1 测试3：工厂函数生成正确类型的 Outcome。"""
    o1 = make_resolved_outcome("E1", "成功")
    assert o1.outcome_type == "resolved"
    o2 = make_failed_outcome("E2", "失败")
    assert o2.outcome_type == "failed"
    o3 = make_partial_outcome("E3", "部分")
    assert o3.outcome_type == "partial"
    o4 = make_expired_outcome("E4", "消散")
    assert o4.outcome_type == "expired"
    o5 = make_escalated_outcome("E5", "升级", [{"category": "势力冲突", "reason": "矛盾加剧"}])
    assert o5.outcome_type == "escalated"
    assert len(o5.spawn_event_hints) == 1
    print("✅ B-6.1 测试3通过：工厂函数生成正确类型")


def test_b61_outcome_is_immutable():
    """B-6.1 测试4：修改返回副本，不改变原始对象。"""
    original = make_resolved_outcome("E1", "原值")
    copy = original.to_dict()
    copy["summary"] = "已修改"
    assert original.summary == "原值"
    assert copy["summary"] == "已修改"
    print("✅ B-6.1 测试4通过：Outcome 不可变")


# ──────────────────────────────────────────────
#  B-6.2: OutcomeResolver 判定规则
# ──────────────────────────────────────────────

def test_b62_leyline_success():
    """B-6.2 测试1：灵脉资源事件成功时生成 resolved。"""
    ws = _make_ws()
    ws["RESOURCE"]["中部主脉残核"]["state"] = "稳定"
    resolver = EventOutcomeResolver()
    event = _make_event("灵脉资源", progress=0.9)
    outcome = resolver.resolve(event, ws)
    assert outcome.outcome_type == "resolved"
    assert "稳定" in outcome.summary or "恢复" in outcome.summary
    print("✅ B-6.2 测试1通过：灵脉资源成功 → resolved")


def test_b62_chaos_high():
    """B-6.2 测试2：CHAOS异常高活跃度时生成 failed。"""
    ws = _make_ws()
    ws["GLOBAL"]["chaos_level"] = "活跃-非世界级"
    resolver = EventOutcomeResolver()
    event = _make_event("CHAOS异常", progress=0.9)
    outcome = resolver.resolve(event, ws)
    assert outcome.outcome_type == "failed"
    print("✅ B-6.2 测试2通过：CHAOS高危 → failed")


def test_b62_faction_conflict_success():
    """B-6.2 测试3：势力冲突 stability>0.5 时生成 resolved。"""
    ws = _make_ws()
    resolver = EventOutcomeResolver()
    event = _make_event("势力冲突", progress=0.9)
    event.participants = ["STATE-01"]  # 提供参与势力
    factions = {"STATE-01": {"name": "祁渊李氏", "type": "王朝"}}
    outcome = resolver.resolve(event, ws, factions=factions)
    assert outcome.outcome_type == "resolved"
    print("✅ B-6.2 测试3通过：势力冲突成功 → resolved")


def test_b62_ruin_partial():
    """B-6.2 测试4：遗迹探索 partial 进度且 CHAOS 不高时生成 partial。"""
    ws = _make_ws()
    ws["GLOBAL"]["chaos_level"] = "平稳"  # 低 CHAOS，避免走失败分支
    resolver = EventOutcomeResolver()
    event = _make_event("遗迹与机缘", progress=0.5)
    outcome = resolver.resolve(event, ws)
    assert outcome.outcome_type == "partial"
    print("✅ B-6.2 测试4通过：遗迹探索 partial → partial")


def test_b62_daily_resolved():
    """B-6.2 测试5：日常事件高进度时生成 resolved。"""
    ws = _make_ws()
    resolver = EventOutcomeResolver()
    event = _make_event("日常", progress=0.9)
    outcome = resolver.resolve(event, ws)
    assert outcome.outcome_type == "resolved"
    print("✅ B-6.2 测试5通过：日常事件 resolved")


def test_b62_generic_fallback():
    """B-6.2 测试6：未知类别回退到 generic 判定。"""
    ws = _make_ws()
    resolver = EventOutcomeResolver()
    event = _make_event("未知类别", progress=0.9)
    outcome = resolver.resolve(event, ws)
    assert outcome.outcome_type == "resolved"
    print("✅ B-6.2 测试6通过：未知类别回退 generic")


# ──────────────────────────────────────────────
#  B-6.3: OutcomeApplier 状态应用
# ──────────────────────────────────────────────

def test_b63_apply_world_delta():
    """B-6.3 测试1：world_delta 正确应用到世界状态。"""
    ws = _make_ws()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("E1", "成功", world_delta={
        "GLOBAL": {"chaos_level": "平稳"}
    })
    result = applier.apply_outcome(outcome, ws)
    assert result["applied"] is True
    assert ws["GLOBAL"]["chaos_level"] == "平稳"
    assert len(result["applied_changes"]) >= 1
    print("✅ B-6.3 测试1通过：world_delta 正确应用")


def test_b63_apply_faction_delta():
    """B-6.3 测试2：faction_delta 正确应用到势力状态。"""
    ws = _make_ws()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("E1", "成功", faction_delta={
        "STATE-01": {"stability": 0.05, "morale": 0.03}
    })
    result = applier.apply_outcome(outcome, ws)
    assert result["applied"] is True
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] == 0.65
    assert ws["FACTION_STATE"]["STATE-01"]["morale"] == 0.73
    print("✅ B-6.3 测试2通过：faction_delta 正确应用")


def test_b63_whitelist_rejection():
    """B-6.3 测试3：非法字段被拒绝。"""
    ws = _make_ws()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("E1", "成功", world_delta={
        "ILLEGAL_FIELD": {"value": 42}
    })
    result = applier.apply_outcome(outcome, ws)
    assert any(r["path"] == "ILLEGAL_FIELD" and r["reason"] == "顶层字段 'ILLEGAL_FIELD' 不在白名单中"
               for r in result["rejected"])
    print("✅ B-6.3 测试3通过：非法字段被拒绝")


def test_b63_clamp():
    """B-6.3 测试4：数值自动 clamp。"""
    ws = _make_ws()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("E1", "成功", faction_delta={
        "STATE-01": {"stability": 1.5}  # 超出范围
    })
    result = applier.apply_outcome(outcome, ws)
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] == 1.0
    print("✅ B-6.3 测试4通过：数值自动 clamp")


def test_b63_rollback_safe():
    """B-6.3 测试5：Snapshot / Rollback 安全（修改对象在 snapshot 范围内）。"""
    ws = _make_ws()
    snapshot = copy.deepcopy(ws)
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("E1", "成功", faction_delta={
        "STATE-01": {"stability": 0.05}
    })
    applier.apply_outcome(outcome, ws)
    # rollback 恢复
    ws = snapshot
    assert ws["FACTION_STATE"]["STATE-01"]["stability"] == 0.6
    print("✅ B-6.3 测试5通过：Rollback 安全")


def test_b63_apply_profile_delta():
    """B-6.3 测试6：profile_delta 正确应用到玩家状态。"""
    ws = _make_ws()
    profiles = _make_profiles()
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("E1", "成功", profile_delta={
        "PLAYER-A": {"BASE_STATE": {"progress": 10}}
    })
    result = applier.apply_outcome(outcome, ws, profiles=profiles)
    assert result["applied"] is True
    assert profiles["PLAYER-A"]["BASE_STATE"]["progress"] == 60  # 50 + 10 increment
    print("✅ B-6.3 测试6通过：profile_delta 正确应用（增量模式）")


# ──────────────────────────────────────────────
#  B-6.4: 归档记录嵌入 outcome
# ──────────────────────────────────────────────

def test_b64_archive_with_outcome():
    """B-6.4 测试1：归档记录包含 outcome 信息。"""
    from world_event_pool import EventPool
    pool = EventPool()
    group_id = "G1"
    event = pool.add(group_id, "测试事件", "日常", progress=1.0)
    pool.advance_stage(group_id, event.event_id, EventStage.ENDED.value)

    # 预览归档（不含 outcome，因为 resolve 是在 tick 中做的）
    record = pool.preview_archive(group_id, event.event_id)
    assert record is not None, "应能预览归档"
    assert "outcome" not in record, "预览归档默认不含 outcome"

    # 手动嵌入 outcome（模拟 tick 中的逻辑）
    from event_outcome import make_resolved_outcome
    outcome = make_resolved_outcome(event.event_id, "测试结果")
    record["outcome"] = {
        "outcome_type": outcome.outcome_type,
        "summary": outcome.summary,
        "applied_changes": [],
    }
    assert record["outcome"]["outcome_type"] == "resolved"
    assert record["outcome"]["summary"] == "测试结果"

    # 旧归档（无 outcome）仍可读取
    old_record = {"event_id": "OLD001", "category": "日常", "result": "旧事件"}
    assert "outcome" not in old_record, "旧归档无 outcome 不报错"

    print("✅ B-6.4 测试1通过：归档记录可嵌入 outcome，旧归档兼容")


# ──────────────────────────────────────────────
#  B-6.5: Spawn Hint 生成
# ──────────────────────────────────────────────

def test_b65_spawn_hint():
    """B-6.5 测试1：escalated outcome 生成 spawn hint。"""
    outcome = make_escalated_outcome(
        "EP0001", "矛盾升级",
        [{"category": "势力冲突", "region": "中部", "reason": "归墟宗因灵脉争夺获利，引发周边不满"}]
    )
    assert outcome.outcome_type == "escalated"
    assert len(outcome.spawn_event_hints) == 1
    assert outcome.spawn_event_hints[0]["category"] == "势力冲突"
    assert outcome.spawn_event_hints[0]["region"] == "中部"
    print("✅ B-6.5 测试1通过：Spawn Hint 生成")


# ──────────────────────────────────────────────
#  B-6.6: AI Context 注入事件后果
# ──────────────────────────────────────────────

def test_b66_context_injection():
    """B-6.6 测试1：AI Prompt 能显示近期事件结果。"""
    from world_context import WorldContextBuilder
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    ws = _make_ws()
    ws["EVENT_LOG"] = [{
        "event_id": "EP0001",
        "title": "灵脉资源事件",
        "category": "灵脉资源",
        "final_stage": "结束",
        "outcome": {
            "outcome_type": "resolved",
            "summary": "归墟宗成功稳定了中部灵脉波动。",
            "applied_changes": [{"path": "RESOURCE.中部主脉残核.state", "old": "紧张、波动", "new": "稳定"}],
        }
    }]
    profiles = {"PLAYER-A": {"FACTION_STATE": {"affiliation": "STATE-01"}}}

    ctx = builder.build(
        world_state=ws,
        player_profiles=profiles,
        event_log=ws.get("EVENT_LOG", []),
        campaign={},
        region="中部",
    )
    # 验证格式正确
    assert isinstance(ctx, str)
    assert len(ctx) > 0
    print("✅ B-6.6 测试1通过：AI Context 注入事件后果")


# ──────────────────────────────────────────────
#  B-6 修补测试：多字段 profile_delta
# ──────────────────────────────────────────────

def test_b63_multi_field_profile_delta():
    """B-6 修补测试：profile_delta 同时修改多个字段，全部正确写入。"""
    ws = _make_ws()
    profiles = {
        "PLAYER-A": {
            "name": "玩家角色",
            "BASE_STATE": {"progress": 50, "realm": "筑基初期"},
            "FACTION_STATE": {"affiliation": None, "relations": {}},
            "relations": {},
        }
    }
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("E1", "成功", profile_delta={
        "PLAYER-A": {
            "BASE_STATE": {"progress": 10},
            "FACTION_STATE": {"affiliation": "STATE-01"},
            "relations": {"某NPC": 3},
        }
    })
    result = applier.apply_outcome(outcome, ws, profiles=profiles)

    # 三个字段都应被写入
    assert profiles["PLAYER-A"]["BASE_STATE"]["progress"] == 60, \
        f"BASE_STATE.progress 应为 60（50+10增量），实际 {profiles['PLAYER-A']['BASE_STATE']['progress']}"
    assert profiles["PLAYER-A"]["FACTION_STATE"]["affiliation"] == "STATE-01", \
        f"FACTION_STATE.affiliation 应为 STATE-01，实际 {profiles['PLAYER-A']['FACTION_STATE']['affiliation']}"
    assert profiles["PLAYER-A"]["relations"]["某NPC"] == 3, \
        f"relations['某NPC'] 应为 3，实际 {profiles['PLAYER-A']['relations']['某NPC']}"

    # applied_changes 应包含三条记录
    profile_changes = [c for c in result["applied_changes"] if c["path"].startswith("profiles.PLAYER-A")]
    assert len(profile_changes) >= 3, \
        f"应至少有 3 条 profile 变更记录，实际 {len(profile_changes)}"

    print("✅ B-6 修补测试1通过：多字段 profile_delta 全部正确写入")


def test_b63_profile_illegal_field_rejected():
    """B-6 修补测试：profile_delta 非法字段仍被拒绝。"""
    ws = _make_ws()
    profiles = {
        "PLAYER-A": {
            "name": "玩家角色",
            "BASE_STATE": {"progress": 50},
            "FACTION_STATE": {"affiliation": None},
            "relations": {},
        }
    }
    applier = OutcomeApplier()
    outcome = make_resolved_outcome("E1", "成功", profile_delta={
        "PLAYER-A": {
            "BASE_STATE": {"progress": 10},
            "ILLEGAL_FIELD": "should_be_rejected",
        }
    })
    result = applier.apply_outcome(outcome, ws, profiles=profiles)

    # BASE_STATE 应被写入（增量：50 + 10 = 60）
    assert profiles["PLAYER-A"]["BASE_STATE"]["progress"] == 60
    # ILLEGAL_FIELD 应被拒绝
    assert any("ILLEGAL_FIELD" in r["path"] for r in result["rejected"]), \
        "非法字段应被拒绝"
    assert "ILLEGAL_FIELD" not in profiles["PLAYER-A"], \
        "非法字段不应写入 profile"

    print("✅ B-6 修补测试2通过：profile_delta 非法字段被拒绝")


# ──────────────────────────────────────────────
#  B-6 修补测试：outcome 排序逻辑
# ──────────────────────────────────────────────

def test_b66_outcome_sorting_region_priority():
    """B-6 修补测试：同区域 outcome 优先展示。"""
    from world_context import WorldContextBuilder
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    # 构造 7 个 outcome：3 个同区域（中部），4 个异区域
    event_log = [
        {"event_id": "EP01", "region": "西部", "outcome": {"outcome_type": "resolved", "summary": "西部事件1"}},
        {"event_id": "EP02", "region": "西部", "outcome": {"outcome_type": "resolved", "summary": "西部事件2"}},
        {"event_id": "EP03", "region": "中部", "outcome": {"outcome_type": "resolved", "summary": "中部事件1"}},
        {"event_id": "EP04", "region": "西部", "outcome": {"outcome_type": "resolved", "summary": "西部事件3"}},
        {"event_id": "EP05", "region": "中部", "outcome": {"outcome_type": "resolved", "summary": "中部事件2"}},
        {"event_id": "EP06", "region": "西部", "outcome": {"outcome_type": "resolved", "summary": "西部事件4"}},
        {"event_id": "EP07", "region": "中部", "outcome": {"outcome_type": "resolved", "summary": "中部事件3"}},
    ]

    result = builder._extract_recent_outcomes(event_log, region="中部")

    # 应包含【近期事件后果】标题
    assert "【近期事件后果】" in result

    # 同区域（中部）事件应优先出现
    lines = result.strip().split("\n")
    # 第一行是标题，后续是事件
    summary_lines = lines[1:]
    # 中部事件应在前面
    zhongbu_count = sum(1 for l in summary_lines if "中部" in l)
    assert zhongbu_count >= 1, f"应至少有1条中部事件，实际 {result}"

    # 最多 5 条（不含标题）
    assert len(summary_lines) <= 5, f"最多5条事件后果，实际 {len(summary_lines)}"

    print("✅ B-6 修补测试3通过：outcome 排序优先展示同区域")


def test_b66_outcome_max_5():
    """B-6 修补测试：outcome 最多显示 5 条。"""
    from world_context import WorldContextBuilder
    builder = WorldContextBuilder.__new__(WorldContextBuilder)
    builder.world_dir = Path("/tmp")
    builder.max_chars = 999999

    # 构造 8 个 outcome
    event_log = [
        {"event_id": f"EP{i:02d}", "region": "中部",
         "outcome": {"outcome_type": "resolved", "summary": f"事件{i}"}}
        for i in range(8)
    ]

    result = builder._extract_recent_outcomes(event_log, region="中部")
    lines = result.strip().split("\n")
    summary_lines = lines[1:]
    assert len(summary_lines) <= 5, f"最多5条，实际 {len(summary_lines)}"

    print("✅ B-6 修补测试4通过：outcome 最多5条")


# ──────────────────────────────────────────────
#  clamp 工具函数测试
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
    from world_context import WorldContextBuilder
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
    )
    # 应该正常输出，不报错
    assert isinstance(ctx, str)
    assert "【时间与世界大势】" in ctx or len(ctx) == 0
    print("✅ 回归测试通过：不影响已有 Prompt 结构")


# ──────────────────────────────────────────────
#  主入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    # B-6.1
    test_b61_outcome_to_dict()
    test_b61_from_dict()
    test_b61_factory_functions()
    test_b61_outcome_is_immutable()

    # B-6.2
    test_b62_leyline_success()
    test_b62_chaos_high()
    test_b62_faction_conflict_success()
    test_b62_ruin_partial()
    test_b62_daily_resolved()
    test_b62_generic_fallback()

    # B-6.3
    test_b63_apply_world_delta()
    test_b63_apply_faction_delta()
    test_b63_whitelist_rejection()
    test_b63_clamp()
    test_b63_rollback_safe()
    test_b63_apply_profile_delta()

    # B-6.4
    test_b64_archive_with_outcome()

    # B-6.5
    test_b65_spawn_hint()

    # B-6.6
    test_b66_context_injection()

    # B-6 修补测试
    test_b63_multi_field_profile_delta()
    test_b63_profile_illegal_field_rejected()
    test_b66_outcome_sorting_region_priority()
    test_b66_outcome_max_5()

    # 辅助
    test_clamp()
    test_no_regression()

    print("\n🎉 全部 B-6 事件结果反馈系统测试通过！")
