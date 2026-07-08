# -*- coding: utf-8 -*-
"""
ecosystem_generator.py — 东荒普通生灵生态圈数据库（禽兽鱼虫草木）
总量约 3 万条，覆盖六大类：走兽/飞禽/游鱼/虫豸/草木/家畜
每类输出 JSONL + sample JSON，字段与 bestiary 兼容。
"""
import json, random, os

random.seed(42)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

REGIONS = ["中部","东部","南部","北地","西部"]
ELEMENTS = ["金","木","水","火","土","雷","冰","风","光","暗","毒"]

# ===================== 走兽（8000条）=====================
_BEASTS = {
    "forest": ["鹿","獐","麂","麝","麋","狍","野猪","山猫","猞猁","貂","鼬","獾","狐","狸","兔","松鼠","鼯鼠","刺猬","穿山甲","犰狳"],
    "mountain": ["岩羊","羚羊","盘羊","雪豹","山猫","猞猁","棕熊","黑熊","狼","豺","狐","旱獭","岩鼠","野山羊","麂"],
    "grassland": ["野马","野驴","黄羊","羚羊","野牛","狼","狐","兔","旱獭","跳鼠","鼬","獾"],
    "swamp": ["水鹿","麋鹿","野猪","水獭","河狸","麝鼠","水鼠","浣熊","獾","水牛"],
    "desert": ["骆驼","野驴","羚羊","沙狐","沙鼠","跳鼠","沙猫","沙漠刺猬","角蝰","沙蜥"],
    "snow": ["雪豹","雪狐","雪兔","白鼬","雪鼠","雪羊","白熊","北极狐","雪鹿","雷鸟"],
    "universal": ["鼠","蝙蝠","野兔","黄鼠狼","鼩鼱","田鼠","仓鼠"],
}
_BEAST_BIOMES = {
    "中部": ["forest","mountain","grassland","universal","universal"],
    "东部": ["forest","grassland","swamp","universal","universal"],
    "南部": ["forest","swamp","grassland","universal","universal"],
    "北地": ["snow","mountain","forest","universal"],
    "西部": ["desert","mountain","grassland","universal"],
}

# ===================== 飞禽（6000条）=====================
_BIRDS = {
    "forest": ["啄木鸟","黄鹂","画眉","百灵","杜鹃","鹧鸪","斑鸠","喜鹊","乌鸦","松鸦","山雀","鸫","鹟","莺","鹀",
              "鹎","鸲","鹪鹩","寿带","卷尾","伯劳","椋鸟","鹩哥","八哥","鹦鹉"],
    "wetland": ["鹤","鹭","鹳","鹬","鸻","秧鸡","水雉","翠鸟","鱼狗","鹡鸰","河乌","苇莺"],
    "grassland": ["雉鸡","鹌鹑","鸨","百灵","云雀","鹨","鵖","沙鸡","石鸡"],
    "mountain": ["鹰","隼","雕","鹫","鸢","鵟","鹞","雪鸡","雪鹑","岩鸽","雨燕","金丝燕"],
    "water": ["雁","鸭","天鹅","鸳鸯","鸬鹚","鹈鹕","海鸥","燕鸥","信天翁","鹱","海雀","企鹅"],
    "universal": ["麻雀","燕子","鸽子","猫头鹰","夜鹰","雨燕","乌鸦","喜鹊"],
}
_BIRD_BIOMES = {
    "中部": ["forest","grassland","mountain","universal","universal"],
    "东部": ["water","wetland","forest","universal"],
    "南部": ["wetland","forest","grassland","universal","universal"],
    "北地": ["mountain","water","forest","universal"],
    "西部": ["grassland","mountain","desert","universal"],
}

# ===================== 游鱼（5000条）=====================
_FISH = {
    "river": ["鲤鱼","鲫鱼","草鱼","鲢鱼","鳙鱼","青鱼","鳊鱼","鲂鱼","鲴鱼","鳜鱼","鲶鱼","黄颡鱼","鳢鱼","鳗鲡","黄鳝",
             "泥鳅","马口鱼","宽鳍鱲","鳑鲏","麦穗鱼","棒花鱼","沙塘鳢","虾虎鱼"],
    "lake": ["鲤鱼","鲫鱼","鲢鱼","鳙鱼","草鱼","青鱼","鲌鱼","鳊鱼","鳜鱼","鲈鱼","鳢鱼","黄颡鱼","鲶鱼","鳡鱼","鳤鱼"],
    "sea": ["带鱼","黄鱼","鲳鱼","鲅鱼","鳕鱼","鲷鱼","鲈鱼","石斑鱼","鲻鱼","梭鱼","鲱鱼","沙丁鱼","鳀鱼","鳗鱼","鳐鱼",
           "鲨鱼","金枪鱼","旗鱼","剑鱼","鲯鳅","飞鱼","海鲶","海鳗","海马","海龙"],
    "cold": ["鲑鱼","鳟鱼","鲟鱼","白鲑","茴鱼","江鳕","狗鱼","杜父鱼","绵鳚","狮子鱼"],
}
_FISH_BIOMES = {
    "中部": ["river","lake","cold"],
    "东部": ["sea","river","lake"],
    "南部": ["river","lake","sea"],
    "北地": ["cold","lake","river"],
    "西部": ["river","lake"],
}

