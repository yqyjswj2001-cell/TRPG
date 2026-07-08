"""
test_tick_scheduler.py — Tick Scheduler 测试

覆盖：
  1. should_tick 首次返回 True
  2. should_tick 冷却期内返回 False
  3. should_tick 冷却期后返回 True
  4. mark_tick 更新状态
  5. get_last_tick 返回正确信息
  6. reset 清除状态
  7. 旧存档兼容（无 tick_state）
  8. format_status 输出格式

运行方式：
  python tools/test_tick_scheduler.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from world_tick_scheduler import TickScheduler, DEFAULT_TICK_INTERVAL


def make_campaign(cycle=1, tick_state=None):
    c = {"state": "active", "cycle": cycle}
    if tick_state is not None:
        c["tick_state"] = tick_state
    return c


def test_should_tick_first_time():
    """测试1：首次 should_tick 返回 True"""
    sched = TickScheduler()
    campaign = make_campaign()  # 无 tick_state
    assert sched.should_tick("g1", campaign) is True
    print("✅ 测试1通过：首次 should_tick 返回 True")


def test_should_tick_cooldown():
    """测试2：冷却期内 should_tick 返回 False"""
    sched = TickScheduler(tick_interval=1800)  # 30 分钟
    now = 1000000.0
    campaign = make_campaign(tick_state={
        "last_tick_time": now,
        "last_tick_cycle": 1,
        "tick_count": 1,
    })

    # 10 分钟后
    assert sched.should_tick("g1", campaign, now=now + 600) is False
    # 29 分钟后
    assert sched.should_tick("g1", campaign, now=now + 1740) is False
    print("✅ 测试2通过：冷却期内 should_tick 返回 False")


def test_should_tick_after_interval():
    """测试3：冷却期后 should_tick 返回 True"""
    sched = TickScheduler(tick_interval=1800)
    now = 1000000.0
    campaign = make_campaign(tick_state={
        "last_tick_time": now,
        "last_tick_cycle": 1,
        "tick_count": 1,
    })

    # 30 分钟后
    assert sched.should_tick("g1", campaign, now=now + 1800) is True
    # 31 分钟后
    assert sched.should_tick("g1", campaign, now=now + 1860) is True
    print("✅ 测试3通过：冷却期后 should_tick 返回 True")


def test_mark_tick():
    """测试4：mark_tick 更新状态"""
    sched = TickScheduler()
    now = 2000000.0
    campaign = make_campaign(cycle=5)

    sched.mark_tick("g1", campaign, now=now)

    state = campaign["tick_state"]
    assert state["last_tick_time"] == now
    assert state["last_tick_cycle"] == 5
    assert state["tick_count"] == 1

    # 第二次 mark
    sched.mark_tick("g1", campaign, now=now + 1800)
    assert state["tick_count"] == 2
    assert state["last_tick_time"] == now + 1800
    print("✅ 测试4通过：mark_tick 更新状态正确")


def test_get_last_tick():
    """测试5：get_last_tick 返回正确信息"""
    sched = TickScheduler()
    now = 3000000.0
    campaign = make_campaign(tick_state={
        "last_tick_time": now,
        "last_tick_cycle": 3,
        "tick_count": 7,
    })

    info = sched.get_last_tick("g1", campaign)
    assert info["last_tick_time"] == now
    assert info["last_tick_cycle"] == 3
    assert info["tick_count"] == 7
    print("✅ 测试5通过：get_last_tick 返回正确信息")


def test_reset():
    """测试6：reset 清除状态"""
    sched = TickScheduler()
    campaign = make_campaign(tick_state={
        "last_tick_time": 999.0,
        "last_tick_cycle": 10,
        "tick_count": 50,
    })

    sched.reset("g1", campaign)

    state = campaign["tick_state"]
    assert state["last_tick_time"] == 0.0
    assert state["last_tick_cycle"] == 0
    assert state["tick_count"] == 0

    # reset 后 should_tick 应返回 True
    assert sched.should_tick("g1", campaign) is True
    print("✅ 测试6通过：reset 清除状态，之后 should_tick=True")


def test_old_campaign_compatibility():
    """测试7：旧存档无 tick_state 自动初始化"""
    sched = TickScheduler()
    campaign = {"state": "active", "cycle": 1}  # 无 tick_state

    # should_tick 不报错
    assert sched.should_tick("g1", campaign) is True

    # tick_state 已自动初始化
    assert "tick_state" in campaign
    assert campaign["tick_state"]["tick_count"] == 0

    # mark_tick 不报错
    sched.mark_tick("g1", campaign, now=1000.0)
    assert campaign["tick_state"]["tick_count"] == 1

    print("✅ 测试7通过：旧存档兼容")


def test_format_status():
    """测试8：format_status 输出格式"""
    sched = TickScheduler(tick_interval=1800)
    now = 1000000.0

    # 从未执行
    campaign1 = make_campaign()
    text1 = sched.format_status("g1", campaign1, now=now)
    assert "从未执行" in text1
    assert "现在可以执行" in text1

    # 冷却中
    campaign2 = make_campaign(tick_state={
        "last_tick_time": now - 600,  # 10 分钟前
        "last_tick_cycle": 2,
        "tick_count": 3,
    })
    text2 = sched.format_status("g1", campaign2, now=now)
    assert "总执行次数：3" in text2
    assert "冷却中" in text2
    assert "20分" in text2  # 还剩 20 分钟

    # 可执行
    campaign3 = make_campaign(tick_state={
        "last_tick_time": now - 1800,  # 30 分钟前
        "last_tick_cycle": 5,
        "tick_count": 10,
    })
    text3 = sched.format_status("g1", campaign3, now=now)
    assert "现在可以执行" in text3
    assert "可执行" in text3

    print("✅ 测试8通过：format_status 输出格式正确")


if __name__ == "__main__":
    test_should_tick_first_time()
    test_should_tick_cooldown()
    test_should_tick_after_interval()
    test_mark_tick()
    test_get_last_tick()
    test_reset()
    test_old_campaign_compatibility()
    test_format_status()
    print("\n🎉 全部 Tick Scheduler 测试通过！")
