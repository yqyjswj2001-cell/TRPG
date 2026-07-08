# -*- coding: utf-8 -*-
"""
generate_timeline.py — 东荒千年时间线生成引擎
用法: python generate_timeline.py [起始年份] [生成年数] [输出文件]

基于东荒世界设定，用规则引擎逐年推导事件。事件密度：
  每 100 年：~150 洲级事件 + ~45 大型事件 + ~450 中型事件
  1000 年总计：~6500 条事件

数据来源：world/TRPG_DH/ 下的势力DB、资源DB、事件模板库、因果系统、世界数据表
"""
import json
import random
import sys
from pathlib import Path

# ══════════════════════════════════════════════════════
# 一、世界初始状态（基于 00_STARTUP_SEED EAST-WORLD-SEED-01）
# ══════════════════════════════════════════════════════

REGIONS = ["中部", "东部", "南部", "北地", "西部"]

# 灵气浓度等级：1(低) 2(中) 3(高) 4(极高)
INITIAL_REGION_STATE = {
    "中部": {"phase": "结构偏移", "qi": 3, "qi_trend": -1, "stability": 60, "pop": 5},
    "东部": {"phase": "开放重组", "qi": 2, "qi_trend": 2,  "stability": 40, "pop": 2},
    "南部": {"phase": "压力积累", "qi": 2, "qi_trend": 0,  "stability": 70, "pop": 4},
    "北地": {"phase": "常态维持", "qi": 1, "qi_trend": 0,  "stability": 90, "pop": 1},
    "西部": {"phase": "临界失衡", "qi": 2, "qi_trend": -1, "stability": 30, "pop": 2},
}

# 17 个势力的初始状态 {编号: {name, region, power, cohesion, aggression, resource, goal, history}}
INITIAL_FACTIONS = {
    "CULT-01": {"name": "中部残存主脉守成宗门", "region": "中部", "power": 80, "cohesion": 60, "aggression": 2, "resource": 70, "goal": "延缓灵气外流"},
    "CULT-02": {"name": "东部新生灵脉拓展宗门", "region": "东部", "power": 30, "cohesion": 35, "aggression": 8, "resource": 40, "goal": "建立独立修行秩序"},
    "CULT-03": {"name": "北地沉潜灵气守护宗门", "region": "北地", "power": 50, "cohesion": 80, "aggression": 1, "resource": 30, "goal": "维持沉潜不醒"},
    "CULT-04": {"name": "南部水土共生维持宗门", "region": "南部", "power": 45, "cohesion": 70, "aggression": 3, "resource": 55, "goal": "维持水土与人口承载"},
    "CULT-05": {"name": "西部断裂带封禁宗门", "region": "西部", "power": 35, "cohesion": 50, "aggression": 2, "resource": 20, "goal": "阻止遗迹异常扩散"},
    "STATE-01": {"name": "中部旧王朝", "region": "中部", "power": 65, "cohesion": 50, "aggression": 4, "resource": 60, "goal": "维持疆域统一"},
    "STATE-02": {"name": "东部新域统合势力", "region": "东部", "power": 25, "cohesion": 30, "aggression": 7, "resource": 35, "goal": "统合东部新兴城邦"},
    "STATE-03": {"name": "南部世俗联合城邦", "region": "南部", "power": 55, "cohesion": 60, "aggression": 3, "resource": 65, "goal": "维持商贸与粮食安全"},
    "STATE-04": {"name": "北地边陲王国", "region": "北地", "power": 30, "cohesion": 40, "aggression": 2, "resource": 25, "goal": "维持边陲自保"},
    "HIDDEN-01": {"name": "上古战争遗迹守护者", "region": "西部", "power": 40, "cohesion": 90, "aggression": 1, "resource": 15, "goal": "守护上古战争遗迹秘密"},
    "HIDDEN-02": {"name": "灵气东移观测者", "region": "中部", "power": 20, "cohesion": 85, "aggression": 1, "resource": 10, "goal": "记录灵气迁移规律"},
    "HIDDEN-03": {"name": "散修情报网络", "region": "南部", "power": 15, "cohesion": 25, "aggression": 2, "resource": 20, "goal": "连接各地散修信息"},
    "HIDDEN-04": {"name": "断脉之变幸存者后裔", "region": "北地", "power": 10, "cohesion": 95, "aggression": 1, "resource": 5,  "goal": "防止断脉之变重演"},
    "FREE-01": {"name": "中部散修市镇联盟", "region": "中部", "power": 10, "cohesion": 20, "aggression": 3, "resource": 15, "goal": "维持自由交易"},
    "FREE-02": {"name": "东部勘察散修群体", "region": "东部", "power": 8,  "cohesion": 15, "aggression": 5, "resource": 10, "goal": "探索新生灵脉"},
    "FREE-03": {"name": "南部商路散修护卫", "region": "南部", "power": 12, "cohesion": 30, "aggression": 4, "resource": 20, "goal": "维护商路安全"},
    "FREE-04": {"name": "西部遗迹散修探秘者", "region": "西部", "power": 6,  "cohesion": 10, "aggression": 6, "resource": 5,  "goal": "从遗迹中获取机缘"},
}

