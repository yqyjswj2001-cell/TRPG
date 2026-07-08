# -*- coding: utf-8 -*-
"""
bestiary_generator.py — 东荒生灵生态圈数据库生成器
生成九类生灵，按品阶分四档，总量约 8 万条。
每类输出一个 JSONL 文件 + 一个 sample JSON 文件。
"""
import json, random, os, sys

random.seed(42)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ===== 基础元素/颜色/部位/原型池 =====
ELEMENTS = ["金","木","水","火","土","雷","冰","风","光","暗","毒"]
COLORS = ["赤","墨","青","白","黑","紫","黄","灰","银","金","碧","苍","玄","幽","血","霜","雷","焰","冰","毒"]
BODY_PARTS = ["鳞","羽","鬃","爪","角","翼","尾","牙","眼","皮","甲","壳","鳍","翅","触"]
CREATURES_BEAST = ["虎","狼","蛇","鹰","熊","豹","狮","蟒","蝎","蛛","蚁","蜂","鱼","鳄","猿","雕","狐","犬","猫","鼠","兔","鹿","象","犀","獾","貂","貂","獭","貘","蜈"]
CREATURES_AQUA = ["鱼","蛇","蟒","蛟","龟","蟹","虾","蛙","鳄","螺","贝","鲤","鳗","鲨","鲸"]
CREATURES_INSECT = ["蚁","蜂","蝎","蛛","蝉","蝶","蛾","蝇","蚊","瓢","螳","蜈","蛉","蠹","蚣"]
CREATURES_PLANT = ["藤","花","草","树","竹","莲","菇","苔","藓","藻","蔓","棘","蒲","葛","兰"]
CREATURES_OBJ = ["石","木","铁","铜","玉","晶","骨","纸","布","瓦","瓷","镜","灯","锁","剑"]

# 各区域特征
REGIONS = ["中部","东部","南部","北地","西部"]
REGION_BIAS = {
    "中部": ["山","林","原","矿"],
    "东部": ["海","竹","岛","港"],
    "南部": ["泽","田","河","湖"],
    "北地": ["雪","冰","山","松"],
    "西部": ["沙","漠","崖","墟"],
}

# 品阶分布权重
TIER_WEIGHTS = {"黄级":[70,1],"玄级":[25,2],"地级":[4,5],"天级":[1,10]}

def pick_tier():
    tiers, weights = zip(*[(k, v[0]) for k, v in TIER_WEIGHTS.items()])
    return random.choices(tiers, weights=weights, k=1)[0]

