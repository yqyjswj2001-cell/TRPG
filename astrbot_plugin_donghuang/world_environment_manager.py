"""
world_environment_manager.py — 修仙环境管理器 (B-15)

职责：
  1. 继续复用现有普通天气变化结果
  2. 根据灵气流向、CHAOS、区域资源生成灵气天气
  3. 检查特殊天象是否开始或结束
  4. 检查异常环境是否开始或结束
  5. 更新持续周期
  6. 不直接创建 EventPool 事件

核心原则：
  - 灵气天气必须由世界状态决定，不允许完全随机
  - 变化概率受灵气流向数值影响
  - 不允许每次Tick都改变灵气天气
  - 灵气天气至少持续2个Cycle
  - 同一区域同时只能有一个主要灵气天气
  - 不修改现有leyline_flow_value字段
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional

try:
    from .world_environment import (
        EnvironmentState,
        EFFECT_TAGS,
        SPIRITUAL_WEATHERS,
        CELESTIAL_PHENOMENA,
        ANOMALY_ENVIRONMENTS,
    )
except ImportError:
    from world_environment import (
        EnvironmentState,
        EFFECT_TAGS,
        SPIRITUAL_WEATHERS,
        CELESTIAL_PHENOMENA,
        ANOMALY_ENVIRONMENTS,
    )

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  常量
# ──────────────────────────────────────────────

# 灵气天气最小持续周期
SPIRITUAL_MIN_DURATION = 2

# 天象最小持续周期
CELESTIAL_MIN_DURATION = 1

# 异常环境最小持续周期
ANOMALY_MIN_DURATION = 1

# 灵气天气变化概率（每次Tick）
SPIRITUAL_CHANGE_PROBABILITY = 0.12

# 天象触发概率基数（每次Tick每区域）
CELESTIAL_TRIGGER_BASE_PROB = 0.005

# 异常环境触发概率基数（每次Tick每区域）
ANOMALY_TRIGGER_BASE_PROB = 0.008

# CHAOS 高风险级别
_CHAOS_HIGH_LEVELS = frozenset({"活跃", "高压", "临界", "活跃-非世界级"})

# CHAOS 中等级别
_CHAOS_MEDIUM_LEVELS = frozenset({"活跃", "活跃-非世界级"})

# CHAOS 高级别（异常环境触发）
_CHAOS_VERY_HIGH_LEVELS = frozenset({"高压", "临界"})


class WorldEnvironmentManager:
    """管理世界环境状态的演化。"""

    def evolve_environment(
        self,
        group_id: str,
        world_state: Dict[str, Any],
        cycle: int,
        campaign: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行一次环境演化。

        Args:
            group_id: 群号
            world_state: 当前世界状态（会被修改：REGION[region].environment）
            cycle: 当前 cycle
            campaign: 团务状态字典（可选，用于读写 evolution_memory）

        Returns:
            {
                "physical_changed": [{"region", "field", "old_value", "new_value"}],
                "spiritual_changed": [{"region", "field", "old_value", "new_value"}],
                "celestial_started": [{"region", "phenomenon", "intensity"}],
                "celestial_ended": [{"region", "phenomenon"}],
                "anomaly_started": [{"region", "anomaly", "intensity"}],
                "anomaly_ended": [{"region", "anomaly"}],
                "effect_changes": [{"region", "added", "removed"}],
            }
        """
        result = {
            "physical_changed": [],
            "spiritual_changed": [],
            "celestial_started": [],
            "celestial_ended": [],
            "anomaly_started": [],
            "anomaly_ended": [],
            "effect_changes": [],
        }

        # 确保 evolution_memory 存在
        if campaign is None:
            campaign = {}
        if "evolution_memory" not in campaign:
            campaign["evolution_memory"] = {}
        memory = campaign["evolution_memory"]

        # 确保环境相关记忆字段存在
        memory.setdefault("spiritual_history", {})
        memory.setdefault("last_spiritual_change_cycle", {})

        # 遍历所有区域
        region_state = world_state.get("REGION", {})
        for region in list(region_state.keys()):
            self._evolve_region(
                region, world_state, cycle, memory, result
            )

        logger.debug(
            f"[WorldEnvironment] evolve({group_id}): "
            f"灵气变化{len(result['spiritual_changed'])}, "
            f"天象开始{len(result['celestial_started'])}, "
            f"异常开始{len(result['anomaly_started'])}"
        )

        return result

    def _evolve_region(
        self,
        region: str,
        world_state: Dict[str, Any],
        cycle: int,
        memory: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """演化单个区域的四层环境。"""
        region_data = world_state.get("REGION", {}).get(region, {})
        if not isinstance(region_data, dict):
            return

        # 获取或创建环境状态
        env_dict = region_data.get("environment")
        if env_dict is None:
            env = EnvironmentState.create_default()
            # 同步当前普通天气
            weather_data = world_state.get("weather", {})
            env.physical_weather = weather_data.get(region, "")
            region_data["environment"] = env.to_dict()
        else:
            env = EnvironmentState.from_dict(env_dict)

        # ── 1. 同步普通天气 ──
        self._sync_physical_weather(region, world_state, env, result)

        # ── 2. 灵气天气演化 ──
        self._evolve_spiritual(region, world_state, cycle, memory, env, result)

        # ── 3. 特殊天象检测 ──
        self._check_celestial(region, world_state, cycle, memory, env, result)

        # ── 4. 异常环境检测 ──
        self._check_anomaly(region, world_state, cycle, memory, env, result)

        # ── 5. 更新持续周期 ──
        self._tick_durations(region, env, result)

        # ── 6. 更新效果标签 ──
        old_effects = list(env.effects)
        env.effects = env.collect_effects()
        if set(old_effects) != set(env.effects):
            added = list(set(env.effects) - set(old_effects))
            removed = list(set(old_effects) - set(env.effects))
            result["effect_changes"].append({
                "region": region,
                "added": added,
                "removed": removed,
            })

        # 保存回 world_state
        region_data["environment"] = env.to_dict()

    # ──────────────────────────────────────────────
    #  1. 同步普通天气
    # ──────────────────────────────────────────────

    def _sync_physical_weather(
        self,
        region: str,
        world_state: Dict[str, Any],
        env: EnvironmentState,
        result: Dict[str, Any],
    ) -> None:
        """将现有 weather 字段同步到 physical_weather。"""
        weather_data = world_state.get("weather", {})
        current_weather = weather_data.get(region, "")
        if current_weather and env.physical_weather != current_weather:
            old = env.physical_weather
            env.physical_weather = current_weather
            result["physical_changed"].append({
                "region": region,
                "field": "physical_weather",
                "old_value": old,
                "new_value": current_weather,
            })

    # ──────────────────────────────────────────────
    #  2. 灵气天气演化
    # ──────────────────────────────────────────────

    def _evolve_spiritual(
        self,
        region: str,
        world_state: Dict[str, Any],
        cycle: int,
        memory: Dict[str, Any],
        env: EnvironmentState,
        result: Dict[str, Any],
    ) -> None:
        """根据灵气流向演化灵气天气。

        规则：
          - 灵气流向值在 40-60 → 平稳
          - 灵气流向值 >= 70 → 灵潮/灵雾/五行偏盛
          - 灵气流向值 <= 30 → 灵气衰潮/灵压沉降
          - 连续多次灵气变化 → 地脉回响
          - 至少持续 2 个 Cycle
          - 不允许每次 Tick 都改变
        """
        global_state = world_state.get("GLOBAL", {})
        flow_value = global_state.get("leyline_flow_value", 50)

        # 记录灵气流向历史
        spiritual_history = memory.get("spiritual_history", {})
        region_history = spiritual_history.get(region, [])
        region_history.append(flow_value)
        # 只保留最近 5 次
        if len(region_history) > 5:
            region_history = region_history[-5:]
        spiritual_history[region] = region_history

        # 检查是否在最小持续期内
        if env.spiritual_weather != "平稳" and env.remaining_cycles > 0:
            # 还在持续期内，不变化
            return

        # 检查上次变化距离当前多少 cycle
        last_change = memory.get("last_spiritual_change_cycle", {})
        last_cycle = last_change.get(region, 0)
        if cycle - last_cycle < SPIRITUAL_MIN_DURATION:
            # 距离上次变化不足最小持续期
            return

        # 计算变化概率
        change_prob = SPIRITUAL_CHANGE_PROBABILITY
        # 高灵气或低灵气时增加变化概率
        if flow_value >= 70:
            change_prob *= 2.0
        elif flow_value <= 30:
            change_prob *= 2.0

        # 随机决定是否变化
        if random.random() >= change_prob:
            return

        # 确定新的灵气天气
        new_weather = self._determine_spiritual_weather(flow_value, region_history)

        if new_weather == env.spiritual_weather:
            return  # 没有实际变化

        old_weather = env.spiritual_weather
        env.spiritual_weather = new_weather

        # 设置持续时间和强度
        if new_weather == "平稳":
            env.duration_cycles = 0
            env.remaining_cycles = 0
            env.intensity = 0
            env.source = "natural"
        else:
            env.duration_cycles = SPIRITUAL_MIN_DURATION + random.randint(0, 3)
            env.remaining_cycles = env.duration_cycles
            env.intensity = min(100, abs(flow_value - 50) * 2)
            env.source = "leyline"

        # 记录变化时间
        last_change[region] = cycle

        result["spiritual_changed"].append({
            "region": region,
            "field": "spiritual_weather",
            "old_value": old_weather,
            "new_value": new_weather,
        })

    def _determine_spiritual_weather(
        self,
        flow_value: int,
        history: List[int],
    ) -> str:
        """根据灵气流向值和历史确定灵气天气。"""
        # 连续多次灵气变化 → 地脉回响
        if len(history) >= 4:
            # 检查最近4次是否有3次以上变化方向不同
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

        # 30-40 或 60-70 之间 → 保持当前或平稳
        return "平稳"

    # ──────────────────────────────────────────────
    #  3. 特殊天象检测
    # ──────────────────────────────────────────────

    def _check_celestial(
        self,
        region: str,
        world_state: Dict[str, Any],
        cycle: int,
        memory: Dict[str, Any],
        env: EnvironmentState,
        result: Dict[str, Any],
    ) -> None:
        """检查特殊天象是否应该开始或结束。

        规则：
          - 灵气高涨（flow >= 70）→ 天青异霞/紫气东来/星河倒映
          - 灵气异常波动 → 九曜乱象/天雷云海
          - CHAOS较高 → 血月临空/日月同辉异常态
          - 至少持续 1 个 Cycle
          - 已存在天象时不重复触发
          - 不允许每个 Tick 都生成天象
          - 天象结束后恢复为"无"
        """
        # 已存在天象 → 检查是否结束
        if env.celestial_phenomenon != "无":
            if env.remaining_cycles <= 0:
                # 天象结束
                old_phenom = env.celestial_phenomenon
                env.celestial_phenomenon = "无"
                env.intensity = 0
                env.duration_cycles = 0
                env.remaining_cycles = 0
                result["celestial_ended"].append({
                    "region": region,
                    "phenomenon": old_phenom,
                })
            return  # 已有天象时不重复触发

        # 没有天象 → 检查是否应该触发
        global_state = world_state.get("GLOBAL", {})
        chaos_level = global_state.get("chaos_level", "平稳")
        flow_value = global_state.get("leyline_flow_value", 50)

        # 计算触发概率
        prob = CELESTIAL_TRIGGER_BASE_PROB

        # 灵气高涨增加概率
        if flow_value >= 70:
            prob *= 4.0
        elif flow_value >= 60:
            prob *= 2.0

        # CHAOS 较高增加概率
        if chaos_level in _CHAOS_HIGH_LEVELS:
            prob *= 3.0

        # 随机决定是否触发
        if random.random() >= prob:
            return

        # 根据条件选择天象
        phenom = self._trigger_celestial(region, flow_value, chaos_level, env, result)

    def _trigger_celestial(
        self,
        region: str,
        flow_value: int,
        chaos_level: str,
        env: EnvironmentState,
        result: Dict[str, Any],
    ) -> None:
        """触发一个特殊天象。"""
        # 优先级：CHAOS高 → 灵气异常 → 灵气高涨
        if chaos_level in _CHAOS_HIGH_LEVELS:
            candidates = ["血月临空", "日月同辉"]
            phenom = random.choice(candidates)
            source = "chaos"
        elif flow_value >= 70:
            candidates = ["天青异霞", "紫气东来", "星河倒映"]
            phenom = random.choice(candidates)
            source = "leyline"
        elif 30 <= flow_value <= 70 and chaos_level in _CHAOS_MEDIUM_LEVELS:
            candidates = ["九曜乱象", "天雷云海"]
            phenom = random.choice(candidates)
            source = "natural"
        else:
            # 条件不充分，不触发
            return

        env.celestial_phenomenon = phenom
        env.intensity = min(100, max(20, flow_value // 2 + random.randint(0, 20)))
        env.duration_cycles = CELESTIAL_MIN_DURATION + random.randint(0, 4)
        env.remaining_cycles = env.duration_cycles
        env.source = source

        result["celestial_started"].append({
            "region": region,
            "phenomenon": phenom,
            "intensity": env.intensity,
        })

    # ──────────────────────────────────────────────
    #  4. 异常环境检测
    # ──────────────────────────────────────────────

    def _check_anomaly(
        self,
        region: str,
        world_state: Dict[str, Any],
        cycle: int,
        memory: Dict[str, Any],
        env: EnvironmentState,
        result: Dict[str, Any],
    ) -> None:
        """检查异常环境是否应该开始或结束。

        规则：
          - CHAOS低 → 无
          - CHAOS中等 → 虚空潮汐/因果乱流/梦境侵蚀
          - CHAOS较高 → 空间裂隙/时间错层/灵墟投影/天道压制
          - 异常环境必须有持续时间
          - 异常结束后清除对应 effects
          - 不允许异常环境直接造成玩家死亡
          - 不允许直接修改玩家属性
        """
        # 已存在异常环境 → 检查是否结束
        if env.anomaly_environment != "无":
            if env.remaining_cycles <= 0:
                # 异常环境结束
                old_anomaly = env.anomaly_environment
                env.anomaly_environment = "无"
                env.intensity = 0
                env.duration_cycles = 0
                env.remaining_cycles = 0
                result["anomaly_ended"].append({
                    "region": region,
                    "anomaly": old_anomaly,
                })
            return  # 已有异常时不重复触发

        # 没有异常环境 → 检查是否应该触发
        global_state = world_state.get("GLOBAL", {})
        chaos_level = global_state.get("chaos_level", "平稳")

        # CHAOS低 → 不触发
        if chaos_level not in _CHAOS_HIGH_LEVELS:
            return

        # 计算触发概率
        prob = ANOMALY_TRIGGER_BASE_PROB
        if chaos_level in _CHAOS_VERY_HIGH_LEVELS:
            prob *= 3.0

        # 随机决定是否触发
        if random.random() >= prob:
            return

        # 根据CHAOS级别选择异常环境
        self._trigger_anomaly(region, chaos_level, env, result)

    def _trigger_anomaly(
        self,
        region: str,
        chaos_level: str,
        env: EnvironmentState,
        result: Dict[str, Any],
    ) -> None:
        """触发一个异常环境。"""
        if chaos_level in _CHAOS_VERY_HIGH_LEVELS:
            # CHAOS较高 → 空间裂隙/时间错层/灵墟投影/天道压制
            candidates = ["空间裂隙", "时间错层", "灵墟投影", "天道压制"]
        else:
            # CHAOS中等 → 虚空潮汐/因果乱流/梦境侵蚀
            candidates = ["虚空潮汐", "因果乱流", "梦境侵蚀"]

        anomaly = random.choice(candidates)
        env.anomaly_environment = anomaly
        env.intensity = _chaos_to_intensity(chaos_level)
        env.duration_cycles = ANOMALY_MIN_DURATION + random.randint(1, 4)
        env.remaining_cycles = env.duration_cycles
        env.source = "chaos"

        result["anomaly_started"].append({
            "region": region,
            "anomaly": anomaly,
            "intensity": env.intensity,
        })

    # ──────────────────────────────────────────────
    #  5. 更新持续周期
    # ──────────────────────────────────────────────

    def _tick_durations(
        self,
        region: str,
        env: EnvironmentState,
        result: Dict[str, Any],
    ) -> None:
        """递减所有环境的剩余周期。"""
        if env.remaining_cycles > 0:
            env.remaining_cycles -= 1

        # 灵气天气到期 → 恢复平稳
        if env.spiritual_weather != "平稳" and env.remaining_cycles <= 0:
            # 只有在 _evolve_spiritual 没有更新时才恢复
            # （如果 _evolve_spiritual 已经设置了新天气，这里不会覆盖）
            pass  # 由 _evolve_spiritual 处理

        # 天象到期 → 由 _check_celestial 处理
        # 异常到期 → 由 _check_anomaly 处理


def _chaos_to_intensity(chaos_level: str) -> int:
    """将CHAOS级别转换为强度值。"""
    levels = {
        "平稳": 10,
        "微动": 20,
        "活跃": 40,
        "高压": 60,
        "临界": 80,
        "活跃-非世界级": 50,
    }
    return levels.get(chaos_level, 30)
