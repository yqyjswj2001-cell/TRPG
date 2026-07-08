# -*- coding: utf-8 -*-
"""
npc_attribute_roller.py — 给 NPC 预先摇生辰八字和衍生属性。

跟玩家角色同一套逻辑：数值/客观事实（生辰八字、灵根、六维、区域倾向、
身份阶层、性别）由代码摇，不让 AI 编数字；AI 只负责在这些既定属性基础上
写名字/性格/背景故事。

输出两批"属性签"：
- major_npc_slots.json：51条（17个势力各3个），每条绑定一个具体势力代号，
  给「重要人物」用，后续生成时要详细设定。
- minor_npc_slots.json：300条，按现有子区域数量平均分配（每个子区域约7个），
  给「常见互动NPC」用，设定可以更轻量。

用法：python npc_attribute_roller.py
"""
import json, random
from pathlib import Path
from bazi import calc_bazi, bazi_to_attributes

random.seed(42)
OUT_DIR = Path(__file__).parent / "data"

FACTION_CODES = [
    "STATE-01", "STATE-02", "STATE-03", "STATE-04",
    "CULT-01", "CULT-02", "CULT-03", "CULT-04", "CULT-05",
    "FREE-01", "FREE-02", "FREE-03", "FREE-04",
    "HIDDEN-01", "HIDDEN-02", "HIDDEN-03", "HIDDEN-04",
]


def _roll_birth(min_age=16, max_age=130):
    """随机摇一个出生年月日时，年份基准用东荒历（12000+），只是相对
    基准，不需要精确对应某一局具体的开团年份——NPC是跨团共用的静态数据。"""
    age = random.randint(min_age, max_age)
    year = 12000 - age
    month = random.randint(1, 12)
    day = random.randint(1, 28)  # 避开大小月/闰年问题，够用
    hour = random.randint(0, 23)
    return year, month, day, hour, age


def _roll_slot(tag_key, tag_value):
    year, month, day, hour, age = _roll_birth()
    bazi = calc_bazi(year, month, day, hour)
    attrs = bazi_to_attributes(bazi)
    return {
        tag_key: tag_value,
        "age": age,
        "birth": {"year": year, "month": month, "day": day, "hour": hour},
        "eight_chars": bazi["eight_chars"],
        "spirit_root_element": attrs["spirit_root"],
        "spirit_root_tier": attrs["root_tier"],
        "six_dims": attrs["six_dims"],
        "region_lean": attrs["region"],
        "identity_tier": attrs["identity_tier"],
        "gender": attrs["gender"],
    }


def main():
    # 重要人物：每个势力3个槽位
    major_slots = []
    for code in FACTION_CODES:
        for _ in range(3):
            major_slots.append(_roll_slot("faction_code", code))
    (OUT_DIR / "major_npc_slots.json").write_text(
        json.dumps(major_slots, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"重要人物属性签：{len(major_slots)} 条 -> major_npc_slots.json")

    # 常见NPC：按现有子区域数量平均分配
    minor_slots = []
    target_total = 300
    for region in ["中部", "东部", "南部", "北地", "西部"]:
        sub_path = OUT_DIR / f"{region}_subregions.json"
        if not sub_path.exists():
            continue
        subs = json.loads(sub_path.read_text(encoding="utf-8"))
        per_sub = max(1, target_total // (5 * max(1, len(subs))))
        for sub in subs:
            for _ in range(per_sub):
                minor_slots.append(_roll_slot("subregion", sub["name"]) | {"region": region})
    (OUT_DIR / "minor_npc_slots.json").write_text(
        json.dumps(minor_slots, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"常见NPC属性签：{len(minor_slots)} 条 -> minor_npc_slots.json")


if __name__ == "__main__":
    main()
