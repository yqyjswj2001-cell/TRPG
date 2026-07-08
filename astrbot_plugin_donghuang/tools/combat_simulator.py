"""
combat_simulator.py - 战斗数值平衡模拟器

每次启动跑一大批模拟战斗（默认约 5 万场，几十秒内跑完），把结果记录成
JSON 存档 + 控制台报告，供数值平衡调整时对比参考。

用法（在插件目录下）：
    py tools\\combat_simulator.py                # 默认每格 300 场
    py tools\\combat_simulator.py --battles 500  # 提高采样精度
    py tools\\combat_simulator.py --quick        # 快速粗测（每格 80 场）
    py tools\\combat_simulator.py --seed 42      # 固定随机种子复现结果

产出：
  - 控制台：胜率矩阵（境界×妖兽品阶×队伍人数）、策略对比、武器影响、
    逃跑成功率、自动平衡告警、各品阶推荐挑战境界区间。
  - tools/balance_results/combat_sim_<时间戳>.json：本次完整数据 +
    当前数值常量快照（改了 main.py 里的怪物数值/品阶加成等常量后再跑，
    对比两份文件就知道哪个旋钮造成了哪些变化）。
  - tools/balance_results/history.jsonl：每次运行追加一行摘要，方便看趋势。
  - 若已有历史存档，自动打印与最近一次运行的胜率差异（|Δ|≥8个百分点才报，
    低于这个幅度在默认采样量下无法跟随机噪声区分）。

设计原则（跟测试套件同一思路）：
  - 一切战斗数学【直接复用 main.py 的真实函数】——_combat_stats /
    _roll_attack / _generate_monster / _apply_status_tick / _status_modifiers /
    _consume_shield，玩家行动更是直接调用真实的
    DonghuangPlugin._combat_player_action（含逃跑/防御/施法/用物品/普攻的
    完整分支判定）。改了游戏数值，模拟结果自动跟着变，不存在两套数字。
  - 唯一无法直接复用的是妖兽回合（它内嵌在异步的 _resolve_combat_round
    里，跟 campaign/turn_lock/AI 叙事耦合），本文件的 _monster_turn 是它
    的逐行镜像，改 main.py 的妖兽回合逻辑时必须同步改这里（有测试兜底：
    test_combat_simulator.py）。
  - 角色不是随手编的：六维走真实的八字推算（bazi.py），HP 上限走真实的
    突破成长曲线（基础20，每次突破+5，跨大境界+15，见 _apply_breakthrough）。

已知观察（记录在此，属于设计事实而非本工具的缺陷）：
  - PvE 战斗循环里妖兽只会普攻，STATUS_EFFECTS 里的眩晕/中毒/灼烧/破甲/
    加速/灵气紊乱目前没有任何施加入口，唯一能出现的状态是玩家防御产生的
    "护盾"。这些状态目前是"死旋钮"，平衡时不用考虑，但接入后要重跑模拟。
"""

import argparse
import hashlib
import json
import random
import sys
import time
import types
from datetime import datetime
from pathlib import Path

# Windows 控制台默认 GBK，emoji/生僻字会直接把脚本炸掉，强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PLUGIN_DIR.parent))

_RESULTS_DIR = _PLUGIN_DIR / "tools" / "balance_results"


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
from astrbot_plugin_donghuang.bazi import calc_bazi, bazi_to_attributes  # noqa: E402


class _FakeSelf:
    """_combat_player_action 只用到 self._display，给它一个最小替身。"""

    def _display(self, group_id, slot):
        return slot


_SELF = _FakeSelf()

_MONSTER_TIERS = ["黄级", "玄级", "地级", "天级"]
_SIM_TECHNIQUE = "御风剑诀"  # 施法策略用的功法名，只要在 known_techniques 里即可


# ==================================================
# 角色工厂：按游戏真实成长曲线造合成角色
# ==================================================

