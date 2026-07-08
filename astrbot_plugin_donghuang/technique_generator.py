# -*- coding: utf-8 -*-
"""
technique_generator.py — 东荒十万功法生成器
用法: python technique_generator.py [输出文件]

天级 10 本（手写）、地级 200 本（手写）、玄级 5000 本（半手写+模板）、
黄级 ~94800 本（模板组合生成），总计 100,000 本。

每本包含：名称、等级、属性、类别、创始人、所属、传播度、效果
"""
import json, random, sys
from pathlib import Path

random.seed(42)

# ══════════════════════════════════════════════════════
# 天级功法（10本，手写，每本独一无二）
# ══════════════════════════════════════════════════════
HEAVEN_TECHNIQUES = [
    {
        "name": "混沌圣诀", "tier": "天级", "element": "混沌",
        "category": "心法", "creator": "混沌道祖",
        "holder": "失传", "prevalence": "失传",
        "desc": "传说中开天辟地前的第一缕混沌之气所化，修至大成可身化混沌，万法不侵",
        "effect": {"cultivation_speed": 5, "all_resist": 3, "hp_max": 30, "luck": 5}
    },
    {
        "name": "九转魂功", "tier": "天级", "element": "全属性",
        "category": "心法", "creator": "九幽魂帝",
        "holder": "失落于北地冰川", "prevalence": "失传",
        "desc": "每转一次灵魂凝实一倍，九转之后魂魄不朽，肉身可弃",
        "effect": {"death_save": 5, "hp_max": 20, "stabilize": 3, "all_resist": 2}
    },
    {
        "name": "万剑归宗诀", "tier": "天级", "element": "金",
        "category": "剑法", "creator": "剑祖独孤",
        "holder": "东部灵竹海某处秘境", "prevalence": "绝学",
        "desc": "世间万剑皆为你所用，一剑出则万剑随，可斩断因果",
        "effect": {"attack_bonus": 8, "dodge_bonus": 2, "perception_bonus": 3}
    },
    {
        "name": "太虚步", "tier": "天级", "element": "风",
        "category": "身法", "creator": "太虚真人",
        "holder": "失传", "prevalence": "失传",
        "desc": "一步踏出可跨越千里，身化虚影不可捉摸，传说修炼至极可踏破虚空",
        "effect": {"dodge_bonus": 8, "speed_bonus": 5, "perception_bonus": 2}
    },
    {
        "name": "焚天圣焰典", "tier": "天级", "element": "火",
        "category": "道法", "creator": "炎帝",
        "holder": "西部火山遗迹", "prevalence": "失传",
        "desc": "以身为炉以魂为火，焚尽万物亦可焚尽自身业障",
        "effect": {"attack_bonus": 7, "chaos_resist": 4, "poison_immune": True}
    },
    {
        "name": "永恒冰封咒", "tier": "天级", "element": "冰",
        "category": "道法", "creator": "冰皇",
        "holder": "北地极寒深渊", "prevalence": "失传",
        "desc": "一念之间可冻结时光，万物停滞唯你独行",
        "effect": {"attack_bonus": 6, "speed_bonus": -1, "defense_bonus": 5, "paralyze_chance": 0.3}
    },
    {
        "name": "万灵归元术", "tier": "天级", "element": "木",
        "category": "心法", "creator": "青帝",
        "holder": "南部千年水松林", "prevalence": "绝学",
        "desc": "与天地万灵共鸣，可借草木之力疗伤回气，寿元绵长",
        "effect": {"heal_bonus": 5, "hp_max": 25, "cultivation_speed": 3, "luck": 2}
    },
    {
        "name": "大衍天机术", "tier": "天级", "element": "全属性",
        "category": "阵法", "creator": "天机子",
        "holder": "失传", "prevalence": "失传",
        "desc": "可推演天机预知祸福，布下大衍之阵困杀一切来犯之敌",
        "effect": {"perception_bonus": 5, "luck": 5, "defense_bonus": 4}
    },
    {
        "name": "雷帝真解", "tier": "天级", "element": "雷",
        "category": "道法", "creator": "雷帝",
        "holder": "中部断脉之下", "prevalence": "绝学",
        "desc": "引天地雷霆为己用，以雷淬体以电锻魂，天劫亦为你所用",
        "effect": {"attack_bonus": 7, "death_save": 3, "speed_bonus": 3}
    },
    {
        "name": "乾坤造化功", "tier": "天级", "element": "土",
        "category": "心法", "creator": "造化神君",
        "holder": "失传", "prevalence": "失传",
        "desc": "乾坤在手造化由心，可重塑山河亦可再造肉身",
        "effect": {"hp_max": 40, "defense_bonus": 5, "cultivation_speed": 4}
    },
]

