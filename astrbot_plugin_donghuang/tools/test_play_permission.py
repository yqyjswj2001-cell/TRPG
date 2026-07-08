"""
test_play_permission.py - /dh play 权限校验测试

COMMAND_AUDIT.md 第4.1节发现 /dh play 完全没有权限校验，任何已加入的
玩家都能单方面切换全群的强制游戏模式。已改为"开关仅管理员，查看所有人
可用"，本文件锁定这个行为。
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
        GROUP_MESSAGE = "group_message"

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
    def __init__(self, group_id, is_admin=False):
        self._group_id = group_id
        self._is_admin = is_admin
        self.messages = []

    def get_group_id(self):
        return self._group_id

    def is_admin(self):
        return self._is_admin

    def plain_result(self, text):
        self.messages.append(text)
        return text


class _FakeSelf:
    def __init__(self, campaign):
        self._campaign = campaign
        self.saved = 0

    def _get_campaign(self, group_id):
        return self._campaign

    def _is_gm(self, event):
        try:
            return bool(event.is_admin())
        except Exception:
            return False

    def _save_campaign(self):
        self.saved += 1


async def _run_play(fake_self, event, mode=""):
    messages = []
    async for msg in m.DonghuangPlugin.dh_play(fake_self, event, mode):
        messages.append(msg)
    return messages


def _run(coro):
    return asyncio.run(coro)


def test_non_admin_cannot_toggle_on():
    fake_self = _FakeSelf({"force_play": False})
    event = _FakeEvent(group_id="g1", is_admin=False)
    messages = _run(_run_play(fake_self, event, "on"))
    assert any("只有 AstrBot 管理员" in msg for msg in messages)
    assert fake_self._campaign["force_play"] is False
    assert fake_self.saved == 0


def test_non_admin_cannot_toggle_off():
    fake_self = _FakeSelf({"force_play": True})
    event = _FakeEvent(group_id="g1", is_admin=False)
    messages = _run(_run_play(fake_self, event, "off"))
    assert any("只有 AstrBot 管理员" in msg for msg in messages)
    assert fake_self._campaign["force_play"] is True
    assert fake_self.saved == 0


def test_non_admin_can_view():
    fake_self = _FakeSelf({"force_play": True})
    event = _FakeEvent(group_id="g1", is_admin=False)
    messages = _run(_run_play(fake_self, event, ""))
    assert any("开启" in msg for msg in messages)
    assert fake_self.saved == 0


def test_admin_can_toggle():
    fake_self = _FakeSelf({"force_play": False})
    event = _FakeEvent(group_id="g1", is_admin=True)
    messages = _run(_run_play(fake_self, event, "on"))
    assert any("强制游戏模式开启" in msg for msg in messages)
    assert fake_self._campaign["force_play"] is True
    assert fake_self.saved == 1


if __name__ == "__main__":
    test_non_admin_cannot_toggle_on()
    test_non_admin_cannot_toggle_off()
    test_non_admin_can_view()
    test_admin_can_toggle()
    print("\nplay_permission tests passed")
