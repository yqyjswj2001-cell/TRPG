# -*- coding: utf-8 -*-
"""
item_generator.py — 东荒法宝/武器/丹药/灵材 四库生成器
用法: python item_generator.py

跟 technique_generator.py 是同一套思路：天级手写、地级半手写、玄级模板+
随机属性、黄级用多个词槽做笛卡尔积爆量。每类目标 20万条左右（"几十万"），
四类合计约 80 万条。输出格式统一为 JSONL（一行一个 JSON 对象），跟已有的
techniques_100k.json 保持一致，方便 main.py 用同一套"按需扫描"逻辑读取。

黄级词槽用笛卡尔积而不是"随机拼接+随机再抽类别"，保证名字里的类别词
跟 category 字段永远一致（比如名字叫"白银戒指"，category 字段就是"戒指"，
不会出现名字是戒指、类别却写成剑这种对不上的情况）。

四个输出文件：
  artifacts_200k.jsonl  —— 法宝（飞剑/法印/戒指/铃铛……）
  weapons_200k.jsonl    —— 武器（剑/刀/枪/斧……凡兵到仙兵）
  pills_200k.jsonl      —— 丹药（疗伤/筑基/解毒……）
  materials_200k.jsonl  —— 灵材（灵草/灵矿/灵兽材料……）
另外每类各抽 150 条黄级样本，存成 xxx_sample.json（普通 JSON 数组），
供 main.py 常驻内存加载，用法跟 techniques_sample.json 一致。
"""
import json, random, itertools
from pathlib import Path

random.seed(42)

ELEMENTS = ["金", "木", "水", "火", "土", "雷", "冰", "风", "光", "暗", "毒", "无"]
REGIONS = ["中部", "东部", "南部", "北地", "西部"]
TARGET_PER_CATEGORY = 200000
OUT_DIR = Path(__file__).parent / "data"

# 只谈新旧/大小/精糙这类"状态"形容词，跟"谁做的/哪来的"完全是两个语义域，
# 避免跟下面各类"制作方式"词槽撞词（比如都出现"民间"，拼出来变成
# "民间民间打造xxx"这种重复）。
QUALITY_PREFIX = ["小", "破", "古旧", "斑驳", "不起眼", "朴素", "精致", "崭新",
                  "残破", "老旧", "陈旧", "粗陋", "硕大", "轻巧", "厚重"]

# 各类目的"制作方式/来源"词槽——放在"品质前缀"和"材质"之间，必须是能
# 直接修饰名词的形容词/来源描述，不能是"纹样""品相"这类抽象名词
# （那种词只能用来描述物品，不能出现在物品名字本身里），且不能跟
# QUALITY_PREFIX 里的词重复或互为子串。
ARTIFACT_MAKE = ["手工", "精工", "量产", "御制", "官造", "私造", "仿古", "秘制",
                "古法", "批量", "坊间", "散修自制", "宗门制式", "民间打造", "作坊制"]
WEAPON_MAKE = ["军用", "官造", "民造", "私造", "量产", "制式", "仿制", "精工",
              "古法", "批量", "坊间", "镖局制式", "军中制式", "乡勇自制", "匠人手造"]
PILL_MAKE = ["秘制", "古法", "祖传", "坊间验方", "官制", "民间验方", "土法", "自炼",
            "批量精炼", "粗炼", "家传", "药铺常备方", "行脚郎中方", "土方", "验方"]
MATERIAL_MAKE = ["野生", "家养", "人工培育", "天然", "深山", "近海", "高山",
                 "批量采集", "坊间收购", "散修采集", "农户自种", "山民采摘",
                 "商贩转运", "寻常产地", "偏僻产地"]


def combo_names(slot_lists, category_slot_index, needed):
    """对多个词槽做笛卡尔积，返回 (name, category) 元组列表，category 取自
    category_slot_index 对应的那个槽位，保证名字和类别字段永远一致。
    结果数量不够 needed 时直接全量返回（调用方自己决定怎么补）。"""
    combos = list(itertools.product(*slot_lists))
    random.shuffle(combos)
    combos = combos[:needed]
    return [("".join(parts), parts[category_slot_index]) for parts in combos]


def write_jsonl(path, items):
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return len(items)


