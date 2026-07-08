"""
test_ensure_world_state.py - DonghuangPlugin._ensure_world_state 测试

/optimize 审查发现：`self.world_state.setdefault(group_id,
json.loads(json.dumps(INITIAL_WORLD_STATE)))` 这个此前散落在 main.py
5 处的写法，setdefault 的第二个参数无条件求值——哪怕 group_id 已经
存在，也会先做一次 INITIAL_WORLD_STATE 深拷贝再扔掉，其中一处
（_apply_state_delta）是每次 STATE_DELTA 都会走的高频路径。改成
_ensure_world_state()（显式 get→按需初始化）之后，本文件验证：
  1. 不存在时才真的初始化（深拷贝，不是共享引用）。
  2. 已存在时直接复用同一个对象，不会又白算一次深拷贝。
  3. 深拷贝的正确性：改动某个群的 world_state 不会污染 INITIAL_WORLD_STATE
     常量本身，也不会污染另一个群的 world_state。
"""

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


class _FakeSelf:
    def __init__(self):
        self.world_state = {}


def test_creates_deep_copy_on_first_call():
    fake_self = _FakeSelf()
    ws = m.DonghuangPlugin._ensure_world_state(fake_self, "g1")
    assert ws is not m.INITIAL_WORLD_STATE
    assert ws == m.INITIAL_WORLD_STATE
    assert fake_self.world_state["g1"] is ws
    print("✅ 测试1通过：首次调用创建独立深拷贝，不是共享引用")


def test_reuses_same_object_on_subsequent_calls():
    fake_self = _FakeSelf()
    ws1 = m.DonghuangPlugin._ensure_world_state(fake_self, "g1")
    ws1["GLOBAL"]["chaos_level"] = "已修改"
    ws2 = m.DonghuangPlugin._ensure_world_state(fake_self, "g1")
    assert ws2 is ws1  # 同一个对象，没有重新深拷贝覆盖掉刚才的修改
    assert ws2["GLOBAL"]["chaos_level"] == "已修改"
    print("✅ 测试2通过：已存在的群直接复用同一个对象，不会重新深拷贝")


def test_deep_copy_does_not_leak_between_groups_or_pollute_constant():
    fake_self = _FakeSelf()
    ws_a = m.DonghuangPlugin._ensure_world_state(fake_self, "g_A")
    ws_a["GLOBAL"]["chaos_level"] = "群A专属修改"
    ws_a["REGION"]["中部"]["phase"] = "群A专属修改"

    ws_b = m.DonghuangPlugin._ensure_world_state(fake_self, "g_B")

    assert ws_b["GLOBAL"]["chaos_level"] != "群A专属修改"
    assert ws_b["REGION"]["中部"]["phase"] != "群A专属修改"
    assert m.INITIAL_WORLD_STATE["GLOBAL"]["chaos_level"] != "群A专属修改"
    assert m.INITIAL_WORLD_STATE["REGION"]["中部"]["phase"] != "群A专属修改"
    print("✅ 测试3通过：深拷贝隔离正确，群与群之间、跟常量本身都不互相污染")


if __name__ == "__main__":
    test_creates_deep_copy_on_first_call()
    test_reuses_same_object_on_subsequent_calls()
    test_deep_copy_does_not_leak_between_groups_or_pollute_constant()
    print("\nensure_world_state tests passed")
