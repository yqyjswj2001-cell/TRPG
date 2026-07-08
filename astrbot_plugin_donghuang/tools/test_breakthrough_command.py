"""
test_breakthrough_command.py - /dh breakthrough 指令测试

/dh breakthrough 只是给已有的"自然语言 → AI分类 → _trigger_turn_lock"
路径加一个直接入口，不重新实现突破判定逻辑。所以这里只验证 dh_breakthrough
自己新增的部分：各种前置门槛检查，以及门槛都过了之后是否用正确的参数
（category="CULTIVATION_BREAKTHROUGH"）调用了 _trigger_turn_lock——
不重新测 _trigger_turn_lock/BreakthroughManager 内部行为，那些已经在
test_cultivation_system.py / 其它地方测过。
"""

import asyncio
import sys
import types
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PLUGIN_DIR.parent))


def _install_astrbot_stub():
    if "astrbot" in sys.modules:
        return

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

        def __call__(self, *args, **kwargs):
            return self._func(*args, **kwargs)

    class _EventMessageType:
        ALL = "all"
        GROUP_MESSAGE = "group_message"
        PRIVATE_MESSAGE = "private_message"

    class _Filter:
        EventMessageType = _EventMessageType

        @staticmethod
        def command_group(name):
            def deco(func):
                return _Group(func)
            return deco

        @staticmethod
        def event_message_type(*args, **kwargs):
            def deco(func):
                return func
            return deco

    class _AstrMessageEvent:
        pass

    class _Context:
        pass

    class _Star:
        def __init__(self, *args, **kwargs):
            pass

    def _register(*args, **kwargs):
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


_install_astrbot_stub()

import astrbot_plugin_donghuang.main as m  # noqa: E402


class _FakeEvent:
    def __init__(self, group_id, sender_id):
        self._group_id = group_id
        self._sender_id = sender_id
        self.messages = []

    def get_group_id(self):
        return self._group_id

    def get_sender_id(self):
        return self._sender_id

    def plain_result(self, text):
        self.messages.append(text)
        return text


class _FakeSelf:
    def __init__(self, player_profiles, campaign=None):
        self.player_profiles = player_profiles
        self._campaign = campaign or {
            "state": "active",
            "combat": {"active": False},
            "turn_lock": {"active": False},
        }
        self.archived = 0
        self.trigger_calls = []

    def _get_campaign(self, group_id):
        return self._campaign

    def _find_slot_by_qq(self, group_id, qq_id):
        for slot, profile in self.player_profiles.get(group_id, {}).items():
            if profile.get("qq_id") == qq_id:
                return slot
        return None

    def _archive_ended_events(self, group_id):
        self.archived += 1

    async def _trigger_turn_lock(self, event, group_id, campaign, slot, raw_text, category):
        self.trigger_calls.append({
            "group_id": group_id, "slot": slot, "raw_text": raw_text, "category": category,
        })
        yield event.plain_result(f"⚔️ 触发了 {category} 回合锁定")


def _base_profile(qq_id="QQ-1", progress=0, **overrides):
    profile = {
        "qq_id": qq_id,
        "status": "confirmed",
        "METHOD_STATE": {"progress": progress},
    }
    profile.update(overrides)
    return profile


async def _run_breakthrough(fake_self, event):
    messages = []
    async for msg in m.DonghuangPlugin.dh_breakthrough(fake_self, event):
        messages.append(msg)
    return messages


def _run(coro):
    return asyncio.run(coro)


# ── 1. 未报名/未开团/战斗中/已有事件锁定 时的拒绝路径 ──

def test_breakthrough_requires_group():
    fake_self = _FakeSelf({})
    event = _FakeEvent(group_id="", sender_id="QQ-1")
    messages = _run(_run_breakthrough(fake_self, event))
    assert any("群聊" in msg for msg in messages)


def test_breakthrough_requires_active_campaign():
    fake_self = _FakeSelf({"g1": {}}, campaign={
        "state": "not_started", "combat": {"active": False}, "turn_lock": {"active": False},
    })
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_breakthrough(fake_self, event))
    assert any("团还没开始" in msg for msg in messages)


def test_breakthrough_blocked_during_combat():
    fake_self = _FakeSelf({"g1": {}}, campaign={
        "state": "active", "combat": {"active": True}, "turn_lock": {"active": False},
    })
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_breakthrough(fake_self, event))
    assert any("战斗中" in msg for msg in messages)


def test_breakthrough_blocked_when_turn_lock_active():
    fake_self = _FakeSelf({"g1": {}}, campaign={
        "state": "active", "combat": {"active": False}, "turn_lock": {"active": True},
    })
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_breakthrough(fake_self, event))
    assert any("正在等待玩家提交行动" in msg for msg in messages)


def test_breakthrough_requires_slot():
    fake_self = _FakeSelf({"g1": {}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_breakthrough(fake_self, event))
    assert any("/dh join" in msg for msg in messages)


# ── 2. 修为进度不够时拒绝（不能绕过火候门槛）──

def test_breakthrough_rejected_when_progress_insufficient():
    profile = _base_profile(progress=50)
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_breakthrough(fake_self, event))
    assert any("火候未到" in msg for msg in messages)
    assert fake_self.trigger_calls == []


# ── 3. 火候够了：正确调用 _trigger_turn_lock 触发 CULTIVATION_BREAKTHROUGH ──

def test_breakthrough_triggers_turn_lock_when_ready():
    profile = _base_profile(progress=100)
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_breakthrough(fake_self, event))
    assert len(fake_self.trigger_calls) == 1
    call = fake_self.trigger_calls[0]
    assert call["category"] == "CULTIVATION_BREAKTHROUGH"
    assert call["slot"] == "PLAYER-A"
    assert fake_self.archived == 1
    assert any("CULTIVATION_BREAKTHROUGH" in msg for msg in messages)


if __name__ == "__main__":
    test_breakthrough_requires_group()
    test_breakthrough_requires_active_campaign()
    test_breakthrough_blocked_during_combat()
    test_breakthrough_blocked_when_turn_lock_active()
    test_breakthrough_requires_slot()
    test_breakthrough_rejected_when_progress_insufficient()
    test_breakthrough_triggers_turn_lock_when_ready()
    print("\nbreakthrough_command tests passed")
