"""
test_technique_command.py - /dh technique 指令测试（cultivation_technique.py 接线）

复用 test_ability_command.py 验证过的 astrbot stub 手法。这个指令依赖
get_technique_manager() 返回的真实功法数据（从 data/techniques/*.jsonl
加载），为了不让测试跟具体数据文件内容耦合，这里用一个假的
manager 替换掉 m.get_technique_manager，只测指令自己的逻辑分支。
"""

import asyncio
import sys
import types
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PLUGIN_DIR.parent))
sys.path.insert(0, str(_PLUGIN_DIR))


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
from cultivation_technique import CultivationTechnique  # noqa: E402


class _FakeEvent:
    def __init__(self, group_id, sender_id, message=""):
        self._group_id = group_id
        self._sender_id = sender_id
        self.message = message
        self.messages = []

    def get_group_id(self):
        return self._group_id

    def get_sender_id(self):
        return self._sender_id

    def plain_result(self, text):
        self.messages.append(text)
        return text


class _FakeSelf:
    def __init__(self, player_profiles):
        self.player_profiles = player_profiles
        self.saved = 0

    def _find_slot_by_qq(self, group_id, qq_id):
        for slot, profile in self.player_profiles.get(group_id, {}).items():
            if profile.get("qq_id") == qq_id:
                return slot
        return None

    def _save_profiles(self):
        self.saved += 1


class _FakeTechniqueManager:
    def __init__(self, techniques, suggestion=None):
        self._by_name = {t.name: t for t in techniques}
        self._suggestion = suggestion

    def get_by_name(self, name):
        return self._by_name.get(name)

    def find_matching_technique(self, spiritual_root, current_realm):
        return self._suggestion


def _base_profile(qq_id="QQ-1", realm="练气一层", known=None, **overrides):
    profile = {
        "qq_id": qq_id,
        "status": "confirmed",
        "cultivation_realm": realm,
        "METHOD_STATE": {"known_techniques": list(known or [])},
        "CORE_STATE": {},
    }
    profile.update(overrides)
    return profile


async def _run_technique(fake_self, event, technique_name=""):
    messages = []
    async for msg in m.DonghuangPlugin.dh_technique(fake_self, event, technique_name):
        messages.append(msg)
    return messages


def _run(coro):
    return asyncio.run(coro)


# ── 1. 未报名/未生成角色时的拒绝路径 ──

def test_technique_requires_group_and_slot():
    fake_self = _FakeSelf({})
    event = _FakeEvent(group_id="", sender_id="QQ-1")
    messages = _run(_run_technique(fake_self, event))
    assert any("群聊" in msg for msg in messages)

    fake_self = _FakeSelf({"g1": {}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_technique(fake_self, event))
    assert any("/dh join" in msg for msg in messages)


# ── 2. 无参数时展示已学功法 + 推荐 ──

def test_technique_no_arg_shows_known_and_suggestion():
    m.get_technique_manager = lambda: _FakeTechniqueManager(
        techniques=[CultivationTechnique(name="流云诀", tier="黄级", element="水")],
        suggestion=CultivationTechnique(name="流云诀", tier="黄级", element="水"),
    )
    profile = _base_profile(known=["烈焰诀"])
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_technique(fake_self, event, ""))
    text = "\n".join(messages)
    assert "已学功法" in text
    assert "烈焰诀" in text
    assert "推荐可学" in text
    assert "流云诀" in text


# ── 3. 已学过的功法不能重复学 ──

def test_technique_rejects_duplicate():
    m.get_technique_manager = lambda: _FakeTechniqueManager(
        techniques=[CultivationTechnique(name="烈焰诀", tier="黄级", element="火")],
    )
    profile = _base_profile(known=["烈焰诀"])
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_technique(fake_self, event, "烈焰诀"))
    assert any("已经学过" in msg for msg in messages)
    assert fake_self.saved == 0


# ── 4. 未知功法名 ──

def test_technique_unknown_name_rejected():
    m.get_technique_manager = lambda: _FakeTechniqueManager(techniques=[])
    profile = _base_profile()
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_technique(fake_self, event, "不存在的功法"))
    assert any("未知功法" in msg for msg in messages)


# ── 5. 境界不足时拒绝学习 ──

def test_technique_blocked_by_realm_requirement():
    # 天级功法要求境界 index>=13（金丹初期），练气一层（index 0）学不了
    m.get_technique_manager = lambda: _FakeTechniqueManager(
        techniques=[CultivationTechnique(name="九天诀", tier="天级", element="雷")],
    )
    profile = _base_profile(realm="练气一层")
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_technique(fake_self, event, "九天诀"))
    assert any("境界不足" in msg for msg in messages)
    assert fake_self.saved == 0
    assert "九天诀" not in profile["METHOD_STATE"]["known_techniques"]


# ── 6. 正常学习：加入已学列表并保存 ──

def test_technique_learns_and_saves():
    m.get_technique_manager = lambda: _FakeTechniqueManager(
        techniques=[CultivationTechnique(name="流云诀", tier="黄级", element="水")],
    )
    profile = _base_profile(realm="练气一层")
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_technique(fake_self, event, "流云诀"))
    text = "\n".join(messages)
    assert "学会了" in text
    assert "流云诀" in profile["METHOD_STATE"]["known_techniques"]
    assert fake_self.saved == 1


if __name__ == "__main__":
    test_technique_requires_group_and_slot()
    test_technique_no_arg_shows_known_and_suggestion()
    test_technique_rejects_duplicate()
    test_technique_unknown_name_rejected()
    test_technique_blocked_by_realm_requirement()
    test_technique_learns_and_saves()
    print("\ntechnique_command tests passed")
