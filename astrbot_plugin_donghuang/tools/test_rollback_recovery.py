"""
test_rollback_recovery.py — rollback 恢复测试

验证 snapshot 包含 EventPool 数据，rollback 能恢复 EventPool 状态：
  1. 正常 snapshot 包含 event_pool
  2. rollback 恢复 EventPool progress、stage、活跃事件数量
  3. 旧 snapshot 没有 event_pool 字段时兼容处理

运行方式：
  python tools/test_rollback_recovery.py
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_event_pool import EventPool, EventStage, EventCategory, EventPriority, EventVisibility


def simulate_snapshot(pool: EventPool, group_id: str, extra_state: dict = None) -> dict:
    """模拟 main.py 的 _snapshot_group_state，包含 event_pool。"""
    snapshot = {
        "world_state": {"GLOBAL": {"phase": "灵气东移"}},
        "player_profiles": {},
        "event_log": [],
        "campaign": {"state": "active", "cycle": 1},
        "event_pool": json.loads(json.dumps(pool.dump(group_id))),
    }
    if extra_state:
        snapshot.update(extra_state)
    return snapshot


def simulate_rollback(pool: EventPool, group_id: str, snapshot: dict) -> None:
    """模拟 main.py 的 rollback 恢复逻辑。"""
    # 清空当前池
    pool.clear(group_id)
    # 从 snapshot 恢复（兼容旧格式）
    saved_pool = snapshot.get("event_pool", [])
    if saved_pool:
        pool.load(group_id, saved_pool)


def test_snapshot_contains_event_pool():
    """测试1：snapshot 包含 event_pool 数据"""
    pool = EventPool()
    group_id = "test_group1"

    pool.add(
        group_id=group_id,
        title="灵气东移加速",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="东部",
        location="启阳",
        progress=0.15,
        priority=EventPriority.HIGH.value,
        visibility=EventVisibility.PUBLIC.value,
    )
    pool.add(
        group_id=group_id,
        title="西部封印松动",
        category=EventCategory.FACTION_CONFLICT.value,
        region="西部",
        location="裂川",
        progress=0.45,
        priority=EventPriority.CRITICAL.value,
        visibility=EventVisibility.REGIONAL.value,
    )

    snapshot = simulate_snapshot(pool, group_id)
    assert "event_pool" in snapshot, "snapshot 应包含 event_pool 字段"
    assert len(snapshot["event_pool"]) == 2, "snapshot 中应有 2 条事件"

    print("✅ 测试1通过：snapshot 包含 event_pool")


def test_rollback_restores_progress():
    """测试2：rollback 恢复 EventPool progress"""
    pool = EventPool()
    group_id = "test_group2"

    # 创建事件，progress=0.15
    event = pool.add(
        group_id=group_id,
        title="灵气东移",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="东部",
        progress=0.15,
    )

    # 拍快照
    snapshot = simulate_snapshot(pool, group_id)

    # 推进 progress
    pool.update_progress(group_id, event.event_id, 0.65)
    assert pool.get(group_id, event.event_id).progress == 0.65

    # rollback
    simulate_rollback(pool, group_id, snapshot)

    # 检查恢复
    restored = pool.get(group_id, event.event_id)
    assert restored is not None, "rollback 后事件应存在"
    assert restored.progress == 0.15, f"rollback 后 progress 应恢复到 0.15，实际 {restored.progress}"

    print("✅ 测试2通过：rollback 恢复 progress")


def test_rollback_restores_stage():
    """测试3：rollback 恢复 EventPool stage"""
    pool = EventPool()
    group_id = "test_group3"

    event = pool.add(
        group_id=group_id,
        title="遗迹异动",
        category=EventCategory.RUIN_OPPORTUNITY.value,
        region="中部",
        progress=0.15,
    )
    # 阶段应为萌芽
    assert event.stage == EventStage.SPROUT.value

    # 拍快照
    snapshot = simulate_snapshot(pool, group_id)

    # 推进到扩散
    pool.update_progress(group_id, event.event_id, 0.3)
    pool.advance_stage(group_id, event.event_id, EventStage.SPREAD.value)
    assert pool.get(group_id, event.event_id).stage == EventStage.SPREAD.value

    # rollback
    simulate_rollback(pool, group_id, snapshot)

    # 检查恢复
    restored = pool.get(group_id, event.event_id)
    assert restored is not None
    assert restored.stage == EventStage.SPROUT.value, f"rollback 后 stage 应恢复到萌芽，实际 {restored.stage}"

    print("✅ 测试3通过：rollback 恢复 stage")


def test_rollback_restores_count():
    """测试4：rollback 恢复活跃事件数量"""
    pool = EventPool()
    group_id = "test_group4"

    # 创建 3 条事件
    pool.add(group_id=group_id, title="事件A", category=EventCategory.DAILY.value, region="中部")
    pool.add(group_id=group_id, title="事件B", category=EventCategory.LEYLINE_RESOURCE.value, region="东部")
    pool.add(group_id=group_id, title="事件C", category=EventCategory.FACTION_CONFLICT.value, region="西部")

    snapshot = simulate_snapshot(pool, group_id)
    assert len(pool.list_all(group_id)) == 3

    # 再添加 2 条
    pool.add(group_id=group_id, title="事件D", category=EventCategory.CHAOS_ANOMALY.value, region="西部")
    pool.add(group_id=group_id, title="事件E", category=EventCategory.RUIN_OPPORTUNITY.value, region="中部")
    assert len(pool.list_all(group_id)) == 5

    # rollback
    simulate_rollback(pool, group_id, snapshot)

    # 检查恢复
    assert len(pool.list_all(group_id)) == 3, f"rollback 后应有 3 条事件，实际 {len(pool.list_all(group_id))}"

    print("✅ 测试4通过：rollback 恢复事件数量")


def test_old_snapshot_compatibility():
    """测试5：旧 snapshot 没有 event_pool 字段时兼容处理"""
    pool = EventPool()
    group_id = "test_group5"

    # 先创建一些事件
    pool.add(group_id=group_id, title="当前事件", category=EventCategory.DAILY.value, region="中部")
    assert len(pool.list_all(group_id)) == 1

    # 模拟旧格式 snapshot（没有 event_pool）
    old_snapshot = {
        "world_state": {},
        "player_profiles": {},
        "event_log": [],
        "campaign": {"state": "active"},
        # 没有 "event_pool" 字段！
    }

    # rollback
    simulate_rollback(pool, group_id, old_snapshot)

    # 旧 snapshot 没有 event_pool → 池应为空
    assert len(pool.list_all(group_id)) == 0, "旧 snapshot 恢复后池应为空（兼容处理）"
    # 不应报错
    print("✅ 测试5通过：旧 snapshot 兼容处理")


def test_rollback_after_archive():
    """测试6：归档后再 rollback，已归档事件应恢复为活跃"""
    pool = EventPool()
    group_id = "test_group6"

    event = pool.add(
        group_id=group_id,
        title="即将结束的事件",
        category=EventCategory.DAILY.value,
        region="中部",
    )

    # 拍快照（此时事件在萌芽）
    snapshot = simulate_snapshot(pool, group_id)

    # 推到结束并归档
    pool.advance_stage(group_id, event.event_id, EventStage.SPREAD.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ONGOING.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CLIMAX.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CONVERGE.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ENDED.value)
    pool.archive(group_id, event.event_id)

    # 事件已不在池中
    assert pool.get(group_id, event.event_id) is None
    assert len(pool.list_all(group_id)) == 0

    # rollback 到快照时间点
    simulate_rollback(pool, group_id, snapshot)

    # 事件恢复为萌芽
    restored = pool.get(group_id, event.event_id)
    assert restored is not None, "rollback 后已归档事件应恢复"
    assert restored.stage == EventStage.SPROUT.value, "rollback 后阶段应恢复到萌芽"

    print("✅ 测试6通过：归档后 rollback 可恢复事件")


if __name__ == "__main__":
    test_snapshot_contains_event_pool()
    test_rollback_restores_progress()
    test_rollback_restores_stage()
    test_rollback_restores_count()
    test_old_snapshot_compatibility()
    test_rollback_after_archive()
    print("\n🎉 全部 rollback 恢复测试通过！")