# 5 条因果线的初始阈值（达到 100 触发重大因果回响，然后重置）
INITIAL_CAUSAL = {
    "灵气东移": 0,
    "上古战争": 0,
    "遗迹封闭": 0,
    "南部承载": 0,
    "北地沉潜": 0,
}

# ══════════════════════════════════════════════════════
# 二、事件生成规则
# ══════════════════════════════════════════════════════

EVENT_CATEGORIES = ["FACTION_CONFLICT", "LEYLINE_RESOURCE", "CULTIVATION_BREAKTHROUGH",
                     "CAUSAL_ECHO", "CHAOS_ANOMALY", "RUIN_OPPORTUNITY"]

# 每年各类事件的基础触发概率（%），会受世界状态修正
BASE_EVENT_CHANCE = {
    "FACTION_CONFLICT": 15,
    "LEYLINE_RESOURCE": 12,
    "CULTIVATION_BREAKTHROUGH": 5,
    "CAUSAL_ECHO": 3,
    "CHAOS_ANOMALY": 2,
    "RUIN_OPPORTUNITY": 3,
}

# 事件规模：小型=区域局部, 中型=区域级, 大型=跨区域, 洲级=东荒全域
SCALE_WEIGHTS = [60, 33, 6, 1]  # 小/中/大/洲

# 势力冲突模板
FACTION_CONFLICT_TEMPLATES = [
    {"id": "FC-01", "name": "灵脉归属争夺", "desc": "{f1}与{f2}因{region}灵脉归属爆发冲突", "scale_bias": [45,40,13,2]},
    {"id": "FC-02", "name": "历史债权纠纷", "desc": "{f1}要求{f2}履行旧有盟约中关于{resource}的承诺", "scale_bias": [50,40,8,2]},
    {"id": "FC-03", "name": "边界摩擦升级", "desc": "{region}边界地区的{f1}与{f2}附属势力发生武装摩擦", "scale_bias": [60,32,7,1]},
    {"id": "FC-04", "name": "内部派系分裂", "desc": "{f1}内部因{issue}发生分裂，{f2}趁机介入", "scale_bias": [40,42,15,3]},
    {"id": "FC-05", "name": "庇护责任冲突", "desc": "{f1}拒绝继续为{region}地区的{f2}提供庇护和资源", "scale_bias": [50,38,10,2]},
    {"id": "FC-06", "name": "旧仇清算", "desc": "{f1}以历史仇恨为由对{f2}发起突袭", "scale_bias": [40,40,17,3]},
]

# 灵脉资源模板
LEYLINE_TEMPLATES = [
    {"id": "RS-01", "name": "新灵脉发现", "desc": "{region}发现一处新生灵脉节点，灵气浓度{qi_level}", "scale_bias": [35,45,17,3]},
    {"id": "RS-02", "name": "灵脉衰退", "desc": "{region}的灵脉持续衰退，灵气浓度下降", "scale_bias": [45,42,11,2]},
    {"id": "RS-03", "name": "灵脉迁移", "desc": "{region}灵气向{target_region}方向加速迁移", "scale_bias": [25,45,25,5]},
    {"id": "RS-04", "name": "灵石矿脉暴露", "desc": "{region}因地层变动暴露出大规模灵石矿脉", "scale_bias": [35,43,18,4]},
    {"id": "RS-05", "name": "灵脉污染", "desc": "{region}灵脉受到异常能量污染，修行者吸收后出现异变", "scale_bias": [40,42,15,3]},
    {"id": "RS-06", "name": "灵植大规模异变", "desc": "{region}灵植在灵气波动中发生大规模异变", "scale_bias": [55,35,8,2]},
    {"id": "RS-07", "name": "灵脉枯竭引发地灾", "desc": "{region}灵脉枯竭引发地层坍塌和局部地震", "scale_bias": [25,45,25,5]},
]