# ══════════════════════════════════════════════════════
# 地级功法（200本，模板+手写混合）
# ══════════════════════════════════════════════════════
EARTH_PREFIXES = [
    "天罡","地煞","玄冥","九阳","太阴","混元","无极","万象","星辰","日月",
    "苍龙","白虎","朱雀","玄武","麒麟","凤凰","真龙","鲲鹏","金乌","玉兔",
    "破天","裂地","断岳","分海","焚天","冰封","雷动","风卷","云涌","电闪",
    "紫霄","青冥","赤焰","白金","黑水","黄尘","玄冰","碧落","丹霞","素雪",
    "归元","化生","涅槃","轮回","不朽","永恒","无尽","不灭","无上","至尊",
    "天罚","神裁","圣裁","仙谕","龙吟","凤鸣","虎啸","鹤唳","鹰击","鲸吞",
    "大日","皓月","繁星","流光","飞虹","惊鸿","游龙","翔凤","奔雷","骤雨",
    "虚空","混沌","鸿蒙","太初","洪荒","远古","上古","太古","万古","千劫",
    "镇天","伏魔","斩妖","诛邪","破妄","洞虚","观微","知命","逆命","夺天",
]
EARTH_SUFFIXES = ["诀","经","典","录","谱","卷","策","章","篇","鉴"]
EARTH_CATEGORIES = ["心法","剑法","刀法","枪法","拳法","身法","腿法","道法","阵法","掌法","指法","棍法","鞭法","戟法","斧法","箭术","暗器","御兽","炼丹","炼器","符箓","诅咒","治疗","遁术"]
EARTH_ELEMENTS = ["金","木","水","火","土","雷","冰","风","光","暗","毒","全属性"]
EARTH_PREVALENCE = ["绝学","独门","稀有","稀有","稀有","失传","绝学"]

def gen_earth():
    techniques = []
    used = set()
    for i in range(200):
        while True:
            p = random.choice(EARTH_PREFIXES)
            s = random.choice(EARTH_SUFFIXES)
            name = f"{p}{s}"
            if name not in used:
                used.add(name)
                break
        elem = random.choice(EARTH_ELEMENTS)
        cat = random.choice(EARTH_CATEGORIES)
        creator = random.choice(["失传","无名","上古大能","某位散修","已故宗师","隐世高人","宗门祖师"])
        holder = random.choice(["无主","散落各处",f"{random.choice(['中部','东部','南部','北地','西部'])}{random.choice(['宗门','遗迹','秘境'])}","某位隐修","失传"])
        prev = random.choice(EARTH_PREVALENCE)
        eff = {"attack_bonus": random.randint(1,5), "defense_bonus": random.randint(1,4),
               "hp_max": random.randint(3,15), "cultivation_speed": random.randint(1,3)}
        if cat in ("身法","遁术"): eff["dodge_bonus"] = random.randint(2,5)
        if cat in ("心法","治疗"): eff["heal_bonus"] = random.randint(1,3)
        techniques.append({"name":name,"tier":"地级","element":elem,"category":cat,
                          "creator":creator,"holder":holder,"prevalence":prev,
                          "desc":f"地级{cat}，{elem}属性，{prev}传承",
                          "effect":eff})
    return techniques