# HP 成长曲线参数：镜像 _apply_breakthrough（基础20，每次突破+5，跨大
# 境界瓶颈那次+15）。提成可变常量是给 GUI 数值旋钮做"如果突破多涨血"
# 的假设实验用的——注意游戏真实曲线在 main.py._apply_breakthrough 里，
# 改这里只影响模拟，调好后要手动同步回 main.py。
HP_CURVE = {"base": 20, "step": 5, "boundary_step": 15}


def _hp_max_for_realm(realm_idx):
    """HP 上限成长曲线，参数见 HP_CURVE。忽略天赋对 hp_max 的加成
    （正负抵消，均值≈0）。"""
    hp = HP_CURVE["base"]
    for j in range(realm_idx):
        hp += HP_CURVE["boundary_step"] if m._REALMS[j] in m._BOUNDARY_REALMS else HP_CURVE["step"]
    return hp


def make_player(slot, realm_idx, weapon_tier=None, with_technique=False):
    """造一个符合游戏真实分布的合成角色：六维走真实八字推算，HP 走真实
    突破成长曲线，MP 用战斗系统的默认值 15/15。"""
    bz = calc_bazi(
        random.randint(900, 1100), random.randint(1, 12),
        random.randint(1, 28), random.randint(0, 23),
    )
    six = bazi_to_attributes(bz)["six_dims"]
    hp_max = _hp_max_for_realm(realm_idx)
    held = []
    if weapon_tier:
        held.append(f"制式长剑（{weapon_tier}·金属·武器）")
    return {
        "name": slot,
        "six_dims": six,
        "cultivation_realm": m._REALMS[realm_idx],
        "hp": {"current": hp_max, "max": hp_max},
        "mp": {"current": 15, "max": 15},
        "combat_status": [],
        "IDENTITY_STATE": {"生存状态": "stable"},
        "RESOURCE_STATE": {"held": held},
        "METHOD_STATE": {"known_techniques": [_SIM_TECHNIQUE] if with_technique else []},
        "FACTION_STATE": {},
    }


# ==================================================
# 玩家策略：产出 raw_text，由真实的 _combat_player_action 解析执行
# ==================================================

def _strat_attack(profile, monster):
    return "全力出手攻击"


def _strat_caster(profile, monster):
    # 真实代码里灵力不足会"施法落空"白费一回合，理性玩家会先看灵力
    mp_mult = m._status_modifiers(profile["combat_status"])[3]
    cost = int(m._CAST_MP_COST * mp_mult)
    if profile["METHOD_STATE"]["known_techniques"] and profile["mp"]["current"] >= cost:
        return f"施展「{_SIM_TECHNIQUE}」"
    return "全力出手攻击"


def _strat_cautious(profile, monster):
    hp = profile["hp"]
    has_shield = any(s["name"] == "护盾" for s in profile["combat_status"])
    if hp["current"] < hp["max"] * 0.35 and not has_shield:
        return "全力防御"
    return _strat_caster(profile, monster)


def _strat_flee_low(profile, monster):
    hp = profile["hp"]
    if hp["current"] < hp["max"] * 0.3:
        return "逃跑"
    return "全力出手攻击"


STRATEGIES = {
    "普攻": (_strat_attack, {"with_technique": False}),
    "施法": (_strat_caster, {"with_technique": True}),
    "谨慎": (_strat_cautious, {"with_technique": True}),
    "见势撤": (_strat_flee_low, {"with_technique": False}),
}


# ==================================================
# 单场战斗：镜像 dh_combat 的先攻 + _resolve_combat_round 的回合结算
# ==================================================