# ===== 神兽（手写 20 只）=====
SHENSHOU = [
    {"name":"烛龙","category":"神兽","power_tier":"天级","element":"光","region":"全域","temperament":"太古威严","abilities":"睁眼为昼闭眼为夜、烛照万物","rarity":"传说","desc":"人面龙身，衔火精以照天门，睁眼为白昼闭眼为黑夜，居于极北之巅的钟山之上"},
    {"name":"九尾天狐","category":"神兽","power_tier":"天级","element":"火","region":"东部","temperament":"妖异高贵","abilities":"九尾齐摇可焚天煮海、幻化人形蛊惑人心、每条尾巴蕴含一种神通","rarity":"传说","desc":"通体雪白九尾飘摇，眼瞳如血月，每百年长出一条新尾，九尾俱全时可化为人形行走人间"},
    {"name":"应龙","category":"神兽","power_tier":"天级","element":"水","region":"东部","temperament":"威严仁慈","abilities":"呼风唤雨、展翼遮天、以尾画地即成江河","rarity":"传说","desc":"有翼之龙，双翼展开可遮天蔽日，曾助人族治水开河，是农耕文明信奉的雨神"},
    {"name":"鲲鹏","category":"神兽","power_tier":"天级","element":"风","region":"东部","temperament":"缥缈壮阔","abilities":"化身巨鲲游于深海、展翼为鹏扶摇九万里、吞噬天地灵气","rarity":"传说","desc":"北冥有鱼其名为鲲，化而为鸟其名为鹏，鹏之背不知其几千里，怒而飞翼若垂天之云"},
    {"name":"麒麟","category":"神兽","power_tier":"天级","element":"土","region":"中部","temperament":"祥瑞仁厚","abilities":"踏云而行足不沾尘、所过之处草木逢春、角发金光驱邪避凶","rarity":"传说","desc":"龙头鹿角狮眼虎背熊腰蛇鳞马蹄，不踏活虫不折生草，有圣王出则麒麟现"},
    {"name":"白泽","category":"神兽","power_tier":"天级","element":"全属性","region":"中部","temperament":"博学睿智","abilities":"通晓天下万物之名、能言人语、预知吉凶祸福","rarity":"传说","desc":"形似羊而独角，通体雪白，天下妖怪精怪无不知其名，曾授人族帝王以鬼神图谱"},
    {"name":"玄武","category":"神兽","power_tier":"天级","element":"水","region":"北地","temperament":"沉稳如岳","abilities":"背负神龟壳可挡万法、蛇尾缠绕绞杀、镇守北方","rarity":"传说","desc":"龟蛇合体之相，龟壳上刻满天道符文，沉眠于北地极寒深渊之底，守护世界北方的平衡"},
    {"name":"朱雀","category":"神兽","power_tier":"天级","element":"火","region":"南部","temperament":"高贵炽烈","abilities":"浴火重生不死不灭、羽翼扇动即可焚山沸海、鸣叫可唤来百鸟朝凤","rarity":"传说","desc":"通体燃烧着不灭的南明离火，每五百年浴火重生一次，是火焰与重生的至高象征"},
    {"name":"青龙","category":"神兽","power_tier":"天级","element":"木","region":"东部","temperament":"仁慈威严","abilities":"掌控春雷与万物生发、盘旋之处草木疯长、龙吟可驱散一切邪祟","rarity":"传说","desc":"东方守护之神兽，鳞甲青翠如玉，盘旋于九天云海之中，是生机与希望的化身"},
    {"name":"白虎","category":"神兽","power_tier":"天级","element":"金","region":"西部","temperament":"杀伐果断","abilities":"虎啸震碎神魂、利爪撕裂空间、天生克制一切鬼物邪魔","rarity":"传说","desc":"西方守护之神兽，通体雪白带有黑色虎纹，双眸金光四射，是杀伐与正义的象征"},
    {"name":"凤凰","category":"神兽","power_tier":"天级","element":"火","region":"南部","temperament":"高贵华美","abilities":"百鸟之皇一呼百应、涅槃重生、凤鸣可净化一切诅咒","rarity":"传说","desc":"鸡头燕颔蛇颈鱼尾，五色羽毛流光溢彩，非梧桐不止非练实不食非醴泉不饮"},
    {"name":"饕餮","category":"神兽","power_tier":"天级","element":"暗","region":"西部","temperament":"贪婪凶暴","abilities":"吞噬万物包括灵气和空间、腹中有无尽虚空、被吞之物永远消失","rarity":"传说","desc":"羊身人面虎齿人爪，腋下有巨口可吞食天地，是贪婪与毁灭的化身，被封禁于西部古战场"},
    {"name":"穷奇","category":"神兽","power_tier":"天级","element":"风","region":"西部","temperament":"恶逆无常","abilities":"飞行如风无可捕捉、能识人心善恶专食善人、蛊惑恶人作恶","rarity":"传说","desc":"状如虎而有翼，闻人争斗则食有理者，闻人忠信则啮其鼻，是混乱与背德的化身"},
    {"name":"梼杌","category":"神兽","power_tier":"天级","element":"毒","region":"北地","temperament":"顽固凶残","abilities":"不死不灭刀枪不入、身带剧毒触碰即亡、从无尽顽抗中越发强大","rarity":"传说","desc":"人面虎身犬毛猪牙，尾长一丈八尺，桀骜不驯不可教化，被封于北地冰川深处"},
    {"name":"混沌","category":"神兽","power_tier":"天级","element":"混沌","region":"西部","temperament":"混沌无序","abilities":"无面无窍却可吞噬灵识、触碰者陷入混沌迷失心智、形体可在虚实间任意转换","rarity":"传说","desc":"状如黄囊赤如丹火六足四翼浑敦无面目，是天地未开时的混沌残余，被封于断裂带最深处"},
    {"name":"夔牛","category":"神兽","power_tier":"地级","element":"雷","region":"东部","temperament":"刚猛暴躁","abilities":"独脚跳跃引发地震、吼声如雷百里可闻、皮可制成震天鼓","rarity":"绝迹","desc":"状如牛而苍身无角只有一足，出入海水必伴随狂风暴雨，其声如雷震百里"},
    {"name":"毕方","category":"神兽","power_tier":"地级","element":"火","region":"南部","temperament":"孤傲高洁","abilities":"单足独立于枝头、所落之处必生火灾","rarity":"绝迹","desc":"形如鹤而一足，青羽赤纹白喙，不食五谷只饮灵泉，出现之处必有怪异火灾"},
    {"name":"重明鸟","category":"神兽","power_tier":"地级","element":"光","region":"中部","temperament":"正义光明","abilities":"双目重瞳可看穿一切虚妄和伪装、鸣叫能驱退妖兽邪魔","rarity":"绝迹","desc":"形似鸡而双瞳，鸣声如凤，力能搏逐猛兽，旧王朝以重明鸟为图腾镇守宫门"},
    {"name":"当康","category":"神兽","power_tier":"地级","element":"土","region":"南部","temperament":"温顺祥和","abilities":"出现之处预示丰收、蹄踏大地可使土壤肥沃","rarity":"绝迹","desc":"状如豚而有牙，其名自呼，见则天下大穰，南部农人以当康为丰收之兆"},
    {"name":"腓腓","category":"神兽","power_tier":"地级","element":"木","region":"中部","temperament":"温顺解忧","abilities":"形如狸而白尾、养之可解忧愁、鬃毛能入药炼制解忧丹","rarity":"绝迹","desc":"状如狸而白尾有鬣，养之可以已忧，旧时中部修士多养腓腓以防心魔滋生"},
]

