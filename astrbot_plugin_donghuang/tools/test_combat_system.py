"""
test_combat_system.py - 回合制战斗系统测试（见 world/combat_rules.md）

main.py 依赖 astrbot 框架（astrbot.api.*），测试环境没有装这个包，所以
本文件在 import main 之前先往 sys.modules 里塞一份最小 stub（只提供
main.py 实际用到的属性：filter.command_group/event_message_type/
EventMessageType.GROUP_MESSAGE、Context/Star/register、logger），
不改动 main.py 本身，只是让它能在没有 AstrBot 运行时的情况下被导入测试。

覆盖：
  1. 战斗数值随六维/境界/装备品阶变化（_combat_stats）
  2. 妖兽按品阶生成的数值落在声明区间内（_generate_monster）
  3. 状态效果的持续伤害与到期移除（_apply_status_tick）
  4. 状态效果对攻防/眩晕/灵力消耗的汇总（_status_modifiers）
  5. 命中判定的可复现性（_roll_attack，固定随机种子）
  6. 护盾吸收一次即消耗（_consume_shield）
  7. 玩家单回合行动分类：逃跑/防御/施法/用物品/普通攻击（_combat_player_action）
"""

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
        """@filter.command_group(...) 装饰后返回的对象，支持 .command(name) 继续注册子命令。"""

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


class _FakeSelf:
    """给 _combat_player_action 用的最小 self：它只用到 self._display()。"""

    def __init__(self, profiles):
        self.player_profiles = profiles

    def _display(self, group_id, slot):
        profile = self.player_profiles.get(group_id, {}).get(slot)
        if profile and profile.get("name"):
            return profile["name"]
        return slot


def _base_profile(**overrides):
    profile = {
        "name": "测试道友",
        "cultivation_realm": "练气一层",
        "six_dims": {"根骨": 10, "体质": 10},
        "RESOURCE_STATE": {"held": []},
        "hp": {"current": 20, "max": 20},
        "mp": {"current": 15, "max": 15},
        "METHOD_STATE": {"known_techniques": []},
        "combat_status": [],
    }
    profile.update(overrides)
    return profile


# ── 1. 战斗数值随六维/境界/装备变化 ──

def test_combat_stats_scales_with_six_dims_and_realm():
    baseline = _base_profile()
    atk0, def0, init0 = m._combat_stats(baseline)

    higher_gengu = _base_profile(six_dims={"根骨": 20, "体质": 10})
    atk1, def1, init1 = m._combat_stats(higher_gengu)
    assert atk1 > atk0
    assert init1 > init0

    higher_tizhi = _base_profile(six_dims={"根骨": 10, "体质": 20})
    atk2, def2, init2 = m._combat_stats(higher_tizhi)
    assert def2 > def0

    higher_realm = _base_profile(cultivation_realm="筑基初期")
    atk3, def3, _ = m._combat_stats(higher_realm)
    assert atk3 > atk0
    assert def3 > def0

    with_weapon = _base_profile(RESOURCE_STATE={"held": ["赤霄剑（玄级·火属·武器）"]})
    atk4, _, _ = m._combat_stats(with_weapon)
    assert atk4 == atk0 + 5  # 玄级武器加成

    with_heritage = _base_profile(FACTION_STATE={
        "sect": {"heritage": ["秘术传承", "器物传承"]}
    })
    atk5, def5, _ = m._combat_stats(with_heritage)
    assert atk5 == atk0 + 3  # 秘术传承常驻攻击加成
    assert def5 == def0 + 3  # 器物传承常驻防御加成


# ── 2. 妖兽按品阶生成的数值落在声明区间内 ──

def test_generate_monster_within_tier_ranges():
    random.seed(1)
    for tier, stats in m._MONSTER_TIER_STATS.items():
        for _ in range(20):
            monster = m._generate_monster(tier=tier)
            assert stats["hp"][0] <= monster["hp"] <= stats["hp"][1]
            assert stats["atk"][0] <= monster["atk"] <= stats["atk"][1]
            assert stats["def"][0] <= monster["def"] <= stats["def"][1]
            assert monster["hp"] == monster["hp_max"]
            assert monster["status"] == []


# ── 3. 状态效果的持续伤害与到期移除 ──

def test_apply_status_tick_dot_damage_and_expiry():
    hp_box = {"hp": 30}
    status = [{"name": "中毒", "turns_left": 1}]

    dot = m._apply_status_tick(lambda: hp_box["hp"], lambda v: hp_box.__setitem__("hp", v), status)
    assert dot == 3
    assert hp_box["hp"] == 27
    assert status == []  # turns_left 减到 0 后应被移除

    hp_box["hp"] = 30
    status = [{"name": "灼烧", "turns_left": 2}]
    dot = m._apply_status_tick(lambda: hp_box["hp"], lambda v: hp_box.__setitem__("hp", v), status)
    assert dot == 6
    assert hp_box["hp"] == 24
    assert len(status) == 1
    assert status[0]["turns_left"] == 1


# ── 4. 状态效果对攻防/眩晕/灵力消耗的汇总 ──

def test_status_modifiers_aggregate():
    atk_mod, def_mod, stunned, mp_mult = m._status_modifiers([])
    assert (atk_mod, def_mod, stunned, mp_mult) == (0, 0, False, 1.0)

    atk_mod, def_mod, stunned, mp_mult = m._status_modifiers([
        {"name": "加速", "turns_left": 2},
        {"name": "破甲", "turns_left": 2},
    ])
    assert atk_mod == 3
    assert def_mod == -3
    assert stunned is False

    _, _, stunned, _ = m._status_modifiers([{"name": "眩晕", "turns_left": 1}])
    assert stunned is True

    _, _, _, mp_mult = m._status_modifiers([{"name": "灵气紊乱", "turns_left": 2}])
    assert mp_mult == 1.5


