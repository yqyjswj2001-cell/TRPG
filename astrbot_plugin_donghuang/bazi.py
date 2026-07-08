# -*- coding: utf-8 -*-
"""
astrbot_plugin_donghuang 的生辰八字系统。
根据年/月/日/时计算四柱八字，映射为游戏属性（灵根、六维、出身等）。
"""
import random

# ===== 天干地支 =====
TIAN_GAN = ['甲','乙','丙','丁','戊','己','庚','辛','壬','癸']
DI_ZHI = ['子','丑','寅','卯','辰','巳','午','未','申','酉','戌','亥']
GAN_ELEMENT = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
GAN_YINYANG = {'甲':'阳','乙':'阴','丙':'阳','丁':'阴','戊':'阳','己':'阴','庚':'阳','辛':'阴','壬':'阳','癸':'阴'}
ZHI_ELEMENT = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}
ZHI_HIDDEN = {'子':['癸'],'丑':['己','癸','辛'],'寅':['甲','丙','戊'],'卯':['乙'],
              '辰':['戊','乙','癸'],'巳':['丙','庚','戊'],'午':['丁','己'],'未':['己','丁','乙'],
              '申':['庚','壬','戊'],'酉':['辛'],'戌':['戊','辛','丁'],'亥':['壬','甲']}

# ===== 四柱计算 =====
def _year_ganzhi(year):
    """计算年柱干支（立春为界，简化版用公历）"""
    base = 4  # 甲子=4
    idx = (year - base) % 60
    return TIAN_GAN[idx % 10], DI_ZHI[idx % 12]

def _month_ganzhi(year, month):
    """计算月柱干支（正月建寅）"""
    year_gan = _year_ganzhi(year)[0]
    month_gan_base = {"甲":0,"己":0,"乙":2,"庚":2,"丙":4,"辛":4,"丁":6,"壬":6,"戊":8,"癸":8}
    base = month_gan_base.get(year_gan, 0)
    gan = TIAN_GAN[(base + (month - 1)) % 10]
    zhi = DI_ZHI[(month + 1) % 12]  # 正月=寅
    return gan, zhi

def _julian_day_number(year, month, day):
    """纯整数运算的儒略日数（proleptic Gregorian，Fliegel & Van Flandern
    公式），不用 datetime.date——东荒历年份是 12000+，超出了 Python
    datetime 的年份上限（1~9999），必须用纯算术，不能借用标准库日期类型。"""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045

def _day_ganzhi(year, month, day):
    """计算日柱干支（近似算法），用儒略日数差值代替 datetime 的天数差，
    效果等价但不受年份范围限制。"""
    diff = _julian_day_number(year, month, day) - _julian_day_number(1900, 1, 1)
    base_gan = TIAN_GAN.index('甲')
    base_zhi = DI_ZHI.index('戌')
    gan = TIAN_GAN[(base_gan + diff) % 10]
    zhi = DI_ZHI[(base_zhi + diff) % 12]
    return gan, zhi