# 因果回响模板
CAUSAL_TEMPLATES = [
    {"id": "CE-01", "name": "断脉之变回响", "desc": "断脉之变的因果在{region}再次显现，旧战场遗址出现异常灵气脉冲", "scale_bias": [20,40,30,10]},
    {"id": "CE-02", "name": "上古战争记忆苏醒", "desc": "{region}的上古战场遗址中，沉睡的战争记忆开始苏醒", "scale_bias": [15,35,38,12]},
    {"id": "CE-03", "name": "旧盟约因果反噬", "desc": "古老的盟约被违背，因果反噬降临在{region}", "scale_bias": [30,42,22,6]},
    {"id": "CE-04", "name": "封闭遗迹因果泄漏", "desc": "{region}封闭遗迹的因果封印出现裂痕，历史后果开始外泄", "scale_bias": [15,33,40,12]},
    {"id": "CE-05", "name": "天道因果收敛", "desc": "天道对{region}长期积累的失衡做出反应，引发区域性因果收敛", "scale_bias": [10,30,45,15]},
    {"id": "CE-06", "name": "不灭遗识复苏", "desc": "{region}的古战场中，一位上古修行者的不灭遗识短暂复苏", "scale_bias": [15,35,38,12]},
]

# 修行突破模板
BREAKTHROUGH_TEMPLATES = [
    {"id": "CB-01", "name": "高阶修士突破", "desc": "{region}有修行者突破至{level}，引发天地异象", "scale_bias": [30,45,20,5]},
    {"id": "CB-02", "name": "宗门传承突破", "desc": "{f1}在长期积累后实现传承体系的整体突破", "scale_bias": [25,45,25,5]},
    {"id": "CB-03", "name": "散修意外突破", "desc": "{region}一名散修在极端环境下意外突破，打破既有格局", "scale_bias": [50,38,10,2]},
    {"id": "CB-04", "name": "突破引发天劫", "desc": "{region}的突破尝试引发远超预期的天劫，波及周边区域", "scale_bias": [20,40,30,10]},
    {"id": "CB-05", "name": "灵根跃迁事件", "desc": "{region}出现罕见的灵根自然跃迁现象", "scale_bias": [55,35,8,2]},
    {"id": "CB-06", "name": "修行方法革新", "desc": "{f1}发现了一种与{region}环境高度契合的新修行方法", "scale_bias": [45,38,15,2]},
]

# 混沌异常模板
CHAOS_TEMPLATES = [
    {"id": "CH-01", "name": "空间裂隙", "desc": "{region}出现无法解释的空间裂隙，连接未知区域", "scale_bias": [20,38,30,12]},
    {"id": "CH-02", "name": "时间错位", "desc": "{region}局部时间流速出现异常，过去与现在的边界模糊", "scale_bias": [15,35,35,15]},
    {"id": "CH-03", "name": "灵气风暴", "desc": "{region}爆发大规模灵气风暴，改变当地灵气分布格局", "scale_bias": [20,40,28,12]},
    {"id": "CH-04", "name": "生物异变潮", "desc": "{region}灵气异常引发大规模生物异变", "scale_bias": [35,40,20,5]},
    {"id": "CH-05", "name": "天道感知异常", "desc": "{region}的修士集体感受到天道运行的异常波动", "scale_bias": [45,38,15,2]},
    {"id": "CH-06", "name": "沉眠存在扰动", "desc": "{region}地下深处某个沉眠存在的意识出现扰动", "scale_bias": [10,30,45,15]},
    {"id": "CH-07", "name": "灵脉突然反转", "desc": "{region}灵脉流向突然反转，造成大面积混乱", "scale_bias": [15,38,35,12]},
    {"id": "CH-08", "name": "因果链条断裂", "desc": "{region}某条长期稳定的因果链条突然断裂，引发连锁反应", "scale_bias": [10,30,45,15]},
]

