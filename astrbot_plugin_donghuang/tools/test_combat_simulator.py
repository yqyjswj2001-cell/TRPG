"""
test_combat_simulator.py - 战斗平衡模拟器冒烟测试

combat_simulator.py 直接复用 main.py 的战斗函数（_combat_stats /
_roll_attack / _combat_player_action 等），并逐行镜像了妖兽回合逻辑。
这个测试的意义是防漂移：以后改 main.py 战斗代码（重命名/改签名/改
结算流程），这里会先红灯，提醒同步模拟器，而不是让模拟器悄悄失真。

只做冒烟级验证（跑得快，不做统计精度断言）：
  1. 单场战斗能完整跑完，返回结构完整。
  2. 方向性 sanity：金丹初期打黄级怪应该碾压，练气一层单挑天级怪应该
     毫无胜算——固定种子，结果确定。
  3. 逃跑策略真的会产生逃跑结果（覆盖 _combat_player_action 的逃跑分支）。
  4. 常量快照能生成（改 main.py 常量名会在这里炸）。
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import combat_simulator as cs  # noqa: E402  （它自己会装 astrbot stub）


def test_single_battle_structure():
    random.seed(1234)
    r = cs.simulate_battle(realm_idx=4, tier="黄级", party=3, strategy="普攻")
    assert r["result"] in ("win", "wipe", "all_fled", "timeout")
    assert 1 <= r["rounds"] <= 30
    assert r["downed"] >= 0
    assert 0.0 <= r["monster_hp_pct"] <= 1.0
    print("✅ 测试1通过：单场战斗结构完整")


def test_direction_sanity_high_realm_crushes_low_tier():
    random.seed(42)
    cell = cs.run_cell(realm_idx=13, tier="黄级", party=3, strategy="普攻", battles=40)
    assert cell["win_rate"] >= 0.9, f"金丹初期3人打黄级怪胜率应≥90%，实际{cell['win_rate']:.0%}"
    print(f"✅ 测试2通过：金丹初期3人 vs 黄级 胜率 {cell['win_rate']:.0%}（碾压方向正确）")


def test_direction_sanity_low_realm_hopeless_vs_top_tier():
    random.seed(42)
    cell = cs.run_cell(realm_idx=0, tier="天级", party=1, strategy="普攻", battles=40)
    assert cell["win_rate"] <= 0.1, f"练气一层单挑天级怪胜率应≤10%，实际{cell['win_rate']:.0%}"
    print(f"✅ 测试3通过：练气一层1人 vs 天级 胜率 {cell['win_rate']:.0%}（无望方向正确）")


def test_flee_strategy_actually_flees():
    random.seed(7)
    fled_any = False
    for _ in range(30):
        r = cs.simulate_battle(realm_idx=2, tier="地级", party=1, strategy="见势撤")
        if r["fled"] > 0:
            fled_any = True
            break
    assert fled_any, "低境界打高阶怪、血量跌破30%时，见势撤策略应该出现过成功逃跑"
    print("✅ 测试4通过：逃跑策略走到了真实的逃跑判定分支")


def test_constants_snapshot():
    snap, digest = cs.constants_snapshot()
    assert snap["MONSTER_TIER_STATS"]
    assert snap["TIER_COMBAT_BONUS"]
    assert len(digest) == 12
    print("✅ 测试5通过：数值常量快照生成正常")


if __name__ == "__main__":
    test_single_battle_structure()
    test_direction_sanity_high_realm_crushes_low_tier()
    test_direction_sanity_low_realm_hopeless_vs_top_tier()
    test_flee_strategy_actually_flees()
    test_constants_snapshot()
    print("\ncombat_simulator smoke tests passed")