def _monster_turn(monster, players, remaining, fled_slots, downed):
    """妖兽回合。⚠️ 这是 main.py._resolve_combat_round 里 actor=="M1"
    分支的逐行镜像（状态结算→眩晕检查→挑血最少的目标→摇命中伤害→护盾
    吸收→扣血→濒死判定），改那边必须同步改这里。"""
    if monster["hp"] <= 0:
        return
    m._apply_status_tick(lambda: monster["hp"], lambda v: monster.__setitem__("hp", v), monster["status"])
    if monster["hp"] <= 0:
        return
    _, _, stunned, _ = m._status_modifiers(monster["status"])
    if stunned:
        return
    alive_targets = [
        s for s in remaining if s not in fled_slots
        and players[s]["hp"]["current"] > 0
    ]
    if not alive_targets:
        return
    target_slot = min(alive_targets, key=lambda s: players[s]["hp"]["current"])
    tp = players[target_slot]
    _, target_def, _ = m._combat_stats(tp)
    _, t_def_mod, _, _ = m._status_modifiers(tp["combat_status"])
    hit, dmg, _, _ = m._roll_attack(monster["atk"], target_def + t_def_mod)
    if hit:
        dmg = m._consume_shield(tp["combat_status"], dmg)
        tp["hp"]["current"] = max(0, tp["hp"]["current"] - dmg)
        if tp["hp"]["current"] <= 0 and tp["IDENTITY_STATE"]["生存状态"] == "stable":
            tp["IDENTITY_STATE"]["生存状态"] = "dying"
            downed.add(target_slot)


def simulate_battle(realm_idx, tier, party, strategy="普攻", weapon_tier=None, max_rounds=30):
    """跑一场完整战斗，返回结果记录。max_rounds 是模拟器自己的保险丝
    （真实游戏没有回合上限，打不动时玩家自己会撤），触发即记为 timeout，
    timeout 率高说明这个配置双方都破不了防，本身就是平衡问题。"""
    strategy_fn, pkw = STRATEGIES[strategy]
    monster = m._generate_monster(tier)
    players = {
        f"P{i + 1}": make_player(f"P{i + 1}", realm_idx, weapon_tier=weapon_tier, **pkw)
        for i in range(party)
    }
    remaining = list(players)

    # 先攻排序：镜像 dh_combat（1d20+先攻修正，玩家和妖兽混排）
    rolls = []
    for slot, p in players.items():
        _, _, init_mod = m._combat_stats(p)
        rolls.append((slot, random.randint(1, 20) + init_mod))
    rolls.append(("M1", random.randint(1, 20) + monster["initiative_mod"]))
    rolls.sort(key=lambda x: x[1], reverse=True)
    order = [s for s, _ in rolls]

    downed = set()
    fled_total = set()
    rounds = 0
    result = "timeout"

    for round_no in range(1, max_rounds + 1):
        rounds = round_no
        fled_slots = []
        for actor in order:
            if actor != "M1" and actor not in remaining:
                continue
            if actor == "M1":
                _monster_turn(monster, players, remaining, fled_slots, downed)
                continue
            profile = players[actor]
            # 以下镜像 _resolve_combat_round 玩家分支的回合前置结算
            if profile["IDENTITY_STATE"]["生存状态"] != "stable":
                continue
            m._apply_status_tick(
                lambda p=profile: p["hp"]["current"],
                lambda v, p=profile: p["hp"].__setitem__("current", v),
                profile["combat_status"],
            )
            if profile["hp"]["current"] <= 0:
                profile["IDENTITY_STATE"]["生存状态"] = "dying"
                downed.add(actor)
                continue
            _, _, stunned, _ = m._status_modifiers(profile["combat_status"])
            if stunned:
                continue
            raw_text = strategy_fn(profile, monster)
            # 真实的玩家行动结算（逃跑/防御/施法/用物品/普攻全部分支）
            m.DonghuangPlugin._combat_player_action(
                _SELF, "sim", actor, profile, raw_text, monster, fled_slots,
            )

        remaining = [s for s in remaining if s not in fled_slots]
        fled_total.update(fled_slots)

        # 结束判定：镜像 _resolve_combat_round 的 combat_over 逻辑
        monster_dead = monster["hp"] <= 0
        players_left = [
            s for s in remaining
            if players[s]["IDENTITY_STATE"]["生存状态"] == "stable"
        ]
        if monster_dead:
            result = "win"
            break
        if not players_left:
            result = "all_fled" if not remaining else "wipe"
            break

    survivors_hp_pct = [
        players[s]["hp"]["current"] / players[s]["hp"]["max"]
        for s in remaining
        if players[s]["IDENTITY_STATE"]["生存状态"] == "stable"
    ]
    return {
        "result": result,
        "rounds": rounds,
        "downed": len(downed),
        "fled": len(fled_total),
        "survivors_hp_pct": survivors_hp_pct,
        "monster_hp_pct": monster["hp"] / monster["hp_max"],
    }