# 遗迹与机缘模板
RUIN_TEMPLATES = [
    {"id": "OP-01", "name": "上古遗迹开启", "desc": "{region}一处尘封已久的上古遗迹大门开启", "scale_bias": [20,40,30,10]},
    {"id": "OP-02", "name": "失落传承现世", "desc": "{region}发现一份失落已久的修行传承", "scale_bias": [40,42,15,3]},
    {"id": "OP-03", "name": "天材地宝出世", "desc": "{region}出现一件天材地宝，引起各方势力关注", "scale_bias": [25,45,25,5]},
    {"id": "OP-04", "name": "古战场秘境", "desc": "{region}古战场遗址中出现通往秘境的入口", "scale_bias": [20,38,30,12]},
    {"id": "OP-05", "name": "前辈遗府", "desc": "{region}发现一位已故大修行者的洞府", "scale_bias": [35,45,17,3]},
    {"id": "OP-06", "name": "灵脉交汇宝藏", "desc": "{region}多条灵脉交汇处凝结出高品质灵石矿", "scale_bias": [25,45,25,5]},
    {"id": "OP-07", "name": "远古传送阵激活", "desc": "{region}一座远古传送阵被意外激活，连接至未知区域", "scale_bias": [15,35,38,12]},
]

# 势力名称简称映射
FACTION_SHORT = {k: v["name"] for k, v in INITIAL_FACTIONS.items()}

# 修士境界列表
CULTIVATION_LEVELS = ["筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫"]

# 洲级事件模板（东荒全域，每年 1-2 条）
CONTINENTAL_TEMPLATES = [
    {"id": "GL-01", "name": "灵气大迁移", "desc": "东荒全域灵气流动出现重大变化，{detail}"},
    {"id": "GL-02", "name": "天道异象", "desc": "天道显现罕见的全域异象，{detail}"},
    {"id": "GL-03", "name": "因果共振", "desc": "多条因果线同时激活，东荒全域感受到因果共振，{detail}"},
    {"id": "GL-04", "name": "混沌潮汐", "desc": "混沌异常出现全域性潮汐波动，{detail}"},
    {"id": "GL-05", "name": "势力格局重划", "desc": "东荒势力格局发生重大变化，{detail}"},
    {"id": "GL-06", "name": "修行盛世/寒冬", "desc": "东荒修行环境出现全域性转折，{detail}"},
]


# ══════════════════════════════════════════════════════
# 三、模拟引擎
# ══════════════════════════════════════════════════════

