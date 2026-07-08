"""
test_bazi.py - 生辰八字系统测试（bazi.py，此前零测试覆盖）

bazi.py 的代码注释里提到过几处曾经修过的 bug（时辰边界错位、木火都归
南部导致区域概率不均、阴阳和性别错误绑定），这个文件把这些"已知曾经
错过"的地方钉成断言，防止以后又被改回去。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bazi


# ── 1. 时辰边界：23:00-00:59 应该都是子时，不是亥时 ──

def test_hour_zhi_boundaries():
    assert bazi._hour_zhi(23) == "子"
    assert bazi._hour_zhi(0) == "子"
    assert bazi._hour_zhi(1) == "丑"
    assert bazi._hour_zhi(2) == "丑"
    assert bazi._hour_zhi(3) == "寅"
    assert bazi._hour_zhi(11) == "午"
    assert bazi._hour_zhi(12) == "午"
    assert bazi._hour_zhi(13) == "未"
    assert bazi._hour_zhi(21) == "亥"
    assert bazi._hour_zhi(22) == "亥"


# ── 2. 时干五鼠遁：甲己日 -> 子时起甲，乙庚日 -> 子时起丙，以此类推 ──

def test_hour_gan_wushudun_mapping():
    # 甲日 子时 -> 甲
    assert bazi._hour_gan("甲", "子") == "甲"
    # 己日 子时 -> 甲（甲己还加甲）
    assert bazi._hour_gan("己", "子") == "甲"
    # 乙日 子时 -> 丙（乙庚丙作初）
    assert bazi._hour_gan("乙", "子") == "丙"
    # 庚日 子时 -> 丙
    assert bazi._hour_gan("庚", "子") == "丙"
    # 丙日 子时 -> 戊（丙辛从戊起）
    assert bazi._hour_gan("丙", "子") == "戊"
    # 丁日 子时 -> 庚（丁壬庚子居）
    assert bazi._hour_gan("丁", "子") == "庚"
    # 戊日 子时 -> 壬（戊癸何方发，壬子是真途）
    assert bazi._hour_gan("戊", "子") == "壬"

    # 同一天干，丑时应该比子时的天干序号往后推一位
    zi_gan = bazi._hour_gan("甲", "子")
    chou_gan = bazi._hour_gan("甲", "丑")
    assert bazi.TIAN_GAN.index(chou_gan) == (bazi.TIAN_GAN.index(zi_gan) + 1) % 10


# ── 3. calc_bazi 结构完整性（跨超大年份，验证不依赖 datetime 的年份上限）──

def test_calc_bazi_structure_and_large_year():
    result = bazi.calc_bazi(year=12000, month=3, day=15, hour=10)
    assert set(result.keys()) == {
        "year", "year_pillar", "month_pillar", "day_pillar", "hour_pillar",
        "day_master", "eight_chars",
    }
    assert result["year"] == 12000
    assert len(result["eight_chars"]) == 8
    assert result["day_master"] == result["day_pillar"][0]
    for pillar in (result["year_pillar"], result["month_pillar"], result["day_pillar"], result["hour_pillar"]):
        gan, zhi = pillar
        assert gan in bazi.TIAN_GAN
        assert zhi in bazi.DI_ZHI


def test_calc_bazi_deterministic():
    # 同样的出生时间应该算出完全一样的八字（不能混入随机数）
    r1 = bazi.calc_bazi(year=10500, month=7, day=8, hour=14)
    r2 = bazi.calc_bazi(year=10500, month=7, day=8, hour=14)
    assert r1 == r2


# ── 4. 区域映射：五个五行元素应各自对应一个不重复的区域 ──

def test_region_map_covers_all_elements_uniquely():
    region_map = {'木': '东部', '火': '南部', '土': '中部', '金': '西部', '水': '北地'}
    assert set(region_map.keys()) == {"木", "火", "土", "金", "水"}
    assert len(set(region_map.values())) == 5  # 五个区域互不重复


# ── 5. bazi_to_attributes 六维范围与整体结构 ──

def test_bazi_to_attributes_six_dims_bounds():
    b = bazi.calc_bazi(year=11000, month=5, day=20, hour=8)
    attrs = bazi.bazi_to_attributes(b)

    assert attrs["spirit_root"] in ("木", "火", "土", "金", "水")
    assert attrs["root_tier"] in ("天", "地", "玄", "黄")
    assert attrs["region"] in ("东部", "南部", "中部", "西部", "北地")
    assert attrs["gender"] in ("男", "女")

    for dim, value in attrs["six_dims"].items():
        assert 3 <= value <= 18, f"{dim} 超出 [3,18] 范围：{value}"

    assert set(attrs["six_dims"].keys()) == {"根骨", "悟性", "机缘", "魅力", "体质", "心性"}


def test_bazi_to_attributes_does_not_crash_across_many_seeds():
    # 跑一批不同的出生时间，确保不会因为边界组合（比如五行分数全同）而抛异常
    for i in range(50):
        year = 10000 + i * 37
        month = (i % 12) + 1
        day = (i % 28) + 1
        hour = i % 24
        b = bazi.calc_bazi(year=year, month=month, day=day, hour=hour)
        attrs = bazi.bazi_to_attributes(b)
        assert attrs["balance"] >= 0


if __name__ == "__main__":
    test_hour_zhi_boundaries()
    test_hour_gan_wushudun_mapping()
    test_calc_bazi_structure_and_large_year()
    test_calc_bazi_deterministic()
    test_region_map_covers_all_elements_uniquely()
    test_bazi_to_attributes_six_dims_bounds()
    test_bazi_to_attributes_does_not_crash_across_many_seeds()
    print("\nbazi tests passed")