# ==================================================
# 批量模拟与聚合
# ==================================================

def run_cell(realm_idx, tier, party, strategy="普攻", weapon_tier=None, battles=300):
    """同一配置跑 battles 场，聚合成一格统计。"""
    wins = wipes = all_fled = timeouts = 0
    total_rounds = 0
    battles_with_downed = 0
    total_downed = 0
    win_hp_pcts = []
    loss_monster_hp = []
    pyrrhic = 0  # 赢了但有人倒地
    for _ in range(battles):
        r = simulate_battle(realm_idx, tier, party, strategy, weapon_tier)
        total_rounds += r["rounds"]
        total_downed += r["downed"]
        if r["downed"]:
            battles_with_downed += 1
        if r["result"] == "win":
            wins += 1
            win_hp_pcts.extend(r["survivors_hp_pct"])
            if r["downed"]:
                pyrrhic += 1
        elif r["result"] == "wipe":
            wipes += 1
            loss_monster_hp.append(r["monster_hp_pct"])
        elif r["result"] == "all_fled":
            all_fled += 1
            loss_monster_hp.append(r["monster_hp_pct"])
        else:
            timeouts += 1
    return {
        "realm": m._REALMS[realm_idx],
        "realm_idx": realm_idx,
        "tier": tier,
        "party": party,
        "strategy": strategy,
        "weapon_tier": weapon_tier,
        "battles": battles,
        "win_rate": wins / battles,
        "wipe_rate": wipes / battles,
        "fled_rate": all_fled / battles,
        "timeout_rate": timeouts / battles,
        "avg_rounds": total_rounds / battles,
        "downed_rate": battles_with_downed / battles,
        "avg_downed": total_downed / battles,
        "pyrrhic_rate": (pyrrhic / wins) if wins else 0.0,
        "avg_win_hp_pct": (sum(win_hp_pcts) / len(win_hp_pcts)) if win_hp_pcts else 0.0,
        "avg_loss_monster_hp_pct": (sum(loss_monster_hp) / len(loss_monster_hp)) if loss_monster_hp else 0.0,
    }


def run_matrix(battles=300, party_sizes=(1, 3, 5), realm_indices=None):
    """主矩阵：全境界 × 全品阶 × 各队伍人数，基准策略=普攻、无武器。"""
    if realm_indices is None:
        realm_indices = range(len(m._REALMS))
    cells = []
    for party in party_sizes:
        for tier in _MONSTER_TIERS:
            for idx in realm_indices:
                cells.append(run_cell(idx, tier, party, "普攻", None, battles))
    return cells


def run_strategy_experiment(battles=300):
    """策略对比：三个典型段位打门当户对的妖兽，四种策略各跑一遍。"""
    matchups = [(4, "玄级"), (10, "地级"), (13, "天级")]  # 练气五层/筑基中期/金丹初期
    out = []
    for idx, tier in matchups:
        for strat in STRATEGIES:
            out.append(run_cell(idx, tier, 3, strat, None, battles))
    return out


def run_weapon_experiment(battles=300):
    """武器影响：固定"练气五层3人打玄级"，只改武器品阶。"""
    out = []
    for weapon in [None] + _MONSTER_TIERS:
        out.append(run_cell(4, "玄级", 3, "普攻", weapon, battles))
    return out