class TimelineEngine:
    def __init__(self, seed=42):
        self.rng = random.Random(seed)
        self.regions = {r: dict(INITIAL_REGION_STATE[r]) for r in REGIONS}
        self.factions = {k: dict(v) for k, v in INITIAL_FACTIONS.items()}
        self.causal = dict(INITIAL_CAUSAL)
        self.event_log = []
        self.year = 1
        self.event_counter = 0

    # ---------- 状态更新 ----------
    def _tick_qi(self):
        """每年更新各区域灵气状态：迁移、沉潜、释放"""
        total_trend = 0
        for r in REGIONS:
            st = self.regions[r]
            trend = st["qi_trend"]
            if r == "东部" and self.year > 200:
                trend = min(3, trend + 1)  # 东部加速增长
            if r == "中部" and self.year > 300:
                trend = max(-3, trend - 1)  # 中部加速衰退
            if r == "西部":
                chaos_factor = self.rng.randint(-1, 1)
                trend += chaos_factor
            if r == "北地":
                if self.causal["北地沉潜"] > 70:
                    trend = 1  # 沉潜累积到一定程度开始释放
            st["qi"] = max(1, min(4, st["qi"] + (1 if trend > 0 else (-1 if trend < 0 else 0))))
            st["qi_trend"] = max(-3, min(3, trend))
            total_trend += st["qi"] - INITIAL_REGION_STATE[r]["qi"]

    def _tick_stability(self):
        """每年更新各区域稳定度"""
        for r in REGIONS:
            st = self.regions[r]
            # 灵气变化影响稳定
            qi_change = abs(st["qi"] - INITIAL_REGION_STATE[r]["qi"])
            st["stability"] += self.rng.randint(-3, 3) - qi_change
            # 战斗事件影响
            war_count = sum(1 for e in self.event_log[-20:] if e.get("region") == r and e["category"] == "FACTION_CONFLICT")
            st["stability"] -= war_count
            st["stability"] = max(5, min(95, st["stability"]))

    def _tick_causal(self):
        """每年因果线累积"""
        # 灵气东移持续累积
        east_qi = self.regions["东部"]["qi"]
        central_qi = self.regions["中部"]["qi"]
        self.causal["灵气东移"] += (east_qi - central_qi + 2)
        # 西部不稳定累积上古战争因果
        if self.regions["西部"]["stability"] < 40:
            self.causal["上古战争"] += self.rng.randint(1, 3)
        # 遗迹封闭因果随西部封禁宗门压力累积
        if self.factions["CULT-05"]["power"] < 40:
            self.causal["遗迹封闭"] += self.rng.randint(1, 2)
        # 南部承载随人口和外部需求累积
        self.causal["南部承载"] += self.rng.randint(0, 2)
        # 北地沉潜缓慢累积
        self.causal["北地沉潜"] += self.rng.randint(0, 1)

    def _tick_factions(self):
        """每年更新势力状态"""
        for fid, f in self.factions.items():
            region_st = self.regions[f["region"]]
            # 根据区域稳定度调整势力凝聚力
            f["cohesion"] += self.rng.randint(-2, 2)
            if region_st["stability"] < 30:
                f["cohesion"] -= 1
            # 资源受区域灵气影响
            qi_bonus = (region_st["qi"] - 2) * 2
            f["resource"] += self.rng.randint(-2, 2) + qi_bonus
            f["resource"] = max(0, min(100, f["resource"]))
            # 势力力量随资源和凝聚力变化
            f["power"] += self.rng.randint(-1, 1) + (1 if f["resource"] > 60 else 0) + (1 if f["cohesion"] > 70 else 0)
            f["power"] = max(1, min(100, f["power"]))

    # ---------- 事件生成 ----------
    def _get_factions_in_region(self, region):
        return [fid for fid, f in self.factions.items() if f["region"] == region]

    def _random_scale(self, template_scale_bias=None):
        weights = template_scale_bias if template_scale_bias else SCALE_WEIGHTS
        return self.rng.choices([1, 2, 3, 4], weights=weights, k=1)[0]  # 1=小 2=中 3=大 4=洲

    def _generate_regional_event(self, region, category, templates):
        """为指定区域生成一条事件"""
        template = self.rng.choice(templates)
        scale = self._random_scale(template.get("scale_bias"))
        # 大事件严格受限：只有 ~5% 概率保留 scale=3，其余降为 scale=2
        if scale == 3 and self.rng.random() > 0.05:
            scale = 2
        local_factions = self._get_factions_in_region(region)
        f1 = self.rng.choice(local_factions) if local_factions else "UNKNOWN"
        others = [r for r in REGIONS if r != region]
        target_region = self.rng.choice(others) if others else region
        f2_candidates = [fid for fid in self.factions if fid != f1]
        f2 = self.rng.choice(f2_candidates) if f2_candidates else f1

        desc = template["desc"].format(
            region=region, f1=FACTION_SHORT.get(f1, f1), f2=FACTION_SHORT.get(f2, f2),
            target_region=target_region, qi_level=self.regions[region]["qi"],
            resource=self.rng.choice(["灵脉优先权","庇护协议","历史赔偿","遗迹探索权"]),
            issue=self.rng.choice(["传承归属","灵脉分配","外部威胁应对","与世俗势力关系"]),
            level=self.rng.choice(CULTIVATION_LEVELS),
        )
        self.event_counter += 1
        return {
            "id": f"E{self.year:04d}-{self.event_counter:03d}",
            "year": self.year, "region": region, "category": category,
            "template": template["id"], "scale": scale, "name": template["name"],
            "desc": desc, "factions": [f1, f2] if f1 != f2 else [f1],
            "qi_level": self.regions[region]["qi"],
        }

    def _generate_continental_event(self):
        """生成洲级事件"""
        template = self.rng.choice(CONTINENTAL_TEMPLATES)
        details = [
            f"中部灵气{self.regions['中部']['qi']}级，东部{self.regions['东部']['qi']}级",
            f"多条因果线同时达到临界状态",
            f"{self.rng.choice(REGIONS)}出现前所未有的灵气紊乱",
            f"天道对东荒全域发出罕见的警示征兆",
            f"{self.rng.choice(list(FACTION_SHORT.values()))}的举动改变了全域格局",
            f"东荒修行界迎来{self.rng.choice(['黄金时代','至暗时刻','剧变前夜','新的平衡'])}",
        ]
        self.event_counter += 1
        return {
            "id": f"E{self.year:04d}-{self.event_counter:03d}",
            "year": self.year, "region": "东荒全域", "category": "CONTINENTAL",
            "template": template["id"], "scale": 4, "name": template["name"],
            "desc": template["desc"].format(detail=self.rng.choice(details)),
            "qi_level": sum(self.regions[r]["qi"] for r in REGIONS) // 5,
        }

    def _trigger_causal_echo(self):
        """检查并触发因果回响"""
        events = []
        for causal_name, value in list(self.causal.items()):
            if value >= 100:
                scale = self._random_scale([10, 30, 45, 15])
                self.event_counter += 1
                events.append({
                    "id": f"E{self.year:04d}-{self.event_counter:03d}",
                    "year": self.year, "region": "东荒全域", "category": "CAUSAL_ECHO",
                    "template": "CAUSAL-CLIMAX", "scale": scale,
                    "name": f"{causal_name}因果线达成临界",
                    "desc": f"「{causal_name}」因果线在累积{value}年后达到临界状态，东荒全域感受到因果回响。{self.rng.choice(['世界结构出现微妙变化','各方势力开始感受到历史的重压','天道做出回应','新的时代由此开启'])}",
                })
                self.causal[causal_name] = 0  # 重置
        return events

    # ---------- 主循环 ----------
    def simulate_year(self):
        """模拟一年，返回该年所有事件"""
        self._tick_qi()
        self._tick_stability()
        self._tick_causal()
        self._tick_factions()
        year_events = []

        # 洲级事件：每年 1-2 条
        continental_count = self.rng.choices([1, 2, 3], weights=[55, 40, 5], k=1)[0]
        for _ in range(continental_count):
            year_events.append(self._generate_continental_event())

        # 因果回响触发
        year_events.extend(self._trigger_causal_echo())

        # 区域事件：每年每区生成若干条
        for region in REGIONS:
            st = self.regions[region]
            event_count = self.rng.choices([1, 2, 3, 4], weights=[20, 45, 25, 10], k=1)[0]
            # 不稳定区域更多事件
            if st["stability"] < 30: event_count += 1
            if st["stability"] > 80: event_count = max(1, event_count - 1)

            for _ in range(event_count):
                # 根据区域状态调整事件类型权重
                weights = dict(BASE_EVENT_CHANCE)
                if st["stability"] < 35: weights["FACTION_CONFLICT"] += 15
                if abs(st["qi_trend"]) >= 2: weights["LEYLINE_RESOURCE"] += 10
                if self.causal.get("灵气东移", 0) > 50: weights["CAUSAL_ECHO"] += 5
                if st["phase"] == "临界失衡": weights["CHAOS_ANOMALY"] += 8
                if st["qi"] >= 3: weights["RUIN_OPPORTUNITY"] += 5

                cat = self.rng.choices(
                    list(weights.keys()), weights=list(weights.values()), k=1
                )[0]
                templates_map = {
                    "FACTION_CONFLICT": FACTION_CONFLICT_TEMPLATES,
                    "LEYLINE_RESOURCE": LEYLINE_TEMPLATES,
                    "CULTIVATION_BREAKTHROUGH": BREAKTHROUGH_TEMPLATES,
                    "CAUSAL_ECHO": CAUSAL_TEMPLATES,
                    "CHAOS_ANOMALY": CHAOS_TEMPLATES,
                    "RUIN_OPPORTUNITY": RUIN_TEMPLATES,
                }
                evt = self._generate_regional_event(region, cat, templates_map.get(cat, []))
                year_events.append(evt)

        self.event_log.extend(year_events)
        self.year += 1
        return year_events

    def get_state_summary(self):
        """返回当前世界状态摘要"""
        return {
            "year": self.year,
            "regions": self.regions,
            "factions": {k: {"name": v["name"], "power": v["power"], "region": v["region"]} for k, v in self.factions.items()},
            "causal": dict(self.causal),
        }


# ══════════════════════════════════════════════════════
# 四、主程序
# ══════════════════════════════════════════════════════

def main():
    start_year = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    num_years = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    output_file = sys.argv[3] if len(sys.argv) > 3 else "timeline_output.json"

    engine = TimelineEngine(seed=42)
    all_events = []
    milestones = []

    for y in range(start_year, start_year + num_years):
        events = engine.simulate_year()
        all_events.extend(events)
        # 每 100 年记录一次里程碑
        if y % 100 == 0:
            milestones.append({"year": y, "state": engine.get_state_summary()})

    output = {
        "meta": {
            "total_years": num_years,
            "start_year": start_year,
            "total_events": len(all_events),
            "seed": 42,
        },
        "milestones": milestones,
        "events": all_events,
    }

    out_path = Path(output_file)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"✅ 已生成 {num_years} 年时间线，共 {len(all_events)} 条事件 → {out_path}")
    print(f"   年均事件密度: {len(all_events)/num_years:.1f} 条/年")

if __name__ == "__main__":
    main()