# ===================== 虫豸（5000条）=====================
_INSECTS = {
    "flying": ["蝴蝶","蛾","蜻蜓","豆娘","蜉蝣","石蛾","草蛉","蚁蛉","螳蛉","蜂","熊蜂","胡蜂","蜜蜂","蚜蝇","食蚜蝇",
              "虻","蚊","摇蚊","蠓","蝇","丽蝇","麻蝇","寄蝇"],
    "ground": ["蚂蚁","白蚁","蟋蟀","螽斯","蝗虫","蚱蜢","蜚蠊","螳螂","竹节虫","叶虫","蠼螋","蜈蚣","马陆","潮虫","鼠妇",
              "蝎子","鞭蝎","避日蛛","盲蛛"],
    "aquatic": ["水黾","龙虱","水龟虫","豉甲","水蝎","负子蝽","划蝽","仰泳蝽","蜻蜓幼虫","石蛾幼虫","蜉蝣幼虫","蚊幼虫"],
    "beneficial": ["蜜蜂","蚕","白蜡虫","紫胶虫","五倍子蚜","瓢虫","草蛉","寄生蜂","捕食螨"],
    "pest": ["蝗虫","螟虫","蚜虫","介壳虫","天牛","吉丁虫","象甲","叶甲","金龟子","地老虎","蝼蛄","蛴螬","蝽象","蓟马"],
}
_INSECT_BIOMES = {
    "中部": ["ground","flying","aquatic","pest","beneficial"],
    "东部": ["flying","aquatic","ground","pest","beneficial"],
    "南部": ["aquatic","flying","ground","pest","beneficial"],
    "北地": ["ground","flying","aquatic","pest"],
    "西部": ["ground","flying","pest"],
}

# ===================== 草木（5000条）=====================
_PLANTS = {
    "tree": ["松","柏","杉","槐","榆","杨","柳","枫","桦","椴","樟","楠","榉","栎","槭","梧桐","银杏","合欢","皂荚","楝",
            "桑","柘","漆","盐肤木","乌桕","油桐","油茶","茶","棕榈","椰子","槟榔","桫椤","苏铁","银杏"],
    "shrub": ["杜鹃","山茶","栀子","茉莉","桂花","丁香","连翘","迎春","绣线菊","蔷薇","月季","玫瑰","枸杞","黄荆","紫珠",
             "荚蒾","忍冬","接骨木","胡枝子","锦鸡儿","金缕梅","蜡瓣花","海桐","瑞香","结香"],
    "herb": ["蒿","艾","蓟","蒲公英","车前","马齿苋","荠菜","繁缕","藜","苋","龙葵","曼陀罗","颠茄","乌头","附子",
            "黄连","黄芩","黄芪","当归","党参","人参","三七","甘草","柴胡","桔梗","沙参","麦冬","天冬","百合","贝母"],
    "vine": ["葛","紫藤","凌霄","络石","常春藤","爬山虎","葡萄","猕猴桃","五味子","木通","马兜铃","何首乌","菟丝子"],
    "water": ["莲","荷","菱","芡","菖蒲","香蒲","慈姑","水芹","水蕹","浮萍","满江红","槐叶萍","金鱼藻","黑藻","苦草"],
    "fungus": ["灵芝","茯苓","猪苓","马勃","木耳","银耳","猴头","竹荪","松茸","牛肝菌","鸡枞","虫草","雷丸","麦角","冬虫夏草"],
}
_PLANT_BIOMES = {
    "中部": ["tree","shrub","herb","vine","fungus"],
    "东部": ["tree","vine","water","shrub","fungus"],
    "南部": ["herb","water","tree","vine","fungus"],
    "北地": ["tree","shrub","herb","fungus"],
    "西部": ["shrub","herb","fungus"],
}