def run_flee_table(battles=400):
    """逃跑成功率：1d20+(根骨-10)//2 vs 品阶DC，直接蒙特卡洛验证。"""
    out = []
    for bone in (8, 10, 12, 14):
        for tier in _MONSTER_TIERS:
            dc = m._FLEE_DC_BY_TIER[tier]
            ok = sum(
                1 for _ in range(battles)
                if random.randint(1, 20) + (bone - 10) // 2 >= dc
            )
            out.append({"根骨": bone, "tier": tier, "dc": dc, "success_rate": ok / battles})
    return out


# ==================================================
# 平衡分析：自动告警 + 推荐挑战区间
# ==================================================

def analyze_flags(matrix):
    """把明显失衡的格子挑出来。阈值取自跑团体验常识：胜率≥95%没有紧张感，
    ≤5%是送死，平均回合>8在群聊节奏下太拖（每回合要等全员发言+一次AI叙事），
    timeout 说明双方互相破不了防。"""
    flags = []
    for c in matrix:
        where = f"{c['realm']}·{c['party']}人 vs {c['tier']}"
        if c["timeout_rate"] > 0.02:
            flags.append(f"⚠️ 僵局：{where} 有 {c['timeout_rate']:.0%} 的战斗 30 回合分不出胜负（双方破不了防）")
        if c["win_rate"] >= 0.95 and c["avg_rounds"] <= 3:
            continue  # 高段位碾压低级怪是合理的，秒杀局不告警
        if c["win_rate"] >= 0.95:
            flags.append(f"🟢 过易：{where} 胜率 {c['win_rate']:.0%}，且平均要打 {c['avg_rounds']:.1f} 回合（赢定了还拖沓）")
        elif c["win_rate"] <= 0.05 and c["realm_idx"] >= _MONSTER_TIERS.index(c["tier"]) * 4:
            # 只对"境界档次≥品阶档次却毫无胜算"的格子告警，低修为打高阶怪本就该输
            flags.append(f"🔴 过难：{where} 胜率仅 {c['win_rate']:.0%}")
        if 0.35 <= c["win_rate"] <= 0.9 and c["avg_rounds"] > 8:
            flags.append(f"🐢 拖沓：{where} 势均力敌但平均 {c['avg_rounds']:.1f} 回合，群聊节奏下太长")
        if c["win_rate"] >= 0.5 and c["pyrrhic_rate"] > 0.5:
            flags.append(f"🩸 惨胜：{where} 赢面 {c['win_rate']:.0%}，但赢的场次里 {c['pyrrhic_rate']:.0%} 有人倒地")
    return flags


def recommend_ranges(matrix):
    """按品阶×队伍人数给出"有挑战但打得赢"（胜率35%~90%）的境界区间，
    给团长选怪当参考。"""
    rec = {}
    for tier in _MONSTER_TIERS:
        for party in sorted({c["party"] for c in matrix}):
            ok = [
                c for c in matrix
                if c["tier"] == tier and c["party"] == party
                and 0.35 <= c["win_rate"] <= 0.9
            ]
            key = f"{tier}·{party}人"
            if ok:
                lo = min(ok, key=lambda c: c["realm_idx"])
                hi = max(ok, key=lambda c: c["realm_idx"])
                rec[key] = f"{lo['realm']} ~ {hi['realm']}"
            else:
                rec[key] = "（无合适区间）"
    return rec


# ==================================================
# 常量快照与存档
# ==================================================