def _hour_zhi(hour):
    """时辰→地支：子时是23:00-00:59（跨零点），丑时01:00-02:59，以此类推，
    不是简单的"每2小时一个时辰"从0点开始切——原来的写法在这个边界上错位了
    一整个时辰（比如23点会被错算成亥时，实际应该是子时）。"""
    return DI_ZHI[((hour + 1) // 2) % 12]

def _hour_gan(day_gan, hour_zhi):
    """时干根据日干推算（五鼠遁）：甲己还加甲/乙庚丙作初/丙辛从戊起/
    丁壬庚子居/戊癸何方发/壬子是真途。TIAN_GAN 顺序是甲乙丙丁戊己庚辛壬癸，
    按这个顺序排布局的子时起干偏移量应为 [0,2,4,6,8,0,2,4,6,8]（之前的
    写法 [0,0,2,2,4,4,6,6,8,8] 把配对关系错位了，除了甲和癸之外全错）。"""
    zi_idx = DI_ZHI.index('子')
    h_idx = DI_ZHI.index(hour_zhi)
    day_idx = TIAN_GAN.index(day_gan)
    gan_offsets = [0,2,4,6,8,0,2,4,6,8]  # 甲己0,乙庚2,丙辛4,丁壬6,戊癸8
    start_gan = (gan_offsets[day_idx]) % 10
    return TIAN_GAN[(start_gan + (h_idx - zi_idx)) % 10]

def calc_bazi(year, month, day, hour):
    """计算四柱八字，返回 dict"""
    yg, yz = _year_ganzhi(year)
    mg, mz = _month_ganzhi(year, month)
    dg, dz = _day_ganzhi(year, month, day)
    hz = _hour_zhi(hour)
    hg = _hour_gan(dg, hz)
    return {
        'year': year,  # 原始出生年份（东荒历），方便直接展示"出生于东荒历XXX年"
        'year_pillar': (yg, yz), 'month_pillar': (mg, mz),
        'day_pillar': (dg, dz), 'hour_pillar': (hg, hz),
        'day_master': dg, 'eight_chars': yg+yz+mg+mz+dg+dz+hg+hz,
    }

# ===== 五行计分 =====
def _count_five_elements(bazi):
    """统计八字中五行的分布（含藏干）"""
    scores = {'木':0,'火':0,'土':0,'金':0,'水':0}
    # 天干
    for p in ['year_pillar','month_pillar','day_pillar','hour_pillar']:
        gan = bazi[p][0]
        scores[GAN_ELEMENT[gan]] += 10
    # 地支本气
    for p in ['year_pillar','month_pillar','day_pillar','hour_pillar']:
        zhi = bazi[p][1]
        scores[ZHI_ELEMENT[zhi]] += 7
    # 地支藏干（简化：只取第一个藏干5分）
    for p in ['year_pillar','month_pillar','day_pillar','hour_pillar']:
        zhi = bazi[p][1]
        hidden = ZHI_HIDDEN[zhi]
        if hidden:
            scores[GAN_ELEMENT[hidden[0]]] += 5
    return scores

# ===== 八字→游戏属性 =====
def bazi_to_attributes(bazi):
    """将八字映射为游戏属性"""
    day_master = bazi['day_master']
    dm_element = GAN_ELEMENT[day_master]
    yinyang = GAN_YINYANG[day_master]
    scores = _count_five_elements(bazi)

    # 灵根属性 = 日主五行
    spirit_root = dm_element

    # 灵根等阶：五行平衡者高，极端偏枯者低
    vals = list(scores.values())
    balance = max(vals) - min(vals)
    if balance < 10:       root_tier = '天'
    elif balance < 18:     root_tier = '地'
    elif balance < 25:     root_tier = '玄'
    else:                  root_tier = '黄'

    # 六维：从五行分布映射
    six = {
        '根骨': 8 + (scores['土'] + scores['金']) // 5 + random.randint(-2, 3),
        '悟性': 8 + (scores['水'] + scores['木']) // 5 + random.randint(-2, 3),
        '机缘': 8 + scores['火'] // 4 + random.randint(-2, 3),
        '魅力': 8 + (scores['火'] + scores['木']) // 5 + random.randint(-2, 3),
        '体质': 8 + (scores['土'] + scores['金']) // 5 + random.randint(-2, 3),
        '心性': 8 + (scores['水'] + scores['金']) // 5 + random.randint(-2, 3),
    }
    six = {k: max(3, min(18, v)) for k, v in six.items()}

    # 区域：根据最强元素推荐，按传统五行-方位对应（木东/火南/土中/金西/水北），
    # 五个元素对应五个区域，不重复、不遗漏——之前的写法把木火都归到南部，
    # 导致南部被抽中概率翻倍，北地则永远选不到
    best_elem = max(scores, key=scores.get)
    region_map = {'木':'东部','火':'南部','土':'中部','金':'西部','水':'北地'}
    region = region_map.get(best_elem, random.choice(['中部','东部','南部','北地','西部']))

    # 身份倾向：五行平衡者出身高
    if balance < 12:      idt_weights = [5,10,10,25,25,20,5]   # 多内门/世家/天才
    elif balance < 20:    idt_weights = [25,25,15,15,10,8,2]   # 多外门/散修
    elif balance < 28:    idt_weights = [40,25,15,10,6,3,1]    # 正常分布
    else:                 idt_weights = [55,20,15,5,3,2,0]     # 多杂役/普通人
    idt_list = ['宗门杂役/普通人家子弟','外门弟子','散修','内门弟子','没落世家子弟','内门天才','绝世妖孽']
    identity = random.choices(idt_list, weights=idt_weights, k=1)[0]

    # 性别：八字日主阴阳只作为倾向修正，不是非黑即白的硬开关——之前"阴
    # 就必是女"导致女性比例远超预期（阴阳各占一半概率，等于至少50%女性
    # 起步）。现在阴阳只小幅调整男女权重，两边都以男性为主。
    gender_weights = [62, 38] if yinyang == '阴' else [82, 18]
    gender = random.choices(['男', '女'], weights=gender_weights, k=1)[0]

    return {
        'spirit_root': spirit_root,
        'root_tier': root_tier,
        'six_dims': six,
        'region': region,
        'identity_tier': identity,
        'gender': gender,
        'element_scores': scores,
        'balance': balance,
    }