# ===== 生成器 =====
def gen_name_creature(cat, tier):
    """根据生灵类别生成符合风格的名字"""
    color = random.choice(COLORS)
    part = random.choice(BODY_PARTS)
    if cat in ("妖兽","魔兽","异兽","灵兽"):
        creature = random.choice(CREATURES_BEAST)
        suffix = random.choice(["妖","王","皇","魔","鬼","凶","灵","兽","怪"])
        return f"{color}{part}{creature}{suffix}"
    elif cat == "精灵":
        elem = random.choice(ELEMENTS)
        form = random.choice(["灵","精","魄","魂","心","元","华","英","露","泉","芒","蕊","芽","辉","韵","息","源","核","胎","莹","菡","萏","萱","芷","蕙","蓠","蘅"])
        place = random.choice(["林","潭","谷","涧","溪","泉","岩","窟","洞","崖","峰","岭","湖","沼","原","壑","屿","屿","沚","汀"])
        if random.random() < 0.6:
            return f"{color}{elem}{form}"
        else:
            return f"{place}之{elem}{form}"
    elif cat == "山灵":
        geo = random.choice(["山","峰","岭","崖","谷","丘","岩","壁","峦","嶂","岳","壑","峪","崮","岫","岑","岘","岬","矶","碣","砬","磬","磐","魁","魈","罡","魅","魍","魉","煞","魁","嵬","嵯","嶙","峋","嵯","峨"])
        if random.random() < 0.4:
            return f"{color}{geo}之灵"
        elif random.random() < 0.5:
            return f"{geo}{random.choice(['神','灵','魂','魄','精','煞','魈'])}"
        else:
            return f"{color}{geo}{random.choice(['山神','地灵','石魂','岩心'])}"
    elif cat == "精怪":
        obj = random.choice(CREATURES_OBJ + CREATURES_PLANT + ["灯","锁","伞","扇","笔","墨","砚","琴","棋","书","画","炉","鼎","壶","罐","瓶","碗","筷","勺","帚","绳","袋","囊","笼","箱","柜","榻","枕","帘","帕","簪","钗","镯","坠","杵","钵","铃","鼓","锣","钹","磬","钵","盂","匜","匜","匦"])
        if random.random() < 0.5:
            return f"{color}{obj}精"
        else:
            return f"{color}{obj}{random.choice(['怪','妖','魅','魉','老儿','童子'])}"
    elif cat == "妖怪":
        creature = random.choice(CREATURES_BEAST[:20])
        form = random.choice(["妖","魅","魍","魉","怪","鬼","姬","郎","童","翁"])
        return f"{color}{part}{creature}{form}"
    return f"{color}{random.choice(CREATURES_BEAST)}妖"

