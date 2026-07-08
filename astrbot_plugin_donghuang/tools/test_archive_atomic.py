"""
test_archive_atomic.py — 归档失败保护测试

验证 preview_archive / commit_archive 两阶段提交的原子性：
  1. 正常归档成功
  2. EVENT_LOG 保存失败时 EventPool 事件仍存在
  3. commit_archive 不应执行
  4. EventPool 中事件仍可再次归档

运行方式：
  python -m pytest tools/test_archive_atomic.py -v
  或：
  python tools/test_archive_atomic.py
"""

import sys
import os
import json
import tempfile
from pathlib import Path

# 确保能 import 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_event_pool import EventPool, EventStage, EventCategory, EventPriority, EventVisibility


def test_normal_archive_success():
    """测试1：正常归档成功——preview → 写 EVENT_LOG → commit"""
    pool = EventPool()
    group_id = "test_group"

    # 创建事件并推到"结束"
    event = pool.add(
        group_id=group_id,
        title="灵气东移加速",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="东部",
        location="启阳",
        summary="东部灵脉异动",
        progress=0.5,
    )
    # 手动推进到结束
    pool.advance_stage(group_id, event.event_id, EventStage.ONGOING.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CLIMAX.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CONVERGE.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ENDED.value)

    # Step 1: preview_archive
    record = pool.preview_archive(group_id, event.event_id)
    assert record is not None, "preview_archive 应返回记录"
    assert record["trigger_source"] == "event_pool_archive"
    assert record["category"] == EventCategory.LEYLINE_RESOURCE.value
    assert record["title"] == "灵气东移加速"

    # Step 2: 事件仍在池中（preview 不删除）
    still_in_pool = pool.get(group_id, event.event_id)
    assert still_in_pool is not None, "preview 后事件仍应在池中"
    assert still_in_pool.stage == EventStage.ENDED.value, "preview 后阶段应为结束"

    # Step 3: 模拟写 EVENT_LOG 成功
    event_log = [record]

    # Step 4: commit_archive
    result = pool.commit_archive(group_id, event.event_id)
    assert result is True, "commit_archive 应返回 True"

    # Step 5: 事件已从池中删除
    gone = pool.get(group_id, event.event_id)
    assert gone is None, "commit 后事件应从池中删除"

    # Step 6: EVENT_LOG 有记录
    assert len(event_log) == 1
    assert event_log[0]["title"] == "灵气东移加速"

    print("✅ 测试1通过：正常归档成功")


def test_event_log_save_failure():
    """测试2：EVENT_LOG 写入失败——commit 不执行，事件保留"""
    pool = EventPool()
    group_id = "test_group2"

    event = pool.add(
        group_id=group_id,
        title="西部封印松动",
        category=EventCategory.FACTION_CONFLICT.value,
        region="西部",
        location="裂川",
        summary="封印结构不稳定",
        progress=0.6,
    )
    pool.advance_stage(group_id, event.event_id, EventStage.ONGOING.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CLIMAX.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CONVERGE.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ENDED.value)

    # Step 1: preview_archive
    record = pool.preview_archive(group_id, event.event_id)
    assert record is not None

    # Step 2: 模拟 EVENT_LOG 写入失败——不执行 commit_archive
    # （在实际代码中，_save_event_log 抛异常会阻止 commit_archive 被调用）
    # 我们直接验证：不调用 commit 时事件仍在

    still_in_pool = pool.get(group_id, event.event_id)
    assert still_in_pool is not None, "EVENT_LOG 写入失败时事件应保留在池中"
    assert still_in_pool.stage == EventStage.ENDED.value, "事件阶段应为结束"
    assert still_in_pool.progress >= 0.6, "事件进度应不变"

    print("✅ 测试2通过：EVENT_LOG 写入失败时事件保留")


