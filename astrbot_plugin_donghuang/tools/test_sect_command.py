"""
test_sect_command.py - /dh sect 指令测试（sect_interface.py 接线）

复用 test_ability_command.py / test_combat_system.py 验证过的 astrbot
stub 手法，不改动 main.py 本身。dh_sect 是 async generator，用 asyncio
驱动收集所有产出的消息文本。
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
    """给 dh_sect 用的最小 self：只提供它实际用到的属性/方法。"""

    def __init__(self, player_profiles, factions=None, cycle=1, npcs=None):
        self.player_profiles = player_profiles
        self.factions = factions or {}
        self._cycle = cycle
        self.saved = 0
        self.npc_registry = _FakeNPCRegistry(npcs or {})

    def _find_slot_by_qq(self, group_id, qq_id):
        for slot, profile in self.player_profiles.get(group_id, {}).items():
            if profile.get("qq_id") == qq_id:
                return slot
        return None

    def _find_slot_by_name_or_code(self, group_id, text):
        text = text.strip()
        if not text:
            return None
        for slot, profile in self.player_profiles.get(group_id, {}).items():
            if profile.get("name") == text:
                return slot
        if text.upper() in self.player_profiles.get(group_id, {}):
            return text.upper()
        return None

    def _display(self, group_id, slot):
        profile = self.player_profiles.get(group_id, {}).get(slot)
        if profile and profile.get("name"):
            return profile["name"]
        return slot

    def _get_campaign(self, group_id):
        return {"cycle": self._cycle}

    def _save_profiles(self):
        self.saved += 1


class _FakeNPCRegistry:
    def __init__(self, npcs):
        self._npcs = dict(npcs)

    def get_npc(self, name):
        return self._npcs.get(name)

    def search_npc(self, keyword):
        return [npc for name, npc in self._npcs.items() if keyword in name]


def _base_profile(qq_id="QQ-1", affiliation="", **overrides):
    profile = {
        "qq_id": qq_id,
        "status": "confirmed",
        "cultivation_realm": "练气一层",
        "FACTION_STATE": {"affiliation": affiliation},
    }
    profile.update(overrides)
    return profile


async def _run_sect(fake_self, event, action="", target=""):
    messages = []
    async for msg in m.DonghuangPlugin.dh_sect(fake_self, event, action, target):
        messages.append(msg)
    return messages


def _run(coro):
    return asyncio.run(coro)


# ── 1. 未报名/未生成角色时的拒绝路径 ──

def test_sect_requires_group_and_slot():
    fake_self = _FakeSelf({})
    event = _FakeEvent(group_id="", sender_id="QQ-1")
    messages = _run(_run_sect(fake_self, event))
    assert any("群聊" in msg for msg in messages)

    fake_self = _FakeSelf({"g1": {}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_sect(fake_self, event))
    assert any("/dh join" in msg for msg in messages)


# ── 2. 没加入任何势力/宗门时的提示 ──

def test_sect_no_affiliation_prompts_join_faction():
    profile = _base_profile()
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}})
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_sect(fake_self, event))
    assert any("join_faction" in msg for msg in messages)


# ── 3. 加入的势力不是"宗门"类型时不会被桥接 ──

def test_sect_non_sect_faction_not_bridged():
    profile = _base_profile(affiliation="STATE-01")
    factions = {"STATE-01": {"name": "祁渊李氏", "type": "王朝"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_sect(fake_self, event))
    assert any("join_faction" in msg for msg in messages)
    assert profile["FACTION_STATE"]["sect"]["name"] == ""


# ── 4. 加入"宗门"类型势力后自动桥接建档 ──

def test_sect_bridges_from_sect_type_faction():
    profile = _base_profile(affiliation="CULT-01")
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions, cycle=5)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")
    messages = _run(_run_sect(fake_self, event))
    text = "\n".join(messages)
    assert "归墟宗" in text
    assert "外门弟子" in text  # 初始职位
    assert profile["FACTION_STATE"]["sect"]["name"] == "归墟宗"
    assert profile["FACTION_STATE"]["sect"]["joined_cycle"] == 5


# ── 5. 贡献点累积 ──

def test_sect_contribute_accumulates_points():
    profile = _base_profile(affiliation="CULT-01")
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages1 = _run(_run_sect(fake_self, event, "contribute"))
    assert any("贡献" in msg for msg in messages1)
    contribution_after_1 = profile["FACTION_STATE"]["sect"]["contribution"]
    assert contribution_after_1 > 0
    assert fake_self.saved == 1

    messages2 = _run(_run_sect(fake_self, event, "contribute"))
    contribution_after_2 = profile["FACTION_STATE"]["sect"]["contribution"]
    assert contribution_after_2 > contribution_after_1


# ── 6. 贡献点攒够后自动晋升 ──

def test_sect_auto_promotes_when_contribution_sufficient():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 198,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "contribute"))
    text = "\n".join(messages)
    assert "晋升" in text
    assert profile["FACTION_STATE"]["sect"]["position"] == "内门弟子"


# ── 7. 传承查看：职位不够时提示暂无可解锁传承 ──

def test_sect_heritage_empty_for_low_position():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "heritage"))
    assert any("没有可解锁的传承" in msg for msg in messages)


# ── 8. 传承查看：职位够时列出可解锁传承类型 ──

def test_sect_heritage_lists_types_for_high_position():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "内门弟子", "contribution": 200,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "heritage"))
    text = "\n".join(messages)
    assert "功法传承" in text


# ── 9. 师徒关系查看 ──

def test_sect_master_shows_relationship():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "内门弟子", "contribution": 200,
        "contribution_rank": 0, "heritage": [], "master": "李长老",
        "disciples": ["小徒儿"], "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "master"))
    text = "\n".join(messages)
    assert "李长老" in text
    assert "小徒儿" in text


def test_sect_master_no_master_or_disciples():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "master"))
    text = "\n".join(messages)
    assert "尚未拜师" in text
    assert "尚未收徒" in text


# ── 10. 拜师成功：同宗门 + 长老级身份 ──

def test_sect_worship_succeeds_for_elder_in_same_sect():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    npcs = {"李长老": {"name": "李长老", "role": "传功长老", "faction_code": "CULT-01"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions, npcs=npcs)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "worship", "李长老"))
    text = "\n".join(messages)
    assert "拜" in text and "为师" in text
    assert profile["FACTION_STATE"]["sect"]["master"] == "李长老"
    assert fake_self.saved == 1


# ── 11. 拜师失败：NPC 不属于同一宗门 ──

def test_sect_worship_rejects_npc_from_other_faction():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    npcs = {"孔红美": {"name": "孔红美", "role": "丞相", "faction_code": "STATE-01"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions, npcs=npcs)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "worship", "孔红美"))
    text = "\n".join(messages)
    assert "不属于" in text
    assert profile["FACTION_STATE"]["sect"]["master"] == ""


# ── 12. 拜师失败：身份不够格（不是长老/掌门/宗主/前辈）──

def test_sect_worship_rejects_junior_npc():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    npcs = {"小师弟": {"name": "小师弟", "role": "杂役弟子", "faction_code": "CULT-01"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions, npcs=npcs)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "worship", "小师弟"))
    text = "\n".join(messages)
    assert "不足以收徒指点" in text
    assert profile["FACTION_STATE"]["sect"]["master"] == ""


# ── 13. 已有师父时拒绝重复拜师 ──

def test_sect_worship_rejects_when_already_has_master():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "李长老", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    npcs = {"王长老": {"name": "王长老", "role": "掌律长老", "faction_code": "CULT-01"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions, npcs=npcs)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "worship", "王长老"))
    text = "\n".join(messages)
    assert "已拜" in text
    assert profile["FACTION_STATE"]["sect"]["master"] == "李长老"  # 未被覆盖


# ── 14. 收徒成功：核心弟子以上 + 同宗门 + 对方未拜师 ──

def test_sect_recruit_succeeds_for_senior_member():
    master_profile = _base_profile(qq_id="QQ-1", affiliation="CULT-01", name="张宗主")
    master_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "核心弟子", "contribution": 500,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    disciple_profile = _base_profile(qq_id="QQ-2", affiliation="CULT-01", name="小徒儿")
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf(
        {"g1": {"PLAYER-A": master_profile, "PLAYER-B": disciple_profile}}, factions=factions,
    )
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "recruit", "小徒儿"))
    text = "\n".join(messages)
    assert "收" in text and "为徒" in text
    assert disciple_profile["FACTION_STATE"]["sect"]["master"] == "张宗主"
    assert "小徒儿" in master_profile["FACTION_STATE"]["sect"]["disciples"]


# ── 15. 收徒失败：自己职位不够 ──

def test_sect_recruit_rejects_when_recruiter_junior():
    master_profile = _base_profile(qq_id="QQ-1", affiliation="CULT-01", name="张外门")
    master_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    disciple_profile = _base_profile(qq_id="QQ-2", affiliation="CULT-01", name="小徒儿")
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf(
        {"g1": {"PLAYER-A": master_profile, "PLAYER-B": disciple_profile}}, factions=factions,
    )
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "recruit", "小徒儿"))
    text = "\n".join(messages)
    assert "核心弟子" in text
    assert disciple_profile["FACTION_STATE"].get("sect", {}).get("master", "") in ("", None)


# ── 16. 收徒失败：对方已有师父 ──

def test_sect_recruit_rejects_when_target_already_has_master():
    master_profile = _base_profile(qq_id="QQ-1", affiliation="CULT-01", name="张宗主")
    master_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "长老", "contribution": 2000,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    disciple_profile = _base_profile(qq_id="QQ-2", affiliation="CULT-01", name="小徒儿")
    disciple_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "李长老", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf(
        {"g1": {"PLAYER-A": master_profile, "PLAYER-B": disciple_profile}}, factions=factions,
    )
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "recruit", "小徒儿"))
    text = "\n".join(messages)
    assert "已拜" in text
    assert disciple_profile["FACTION_STATE"]["sect"]["master"] == "李长老"


# ── 17. 领取传承成功 ──

def test_sect_claim_succeeds_for_unlocked_heritage():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "内门弟子", "contribution": 200,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "claim", "功法传承"))
    text = "\n".join(messages)
    assert "领取了" in text
    assert "功法传承" in profile["FACTION_STATE"]["sect"]["heritage"]


# ── 18. 领取传承失败：还没解锁 ──

def test_sect_claim_rejects_locked_heritage():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "claim", "血脉传承"))
    text = "\n".join(messages)
    assert "解锁不了" in text
    assert "血脉传承" not in profile["FACTION_STATE"]["sect"]["heritage"]


# ── 19. 领取传承失败：重复领取 ──

def test_sect_claim_rejects_duplicate():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "内门弟子", "contribution": 200,
        "contribution_rank": 0, "heritage": ["功法传承"], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "claim", "功法传承"))
    text = "\n".join(messages)
    assert "已经领取过" in text
    assert profile["FACTION_STATE"]["sect"]["heritage"].count("功法传承") == 1


# ── 20. 领取"功法传承"立刻获得修为进度加成 ──

def test_sect_claim_progress_bonus_applies_immediately():
    profile = _base_profile(affiliation="CULT-01", METHOD_STATE={"progress": 10})
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "内门弟子", "contribution": 200,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "claim", "功法传承"))
    text = "\n".join(messages)
    assert "效果：" in text
    assert profile["METHOD_STATE"]["progress"] == 15  # 10 + 5


# ── 21. 领取"血脉传承"立刻获得气血上限加成 ──

def test_sect_claim_hp_bonus_applies_immediately():
    profile = _base_profile(affiliation="CULT-01", hp={"current": 20, "max": 20})
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "长老", "contribution": 2000,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "claim", "血脉传承"))
    text = "\n".join(messages)
    assert "气血上限" in text
    assert profile["hp"]["max"] == 30  # 20 + 10
    assert profile["hp"]["current"] == 30


# ── 22. 领取"道心传承"立刻获得灵力上限加成 ──

def test_sect_claim_mp_bonus_applies_immediately():
    profile = _base_profile(affiliation="CULT-01", mp={"current": 15, "max": 15})
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "真传弟子", "master": "李长老",
        "contribution": 1000, "contribution_rank": 0, "heritage": [],
        "disciples": [], "joined_cycle": 1, "status": "active",
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "claim", "道心传承"))
    text = "\n".join(messages)
    assert "灵力上限" in text
    assert profile["mp"]["max"] == 20  # 15 + 5


# ── 23. 师父布置任务成功 ──

def test_sect_assign_task_succeeds():
    master_profile = _base_profile(qq_id="QQ-1", affiliation="CULT-01", name="张宗主")
    master_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "核心弟子", "contribution": 500,
        "contribution_rank": 0, "heritage": [], "master": "",
        "disciples": ["小徒儿"], "joined_cycle": 1, "status": "active",
        "pending_task": None,
    }
    disciple_profile = _base_profile(qq_id="QQ-2", affiliation="CULT-01", name="小徒儿")
    disciple_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "master": "张宗主",
        "contribution": 0, "contribution_rank": 0, "heritage": [],
        "disciples": [], "joined_cycle": 1, "status": "active", "pending_task": None,
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf(
        {"g1": {"PLAYER-A": master_profile, "PLAYER-B": disciple_profile}}, factions=factions,
    )
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "assign", "小徒儿 去后山采十株灵草"))
    text = "\n".join(messages)
    assert "布置了一项任务" in text
    task = disciple_profile["FACTION_STATE"]["sect"]["pending_task"]
    assert task is not None
    assert task["description"] == "去后山采十株灵草"
    assert task["assigned_by"] == "张宗主"


# ── 24. 布置任务失败：目标不是自己的徒弟 ──

def test_sect_assign_task_rejects_non_disciple():
    master_profile = _base_profile(qq_id="QQ-1", affiliation="CULT-01", name="张宗主")
    master_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "核心弟子", "contribution": 500,
        "contribution_rank": 0, "heritage": [], "master": "",
        "disciples": [], "joined_cycle": 1, "status": "active", "pending_task": None,
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": master_profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "assign", "小徒儿 去后山采十株灵草"))
    assert any("不是你的徒弟" in msg for msg in messages)


# ── 25. 徒弟完成任务：双方获得贡献点 ──

def test_sect_complete_task_rewards_both_sides():
    master_profile = _base_profile(qq_id="QQ-1", affiliation="CULT-01", name="张宗主")
    master_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "核心弟子", "contribution": 500,
        "contribution_rank": 0, "heritage": [], "master": "",
        "disciples": ["小徒儿"], "joined_cycle": 1, "status": "active", "pending_task": None,
    }
    disciple_profile = _base_profile(qq_id="QQ-2", affiliation="CULT-01", name="小徒儿")
    disciple_profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "master": "张宗主",
        "contribution": 10, "contribution_rank": 0, "heritage": [],
        "disciples": [], "joined_cycle": 1, "status": "active",
        "pending_task": {"description": "去后山采十株灵草", "assigned_by": "张宗主", "assigned_cycle": 1},
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf(
        {"g1": {"PLAYER-A": master_profile, "PLAYER-B": disciple_profile}}, factions=factions,
    )
    event = _FakeEvent(group_id="g1", sender_id="QQ-2")

    messages = _run(_run_sect(fake_self, event, "complete"))
    text = "\n".join(messages)
    assert "完成了" in text
    assert disciple_profile["FACTION_STATE"]["sect"]["pending_task"] is None
    assert disciple_profile["FACTION_STATE"]["sect"]["contribution"] == 15  # 10 + 5
    assert master_profile["FACTION_STATE"]["sect"]["contribution"] == 503  # 500 + 3


# ── 26. 没有待完成任务时 complete 提示 ──

def test_sect_complete_without_pending_task():
    profile = _base_profile(affiliation="CULT-01")
    profile["FACTION_STATE"]["sect"] = {
        "name": "归墟宗", "position": "外门弟子", "contribution": 0,
        "contribution_rank": 0, "heritage": [], "master": "", "disciples": [],
        "joined_cycle": 1, "status": "active", "pending_task": None,
    }
    factions = {"CULT-01": {"name": "归墟宗", "type": "宗门"}}
    fake_self = _FakeSelf({"g1": {"PLAYER-A": profile}}, factions=factions)
    event = _FakeEvent(group_id="g1", sender_id="QQ-1")

    messages = _run(_run_sect(fake_self, event, "complete"))
    assert any("没有师父布置的待完成任务" in msg for msg in messages)


if __name__ == "__main__":
    test_sect_requires_group_and_slot()
    test_sect_no_affiliation_prompts_join_faction()
    test_sect_non_sect_faction_not_bridged()
    test_sect_bridges_from_sect_type_faction()
    test_sect_contribute_accumulates_points()
    test_sect_auto_promotes_when_contribution_sufficient()
    test_sect_heritage_empty_for_low_position()
    test_sect_heritage_lists_types_for_high_position()
    test_sect_master_shows_relationship()
    test_sect_master_no_master_or_disciples()
    test_sect_worship_succeeds_for_elder_in_same_sect()
    test_sect_worship_rejects_npc_from_other_faction()
    test_sect_worship_rejects_junior_npc()
    test_sect_worship_rejects_when_already_has_master()
    test_sect_recruit_succeeds_for_senior_member()
    test_sect_recruit_rejects_when_recruiter_junior()
    test_sect_recruit_rejects_when_target_already_has_master()
    test_sect_claim_succeeds_for_unlocked_heritage()
    test_sect_claim_rejects_locked_heritage()
    test_sect_claim_rejects_duplicate()
    test_sect_claim_progress_bonus_applies_immediately()
    test_sect_claim_hp_bonus_applies_immediately()
    test_sect_claim_mp_bonus_applies_immediately()
    test_sect_assign_task_succeeds()
    test_sect_assign_task_rejects_non_disciple()
    test_sect_complete_task_rewards_both_sides()
    test_sect_complete_without_pending_task()
    print("\nsect_command tests passed")