TEMPERAMENTS = {
    "灵兽": ["温顺","忠诚","胆小","活泼","沉稳","高傲","粘人","警觉"],
    "妖兽": ["凶暴","狡猾","嗜血","领地意识强","群居协作","独行掠食","记仇","谨慎"],
    "魔兽": ["疯狂","嗜血","不可驯化","残暴","污染源","传染邪气","无差别攻击","憎恨一切活物"],
    "异兽": ["混乱","不可预测","时而温顺时而暴怒","孤独","被排斥","天生异相","精神错乱","自闭"],
    "精灵": ["纯净","好奇","胆小","亲近善意者","无性别","短暂生命","与灵气共存亡","天真"],
    "山灵": ["沉稳","万年不变","守护一方","不欢迎外来者","记忆漫长","与地脉共生","沉默寡言","古老"],
    "精怪": ["调皮","胆小","爱捉弄人","怕修士","法力低微","寿命漫长","爱财","记恩"],
    "妖怪": ["狡诈","诡计多端","善变幻","会说话","能谈判","记仇","欺软怕硬","有自己的一套道德"],
}

ABILITIES = {
    "灵兽": [["灵气感知","急速奔跑","耐力惊人","天生护主","低空飞行","寻路认主","灵草辨识","水下呼吸"],["灵力护盾","腾云驾雾","灵识交流","治愈伤口","隐身匿踪","变形缩小","短暂飞行","属性亲和"]],
    "妖兽": [["利爪撕咬","尾击鞭打","毒液喷射","钻地突袭","群体围攻","拟态伪装","声波攻击","缠绕绞杀"],["火焰吐息","冰冻吐息","雷电吐息","石化凝视","幻术迷惑","毒雾弥漫","狂暴化","再生肢体"]],
    "魔兽": [["邪气侵蚀","腐肉毒液","吞噬灵气","不死之躯","传染诅咒","撕碎魂魄","污染灵脉","扭曲心智"],["魔焰焚天","尸爆术","召唤魔裔","吸取生命","空间腐蚀","暗影潜行","狂暴魔化","不可名状"]],
    "异兽": [["空间褶皱","时间涟漪","因果回响","反噬灵气","自我分裂","元素随机","凭空召唤","形态不定"],["虚空吞噬","维度跳跃","现实扭曲","时间回溯","因果斩断","创造异常区域","异化其他生物","与天道共鸣"]],
    "精灵": [["灵气治愈","引导灵气","净化污染","照亮黑暗","安抚心神","附身灵木","化为灵光","催生灵植"],["灵气风暴","净化诅咒","重塑地貌","召唤同类","与修士共鸣","化身守护灵","加持法器","预知灵气潮汐"]],
    "山灵": [["地震术","岩石塑形","召唤落石","地脉感应","改变地形","凝聚灵石","困敌于山","山崩地裂"],["移山填海","改变灵脉流向","镇压邪祟","唤醒山神意志","与地脉融合","创造秘境","守护一方千年","不灭地魂"]],
    "精怪": [["变幻形态","小法术戏弄","隐身吓人","偷窃小物","模仿人声","草木催生","迷惑路人","开门撬锁"],["幻化人形","操控草木","入梦扰人","搬运重物","点石成金","诅咒霉运","召唤同类","与修士交易"]],
    "妖怪": [["幻化人形","蛊惑人心","入梦盗魂","吸食精气","口吐人言","变化多端","预知吉凶","附身他人"],["创造幻境","不死妖身","魅惑众生","吸收恐惧","操控天气","偷天换日","化身万千","与修士博弈"]],
}