# ══════════════════════════════════════════════════════
# 玄级功法（5000本，前缀+后缀组合+随机属性）
# ══════════════════════════════════════════════════════
MYSTIC_NAMES = [
    "裂石","碎岩","断金","斩铁","破风","裂空","穿云","破浪","劈山","断流",
    "疾风","迅雷","流火","寒冰","暗影","幻光","残月","落日","飞星","惊鹊",
    "虎贲","龙骧","鹰扬","豹变","蛇行","鹤舞","猿纵","鹿奔","熊踞","狼顾",
    "碎玉","破冰","焚木","断水","裂地","劈石","碎金","熔岩","化雪","凝霜",
    "追魂","夺魄","灭灵","诛心","破胆","慑神","断念","绝情","忘忧","清心",
    "血煞","阴风","阳雷","玄水","赤火","青木","黄土","白金","黑冰","紫电",
    "摧山","倒海","翻江","覆雨","排云","推浪","卷沙","扬尘","破阵","陷敌",
    "流光","浮影","掠光","逐影","飞燕","轻云","踏雪","凌波","登萍","渡水",
    "金刚","铁壁","磐石","重岳","厚土","坚冰","玄铁","古铜","硬木","顽石",
    "回春","续命","复生","活血","通脉","醒神","凝气","聚灵","化毒","净身",
    "八卦","四象","两仪","五行","六合","七星","九宫","十方","万象","千机",
    "镇山","压海","定风","止水","灭火","封冰","锁雷","囚电","困兽","缚龙",
    "开天","辟地","碎虚","破界","斩空","断时","逆流","回光","返照","溯源",
    "炼魂","锻骨","淬体","易筋","洗髓","换血","通窍","开脉","筑基","结丹",
    "凌云","摩天","登霄","步虚","踏空","御风","乘风","驾雾","腾云","飞升",
]
MYSTIC_SUFFIXES = ["功","诀","法","术","式","招","手","掌","拳","腿","步","剑","刀","枪","棍","鞭","指","爪","劲","经"]
MYSTIC_CATEGORIES = EARTH_CATEGORIES
MYSTIC_ELEMENTS = EARTH_ELEMENTS
MYSTIC_PREVALENCE = ["大众","大众","大众","稀有","稀有","独门","独门","绝学"]

def gen_mystic():
    techniques = []
    used = set()
    for i in range(5000):
        while True:
            n = random.choice(MYSTIC_NAMES) + random.choice(MYSTIC_SUFFIXES)
            if n not in used:
                used.add(n)
                break
        elem = random.choice(MYSTIC_ELEMENTS)
        cat = random.choice(MYSTIC_CATEGORIES)
        creator = random.choice(["民间散修","某位武士","已故前辈","无名修士","宗门弟子","游方道人","江湖侠客","前辈散修"])
        holder = random.choice(["广为流传","失传","某宗门藏经阁","散修市集有售","边陲小镇流传","某家族祖传"])
        prev = random.choice(MYSTIC_PREVALENCE)
        eff = {"attack_bonus": random.randint(0,2), "defense_bonus": random.randint(0,1),
               "hp_max": random.randint(1,5)}
        if cat in ("身法","遁术"): eff["dodge_bonus"] = random.randint(1,2)
        techniques.append({"name":n,"tier":"玄级","element":elem,"category":cat,
                          "creator":creator,"holder":holder,"prevalence":prev,
                          "desc":f"玄级{cat}，{elem}属性",
                          "effect":eff})
    return techniques

# ══════════════════════════════════════════════════════
# 黄级功法（~94800本，纯模板组合生成）
# ══════════════════════════════════════════════════════
YELLOW_PREFIX_A = [
    "碎","破","断","裂","劈","斩","削","刺","扫","挑","拨","撩","挂","崩","砸",
    "推","拉","撕","扯","扭","绞","缠","绕","锁","扣","擒","拿","摔","打","击",
    "冲","撞","顶","压","挤","碾","揉","搓","抖","震","弹","崩","穿","透","贯",
    "劈","砍","剁","切","割","划","抹","削","刮","刨","凿","钻","挖","掘","铲",
]
YELLOW_PREFIX_B = [
    "石","岩","山","土","沙","泥","木","树","草","藤","竹","花","叶","根","枝",
    "石","岩","壁","崖","峰","岭","丘","坡","谷","涧","溪","河","湖","海","江",
    "铁","铜","钢","银","金","锡","铅","汞","砂","矿","玉","珠","晶","钻","璧",
    "牛","虎","蛇","鹰","鹤","猿","鹿","狼","豹","熊","狮","象","马","犬","猫",
    "风","云","雨","雪","霜","雾","露","冰","雷","电","火","烟","尘","沙","光",
    "日","月","星","天","地","山","水","火","风","雷","云","雨","气","灵","魂",
]
YELLOW_SUFFIX_C = ["手","掌","拳","指","爪","肘","膝","腿","脚","步","身","头","肩","腰","背"]
YELLOW_SUFFIX_D = ["法","术","式","招","击","打","功","诀","劲","经","谱","录","篇","章","卷"]
YELLOW_CATEGORIES = EARTH_CATEGORIES + ["基础拳脚","基础兵器","基础身法","基础心法","基础道术"]
YELLOW_ELEMENTS = EARTH_ELEMENTS + ["无"]
YELLOW_PREVALENCE = ["大众","大众","大众","大众","大众","大众","稀有","稀有","独门"]