def constants_snapshot():
    """把当前所有影响战斗平衡的数值常量抓一份快照存进结果文件——改完
    数值再跑一遍，对比两份文件的快照就知道这次动了哪个旋钮。"""
    snap = {
        "MONSTER_TIER_STATS": m._MONSTER_TIER_STATS,
        "TIER_COMBAT_BONUS": m._TIER_COMBAT_BONUS,
        "STATUS_EFFECTS": m.STATUS_EFFECTS,
        "TIER_HEAL_AMOUNT": m._TIER_HEAL_AMOUNT,
        "FLEE_DC_BY_TIER": m._FLEE_DC_BY_TIER,
        "CAST_MP_COST": m._CAST_MP_COST,
        "REALMS": m._REALMS,
        "BOUNDARY_REALMS": sorted(m._BOUNDARY_REALMS),
        "hp_curve": dict(HP_CURVE),
        "attack_formula": "1d20+atk vs 10+def；暴击=天然20伤害×2；伤害=1d6+atk//2",
        "player_stat_formula": "atk=(根骨-10)//2+境界//2+3+武器加成；def=(体质-10)//2+境界//2+8",
    }
    digest = hashlib.sha1(
        json.dumps(snap, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:12]
    return snap, digest


def _find_previous_result():
    if not _RESULTS_DIR.exists():
        return None
    files = sorted(_RESULTS_DIR.glob("combat_sim_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def compare_with_previous(matrix, previous):
    """跟最近一次存档比矩阵胜率，|Δ|≥8个百分点才报（默认采样量下更小的
    差异分不清是调数值还是随机噪声）。"""
    if not previous:
        return []
    prev_cells = {
        (c["realm"], c["tier"], c["party"]): c
        for c in previous.get("matrix", [])
    }
    diffs = []
    for c in matrix:
        key = (c["realm"], c["tier"], c["party"])
        old = prev_cells.get(key)
        if not old:
            continue
        delta = c["win_rate"] - old["win_rate"]
        if abs(delta) >= 0.08:
            diffs.append(
                f"{c['realm']}·{c['party']}人 vs {c['tier']}：胜率 "
                f"{old['win_rate']:.0%} → {c['win_rate']:.0%}（{delta:+.0%}）"
            )
    return diffs


def save_results(payload):
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = _RESULTS_DIR / f"combat_sim_{ts}.json"
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    # 摘要追加进 history.jsonl，方便肉眼看趋势
    headline = {
        "timestamp": payload["meta"]["timestamp"],
        "seed": payload["meta"]["seed"],
        "battles_per_cell": payload["meta"]["battles_per_cell"],
        "constants_hash": payload["meta"]["constants_hash"],
        "flags_count": len(payload["flags"]),
        "file": out_path.name,
    }
    with (_RESULTS_DIR / "history.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(headline, ensure_ascii=False) + "\n")
    return out_path


# ==================================================
# 控制台报告（中文全角对齐）
# ==================================================

def _disp_width(text):
    return sum(2 if "一" <= ch <= "鿿" or ch in "（）·～" else 1 for ch in text)


def _pad(text, width):
    return text + " " * max(0, width - _disp_width(text))


def print_matrix(matrix, party_sizes):
    for party in party_sizes:
        rows = [c for c in matrix if c["party"] == party]
        if not rows:
            continue
        print(f"\n【胜率矩阵 · {party}人队伍】（策略=普攻，无武器；格式：胜率/平均回合）")
        header = _pad("境界", 12) + "".join(_pad(t, 16) for t in _MONSTER_TIERS)
        print(header)
        realms = sorted({c["realm_idx"] for c in rows})
        for idx in realms:
            line = _pad(m._REALMS[idx], 12)
            for tier in _MONSTER_TIERS:
                c = next(x for x in rows if x["realm_idx"] == idx and x["tier"] == tier)
                mark = ""
                if c["timeout_rate"] > 0.02:
                    mark = "!"
                line += _pad(f"{c['win_rate']:>4.0%}/{c['avg_rounds']:.1f}回{mark}", 16)
            print(line)


def print_report(matrix, strategy_exp, weapon_exp, flee_table, flags, rec, diffs, party_sizes):
    print_matrix(matrix, party_sizes)

    print("\n【策略对比】（3人队伍，门当户对的对局）")
    for idx, tier in [(4, "玄级"), (10, "地级"), (13, "天级")]:
        print(f"  {m._REALMS[idx]} vs {tier}：")
        for c in strategy_exp:
            if c["realm_idx"] == idx and c["tier"] == tier:
                extra = f"，逃走率{c['fled_rate']:.0%}" if c["strategy"] == "见势撤" else ""
                print(
                    f"    {_pad(c['strategy'], 8)}胜率 {c['win_rate']:>4.0%}  "
                    f"平均 {c['avg_rounds']:.1f} 回合  倒地率 {c['downed_rate']:.0%}{extra}"
                )

    print("\n【武器影响】（练气五层3人 vs 玄级，普攻）")
    for c in weapon_exp:
        label = c["weapon_tier"] or "无武器"
        print(f"    {_pad(label, 8)}胜率 {c['win_rate']:>4.0%}  平均 {c['avg_rounds']:.1f} 回合")

    print("\n【逃跑成功率】（1d20+(根骨-10)//2 vs 品阶DC）")
    header = _pad("根骨", 8) + "".join(_pad(t, 10) for t in _MONSTER_TIERS)
    print("    " + header)
    for bone in (8, 10, 12, 14):
        line = _pad(str(bone), 8)
        for tier in _MONSTER_TIERS:
            e = next(x for x in flee_table if x["根骨"] == bone and x["tier"] == tier)
            line += _pad(f"{e['success_rate']:.0%}", 10)
        print("    " + line)

    print("\n【推荐挑战区间】（胜率 35%~90% 的境界范围，供团长选怪参考）")
    for key, val in rec.items():
        print(f"    {_pad(key, 12)}{val}")

    print(f"\n【自动平衡告警】（{len(flags)} 条）")
    if flags:
        for f in flags:
            print(f"    {f}")
    else:
        print("    （无告警）")

    if diffs:
        print(f"\n【与上次运行的显著变化】（|Δ胜率|≥8pp，共 {len(diffs)} 处）")
        for d in diffs:
            print(f"    {d}")


# ==================================================
# 入口
# ==================================================

def main(argv=None):
    parser = argparse.ArgumentParser(description="东荒战斗数值平衡模拟器")
    parser.add_argument("--battles", type=int, default=300, help="每个配置格子跑多少场（默认300）")
    parser.add_argument("--seed", type=int, default=None, help="随机种子（默认随机，会记录进结果文件）")
    parser.add_argument("--quick", action="store_true", help="快速粗测：每格80场")
    args = parser.parse_args(argv)

    battles = 80 if args.quick else args.battles
    seed = args.seed if args.seed is not None else random.randrange(1 << 31)
    random.seed(seed)

    party_sizes = (1, 3, 5)
    snap, digest = constants_snapshot()
    previous = _find_previous_result()

    print(f"东荒战斗平衡模拟 · 种子={seed} · 每格{battles}场 · 常量指纹={digest}")
    total_cells = len(m._REALMS) * len(_MONSTER_TIERS) * len(party_sizes)
    est_battles = total_cells * battles + battles * 12 + battles * 5
    print(f"主矩阵 {total_cells} 格 + 策略/武器/逃跑实验，总计约 {est_battles} 场，开始……")

    t0 = time.time()
    matrix = run_matrix(battles=battles, party_sizes=party_sizes)
    strategy_exp = run_strategy_experiment(battles=battles)
    weapon_exp = run_weapon_experiment(battles=battles)
    flee_table = run_flee_table()
    elapsed = time.time() - t0

    flags = analyze_flags(matrix)
    rec = recommend_ranges(matrix)
    diffs = compare_with_previous(matrix, previous)

    payload = {
        "meta": {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "seed": seed,
            "battles_per_cell": battles,
            "elapsed_seconds": round(elapsed, 1),
            "constants_hash": digest,
            "constants": snap,
        },
        "matrix": matrix,
        "strategy_experiment": strategy_exp,
        "weapon_experiment": weapon_exp,
        "flee_table": flee_table,
        "flags": flags,
        "recommended_ranges": rec,
        "diff_vs_previous": diffs,
    }
    out_path = save_results(payload)

    print_report(matrix, strategy_exp, weapon_exp, flee_table, flags, rec, diffs, party_sizes)
    print(f"\n完成：{est_battles} 场模拟耗时 {elapsed:.1f}s，完整数据已存 {out_path}")


if __name__ == "__main__":
    main()
