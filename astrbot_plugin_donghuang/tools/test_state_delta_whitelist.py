"""
test_state_delta_whitelist.py - _apply_state_delta 模块级白名单测试

SYSTEM_ARCHITECTURE.md 第6.2节记录的风险："STATE_DELTA 是开放式路径
写入，AI 编错字段名可能静默长出新结构"。现在 _apply_state_delta 在原有
的字段级黑名单（_PROFILE_PROTECTED_TOP_FIELDS/_PROFILE_PROTECTED_NESTED_
FIELDS）之外，加了一层模块级白名单：
  - world_state.<模块>.xxx：<模块> 必须是 INITIAL_WORLD_STATE 的已知
    顶层 key（GLOBAL/REGION/FACTION/RESOURCE/ENTITY/METHOD/CORE/CAUSAL/
    CHAOS/PLAYER_LINKAGE/FACTION_STATE）。
  - player_profile.<模块>.<字段>：<模块> 必须是角色创建时那份 profile
    字典的已知顶层 key。

本文件验证两件事：
  1. 所有现有合法路径（角色创建时真实用到的模块）仍然能正常写入，
     没有被误杀。
  2. AI 编造一个全新的、从未设计过的模块名时，整行被拦截丢弃，不会
     在 profile/world_state 里长出意料之外的新结构。
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
    def __init__(self, group_id, world_state=None, profile=None, campaign=None):
        self.world_state = {group_id: world_state if world_state is not None else
                             __import__("json").loads(__import__("json").dumps(m.INITIAL_WORLD_STATE))}
        self.player_profiles = {group_id: {"PLAYER-A": profile or {}}}
        self.event_log = {group_id: []}
        self._campaign = campaign or {"cycle": 1, "next_event_id": 1}
        self.saved_world_state = 0
        self.saved_profiles = 0
        self.saved_campaign = 0
        self.saved_event_log = 0

    def _save_world_state(self):
        self.saved_world_state += 1

    def _save_profiles(self):
        self.saved_profiles += 1

    def _save_campaign(self):
        self.saved_campaign += 1

    def _save_event_log(self):
        self.saved_event_log += 1

    def _get_campaign(self, group_id):
        return self._campaign

    def _compute_causal_linkage(self, group_id, participants):
        return []

    def _ensure_world_state(self, group_id):
        import copy as _copy
        ws = self.world_state.get(group_id)
        if ws is None:
            ws = _copy.deepcopy(m.INITIAL_WORLD_STATE)
            self.world_state[group_id] = ws
        return ws


def _apply(fake_self, group_id, default_slot, lines):
    m.DonghuangPlugin._apply_state_delta(fake_self, group_id, default_slot, lines)


# ── 1. 合法的 world_state 路径正常写入 ──

def test_legit_world_state_paths_still_work():
    fake_self = _FakeSelf("g1")
    _apply(fake_self, "g1", "PLAYER-A", [
        "world_state.GLOBAL.chaos_level: 平稳",
        "world_state.REGION.中部.phase: 稳定",
        "world_state.CHAOS.active_anomalies+: 灵气紊乱",
    ])
    ws = fake_self.world_state["g1"]
    assert ws["GLOBAL"]["chaos_level"] == "平稳"
    assert ws["REGION"]["中部"]["phase"] == "稳定"
    assert "灵气紊乱" in ws["CHAOS"]["active_anomalies"]
    assert fake_self.saved_world_state == 1


# ── 2. 伪造的 world_state 顶层模块被拦截 ──

def test_fabricated_world_state_module_rejected():
    fake_self = _FakeSelf("g1")
    _apply(fake_self, "g1", "PLAYER-A", [
        "world_state.POWER_STATE.超能力: 999",
    ])
    ws = fake_self.world_state["g1"]
    assert "POWER_STATE" not in ws
    assert fake_self.saved_world_state == 0  # 没有任何合法变更，不应该触发保存


# ── 3. 合法的 player_profile 路径正常写入（已知模块下的自由字段）──

def test_legit_profile_paths_still_work():
    # 注意：STATE_DELTA 的 player_profile 分支要求至少
    # "player_profile.<模块>.<字段>" 三段路径才会命中（parts >= 3），
    # 顶层标量字段（比如 history_note）本来就没有合法的写入路径，
    # 这是 DSL 本身的先天限制，跟本次白名单改动无关，不在这里测。
    profile = {
        "IDENTITY_STATE": {"region": "中部"},
        "RESOURCE_STATE": {"held": [], "currency": {"灵石": 10, "贡献点": {}}},
        "FACTION_STATE": {"affiliation": None, "relations": {}},
    }
    fake_self = _FakeSelf("g1", profile=profile)
    _apply(fake_self, "g1", "PLAYER-A", [
        "player_profile.IDENTITY_STATE.subregion: 灵溪谷",
        "player_profile.RESOURCE_STATE.held+: 回气丹",
    ])
    p = fake_self.player_profiles["g1"]["PLAYER-A"]
    assert p["IDENTITY_STATE"]["subregion"] == "灵溪谷"
    assert "回气丹" in p["RESOURCE_STATE"]["held"]
    assert fake_self.saved_profiles == 1


# ── 4. 伪造的 profile 顶层模块被拦截，不会长出新结构 ──

def test_fabricated_profile_module_rejected():
    profile = {"IDENTITY_STATE": {"region": "中部"}}
    fake_self = _FakeSelf("g1", profile=profile)
    _apply(fake_self, "g1", "PLAYER-A", [
        "player_profile.POWER_STATE.超能力: 无敌",
    ])
    p = fake_self.player_profiles["g1"]["PLAYER-A"]
    assert "POWER_STATE" not in p
    assert fake_self.saved_profiles == 0


# ── 5. 白名单和原有黑名单互不干扰：受保护字段依然被拦截 ──

def test_protected_fields_still_blocked_alongside_whitelist():
    profile = {"METHOD_STATE": {"progress": 10}}
    fake_self = _FakeSelf("g1", profile=profile)
    _apply(fake_self, "g1", "PLAYER-A", [
        "player_profile.METHOD_STATE.progress: 100",  # 受保护字段，模块本身在白名单里
    ])
    p = fake_self.player_profiles["g1"]["PLAYER-A"]
    assert p["METHOD_STATE"]["progress"] == 10  # 没被 AI 直接改掉
    assert fake_self.saved_profiles == 0


# ── 6. 一批合法+非法混合的行：合法的照常生效，非法的被单独丢弃 ──

def test_mixed_legit_and_fabricated_lines():
    profile = {"CORE_STATE": {"stability": "stable"}}
    fake_self = _FakeSelf("g1", profile=profile)
    _apply(fake_self, "g1", "PLAYER-A", [
        "player_profile.CORE_STATE.chaos_influence: 轻微",
        "player_profile.GHOST_STATE.幽灵之力: 100",
    ])
    p = fake_self.player_profiles["g1"]["PLAYER-A"]
    assert p["CORE_STATE"]["chaos_influence"] == "轻微"
    assert "GHOST_STATE" not in p
    assert fake_self.saved_profiles == 1  # 有一条合法变更，仍然要保存


if __name__ == "__main__":
    test_legit_world_state_paths_still_work()
    test_fabricated_world_state_module_rejected()
    test_legit_profile_paths_still_work()
    test_fabricated_profile_module_rejected()
    test_protected_fields_still_blocked_alongside_whitelist()
    test_mixed_legit_and_fabricated_lines()
    print("\nstate_delta_whitelist tests passed")