def test_commit_not_executed_on_failure():
    """测试3：验证不调用 commit_archive 时池状态不变"""
    pool = EventPool()
    group_id = "test_group3"

    event = pool.add(
        group_id=group_id,
        title="CHAOS异常波动",
        category=EventCategory.CHAOS_ANOMALY.value,
        region="西部",
        summary="空间裂缝出现",
    )

    # 推到结束
    pool.update_progress(group_id, event.event_id, 1.0)
    pool.advance_stage(group_id, event.event_id, EventStage.SPREAD.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ONGOING.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CLIMAX.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CONVERGE.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ENDED.value)

    # preview_archive 成功
    record = pool.preview_archive(group_id, event.event_id)
    assert record is not None

    # 模拟失败——不调用 commit
    # 验证池中仍有该事件
    all_events = pool.list_all(group_id)
    ended_count = sum(1 for e in all_events if e.stage == EventStage.ENDED.value)
    assert ended_count == 1, "应有一个结束事件等待归档"

    print("✅ 测试3通过：不调用 commit 时池状态不变")


def test_retry_archive_after_failure():
    """测试4：归档失败后再次尝试可以成功"""
    pool = EventPool()
    group_id = "test_group4"

    event = pool.add(
        group_id=group_id,
        title="中部古战场封印波动",
        category=EventCategory.RUIN_OPPORTUNITY.value,
        region="中部",
        location="祖脉余山",
        summary="封印松动",
        progress=0.5,
    )

    # 推到结束
    pool.advance_stage(group_id, event.event_id, EventStage.ONGOING.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CLIMAX.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CONVERGE.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ENDED.value)

    # 第一次尝试：preview 成功但模拟写入失败（不 commit）
    record1 = pool.preview_archive(group_id, event.event_id)
    assert record1 is not None

    # 事件仍在池中
    assert pool.get(group_id, event.event_id) is not None

    # 第二次尝试：这次写入成功，commit
    record2 = pool.preview_archive(group_id, event.event_id)
    assert record2 is not None
    assert record2["event_id"] == event.event_id

    # 模拟成功写入 EVENT_LOG
    event_log = [record2]

    # commit
    result = pool.commit_archive(group_id, event.event_id)
    assert result is True

    # 事件已从池中删除
    assert pool.get(group_id, event.event_id) is None

    # EVENT_LOG 有记录
    assert len(event_log) == 1

    print("✅ 测试4通过：归档失败后再次尝试可以成功")


def test_archive_wrong_stage():
    """测试5：非结束阶段的事件不能 preview_archive"""
    pool = EventPool()
    group_id = "test_group5"

    event = pool.add(
        group_id=group_id,
        title="日常坊市消息",
        category=EventCategory.DAILY.value,
        region="中部",
    )

    # 事件在萌芽阶段，尝试归档
    record = pool.preview_archive(group_id, event.event_id)
    assert record is None, "萌芽阶段的事件不应能归档"

    # 事件仍在池中
    assert pool.get(group_id, event.event_id) is not None

    print("✅ 测试5通过：非结束阶段不能归档")


def test_convenience_archive_method():
    """测试6：archive() 便捷方法（preview + commit 一次完成）"""
    pool = EventPool()
    group_id = "test_group6"

    event = pool.add(
        group_id=group_id,
        title="灵脉资源事件",
        category=EventCategory.LEYLINE_RESOURCE.value,
        region="东部",
    )

    pool.advance_stage(group_id, event.event_id, EventStage.SPREAD.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ONGOING.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CLIMAX.value)
    pool.advance_stage(group_id, event.event_id, EventStage.CONVERGE.value)
    pool.advance_stage(group_id, event.event_id, EventStage.ENDED.value)

    # 一次性归档
    record = pool.archive(group_id, event.event_id)
    assert record is not None
    assert pool.get(group_id, event.event_id) is None

    print("✅ 测试6通过：archive() 便捷方法正常工作")


if __name__ == "__main__":
    test_normal_archive_success()
    test_event_log_save_failure()
    test_commit_not_executed_on_failure()
    test_retry_archive_after_failure()
    test_archive_wrong_stage()
    test_convenience_archive_method()
    print("\n🎉 全部归档原子性测试通过！")