# 区域→元素亲和（什么区域更容易出现什么属性的生灵）
_REGION_ELEMENT_WEIGHTS = {
    "北部": {"冰":10,"水":7,"风":5,"土":3},
    "南部": {"火":10,"木":8,"水":5,"土":3},
    "东部": {"水":10,"木":8,"风":5,"雷":5},
    "西部": {"火":8,"土":8,"金":6,"暗":5},
    "中部": {"土":10,"金":6,"木":4,"火":3},
}
_ELEMENT_REGION_WEIGHTS = {
    "冰": {"北地":10,"东部":3,"中部":1},
    "火": {"西部":8,"南部":8,"中部":3,"东部":1},
    "水": {"东部":10,"南部":6,"北地":4,"中部":2},
    "木": {"南部":8,"东部":8,"中部":4,"北地":1},
    "雷": {"东部":6,"中部":4,"南部":3,"西部":2},
    "风": {"东部":6,"北地":5,"中部":3,"西部":3},
    "土": {"中部":10,"西部":8,"南部":4,"北地":3},
    "金": {"西部":8,"中部":6,"北地":2,"东部":1},
    "光": {"中部":5,"南部":3,"东部":2},
    "暗": {"西部":8,"北地":3,"中部":2},
    "毒": {"南部":5,"西部":5,"东部":2},
}
def _pick_element_and_region():
    """元素和区域绑定抽取：冰系不可能出生在南部火域"""
    if random.random() < 0.7:
        elem = random.choice(ELEMENTS)
        weights = _ELEMENT_REGION_WEIGHTS.get(elem, {r:1 for r in REGIONS})
        regions, w = zip(*weights.items())
        region = random.choices(regions, weights=w, k=1)[0]
    else:
        region = random.choice(REGIONS)
        weights = _REGION_ELEMENT_WEIGHTS.get(region, {e:1 for e in ELEMENTS})
        elems, w = zip(*weights.items())
        elem = random.choices(elems, weights=w, k=1)[0]
    return elem, region

# 区域×元素→描述模板
_REGION_DESCS = {
    ("北地","冰"): ["出没于北地冰川与雪原之间","在极寒的暴风雪中猎食","冰封千里的北地是它的天然猎场"],
    ("北地","水"): ["在冰湖之下潜行觅食","北地的冰下暗河是它的领地"],
    ("南部","火"): ["盘踞于南部火山地带","南部的炎热丛林是它的栖身之所"],
    ("南部","木"): ["出没于南部茂密的水松林","南方的雨季是它最活跃的时节"],
    ("东部","水"): ["潜藏于东部深海之中","东部的灵竹海岸是它的觅食之地"],
    ("东部","木"): ["栖于东部的灵竹林海中","东部新生灵脉滋养了它的族群"],
    ("西部","火"): ["出没于西部沙漠的酷热深处","西部的古战场废墟是它的藏身之地"],
    ("西部","土"): ["盘踞在西部断裂带的岩壁之间","沙漠深处的地下洞穴是它的巢穴"],
    ("中部","土"): ["穿行于中部的古老山脉之间","残存的祖脉是它最后的栖息地"],
}
def _get_desc(cat, element, region):
    """根据类别、元素和区域生成合理的描述"""
    key = (region, element)
    if key in _REGION_DESCS:
        return random.choice(_REGION_DESCS[key])
    # Fallback
    generic = {
        "冰": ["通体散发着刺骨寒气","所过之处冰霜凝结","呼出的气息在空中结成冰晶"],
        "火": ["浑身缭绕着灼热的火焰","口鼻间喷吐着火星","足迹所至焦土一片"],
        "水": ["体表覆盖着湿润的鳞甲","能在水中自由穿梭","离开水依然行动自如"],
        "木": ["与草木融为一体难以发现","身上缠绕着翠绿的灵藤"],
        "雷": ["行动时周身闪烁着电弧","奔跑时如一道闪电划过"],
        "风": ["行动迅捷如风难以捕捉","奔跑时身后卷起一阵旋风"],
        "土": ["皮糙肉厚刀枪难入","潜伏在地下突然发起袭击"],
        "金": ["鳞甲坚硬如金属利刃难伤","在矿脉丰富的山区出没"],
    }
    return random.choice(generic.get(element, ["一种神秘的生灵"])) + f"，常见于{region}地区"