# ── 5. 命中判定的可复现性 ──

def test_roll_attack_deterministic_with_seed():
    random.seed(42)
    hit, dmg, to_hit, dc = m._roll_attack(attacker_atk=5, defender_def=3)
    assert isinstance(hit, bool)
    assert dc == 13
    if hit:
        assert dmg >= 1
    else:
        assert dmg == 0

    # 攻击方修正极高时必定命中（1d20 最小值1 + 修正100 远超 DC）
    hit, dmg, to_hit, dc = m._roll_attack(attacker_atk=100, defender_def=3)
    assert hit is True
    assert dmg >= 1


# ── 6. 护盾吸收一次即消耗 ──

def test_consume_shield_absorbs_once():
    status = [{"name": "护盾", "turns_left": 2}]
    remaining = m._consume_shield(status, 15)
    assert remaining == 5  # 15 - 10
    assert status == []  # 命中一次即移除，不看剩余回合数

    status = []
    remaining = m._consume_shield(status, 15)
    assert remaining == 15  # 没有护盾，伤害原样通过


# ── 7. 玩家单回合行动分类 ──

def test_combat_player_action_branches():
    group_id = "g_combat_test"

    # 逃跑（用极高根骨保证摇骰稳定成功）
    random.seed(7)
    profile = _base_profile(six_dims={"根骨": 30, "体质": 10})
    fake_self = _FakeSelf({group_id: {"PLAYER-A": profile}})
    monster = m._generate_monster(tier="黄级", name="赤鳞妖虎")
    fled = []
    text = m.DonghuangPlugin._combat_player_action(
        fake_self, group_id, "PLAYER-A", profile, "我转身逃跑", monster, fled
    )
    assert "逃跑" in text

    # 防御 -> 附加护盾状态
    profile = _base_profile()
    fake_self = _FakeSelf({group_id: {"PLAYER-A": profile}})
    monster = m._generate_monster(tier="黄级", name="赤鳞妖虎")
    text = m.DonghuangPlugin._combat_player_action(
        fake_self, group_id, "PLAYER-A", profile, "我摆出防御姿态", monster, []
    )
    assert "防御" in text
    assert any(s["name"] == "护盾" for s in profile["combat_status"])

    # 施法：已知功法 + 灵力充足 -> 扣灵力
    profile = _base_profile(METHOD_STATE={"known_techniques": ["烈焰诀"]})
    fake_self = _FakeSelf({group_id: {"PLAYER-A": profile}})
    monster = m._generate_monster(tier="黄级", name="赤鳞妖虎")
    mp_before = profile["mp"]["current"]
    text = m.DonghuangPlugin._combat_player_action(
        fake_self, group_id, "PLAYER-A", profile, "我施展烈焰诀轰击对手", monster, []
    )
    assert "烈焰诀" in text
    assert profile["mp"]["current"] < mp_before

    # 施法：灵力不足 -> 施法落空，不扣血给对手
    profile = _base_profile(METHOD_STATE={"known_techniques": ["烈焰诀"]}, mp={"current": 1, "max": 15})
    fake_self = _FakeSelf({group_id: {"PLAYER-A": profile}})
    monster = m._generate_monster(tier="黄级", name="赤鳞妖虎")
    monster_hp_before = monster["hp"]
    text = m.DonghuangPlugin._combat_player_action(
        fake_self, group_id, "PLAYER-A", profile, "我施展烈焰诀", monster, []
    )
    assert "灵力不足" in text
    assert monster["hp"] == monster_hp_before

    # 使用物品：按品阶回复气血，且从持有列表移除
    profile = _base_profile(
        RESOURCE_STATE={"held": ["回气丹（黄级·木属·丹药）"]},
        hp={"current": 5, "max": 20},
    )
    fake_self = _FakeSelf({group_id: {"PLAYER-A": profile}})
    monster = m._generate_monster(tier="黄级", name="赤鳞妖虎")
    text = m.DonghuangPlugin._combat_player_action(
        fake_self, group_id, "PLAYER-A", profile, "我吃了回气丹", monster, []
    )
    assert "回气丹" in text
    assert profile["hp"]["current"] == 20  # 5 + 15（黄级回复量），封顶 max
    assert profile["RESOURCE_STATE"]["held"] == []

    # 默认：普通攻击
    profile = _base_profile()
    fake_self = _FakeSelf({group_id: {"PLAYER-A": profile}})
    monster = m._generate_monster(tier="黄级", name="赤鳞妖虎")
    text = m.DonghuangPlugin._combat_player_action(
        fake_self, group_id, "PLAYER-A", profile, "我挥剑砍向对手", monster, []
    )
    assert "赤鳞妖虎" in text


if __name__ == "__main__":
    test_combat_stats_scales_with_six_dims_and_realm()
    test_generate_monster_within_tier_ranges()
    test_apply_status_tick_dot_damage_and_expiry()
    test_status_modifiers_aggregate()
    test_roll_attack_deterministic_with_seed()
    test_consume_shield_absorbs_once()
    test_combat_player_action_branches()
    print("\ncombat_system tests passed")