def gen_yellow():
    techniques = []
    needed = 100000 - 10 - 200 - 5000
    p = YELLOW_PREFIX_A; b = YELLOW_PREFIX_B; s = YELLOW_SUFFIX_C + YELLOW_SUFFIX_D
    names = [f"{pa}{pb}{sc}" for pa in p for pb in b for sc in s]
    random.shuffle(names)
    if len(names) < needed:
        extra = [f"{random.choice(['小','大','快','重'])}{n}" for n in random.sample(names, needed - len(names))]
        names.extend(extra)
    names = names[:needed]
    for name in names:
        elem = random.choice(YELLOW_ELEMENTS); cat = random.choice(YELLOW_CATEGORIES)
        prev = random.choice(YELLOW_PREVALENCE)
        creator = random.choice(["无名武者","村中老人","走镖师傅","老猎户","说书人","军营流传","市井流传","已不可考"])
        eff = {"attack_bonus": random.randint(0,1), "defense_bonus": random.randint(0,1)}
        if cat in ("身法","基础身法","遁术"): eff["dodge_bonus"] = random.randint(0,1)
        techniques.append({"name":name,"tier":"黄级","element":elem,"category":cat,
                          "creator":creator,"holder":"广为流传","prevalence":prev,
                          "desc":f"黄级{cat}", "effect":eff})
    return techniques
def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "techniques_100k.json"
    
    total = 0
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("[\n")
        first = True
        for techs, label in [(HEAVEN_TECHNIQUES,'天级'), (gen_earth(),'地级'), (gen_mystic(),'玄级')]:
            print(f'Writing {label} {len(techs)}...')
            for t in techs:
                if not first: f.write(",\n")
                json.dump(t, f, ensure_ascii=False)
                first = False
                total += 1
        
        print(f'Generating 黄级...')
        p = YELLOW_PREFIX_A; b = YELLOW_PREFIX_B; s = YELLOW_SUFFIX_C + YELLOW_SUFFIX_D
        names = [f"{pa}{pb}{sc}" for pa in p for pb in b for sc in s]
        random.shuffle(names)
        needed = 100000 - total
        if len(names) < needed:
            extra = [f"{random.choice(['小','大','快','重'])}{n}" for n in random.sample(names, needed - len(names))]
            names.extend(extra)
        names = names[:needed]
        
        for i, name in enumerate(names):
            if i % 10000 == 0: print(f'  {i}/{needed}')
            elem = random.choice(YELLOW_ELEMENTS); cat = random.choice(YELLOW_CATEGORIES)
            prev = random.choice(YELLOW_PREVALENCE)
            creator = random.choice(["无名武者","村中老人","走镖师傅","老猎户","说书人","军营流传","市井流传","已不可考"])
            eff = {"attack_bonus": random.randint(0,1), "defense_bonus": random.randint(0,1)}
            if cat in ("身法","基础身法","遁术"): eff["dodge_bonus"] = random.randint(0,1)
            t = {"name":name,"tier":"黄级","element":elem,"category":cat,
                 "creator":creator,"holder":"广为流传","prevalence":prev,
                 "desc":f"黄级{cat}", "effect":eff}
            f.write(",\n")
            json.dump(t, f, ensure_ascii=False)
            total += 1
        f.write("\n]")
    
    print(f'Done: {total} techniques -> {output_file}')