# ===================== 家畜（1000条）=====================
_LIVESTOCK = {
    "livestock": ["黄牛","水牛","牦牛","马","驴","骡","骆驼","羊","山羊","绵羊","猪","鸡","鸭","鹅","兔","狗","猫","鸽","鹌鹑","火鸡"],
    "working": ["耕牛","驮牛","战马","驿马","猎犬","牧羊犬","看门犬","捕鼠猫","信鸽","猎鹰","猎隼","鸬鹚"],
}
_LIVESTOCK_BIOMES = {r: ["livestock","working"] for r in REGIONS}

_BIOME_COLORS = {
    "forest": ["青","碧","翠","苍","绿","墨","褐","棕"],
    "mountain": ["灰","岩","石","褐","棕","青","苍","白"],
    "grassland": ["黄","褐","棕","灰","苍","碧"],
    "swamp": ["墨","黑","绿","褐","青","碧"],
    "desert": ["黄","沙","金","褐","棕","赤","灰"],
    "snow": ["白","银","雪","冰","灰","银","霜"],
    "river": ["青","碧","银","白","灰","金"],
    "lake": ["青","碧","银","深","浅","花"],
    "sea": ["蓝","深","灰","银","青","花","斑","条"],
    "cold": ["白","银","灰","冰","深","青"],
    "flying": ["金","彩","红","绿","蓝","紫","花","斑"],
    "ground": ["褐","黑","棕","红","黄","绿","花"],
    "aquatic": ["青","碧","银","黑","褐"],
    "beneficial": ["金","白","银","黄"],
    "pest": ["灰","褐","黑","黄","绿"],
    "tree": ["青","苍","翠","碧","绿","墨"],
    "shrub": ["红","紫","黄","白","粉","金","银"],
    "herb": ["绿","青","紫","白","黄","红"],
    "vine": ["青","绿","紫","黄","红"],
    "water": ["绿","青","碧","翠"],
    "fungus": ["白","黑","褐","红","黄","紫"],
    "livestock": ["黑","白","黄","花","褐","棕"],
    "working": ["黑","褐","灰","白","黄"],
}

# ===================== 生成器 =====================
def gen_ecosystem(cat, biome_map, creature_map, target):
    entries = []
    used = set()
    for i in range(target):
        region = random.choice(REGIONS)
        biomes = biome_map.get(region, ["universal"])
        biome = random.choice(biomes)
        creatures = creature_map.get(biome, ["未知"])
        creature = random.choice(creatures)
        color = random.choice(_BIOME_COLORS.get(biome, ["普通"]))
        name = f"{color}{creature}" if color != "普通" else creature
        if name in used:
            adj = random.choice(["大","小","长","短","肥","瘦","高","矮","粗","细","花","斑","金","银"])
            name = f"{adj}{name}"
        if name in used:
            continue
        used.add(name)
        size = random.choice(["小型","中型","大型","微小","庞大"]) if cat == "草木" else random.choice(["小型","中型","大型","微小"])
        entries.append({
            "name": name, "category": cat, "region": region, "habitat": biome,
            "size": size, "behavior": "野生", "edible": random.choice(["可食","不可食","有毒","药用"]),
            "desc": f"常见于{region}地区的{biome}环境中，是一种常见的{cat}" if cat != "草木" else f"{region}地区{biome}环境中常见的植物",
        })
        if i % 2000 == 0:
            print(f"  {cat}: {i}/{target}", flush=True)
    return entries

def write_files(entries, cat, out_dir):
    full = os.path.join(out_dir, f"{cat}_ecosystem.jsonl")
    sample_path = os.path.join(out_dir, f"{cat}_ecosystem_sample.json")
    with open(full, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    sample = entries[:min(120, len(entries))]
    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    mb = os.path.getsize(full) / 1048576
    print(f"  {cat}: {len(entries)} entries, {mb:.1f} MB -> {full}", flush=True)

def main():
    targets = [
        ("走兽", _BEAST_BIOMES, _BEASTS, 8000),
        ("飞禽", _BIRD_BIOMES, _BIRDS, 6000),
        ("游鱼", _FISH_BIOMES, _FISH, 5000),
        ("虫豸", _INSECT_BIOMES, _INSECTS, 5000),
        ("草木", _PLANT_BIOMES, _PLANTS, 5000),
        ("家畜", _LIVESTOCK_BIOMES, _LIVESTOCK, 1000),
    ]
    total = sum(t[3] for t in targets)
    print(f"Target: {total} entries across {len(targets)} categories")
    for cat, bmap, cmap, count in targets:
        print(f"Generating {cat} ({count})...")
        entries = gen_ecosystem(cat, bmap, cmap, count)
        write_files(entries, cat, OUT_DIR)
    print("Done!")

if __name__ == "__main__":
    main()