def gen_entry(cat, tier):
    name = gen_name_creature(cat, tier)
    element, region = _pick_element_and_region()
    tempers = TEMPERAMENTS.get(cat, ["未知"])
    temperament = random.choice(tempers)
    abi_pool = ABILITIES.get(cat, [["未知"],["未知"]])
    if tier in ("地级","天级"):
        abis = random.sample(abi_pool[1], min(3, len(abi_pool[1])))
    else:
        abis = random.sample(abi_pool[0], min(2, len(abi_pool[0])))
    desc = _get_desc(cat, element, region)
    if tier == "天级": rarity = "传说"
    elif tier == "地级": rarity = random.choice(["稀有","极稀有","绝迹"])
    elif tier == "玄级": rarity = random.choice(["稀有","罕见","偶见"])
    else: rarity = random.choice(["常见","常见","常见","偶见"])
    return {"name":name,"category":cat,"power_tier":tier,"element":element,
            "region":region,"temperament":temperament,"abilities":"、".join(abis),
            "rarity":rarity,"desc":desc}

# ===== 生成并写出 =====
def generate_category(cat, target_count):
    entries = []
    used_names = set()
    for i in range(target_count):
        tier = pick_tier()
        for _ in range(50):  # retry for unique name
            entry = gen_entry(cat, tier)
            if entry["name"] not in used_names:
                used_names.add(entry["name"])
                entries.append(entry)
                break
        if i % 5000 == 0:
            print(f"  {cat}: {i}/{target_count}", flush=True)
    return entries

def write_files(entries, cat, out_dir):
    full_path = os.path.join(out_dir, f"{cat}_bestiary.jsonl")
    sample_path = os.path.join(out_dir, f"{cat}_sample.json")
    with open(full_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    # Sample: first 120 or all if fewer
    sample = entries[:min(120, len(entries))]
    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    mb = os.path.getsize(full_path) / 1048576
    print(f"  {cat}: {len(entries)} entries, {mb:.1f} MB -> {full_path}", flush=True)

def main():
    targets = [
        ("神兽", len(SHENSHOU), True),  # hand-written
        ("妖兽", 35000, False),
        ("魔兽", 5000, False),
        ("异兽", 500, False),
        ("灵兽", 8000, False),
        ("精灵", 3000, False),
        ("山灵", 3000, False),
        ("精怪", 5000, False),
        ("妖怪", 5000, False),
    ]
    total = sum(t[1] for t in targets)
    print(f"Target total: {total} entries across {len(targets)} categories", flush=True)
    
    for cat, count, is_handwritten in targets:
        print(f"Generating {cat} ({count})...", flush=True)
        if is_handwritten:
            entries = SHENSHOU
        else:
            entries = generate_category(cat, count)
        write_files(entries, cat, OUT_DIR)
    
    print("Done!", flush=True)

if __name__ == "__main__":
    main()
