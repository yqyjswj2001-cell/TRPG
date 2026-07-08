"""
world_environment.py — 环境状态数据模型 (B-15)

四层环境结构：
  1. physical_weather: 普通天气（晴/阴/雨等）
  2. spiritual_weather: 灵气天气（灵潮/灵气衰潮等）
  3. celestial_phenomenon: 特殊天象（紫气东来/血月临空等）
  4. anomaly_environment: 异常环境（虚空潮汐/空间裂隙等）

存储位置：world_state["REGION"][region]["environment"]

核心原则：
  - 普通天气与修仙天象必须分开保存
  - 天气是环境状态，不是正式事件
  - 环境变化可以提供事件触发条件，但不能直接写剧情结局
  - 所有数值变化由代码处理
  - AI只负责描述环境，不负责决定数值
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
#  常量定义
# ──────────────────────────────────────────────

# 普通天气
PHYSICAL_WEATHERS = frozenset({
    "晴", "多云", "阴", "小雨", "中雨", "大雨", "暴雨", "雷暴",
    "大雪", "寒潮", "干旱", "薄雾", "浓雾", "微风", "大风", "暴风",
    "小雪", "中雪", "暴雪", "沙尘", "沙暴",
})

# 灵气天气
SPIRITUAL_WEATHERS = frozenset({
    "平稳", "灵潮", "灵气衰潮", "灵雾", "五行偏盛", "灵压沉降", "地脉回响",
})

# 特殊天象
CELESTIAL_PHENOMENA = frozenset({
    "无", "天青异霞", "紫气东来", "九曜乱象", "血月临空",
    "天雷云海", "星河倒映", "日月同辉",
})

# 异常环境
ANOMALY_ENVIRONMENTS = frozenset({
    "无", "虚空潮汐", "空间裂隙", "因果乱流", "时间错层",
    "梦境侵蚀", "灵墟投影", "天道压制",
})

# 环境效果标签映射
EFFECT_TAGS: Dict[str, List[str]] = {
    "灵潮": ["cultivation_bonus", "spirit_beast_activity_up", "spiritual_resource_growth"],
    "灵气衰潮": ["cultivation_penalty", "resource_recovery_down"],
    "天青异霞": ["ruin_resonance_up", "divination_clarity_up"],
    "九曜乱象": ["divination_disrupted", "causal_noise_up"],
    "血月临空": ["beast_aggression_up", "demonic_activity_up", "chaos_pressure_up"],
    "天雷云海": ["lightning_affinity_up", "breakthrough_risk_up"],
    "虚空潮汐": ["ruin_entrance_activity_up", "spatial_instability"],
    "空间裂隙": ["travel_risk_up", "anomaly_event_probability_up"],
    "因果乱流": ["causal_detection_down", "causal_echo_probability_up"],
}

# 来源类型
SOURCE_TYPES = frozenset({"natural", "leyline", "chaos", "event", "manual"})

# 效果标签中文描述
EFFECT_DESCRIPTIONS: Dict[str, str] = {
    "cultivation_bonus": "修炼效率略有提升",
    "spirit_beast_activity_up": "灵兽活动更加频繁",
    "spiritual_resource_growth": "灵气资源增长加速",
    "cultivation_penalty": "修炼效率降低",
    "resource_recovery_down": "资源恢复速度减缓",
    "ruin_resonance_up": "遗迹共鸣概率提高",
    "divination_clarity_up": "占卜清晰度提升",
    "divination_disrupted": "占卜受到干扰",
    "causal_noise_up": "因果噪音增强",
    "beast_aggression_up": "妖兽攻击性增强",
    "demonic_activity_up": "魔修活动增多",
    "chaos_pressure_up": "混沌压力上升",
    "lightning_affinity_up": "雷属性亲和提升",
    "breakthrough_risk_up": "突破风险增大",
    "ruin_entrance_activity_up": "遗迹入口活跃度上升",
    "spatial_instability": "空间不稳定",
    "travel_risk_up": "出行风险增加",
    "anomaly_event_probability_up": "异常事件概率上升",
    "causal_detection_down": "因果感知降低",
    "causal_echo_probability_up": "因果回响概率上升",
}


@dataclass
class EnvironmentState:
    """四层环境状态数据模型。

    Attributes:
        physical_weather: 普通天气，如 "晴"、"小雨"
        spiritual_weather: 灵气天气，如 "灵潮"、"灵气衰潮"
        celestial_phenomenon: 特殊天象，如 "紫气东来"、"血月临空"
        anomaly_environment: 异常环境，如 "虚空潮汐"、"空间裂隙"
        intensity: 强度值 0-100
        duration_cycles: 总持续周期数
        remaining_cycles: 剩余周期数
        effects: 结构化效果标签列表
        source: 来源类型 (natural/leyline/chaos/event/manual)
    """

    physical_weather: str = ""
    spiritual_weather: str = ""
    celestial_phenomenon: str = ""
    anomaly_environment: str = ""
    intensity: int = 0
    duration_cycles: int = 0
    remaining_cycles: int = 0
    effects: List[str] = field(default_factory=list)
    source: str = "natural"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "physical_weather": self.physical_weather,
            "spiritual_weather": self.spiritual_weather,
            "celestial_phenomenon": self.celestial_phenomenon,
            "anomaly_environment": self.anomaly_environment,
            "intensity": self.intensity,
            "duration_cycles": self.duration_cycles,
            "remaining_cycles": self.remaining_cycles,
            "effects": list(self.effects),
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EnvironmentState":
        """从字典还原。"""
        if not isinstance(d, dict):
            return cls()
        return cls(
            physical_weather=d.get("physical_weather", ""),
            spiritual_weather=d.get("spiritual_weather", ""),
            celestial_phenomenon=d.get("celestial_phenomenon", ""),
            anomaly_environment=d.get("anomaly_environment", ""),
            intensity=d.get("intensity", 0),
            duration_cycles=d.get("duration_cycles", 0),
            remaining_cycles=d.get("remaining_cycles", 0),
            effects=list(d.get("effects", [])),
            source=d.get("source", "natural"),
        )

    @classmethod
    def create_default(cls) -> "EnvironmentState":
        """创建默认环境状态。"""
        return cls(
            physical_weather="",
            spiritual_weather="平稳",
            celestial_phenomenon="无",
            anomaly_environment="无",
            intensity=0,
            duration_cycles=0,
            remaining_cycles=0,
            effects=[],
            source="natural",
        )

    def validate(self) -> bool:
        """验证环境状态是否合法。"""
        if not isinstance(self.intensity, (int, float)):
            return False
        if not (0 <= self.intensity <= 100):
            return False
        if self.duration_cycles < 0 or self.remaining_cycles < 0:
            return False
        if self.remaining_cycles > self.duration_cycles and self.duration_cycles > 0:
            return False
        if self.source and self.source not in SOURCE_TYPES:
            return False
        return True

    def collect_effects(self) -> List[str]:
        """收集当前所有环境的效果标签。"""
        all_effects = []
        # 灵气天气效果
        if self.spiritual_weather in EFFECT_TAGS:
            all_effects.extend(EFFECT_TAGS[self.spiritual_weather])
        # 天象效果
        if self.celestial_phenomenon in EFFECT_TAGS:
            all_effects.extend(EFFECT_TAGS[self.celestial_phenomenon])
        # 异常环境效果
        if self.anomaly_environment in EFFECT_TAGS:
            all_effects.extend(EFFECT_TAGS[self.anomaly_environment])
        # 去重
        return list(dict.fromkeys(all_effects))

    def describe_effects(self) -> str:
        """将效果标签转换为简短中文描述。"""
        effects = self.collect_effects()
        if not effects:
            return ""
        descs = []
        for tag in effects:
            desc = EFFECT_DESCRIPTIONS.get(tag, "")
            if desc:
                descs.append(desc)
        return "，".join(descs)


# ──────────────────────────────────────────────
#  辅助函数
# ──────────────────────────────────────────────

def get_spiritual_weather_at(flow_value: int, history: list = None) -> str:
    """根据灵气流向数值推荐灵气天气。

    Args:
        flow_value: 灵气流向数值 (0-100)
        history: 最近几次的灵气流向变化历史（可选）

    Returns:
        推荐的灵气天气名称
    """
    import random

    # 连续多次灵气变化 → 地脉回响
    if history and len(history) >= 4:
        diffs = [history[i] - history[i - 1] for i in range(1, len(history))]
        sign_changes = sum(
            1 for i in range(1, len(diffs))
            if (diffs[i] > 0) != (diffs[i - 1] > 0)
        )
        if sign_changes >= 2:
            return "地脉回响"

    # 灵气流向值在 40-60 → 平稳
    if 40 <= flow_value <= 60:
        return "平稳"

    # 灵气流向值 >= 70 → 灵潮/灵雾/五行偏盛
    if flow_value >= 70:
        return random.choice(["灵潮", "灵雾", "五行偏盛"])

    # 灵气流向值 <= 30 → 灵气衰潮/灵压沉降
    if flow_value <= 30:
        return random.choice(["灵气衰潮", "灵压沉降"])

    return "平稳"
