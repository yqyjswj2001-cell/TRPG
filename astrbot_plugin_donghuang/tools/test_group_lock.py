"""
test_group_lock.py - group 级并发锁测试

SYSTEM_ARCHITECTURE.md 第6.4节记录过"状态文件是整体读→内存改→整体
覆盖写，没有 asyncio.Lock 保护，并发写入有后写覆盖前写的风险"。现在
on_group_message/dh_start/dh_decree 都改成"薄包装函数持锁 + _locked
版本做实际逻辑"的模式，靠 DonghuangPlugin._get_group_lock(group_id)
惰性创建的 per-group asyncio.Lock 序列化处理。

本文件测试两件事：
  1. _get_group_lock 本身的正确性（同群拿到同一把锁，不同群互不干扰）。
  2. 用一个最小复现（不依赖 astrbot stub，直接测锁的排它性）验证：
     持锁期间两个协程并发进入同一个"读状态→await→写状态"临界区时，
     确实是严格顺序执行，不会交错。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _FakeSelf:
    def __init__(self):
        self._group_locks = {}

    def _get_group_lock(self, group_id):
        lock = self._group_locks.get(group_id)
        if lock is None:
            lock = asyncio.Lock()
            self._group_locks[group_id] = lock
        return lock


def test_same_group_returns_same_lock_instance():
    fake_self = _FakeSelf()
    lock1 = fake_self._get_group_lock("g1")
    lock2 = fake_self._get_group_lock("g1")
    assert lock1 is lock2
    print("✅ 测试1通过：同一个群两次取锁是同一个 Lock 实例")


def test_different_groups_get_different_locks():
    fake_self = _FakeSelf()
    lock_a = fake_self._get_group_lock("g_A")
    lock_b = fake_self._get_group_lock("g_B")
    assert lock_a is not lock_b
    print("✅ 测试2通过：不同群拿到互相独立的 Lock 实例，互不阻塞")


async def _critical_section(fake_self, group_id, shared_state, delay, tag):
    """模拟 on_group_message 的模式：持锁 → 读状态 → await（模拟LLM调用）
    → 写状态。如果锁没生效，两个并发调用会在 await 期间交错读到彼此的
    旧值，最终 shared_state["value"] 会呈现"更新丢失"的错误结果。"""
    async with fake_self._get_group_lock(group_id):
        old_value = shared_state["value"]
        shared_state["log"].append(f"{tag} 读到 {old_value}")
        await asyncio.sleep(delay)  # 模拟 await self._call_llm(...)
        shared_state["value"] = old_value + 1
        shared_state["log"].append(f"{tag} 写入 {shared_state['value']}")


def test_lock_prevents_lost_update_under_concurrency():
    fake_self = _FakeSelf()
    shared_state = {"value": 0, "log": []}

    async def run():
        # 两个协程"同时"想处理同一个群的消息，其中一个的模拟LLM调用更慢
        await asyncio.gather(
            _critical_section(fake_self, "g1", shared_state, delay=0.05, tag="消息A"),
            _critical_section(fake_self, "g1", shared_state, delay=0.01, tag="消息B"),
        )

    asyncio.run(run())

    # 没有锁保护时，消息B会在消息A的 await 期间插进来读到同样的旧值0，
    # 两个都写成1，最终 value=1（丢失了一次更新）。有锁保护时严格串行，
    # 最终应该是 0 -> 1 -> 2，value == 2。
    assert shared_state["value"] == 2, (
        f"锁没有生效，出现了更新丢失：最终 value={shared_state['value']}，"
        f"执行日志：{shared_state['log']}"
    )
    print(f"✅ 测试3通过：并发场景下锁生效，没有更新丢失（日志：{shared_state['log']}）")


def test_different_groups_process_concurrently_not_serialized():
    """不同群之间不应该互相阻塞——这不是要"全局串行"，只是同一个群内部
    串行。用总耗时验证：两个不同群的临界区应该并发执行，总耗时接近
    单次耗时而不是两次相加。"""
    fake_self = _FakeSelf()
    shared_state_a = {"value": 0, "log": []}
    shared_state_b = {"value": 0, "log": []}

    async def run():
        import time
        start = time.monotonic()
        await asyncio.gather(
            _critical_section(fake_self, "g_A", shared_state_a, delay=0.1, tag="A"),
            _critical_section(fake_self, "g_B", shared_state_b, delay=0.1, tag="B"),
        )
        return time.monotonic() - start

    elapsed = asyncio.run(run())
    assert elapsed < 0.18, f"不同群之间不应该互相阻塞，实际耗时 {elapsed:.3f}s（接近0.1s才对，接近0.2s说明被错误串行了）"
    print(f"✅ 测试4通过：不同群互不阻塞，并发执行耗时 {elapsed:.3f}s")


def test_real_donghuang_plugin_has_get_group_lock():
    """确认 main.py 里真实的 DonghuangPlugin._get_group_lock 方法存在，
    行为跟上面用 _FakeSelf 验证过的逻辑一致——防止以后重构时这个方法
    被改名/删掉但测试还在测一份自己重新实现的假逻辑。"""
    import types
    import importlib

    plugin_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(plugin_dir.parent))

    if "astrbot" not in sys.modules:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api_event = types.ModuleType("astrbot.api.event")
        astrbot_api_star = types.ModuleType("astrbot.api.star")

        class _Group:
            def __init__(self, func):
                self._func = func

            def command(self, name):
                def deco(f):
                    return f
                return deco

            def __call__(self, *a, **kw):
                return self._func(*a, **kw)

        class _EventMessageType:
            GROUP_MESSAGE = "group_message"

        class _Filter:
            EventMessageType = _EventMessageType

            @staticmethod
            def command_group(name):
                def deco(func):
                    return _Group(func)
                return deco

            @staticmethod
            def event_message_type(*a, **kw):
                def deco(func):
                    return func
                return deco

        class _AstrMessageEvent:
            pass

        class _Context:
            pass

        class _Star:
            def __init__(self, *a, **kw):
                pass

        def _register(*a, **kw):
            def deco(cls):
                return cls
            return deco

        class _Logger:
            def info(self, *a, **kw): pass
            def warning(self, *a, **kw): pass
            def error(self, *a, **kw): pass
            def debug(self, *a, **kw): pass

        astrbot_api_event.filter = _Filter()
        astrbot_api_event.AstrMessageEvent = _AstrMessageEvent
        astrbot_api_star.Context = _Context
        astrbot_api_star.Star = _Star
        astrbot_api_star.register = _register
        astrbot_api.logger = _Logger()

        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api
        sys.modules["astrbot.api.event"] = astrbot_api_event
        sys.modules["astrbot.api.star"] = astrbot_api_star

    m = importlib.import_module("astrbot_plugin_donghuang.main")

    class _RealFakeSelf:
        def __init__(self):
            self._group_locks = {}

    fake_self = _RealFakeSelf()
    lock1 = m.DonghuangPlugin._get_group_lock(fake_self, "g1")
    lock2 = m.DonghuangPlugin._get_group_lock(fake_self, "g1")
    lock3 = m.DonghuangPlugin._get_group_lock(fake_self, "g2")
    assert isinstance(lock1, asyncio.Lock)
    assert lock1 is lock2
    assert lock1 is not lock3
    print("✅ 测试5通过：main.py 里真实的 _get_group_lock 行为符合预期")


if __name__ == "__main__":
    test_same_group_returns_same_lock_instance()
    test_different_groups_get_different_locks()
    test_lock_prevents_lost_update_under_concurrency()
    test_different_groups_process_concurrently_not_serialized()
    test_real_donghuang_plugin_has_get_group_lock()
    print("\ngroup_lock tests passed")