def write_sample(path, items, n=150):
    pool = [it for it in items if it["tier"] == "黄级"]
    random.shuffle(pool)
    json.dump(pool[:n], path.open("w", encoding="utf-8"), ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════
# 一、法宝（飞剑/法印/戒指/铃铛……随身携带、直接触发效果的法器）
# ══════════════════════════════════════════════════════
ARTIFACT_HEAVEN = [
    {"name": "混沌钟", "tier": "天级", "element": "混沌", "category": "钟", "creator": "混沌道祖", "holder": "失传", "prevalence": "失传", "desc": "一钟出世，可镇压万法，钟声所及因果皆止", "effect": {"defense_bonus": 8, "all_resist": 4, "stun_chance": 0.4}},
    {"name": "轮回镜", "tier": "天级", "element": "全属性", "category": "镜", "creator": "轮回古神", "holder": "失落于因果长河", "prevalence": "失传", "desc": "照见三世因果，可令敌手重历轮回之苦", "effect": {"perception_bonus": 6, "luck": 4, "curse_chance": 0.3}},
    {"name": "诛仙剑", "tier": "天级", "element": "金", "category": "飞剑", "creator": "剑祖", "holder": "四剑之一，下落不明", "prevalence": "绝学", "desc": "斩尽世间不平之事，出鞘则天地变色", "effect": {"attack_bonus": 10, "dodge_bonus": 2}},
    {"name": "太极符印", "tier": "天级", "element": "全属性", "category": "符印", "creator": "太极道人", "holder": "失传", "prevalence": "失传", "desc": "阴阳相生相克，可化解一切外来法力冲击", "effect": {"all_resist": 5, "heal_bonus": 3}},
    {"name": "紫金葫芦", "tier": "天级", "element": "土", "category": "葫芦", "creator": "炼丹祖师", "holder": "南部千年药田深处", "prevalence": "绝学", "desc": "内藏一方小世界，可炼万物为丹", "effect": {"heal_bonus": 6, "hp_max": 20}},
    {"name": "灭世幡", "tier": "天级", "element": "暗", "category": "幡", "creator": "幽冥教主", "holder": "北地极寒深渊", "prevalence": "失传", "desc": "幡动之处万物凋零，可摄魂夺魄", "effect": {"attack_bonus": 8, "curse_chance": 0.35}},
    {"name": "河图玉盘", "tier": "天级", "element": "全属性", "category": "罗盘", "creator": "上古巫祝", "holder": "失传", "prevalence": "失传", "desc": "推演天地大势，可预知一切劫数", "effect": {"perception_bonus": 8, "luck": 6}},
    {"name": "不灭金身甲", "tier": "天级", "element": "金", "category": "铠甲", "creator": "金身罗汉", "holder": "东部灵竹海某处秘境", "prevalence": "绝学", "desc": "披上此甲万法不侵，刀枪难伤", "effect": {"defense_bonus": 10, "hp_max": 25}},
    {"name": "九幽引魂铃", "tier": "天级", "element": "暗", "category": "铃铛", "creator": "九幽魂帝", "holder": "失传", "prevalence": "失传", "desc": "铃声一响，游魂尽归，生人闻之亦觉心悸", "effect": {"curse_chance": 0.4, "perception_bonus": 3}},
    {"name": "补天石", "tier": "天级", "element": "土", "category": "灵石", "creator": "女娲遗泽", "holder": "失落人间", "prevalence": "失传", "desc": "补天所遗一角，蕴含开天辟地之力", "effect": {"defense_bonus": 6, "hp_max": 30, "all_resist": 3}},
]

ARTIFACT_CATEGORY = ["飞剑", "法印", "法幡", "葫芦", "铃铛", "镜子", "伞", "扇子", "戒指", "项链",
                     "手镯", "念珠", "拂尘", "令牌", "罗盘", "傀儡", "纸人", "幡旗", "鼎", "炉",
                     "钵", "珠", "符箓", "玉牌", "玉镯", "冠冕", "铠甲", "盾牌", "法鼓", "玉笛",
                     "灵琴", "丝弦", "法网", "锁链", "玉秤", "玉尺", "法针", "玉梭", "法轮", "玉盘",
                     "宝壶", "宝瓶", "玉匣", "宝盒", "储物袋", "玉舟", "面具", "腰带", "玉佩", "玉简"]
ARTIFACT_PREVALENCE = ["大众", "大众", "大众", "稀有", "稀有", "独门", "绝学"]
ARTIFACT_MATERIAL = ["玄铁", "紫金", "寒玉", "赤铜", "墨玉", "白银", "陨石", "血玉", "青铜", "乌木",
                     "星辰砂", "龙鳞", "凤羽", "兽骨", "玄冰", "赤焰石", "黑曜石", "灵犀", "琉璃", "水晶"]


def gen_artifact_earth():
    items = []
    used = set()
    for i in range(300):
        while True:
            cat = random.choice(ARTIFACT_CATEGORY)
            name = f"{random.choice(ARTIFACT_MATERIAL)}{cat}"
            if name not in used:
                used.add(name); break
        eff = {"attack_bonus": random.randint(2, 6), "defense_bonus": random.randint(1, 5), "hp_max": random.randint(5, 15)}
        items.append({"name": name, "tier": "地级", "element": random.choice(ELEMENTS), "category": cat,
                      "creator": random.choice(["上古大能", "隐世宗门", "已故炼器宗师", "散修前辈"]),
                      "holder": random.choice(["无主", "散落各处", f"{random.choice(REGIONS)}秘境", "某宗门库房"]),
                      "prevalence": random.choice(ARTIFACT_PREVALENCE), "desc": f"地级{cat}，灵气充盈",
                      "effect": eff})
    return items


def gen_artifact_mystic():
    items = []
    used = set()
    prefixes = ["紫", "玄", "青", "赤", "白", "黑", "金", "银", "碧", "翠", "苍", "素", "皓", "幽", "灵",
               "云", "霜", "雪", "月", "星", "日", "辰", "岚", "霞", "露", "烟", "焰", "冰", "雷", "风"]
    for i in range(8000):
        while True:
            cat = random.choice(ARTIFACT_CATEGORY)
            name = f"{random.choice(prefixes)}{random.choice(ARTIFACT_MATERIAL)}{cat}"
            if name not in used:
                used.add(name); break
        eff = {"attack_bonus": random.randint(0, 3), "defense_bonus": random.randint(0, 2), "hp_max": random.randint(1, 6)}
        items.append({"name": name, "tier": "玄级", "element": random.choice(ELEMENTS), "category": cat,
                      "creator": random.choice(["民间炼器师", "游方道人", "无名工匠", "散修世家"]),
                      "holder": random.choice(["坊市有售", "某家族祖传", "散修市集流通", "边陲小镇流传"]),
                      "prevalence": random.choice(["大众", "大众", "大众", "稀有", "稀有", "独门"]),
                      "desc": f"玄级{cat}", "effect": eff})
    return items


def gen_artifact_yellow(needed):
    materials = ARTIFACT_MATERIAL + ["石", "铁", "木", "土", "布", "皮", "陶", "竹", "藤", "麻", "草"]
    pairs = combo_names([QUALITY_PREFIX, ARTIFACT_MAKE, materials, ARTIFACT_CATEGORY], 3, needed)
    items = []
    for name, cat in pairs:
        eff = {"attack_bonus": random.randint(0, 1), "defense_bonus": random.randint(0, 1)}
        items.append({"name": name, "tier": "黄级", "element": random.choice(ELEMENTS), "category": cat,
                      "creator": random.choice(["无名工匠", "村中铁匠", "行脚商贩", "已不可考"]),
                      "holder": "坊市常见", "prevalence": random.choice(["大众", "大众", "大众", "大众", "稀有"]),
                      "desc": f"黄级{cat}", "effect": eff})
    return items


# ══════════════════════════════════════════════════════
# 二、武器（凡兵到仙兵，强调实体兵刃本身而非法器效果）
# ══════════════════════════════════════════════════════
WEAPON_HEAVEN = [
    {"name": "弑神戈", "tier": "天级", "element": "金", "category": "戈", "creator": "战神", "holder": "失传", "prevalence": "失传", "desc": "曾弑一方天神，锋芒所指万物臣服", "effect": {"attack_bonus": 10, "hp_max": 15}},
    {"name": "断念枪", "tier": "天级", "element": "木", "category": "枪", "creator": "枪神", "holder": "东部灵竹海某处秘境", "prevalence": "绝学", "desc": "一枪破万法，念断则物灭", "effect": {"attack_bonus": 9, "dodge_bonus": 2}},
    {"name": "裂天弓", "tier": "天级", "element": "风", "category": "弓", "creator": "射日大羿后人", "holder": "失传", "prevalence": "失传", "desc": "开弓射日，箭出裂天", "effect": {"attack_bonus": 9, "perception_bonus": 4}},
    {"name": "镇岳斧", "tier": "天级", "element": "土", "category": "斧", "creator": "开山巨神", "holder": "中部断脉之下", "prevalence": "绝学", "desc": "一斧下去可断山河，镇压八方", "effect": {"attack_bonus": 8, "defense_bonus": 4, "hp_max": 20}},
    {"name": "血魔刀", "tier": "天级", "element": "暗", "category": "刀", "creator": "上古魔君", "holder": "失落于杀劫之地", "prevalence": "失传", "desc": "嗜血成性，越战越强，然反噬极重", "effect": {"attack_bonus": 11, "hp_max": -5}},
    {"name": "青莲剑", "tier": "天级", "element": "木", "category": "剑", "creator": "剑仙", "holder": "南部千年水松林", "prevalence": "绝学", "desc": "剑意如青莲绽放，斩妖除魔不沾因果", "effect": {"attack_bonus": 9, "all_resist": 2}},
]

WEAPON_MATERIAL = ["玄铁", "寒铁", "紫金", "精钢", "陨铁", "龙骨", "兽骨", "玄冰", "赤金", "墨玉",
                   "黑曜", "血色", "幽冥", "苍狼", "赤龙", "青龙", "白虎", "朱雀", "玄武", "星辰"]
WEAPON_CATEGORY = ["剑", "刀", "枪", "戟", "斧", "锤", "鞭", "弓", "弩", "匕首", "长枪", "狼牙棒",
                   "流星锤", "九节鞭", "飞镖", "铁尺", "双截棍", "月牙铲", "禅杖", "链锤", "钉锤",
                   "战斧", "砍刀", "弯刀", "直刀", "长剑", "短剑", "飞刀", "标枪", "长矛", "三叉戟",
                   "大锤", "骨朵", "锏", "戈", "矛", "钩", "拐", "镰", "锁镰", "判官笔", "双刀", "环刀"]


def gen_weapon_earth():
    items = []
    used = set()
    for i in range(300):
        while True:
            cat = random.choice(WEAPON_CATEGORY)
            name = f"{random.choice(WEAPON_MATERIAL)}{cat}"
            if name not in used:
                used.add(name); break
        eff = {"attack_bonus": random.randint(3, 7), "dodge_bonus": random.randint(0, 2)}
        items.append({"name": name, "tier": "地级", "grade": "法兵", "element": random.choice(ELEMENTS), "category": cat,
                      "creator": random.choice(["上古铸兵师", "隐世铁匠世家", "已故兵器宗师"]),
                      "holder": random.choice(["无主", "散落各处", f"{random.choice(REGIONS)}秘境"]),
                      "prevalence": random.choice(ARTIFACT_PREVALENCE), "desc": f"地级{cat}，锋锐无匹",
                      "effect": eff})
    return items


def gen_weapon_mystic():
    items = []
    used = set()
    prefixes = ["紫", "玄", "青", "赤", "白", "黑", "金", "银", "碧", "翠", "苍", "素", "皓", "幽",
               "云", "霜", "雪", "月", "星", "日", "辰", "岚", "霞", "露", "烟", "焰", "冰", "雷", "风"]
    for i in range(8000):
        while True:
            cat = random.choice(WEAPON_CATEGORY)
            name = f"{random.choice(prefixes)}{random.choice(WEAPON_MATERIAL)}{cat}"
            if name not in used:
                used.add(name); break
        eff = {"attack_bonus": random.randint(1, 4), "dodge_bonus": random.randint(0, 1)}
        items.append({"name": name, "tier": "玄级", "grade": "灵兵", "element": random.choice(ELEMENTS), "category": cat,
                      "creator": random.choice(["民间铁匠", "游方铸剑师", "无名工匠", "散修世家"]),
                      "holder": random.choice(["坊市有售", "某家族祖传", "散修市集流通"]),
                      "prevalence": random.choice(["大众", "大众", "大众", "稀有", "稀有"]),
                      "desc": f"玄级{cat}", "effect": eff})
    return items


def gen_weapon_yellow(needed):
    materials = WEAPON_MATERIAL + ["铁", "钢", "木", "石", "铜", "竹", "骨", "皮", "藤", "青铜"]
    pairs = combo_names([QUALITY_PREFIX, WEAPON_MAKE, materials, WEAPON_CATEGORY], 3, needed)
    items = []
    for name, cat in pairs:
        eff = {"attack_bonus": random.randint(0, 1)}
        items.append({"name": name, "tier": "黄级", "grade": "凡兵", "element": "无", "category": cat,
                      "creator": random.choice(["村中铁匠", "行脚商贩", "军中制式", "已不可考"]),
                      "holder": "坊市常见", "prevalence": random.choice(["大众", "大众", "大众", "大众", "稀有"]),
                      "desc": f"凡间{cat}", "effect": eff})
    return items


# ══════════════════════════════════════════════════════
# 三、丹药（服食生效，跟持续病症系统的"调理"直接对应）
# ══════════════════════════════════════════════════════
PILL_HEAVEN = [
    {"name": "九转还魂丹", "tier": "天级", "element": "全属性", "category": "回魂丹", "creator": "丹圣", "holder": "失传", "prevalence": "失传", "desc": "服之可续将断之命，甚至起死回生", "effect": {"heal_bonus": 8, "hp_max": 20, "death_save": 3}, "cures": ["重度"]},
    {"name": "太乙筑基丹", "tier": "天级", "element": "土", "category": "筑基丹", "creator": "太乙真人", "holder": "失传", "prevalence": "绝学", "desc": "筑基必成，且根基极为稳固", "effect": {"cultivation_speed": 5, "hp_max": 15}, "cures": []},
    {"name": "百草回春丹", "tier": "天级", "element": "木", "category": "疗伤丹", "creator": "药王", "holder": "南部千年药田深处", "prevalence": "绝学", "desc": "集百草之精华，愈合伤势快如再生", "effect": {"heal_bonus": 10}, "cures": ["轻度", "中度"]},
    {"name": "净心涤魂丹", "tier": "天级", "element": "光", "category": "清心丹", "creator": "静心道人", "holder": "失传", "prevalence": "失传", "desc": "涤荡心魔，走火入魔亦可化解", "effect": {"luck": 4}, "cures": ["轻度", "中度", "重度"]},
    {"name": "补天续元丹", "tier": "天级", "element": "土", "category": "续元丹", "creator": "补天氏传人", "holder": "失传", "prevalence": "绝学", "desc": "续元气于将断，损耗的寿元亦可稍补", "effect": {"hp_max": 25, "cultivation_speed": 3}, "cures": ["重度"]},
]

PILL_CATEGORY = ["疗伤丹", "回气丹", "筑基丹", "凝神丹", "解毒丹", "清心丹", "培元丹", "固本丹",
                 "养颜丹", "聚灵丹", "破障丹", "洗髓丹", "淬体丹", "回魂丹", "续命丹", "醒神丹",
                 "化瘀丹", "续元丹", "补血丹", "壮骨丹", "通脉丹", "养气丹", "安神丹", "辟谷丹",
                 "渡劫丹", "金创药", "驱毒散", "定神丸", "回阳丹", "养元散"]
PILL_MATERIAL = ["紫芝", "赤参", "雪莲", "灵芝", "首乌", "血珀", "玉髓", "青芷", "白术", "朱砂",
                 "冰蚕丝", "龙涎", "凤血", "麒麟草", "九叶", "千年", "百年", "野生", "灵田", "秘制"]
_CURE_CATEGORIES = {"解毒丹", "疗伤丹", "清心丹", "驱毒散", "化瘀丹"}


def gen_pill_earth():
    items = []
    used = set()
    for i in range(300):
        while True:
            cat = random.choice(PILL_CATEGORY)
            name = f"{random.choice(PILL_MATERIAL)}{cat}"
            if name not in used:
                used.add(name); break
        eff = {"heal_bonus": random.randint(2, 6), "hp_max": random.randint(0, 5)}
        cures = random.choice([[], ["轻度"], ["轻度", "中度"], ["中度"]]) if cat in _CURE_CATEGORIES else []
        items.append({"name": name, "tier": "地级", "element": random.choice(ELEMENTS), "category": cat,
                      "creator": random.choice(["上古炼丹宗师", "隐世药宗", "已故丹师"]),
                      "holder": random.choice(["无主", "散落各处", f"{random.choice(REGIONS)}秘境"]),
                      "prevalence": random.choice(ARTIFACT_PREVALENCE), "desc": f"地级{cat}，药效浓郁",
                      "effect": eff, "cures": cures})
    return items


def gen_pill_mystic():
    items = []
    used = set()
    for i in range(8000):
        while True:
            cat = random.choice(PILL_CATEGORY)
            name = f"{random.choice(PILL_MATERIAL)}{random.choice(PILL_MATERIAL)}{cat}"
            if name not in used:
                used.add(name); break
        eff = {"heal_bonus": random.randint(1, 3), "hp_max": random.randint(0, 2)}
        cures = random.choice([[], [], ["轻度"]]) if cat in _CURE_CATEGORIES else []
        items.append({"name": name, "tier": "玄级", "element": random.choice(ELEMENTS), "category": cat,
                      "creator": random.choice(["民间药师", "游方郎中", "无名炼丹师"]),
                      "holder": random.choice(["坊市有售", "药铺常备", "散修市集流通"]),
                      "prevalence": random.choice(["大众", "大众", "大众", "稀有"]),
                      "desc": f"玄级{cat}", "effect": eff, "cures": cures})
    return items


def gen_pill_yellow(needed):
    materials = PILL_MATERIAL + ["草", "根", "叶", "花", "果", "藤", "菌", "苔", "籽", "皮"]
    pairs = combo_names([QUALITY_PREFIX, PILL_MAKE, materials, PILL_CATEGORY], 3, needed)
    items = []
    for name, cat in pairs:
        eff = {"heal_bonus": random.randint(0, 1)}
        cures = ["轻度"] if cat in _CURE_CATEGORIES and random.random() < 0.5 else []
        items.append({"name": name, "tier": "黄级", "element": random.choice(ELEMENTS), "category": cat,
                      "creator": random.choice(["村中郎中", "行脚药贩", "已不可考"]),
                      "holder": "药铺常见", "prevalence": random.choice(["大众", "大众", "大众", "大众", "稀有"]),
                      "desc": f"黄级{cat}", "effect": eff, "cures": cures})
    return items


# ══════════════════════════════════════════════════════
# 四、灵材（炼丹炼器原料，本身不直接生效，靠"珍稀度"体现价值）
# ══════════════════════════════════════════════════════
MATERIAL_HEAVEN = [
    {"name": "混沌灵髓", "tier": "天级", "element": "混沌", "category": "灵髓", "origin": "失传", "prevalence": "失传", "desc": "开天辟地时残留的一缕混沌之髓，炼制天级法宝的顶级材料"},
    {"name": "龙血晶", "tier": "天级", "element": "金", "category": "灵晶", "origin": "上古真龙陨落之地", "prevalence": "绝学", "desc": "真龙精血凝结而成，蕴含磅礴生机与力量"},
    {"name": "九幽阴魂木", "tier": "天级", "element": "暗", "category": "灵木", "origin": "北地极寒深渊", "prevalence": "失传", "desc": "生长万年方能成材，木中蕴含幽冥之气"},
    {"name": "太虚星辰砂", "tier": "天级", "element": "全属性", "category": "灵砂", "origin": "坠星之地", "prevalence": "失传", "desc": "陨星坠地凝结而成，蕴含星辰本源之力"},
    {"name": "不灭火种", "tier": "天级", "element": "火", "category": "灵火", "origin": "西部火山遗迹", "prevalence": "绝学", "desc": "万年不熄的天地本源之火，炼器炼丹皆是极品引火之物"},
]

MATERIAL_CATEGORY = ["灵草", "灵矿", "灵石", "灵木", "灵藤", "灵果", "灵花", "灵叶", "灵根", "灵芝",
                     "灵砂", "灵晶", "灵髓", "灵羽", "灵鳞", "灵甲", "灵角", "灵牙", "灵骨", "灵血",
                     "灵胆", "灵丹", "灵油", "灵蜜", "灵浆", "灵泉水", "灵晶矿", "灵纹壳", "灵魄核", "灵息珠"]
MATERIAL_PREFIX = ["赤", "青", "白", "黑", "黄", "紫", "碧", "金", "银", "玄", "冰", "焰", "雷", "风",
                   "沙", "海", "山", "岩", "云", "星", "月", "日", "霜", "露", "雾", "烟", "血", "魂",
                   "幽", "圣"]
MATERIAL_ANIMAL = ["虎", "龙", "凤", "蛇", "鹰", "狼", "熊", "鹿", "猿", "蟒", "蝎", "蜘蛛", "螭", "犀"]


def gen_material_earth():
    items = []
    used = set()
    for i in range(300):
        while True:
            cat = random.choice(MATERIAL_CATEGORY)
            base = random.choice([f"{random.choice(MATERIAL_PREFIX)}{random.choice(MATERIAL_ANIMAL)}",
                                  f"{random.choice(MATERIAL_PREFIX)}{random.choice(REGIONS)}"])
            name = f"{base}{cat}"
            if name not in used:
                used.add(name); break
        items.append({"name": name, "tier": "地级", "element": random.choice(ELEMENTS), "category": cat,
                      "origin": random.choice([f"{random.choice(REGIONS)}秘境", "上古遗迹深处", "灵脉交汇之地"]),
                      "prevalence": random.choice(ARTIFACT_PREVALENCE), "desc": f"地级{cat}，蕴含浓郁灵气"})
    return items


def gen_material_mystic():
    items = []
    used = set()
    for i in range(8000):
        while True:
            cat = random.choice(MATERIAL_CATEGORY)
            name = f"{random.choice(MATERIAL_PREFIX)}{random.choice(MATERIAL_PREFIX)}{cat}"
            if name not in used:
                used.add(name); break
        items.append({"name": name, "tier": "玄级", "element": random.choice(ELEMENTS), "category": cat,
                      "origin": random.choice([f"{random.choice(REGIONS)}山野", "坊市有售", "散修采集流通"]),
                      "prevalence": random.choice(["大众", "大众", "大众", "稀有"]), "desc": f"玄级{cat}"})
    return items


def gen_material_yellow(needed):
    prefixes = MATERIAL_PREFIX + ["野", "山", "田", "村", "溪", "林", "谷", "坡", "岭", "洼"]
    pairs = combo_names([QUALITY_PREFIX, MATERIAL_MAKE, prefixes, MATERIAL_CATEGORY], 3, needed)
    items = []
    for name, cat in pairs:
        items.append({"name": name, "tier": "黄级", "element": random.choice(ELEMENTS), "category": cat,
                      "origin": "山野常见", "prevalence": random.choice(["大众", "大众", "大众", "大众", "稀有"]),
                      "desc": f"黄级{cat}"})
    return items


def build_and_write(label, heaven, earth_fn, mystic_fn, yellow_fn, out_name):
    earth = earth_fn()
    mystic = mystic_fn()
    used_total = len(heaven) + len(earth) + len(mystic)
    yellow = yellow_fn(TARGET_PER_CATEGORY - used_total)
    all_items = heaven + earth + mystic + yellow
    out_path = OUT_DIR / out_name
    total = write_jsonl(out_path, all_items)
    sample_path = OUT_DIR / out_name.replace("200k.jsonl", "sample.json")
    write_sample(sample_path, all_items)
    print(f"{label}: {total} 条 -> {out_path.name}（样本 {sample_path.name}）")


def main():
    build_and_write("法宝", ARTIFACT_HEAVEN, gen_artifact_earth, gen_artifact_mystic, gen_artifact_yellow, "artifacts_200k.jsonl")
    build_and_write("武器", WEAPON_HEAVEN, gen_weapon_earth, gen_weapon_mystic, gen_weapon_yellow, "weapons_200k.jsonl")
    build_and_write("丹药", PILL_HEAVEN, gen_pill_earth, gen_pill_mystic, gen_pill_yellow, "pills_200k.jsonl")
    build_and_write("灵材", MATERIAL_HEAVEN, gen_material_earth, gen_material_mystic, gen_material_yellow, "materials_200k.jsonl")


if __name__ == "__main__":
    main()
