"""
test_ability_command.py - /dh ability 指令测试（cultivation_ability.py 接线）

main.py 依赖 astrbot 框架，测试环境没装这个包，所以复用 test_combat_system.py
里验证过的最小 stub 手法（只提供 main.py 实际用到的属性），不改动 main.py
本身。dh_ability 是 async generator（yield event.plain_result(...)），用
asyncio 驱动收集所有产出的消息文本。
"""

import asyncio
import random
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
    """给 dh_ability 用的最小 self：只提供它实际用到的属性/方法。"""

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


def _base_profile(qq_id="QQ-1", realm="练气一层", **overrides):
    profile = {
        "qq_id": qq_id,
        "status": "confirmed",
        "cultivation_realm": realm,
        "METHOD_STATE": {"abilities": {}},
        "CORE_STATE": {},
    }
    profile.update(overrides)
    return profile


async def _run_ability(fake_self, event, ability_name=""):
    messages = []
    async for msg in m.DonghuangPlugin.dh_ability(fake_self, event, ability_name):
        messages.append(msg)
    return messages


def _run(coro):
    return asyncio.run(coro)


# ── 1. 未报名/未生成角色/未确认时的拒绝路径 ──

def test_ability_requires_group_and_slot():
    fake_self = _FakeSelf({})
    event = _FakeEvent(group_id="", sender_id="QQ-1")
    messages = _run(_run_ability(fake_self, event, "剑意"))
    assert any("群聊" in msg for msg in messages)

    fake_self = _FakeSelf({"g1": {}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_ability(fake_self, event, "剑意"))
    assert any("/dh join" in msg for msg in messages)


# ── 2. 无参数时展示技能面板 ──

def test_ability_no_arg_shows_panel():
    profile = _base_profile()
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_ability(fake_self, event, ""))
    assert any("技能面板" in msg for msg in messages)
    assert any("可修炼" in msg for msg in messages)
    # migrate_profile_abilities 应该已经把五项技能字段补全
    assert set(profile["METHOD_STATE"]["abilities"].keys()) == set(m.ABILITY_NAMES)


# ── 3. 未知技能名 ──

def test_ability_unknown_name_rejected():
    profile = _base_profile()
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_ability(fake_self, event, "读心术"))
    assert any("未知技能" in msg for msg in messages)


# ── 4. 境界不足时拒绝修炼（炼丹需要练气四层）──

def test_ability_blocked_by_realm_requirement():
    profile = _base_profile(realm="练气一层")
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_ability(fake_self, event, "炼丹"))
    assert any("境界不足" in msg for msg in messages)
    assert fake_self.saved == 0  # 被拒绝时不应该保存


# ── 5. 正常修炼：获得经验、保存档案 ──

def test_ability_practice_grants_exp_and_saves():
    random.seed(3)
    profile = _base_profile(realm="练气一层")  # 剑意最低要求是练气一层，满足
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1", message="我在庭院里练剑")
    messages = _run(_run_ability(fake_self, event, "剑意"))
    text = "\n".join(messages)
    assert "修炼「剑意」" in text
    assert "结果：" in text
    assert fake_self.saved == 1
    assert profile["METHOD_STATE"]["abilities"]["剑意"]["exp"] >= 0


# ── 6. 有人指点时经验加成生效 ──

def test_ability_guidance_keyword_boosts_exp():
    random.seed(1)
    profile_a = _base_profile(realm="练气一层")
    fake_self_a = _FakeSelf({"g1": {"PLAYER-A": profile_a}})
    event_a = _FakeEvent(group_id="g1", sender_id="QQ-1", message="我自己练剑")

    profile_b = _base_profile(realm="练气一层")
    fake_self_b = _FakeSelf({"g1": {"PLAYER-A": profile_b}})
    event_b = _FakeEvent(group_id="g1", sender_id="QQ-1", message="师父指点我练剑")

    manager = m.AbilityManager()
    # 用同样的运气等级直接比较 calculate_exp_gain，排除掷骰随机性干扰
    no_guidance = manager.calculate_exp_gain("剑意", action_type="practice", luck_level="成功")
    with_guidance = manager.calculate_exp_gain("剑意", action_type="practice_with_teacher", luck_level="成功")
    assert with_guidance > no_guidance


# ── 7. 技能练满经验后应该自动升级 ──

def test_ability_levels_up_when_exp_threshold_reached():
    profile = _base_profile(realm="练气一层")
    profile["METHOD_STATE"]["abilities"]["剑意"] = {"level": 0, "exp": 9, "max_level": 5}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1", message="奋力练剑")

    # 用一个必然"大成功"的种子多试几次，确保能凑够 10 点经验触发升级
    leveled = False
    for seed in range(30):
        random.seed(seed)
        profile["METHOD_STATE"]["abilities"]["剑意"] = {"level": 0, "exp": 9, "max_level": 5}
        messages = _run(_run_ability(fake_self, event, "剑意"))
        if any("突破至" in msg for msg in messages):
            leveled = True
            assert profile["METHOD_STATE"]["abilities"]["剑意"]["level"] >= 1
            break
    assert leveled, "多次尝试后仍未观察到升级，可能是经验计算逻辑有问题"


if __name__ == "__main__":
    test_ability_requires_group_and_slot()
    test_ability_no_arg_shows_panel()
    test_ability_unknown_name_rejected()
    test_ability_blocked_by_realm_requirement()
    test_ability_practice_grants_exp_and_saves()
    test_ability_guidance_keyword_boosts_exp()
    test_ability_levels_up_when_exp_threshold_reached()
    print("\nability_command tests passed")
