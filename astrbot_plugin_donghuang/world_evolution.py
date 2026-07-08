"""
world_evolution.py — 世界状态自然演化

每次 World Tick 后，对已有 World State 做轻量确定性更新。

职责：
  1. 天气自然变化（相邻状态转移，不跨级跳跃）
  2. 灵气流向微调（±1 小幅变化，范围 0-100）
  3. 区域资源轻微变化（+1 或 -1，范围 0-100）
  4. 势力运行时状态初始化与补全（ensure_faction_state）
  5. 势力状态演化（evolve_factions）——B-5.2
  6. 修仙环境演化（四层环境系统）——B-15

不负责：
  - NPC 行为模拟
  - 新事件生成（由 EventPool 处理）
  - AI Prompt 修改
  - 世界观扩展
"""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  天气相邻转移图
# ──────────────────────────────────────────────

# 每种天气只能转移到相邻状态（或保持不变），禁止跨级跳跃
# 格式：当前天气 → [可能的下一状态]（权重相同）
_WEATHER_TRANSITIONS = {
    "晴": ["晴", "晴", "多云", "微风"],
    "多云": ["多云", "多云", "晴", "阴", "薄雾"],
    "阴": ["阴", "阴", "多云", "小雨", "薄雾"],
    "小雨": ["小雨", "小雨", "阴", "中雨", "薄雾"],
    "中雨": ["中雨", "中雨", "小雨", "大雨"],
    "大雨": ["大雨", "大雨", "中雨", "暴雨"],
    "暴雨": ["暴雨", "大雨"],
    "薄雾": ["薄雾", "薄雾", "多云", "阴", "浓雾"],
    "浓雾": ["浓雾", "薄雾", "阴"],
    "微风": ["微风", "微风", "晴", "多云", "大风"],
    "大风": ["大风", "大风", "微风", "暴风"],
    "暴风": ["暴风", "大风"],
    "小雪": ["小雪", "小雪", "阴", "中雪"],
    "中雪": ["中雪", "中雪", "小雪", "大雪"],
    "大雪": ["大雪", "大雪", "中雪", "暴雪"],
    "暴雪": ["暴雪", "大雪"],
    "沙尘": ["沙尘", "沙尘", "多云", "沙暴"],
    "沙暴": ["沙暴", "沙暴", "沙尘"],
    # 稀有天气：不主动转移，回归普通天气
    "灵气潮汐": ["晴", "多云", "薄雾"],
    "灵雾": ["薄雾", "多云", "阴"],
    "灵雨": ["小雨", "多云", "薄雾"],
    "天象裂痕": ["阴", "多云", "暴风"],
    "血色黄昏": ["晴", "多云", "阴"],
    "逆流风暴": ["大风", "暴风", "阴"],
}

# 天气变化概率（每次 Tick 有多少概率发生变化）
_WEATHER_CHANGE_PROBABILITY = 0.3  # 30%

# 灵气流向数值键名（存储在 world_state["GLOBAL"]["leyline_flow_value"] 中）
_LEYLINE_FLOW_VALUE_KEY = "leyline_flow_value"

# 资源数值键名（存储在 world_state["RESOURCE"][name]["value"] 中）
_RESOURCE_VALUE_KEY = "value"

# ──────────────────────────────────────────────
#  势力演化常量（B-5.2）
# ──────────────────────────────────────────────

# 区域 → 默认资源键名映射（用于灵脉资源影响稳定度规则）
# 每个区域对应 RESOURCE 中的一个主资源键
_REGION_RESOURCE_MAP = {
    "中部": "中部主脉残核",
    "东部": "东部新生支脉",
    "南部": "南部资源网络",
    "北地": "北地沉潜资源",
    "西部": "西部遗迹与异常资源",
}

# 资源值阈值：≤30 时区域势力 stability -0.03
_RESOURCE_LOW_THRESHOLD = 30
# 资源值阈值：≥70 时区域势力 stability +0.02
_RESOURCE_HIGH_THRESHOLD = 70
# 资源低值对稳定度的影响量
_STABILITY_DELTA_RESOURCE_LOW = -0.03
# 资源高值对稳定度的影响量
_STABILITY_DELTA_RESOURCE_HIGH = 0.02

# 资源流健康度阈值
_FLOW_LOW_THRESHOLD = 30
_FLOW_HIGH_THRESHOLD = 80
# 资源流低值对士气的影响量（双方）
_MORALE_DELTA_FLOW_LOW = -0.02
# 资源流高值对士气的影响量（双方）
_MORALE_DELTA_FLOW_HIGH = 0.01

# CHAOS 高风险状态集合
_CHAOS_HIGH_RISK_LEVELS = frozenset({"活跃", "高压", "临界", "活跃-非世界级"})
# CHAOS 对稳定度的影响量
_STABILITY_DELTA_CHAOS = -0.02

# 稳定度影响 power 的阈值
_STABILITY_POWER_LOW_THRESHOLD = 0.3
_STABILITY_POWER_HIGH_THRESHOLD = 0.8
_MORALE_POWER_HIGH_THRESHOLD = 0.7

# 连续低稳定度/低士气触发 goal 切换的阈值（连续 Tick 数）
_GOAL_SWITCH_THRESHOLD = 3

# evolution_memory 中势力相关字段的默认值
_FACTION_MEMORY_DEFAULTS = {
    "faction_low_stability_ticks": {},
    "faction_low_morale_ticks": {},
    "faction_power_decline_ticks": {},
}


class WorldEvolutionManager:
    """每次 World Tick 后对 World State 做轻量更新。"""

    def evolve(
        self,
        group_id: str,
        world_state: Dict[str, Any],
        cycle: int,
        campaign: Optional[Dict[str, Any]] = None,
        factions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行一次世界状态演化。

        Args:
            group_id: 群号
            world_state: 当前世界状态（会被修改）
            cycle: 当前 cycle
            campaign: 团务状态字典（可选，势力演化需要读写 evolution_memory）
            factions: 静态势力数据字典（可选，势力演化需要读取 region/relations）

        Returns:
            演化结果字典：
            {
                "weather_changed": [{"region", "from", "to"}],
                "region_changed": [],
                "resource_changed": [{"name", "from", "to"}],
                "leyline_flow_changed": bool,
                "leyline_flow_from": int,
                "leyline_flow_to": int,
                "faction_changed": [{"code", "field", "from", "to"}],  # B-5.2 新增
                "environment_changed": [{"region", ...}],              # B-15 新增
            }
        """
        result = {
            "weather_changed": [],
            "region_changed": [],
            "resource_changed": [],
            "leyline_flow_changed": False,
            "leyline_flow_from": 0,
            "leyline_flow_to": 0,
            "faction_changed": [],  # B-5.2 新增
            "environment_changed": [],  # B-15 新增
        }

        # ── 天气自然变化 ──
        self._evolve_weather(world_state, result)

        # ── 灵气流向微调 ──
        self._evolve_leyline_flow(world_state, result)

        # ── 区域资源轻微变化 ──
        self._evolve_resources(world_state, result)

        # ── 势力状态演化（B-5.2）──
        self._evolve_factions(world_state, result, campaign, factions)

        # ── 修仙环境演化（B-15）──
        self._evolve_environment(world_state, result, cycle, campaign)

        logger.debug(
            f"[WorldEvolution] evolve({group_id}): "
            f"天气变化{len(result['weather_changed'])}处, "
            f"资源变化{len(result['resource_changed'])}处, "
            f"灵气流向变化={result['leyline_flow_changed']}, "
            f"势力变化{len(result['faction_changed'])}处, "
            f"环境变化{len(result['environment_changed'])}处"
        )

        return result

    # ──────────────────────────────────────────────
    #  天气自然变化
    # ──────────────────────────────────────────────

    def _evolve_weather(self, world_state: Dict, result: Dict) -> None:
        """天气相邻状态转移，小概率变化，不跨级跳跃。"""
        weather_data = world_state.get("weather", {})
        if not weather_data:
            return

        for region, current_weather in list(weather_data.items()):
            # 小概率变化
            if random.random() > _WEATHER_CHANGE_PROBABILITY:
                continue

            transitions = _WEATHER_TRANSITIONS.get(current_weather)
            if not transitions:
                # 未知天气类型，不处理
                continue

            new_weather = random.choice(transitions)
            if new_weather != current_weather:
                weather_data[region] = new_weather
                result["weather_changed"].append({
                    "region": region,
                    "from": current_weather,
                    "to": new_weather,
                })

    # ──────────────────────────────────────────────
    #  灵气流向微调
    # ──────────────────────────────────────────────

    def _evolve_leyline_flow(self, world_state: Dict, result: Dict) -> None:
        """灵气流向数值 ±1，范围 0-100。"""
        global_state = world_state.get("GLOBAL", {})
        if not global_state:
            return

        # 初始化数值（如果不存在）
        if _LEYLINE_FLOW_VALUE_KEY not in global_state:
            # 默认 50（中性值）
            global_state[_LEYLINE_FLOW_VALUE_KEY] = 50

        old_value = global_state[_LEYLINE_FLOW_VALUE_KEY]
        # ±1 变化
        delta = random.choice([-1, 1])
        new_value = max(0, min(100, old_value + delta))

        global_state[_LEYLINE_FLOW_VALUE_KEY] = new_value

        if new_value != old_value:
            result["leyline_flow_changed"] = True
            result["leyline_flow_from"] = old_value
            result["leyline_flow_to"] = new_value

    # ──────────────────────────────────────────────
    #  区域资源轻微变化
    # ──────────────────────────────────────────────

    def _evolve_resources(self, world_state: Dict, result: Dict) -> None:
        """每个资源 +1 或 -1，范围 0-100。不产生新资源，不删除资源。"""
        resource_state = world_state.get("RESOURCE", {})
        if not resource_state:
            return

        for name, info in list(resource_state.items()):
            if not isinstance(info, dict):
                continue

            # 初始化数值（如果不存在）
            if _RESOURCE_VALUE_KEY not in info:
                info[_RESOURCE_VALUE_KEY] = 50

            old_value = info[_RESOURCE_VALUE_KEY]
            # +1 或 -1
            delta = random.choice([-1, 1])
            new_value = max(0, min(100, old_value + delta))

            info[_RESOURCE_VALUE_KEY] = new_value

            if new_value != old_value:
                result["resource_changed"].append({
                    "name": name,
                    "from": old_value,
                    "to": new_value,
                })

    # ──────────────────────────────────────────────
    #  势力状态演化（B-5.2）
    # ──────────────────────────────────────────────

    def _evolve_factions(
        self,
        world_state: Dict[str, Any],
        result: Dict[str, Any],
        campaign: Optional[Dict[str, Any]],
        factions: Optional[Dict[str, Any]],
    ) -> None:
        """Tick 中势力状态自然演化。

        规则执行顺序：
          1. 灵脉资源影响稳定度
          2. Resource Flow 影响士气
          3. CHAOS 影响全部势力稳定度
          4. 稳定度影响 Power
          5. 连续状态计数与 Goal 切换
          6. 边界 clamp

        不负责：
          - 触发事件（B-5.3）
          - 修改 EventPool
          - 修改 stance_overrides（B-5.2 不实现）
        """
        faction_state = world_state.get("FACTION_STATE")
        if not faction_state or not isinstance(faction_state, dict):
            return

        # 无 factions 配置时无法执行（需要 region/relations 信息）
        if not factions:
            return

        # 确保 evolution_memory 存在且包含势力相关字段
        if campaign is None:
            return
        if "evolution_memory" not in campaign:
            campaign["evolution_memory"] = {}
        memory = campaign["evolution_memory"]
        for key, default in _FACTION_MEMORY_DEFAULTS.items():
            memory.setdefault(key, default)

        low_stab_ticks = memory["faction_low_stability_ticks"]
        low_morale_ticks = memory["faction_low_morale_ticks"]

        for code, entry in faction_state.items():
            if not isinstance(entry, dict):
                continue

            fac_info = factions.get(code)
            if not fac_info:
                continue

            # ── 规则1: 灵脉资源影响稳定度 ──
            self._apply_resource_to_stability(world_state, entry, fac_info, result)

            # ── 规则2: Resource Flow 影响士气 ──
            self._apply_flow_to_morale(world_state, entry, fac_info, result)

            # ── 规则3: CHAOS 影响全部势力 ──
            self._apply_chaos_to_stability(world_state, entry, code, result)

            # ── 规则4: 稳定度影响 Power ──
            self._apply_stability_to_power(entry, code, result)

            # ── 规则5 & 6: 连续状态计数与 Goal 切换 ──
            self._apply_goal_switch(entry, code, low_stab_ticks, low_morale_ticks, result)
            self._apply_long_term_faction_ecology(world_state, entry, fac_info, code, result)

            # ── 规则7: 边界保护 ──
            self._clamp_faction_entry(entry)

    def _apply_resource_to_stability(
        self,
        world_state: Dict,
        entry: Dict,
        fac_info: Dict,
        result: Dict,
    ) -> None:
        """规则1：势力所在区域灵脉资源值影响稳定度。"""
        region = fac_info.get("region", "")
        resource_key = _REGION_RESOURCE_MAP.get(region)
        if not resource_key:
            return

        resource_data = world_state.get("RESOURCE", {}).get(resource_key)
        if not isinstance(resource_data, dict):
            return

        value = resource_data.get(_RESOURCE_VALUE_KEY)
        if value is None:
            return

        old_stab = entry.get("stability", 0.5)
        new_stab = old_stab

        if value <= _RESOURCE_LOW_THRESHOLD:
            new_stab = old_stab + _STABILITY_DELTA_RESOURCE_LOW
        elif value >= _RESOURCE_HIGH_THRESHOLD:
            new_stab = old_stab + _STABILITY_DELTA_RESOURCE_HIGH

        if new_stab != old_stab:
            entry["stability"] = new_stab
            result["faction_changed"].append({
                "code": fac_info.get("code", ""),
                "field": "stability",
                "from": round(old_stab, 4),
                "to": round(new_stab, 4),
            })

    def _apply_flow_to_morale(
        self,
        world_state: Dict,
        entry: Dict,
        fac_info: Dict,
        result: Dict,
    ) -> None:
        """规则2：关联资源流健康度影响士气（影响双方）。"""
        faction_code = fac_info.get("code", "")
        flows = world_state.get("RESOURCE_FLOW", {})
        if not flows:
            return

        # 收集与该势力相关的所有资源流健康度
        for rel in fac_info.get("relations", []) or []:
            if not isinstance(rel, dict):
                continue
            target_code = rel.get("code", "")
            if not target_code:
                continue

            # 构建 flow key（排序后拼接）
            flow_key = "|".join(sorted([faction_code, target_code]))
            health = flows.get(flow_key)
            if health is None:
                continue

            # 只记录一次变化（每个势力每 Tick 最多一条 morale 变化）
            old_morale = entry.get("morale", 0.7)
            new_morale = old_morale

            if health <= _FLOW_LOW_THRESHOLD:
                new_morale = old_morale + _MORALE_DELTA_FLOW_LOW
            elif health >= _FLOW_HIGH_THRESHOLD:
                new_morale = old_morale + _MORALE_DELTA_FLOW_HIGH

            if new_morale != old_morale:
                entry["morale"] = new_morale
                result["faction_changed"].append({
                    "code": faction_code,
                    "field": "morale",
                    "from": round(old_morale, 4),
                    "to": round(new_morale, 4),
                })
                # 每个势力每 Tick 只记录第一次 morale 变化
                break

    def _apply_chaos_to_stability(
        self,
        world_state: Dict,
        entry: Dict,
        code: str,
        result: Dict,
    ) -> None:
        """规则3：CHAOS 高风险状态影响全部势力稳定度。"""
        chaos_level = world_state.get("GLOBAL", {}).get("chaos_level", "")
        if chaos_level not in _CHAOS_HIGH_RISK_LEVELS:
            return

        old_stab = entry.get("stability", 0.5)
        new_stab = old_stab + _STABILITY_DELTA_CHAOS

        if new_stab != old_stab:
            entry["stability"] = new_stab
            result["faction_changed"].append({
                "code": code,
                "field": "stability",
                "from": round(old_stab, 4),
                "to": round(new_stab, 4),
            })

    def _apply_stability_to_power(
        self,
        entry: Dict,
        code: str,
        result: Dict,
    ) -> None:
        """规则4：稳定度影响 Power（每 Tick 最多 ±1）。"""
        stab = entry.get("stability", 0.5)
        morale = entry.get("morale", 0.7)
        old_power = entry.get("power", 50)
        delta = 0

        if stab < _STABILITY_POWER_LOW_THRESHOLD:
            delta = -1
        elif stab > _STABILITY_POWER_HIGH_THRESHOLD and morale > _MORALE_POWER_HIGH_THRESHOLD:
            delta = +1

        if delta != 0:
            new_power = old_power + delta
            entry["power"] = new_power
            result["faction_changed"].append({
                "code": code,
                "field": "power",
                "from": old_power,
                "to": new_power,
            })

    def _apply_goal_switch(
        self,
        entry: Dict,
        code: str,
        low_stab_ticks: Dict[str, int],
        low_morale_ticks: Dict[str, int],
        result: Dict,
    ) -> None:
        """规则5 & 6：连续低稳定度/低士气 → Goal 切换。"""
        stab = entry.get("stability", 0.5)
        morale = entry.get("morale", 0.7)
        current_goal = entry.get("active_goal", "")

        # ── 连续低稳定度计数 ──
        if stab < _STABILITY_POWER_LOW_THRESHOLD:
            low_stab_ticks[code] = low_stab_ticks.get(code, 0) + 1
        else:
            low_stab_ticks[code] = 0

        # ── 连续低士气计数 ──
        if morale < _STABILITY_POWER_LOW_THRESHOLD:
            low_morale_ticks[code] = low_morale_ticks.get(code, 0) + 1
        else:
            low_morale_ticks[code] = 0

        # ── Goal 切换（需要连续 _GOAL_SWITCH_THRESHOLD Tick） ──
        # 优先级：内乱 > 自保——如果已经是"内乱"，不会被"自保"降级
        new_goal = None
        if low_morale_ticks.get(code, 0) >= _GOAL_SWITCH_THRESHOLD and current_goal != "内乱":
            new_goal = "内乱"
        elif (low_stab_ticks.get(code, 0) >= _GOAL_SWITCH_THRESHOLD
              and current_goal != "自保"
              and current_goal != "内乱"):
            new_goal = "自保"

        if new_goal is not None:
            old_goal = current_goal
            entry["active_goal"] = new_goal
            result["faction_changed"].append({
                "code": code,
                "field": "active_goal",
                "from": old_goal,
                "to": new_goal,
            })

    def _apply_long_term_faction_ecology(
        self,
        world_state: Dict[str, Any],
        entry: Dict[str, Any],
        fac_info: Dict[str, Any],
        code: str,
        result: Dict[str, Any],
    ) -> None:
        region = fac_info.get("region", "")
        resource_key = _REGION_RESOURCE_MAP.get(region)
        resource_value = 50
        if resource_key:
            resource_data = world_state.get("RESOURCE", {}).get(resource_key, {})
            if isinstance(resource_data, dict):
                resource_value = int(resource_data.get(_RESOURCE_VALUE_KEY, 50) or 50)

        flow_scores = []
        for rel in fac_info.get("relations", []) or []:
            if not isinstance(rel, dict):
                continue
            target_code = rel.get("code", "")
            if not target_code:
                continue
            flow_key = "|".join(sorted([code, target_code]))
            health = world_state.get("RESOURCE_FLOW", {}).get(flow_key)
            if isinstance(health, (int, float)):
                flow_scores.append(float(health))
        flow_value = sum(flow_scores) / len(flow_scores) if flow_scores else 50.0

        old_resources = int(entry.get("resources", 50) or 50)
        new_resources = old_resources
        if resource_value <= _RESOURCE_LOW_THRESHOLD:
            new_resources -= 2
        elif resource_value >= _RESOURCE_HIGH_THRESHOLD:
            new_resources += 1
        if flow_value <= _FLOW_LOW_THRESHOLD:
            new_resources -= 1
        elif flow_value >= _FLOW_HIGH_THRESHOLD:
            new_resources += 1
        if new_resources != old_resources:
            entry["resources"] = new_resources
            result["faction_changed"].append({"code": code, "field": "resources", "from": old_resources, "to": new_resources})

        old_influence = int(entry.get("influence", 50) or 50)
        target_influence = int((int(entry.get("power", 50) or 50) * 0.8) + (float(entry.get("stability", 0.5) or 0.5) * 20))
        new_influence = old_influence
        if target_influence > old_influence:
            new_influence += 1
        elif target_influence < old_influence:
            new_influence -= 1
        if new_influence != old_influence:
            entry["influence"] = new_influence
            result["faction_changed"].append({"code": code, "field": "influence", "from": old_influence, "to": new_influence})

        old_reputation = float(entry.get("reputation", 0.5) or 0.5)
        target_reputation = (float(entry.get("stability", 0.5) or 0.5) + float(entry.get("morale", 0.7) or 0.7)) / 2
        new_reputation = round(old_reputation, 4)
        if target_reputation - old_reputation > 0.03:
            new_reputation = round(old_reputation + 0.02, 4)
        elif old_reputation - target_reputation > 0.03:
            new_reputation = round(old_reputation - 0.02, 4)
        if new_reputation != old_reputation:
            entry["reputation"] = new_reputation
            result["faction_changed"].append({"code": code, "field": "reputation", "from": round(old_reputation, 4), "to": round(new_reputation, 4)})

        old_internal = entry.get("internal_state", "stable")
        stab = float(entry.get("stability", 0.5) or 0.5)
        morale = float(entry.get("morale", 0.7) or 0.7)
        if stab < 0.3 or morale < 0.3:
            new_internal = "fragmenting"
        elif stab < 0.5 or morale < 0.5:
            new_internal = "strained"
        else:
            new_internal = "stable"
        if new_internal != old_internal:
            entry["internal_state"] = new_internal
            result["faction_changed"].append({"code": code, "field": "internal_state", "from": old_internal, "to": new_internal})

        old_strategic_goal = entry.get("strategic_goal", entry.get("active_goal", "维持现状"))
        active_goal = entry.get("active_goal", "维持现状")
        if active_goal in ("扩张领土", "鎷撳睍鍔垮姏"):
            new_strategic_goal = "扩张"
        elif active_goal in ("自保", "鏀剁缉鑷繚", "闂叧鍥哄畧"):
            new_strategic_goal = "防守"
        elif active_goal in ("资源争夺", "瀵绘壘鏂拌剦"):
            new_strategic_goal = "资源争夺"
        elif active_goal in ("研究", "瀹堟姢绉樺瘑"):
            new_strategic_goal = "研究"
        elif active_goal in ("内乱", "鍐呬贡", "内部变化", "鍐呴儴鍒嗗寲"):
            new_strategic_goal = "内部变化"
        else:
            new_strategic_goal = "维持现状"
        if new_strategic_goal != old_strategic_goal:
            entry["strategic_goal"] = new_strategic_goal
            result["faction_changed"].append({"code": code, "field": "strategic_goal", "from": old_strategic_goal, "to": new_strategic_goal})

        runtime_rel = entry.get("faction_relations_runtime")
        if not isinstance(runtime_rel, dict):
            runtime_rel = {}
            entry["faction_relations_runtime"] = runtime_rel
        for rel in fac_info.get("relations", []) or []:
            if not isinstance(rel, dict):
                continue
            target_code = rel.get("code", "")
            if not target_code:
                continue
            item = runtime_rel.setdefault(target_code, {"stance": rel.get("stance", "中立"), "tension": 0.5, "trust": 0.5})
            item.setdefault("stance", rel.get("stance", "中立"))
            item.setdefault("tension", 0.5)
            item.setdefault("trust", 0.5)
            old_tension = float(item.get("tension", 0.5) or 0.5)
            old_trust = float(item.get("trust", 0.5) or 0.5)
            new_tension = old_tension
            new_trust = old_trust

            stance = str(item.get("stance", ""))
            if flow_value <= _FLOW_LOW_THRESHOLD:
                new_tension += 0.03
                new_trust -= 0.02
            elif flow_value >= _FLOW_HIGH_THRESHOLD and stance in ("盟友", "合作竞争", "从属", "浠庡睘"):
                new_tension -= 0.02
                new_trust += 0.02


            new_tension = max(0.0, min(1.0, round(new_tension, 4)))
            new_trust = max(0.0, min(1.0, round(new_trust, 4)))
            if new_tension != old_tension:
                item["tension"] = new_tension
                result["faction_changed"].append({
                    "code": code,
                    "field": f"faction_relations_runtime.{target_code}.tension",
                    "from": round(old_tension, 4),
                    "to": round(new_tension, 4),
                })
            if new_trust != old_trust:
                item["trust"] = new_trust
                result["faction_changed"].append({
                    "code": code,
                    "field": f"faction_relations_runtime.{target_code}.trust",
                    "from": round(old_trust, 4),
                    "to": round(new_trust, 4),
                })



    def _clamp_faction_entry(self, entry: Dict) -> None:
        """规则7：边界保护——stability/morale [0.0, 1.0]，power [0, 100]。"""
        if "stability" in entry:
            entry["stability"] = max(0.0, min(1.0, entry["stability"]))
        if "morale" in entry:
            entry["morale"] = max(0.0, min(1.0, entry["morale"]))
        if "power" in entry:
            entry["power"] = max(0, min(100, entry["power"]))
        if "reputation" in entry:
            entry["reputation"] = max(0.0, min(1.0, entry["reputation"]))
        if "resources" in entry:
            entry["resources"] = max(0, min(100, entry["resources"]))
        if "influence" in entry:
            entry["influence"] = max(0, min(100, entry["influence"]))

    # ──────────────────────────────────────────────
    #  修仙环境演化（B-15）
    # ──────────────────────────────────────────────

    def _evolve_environment(
        self,
        world_state: Dict[str, Any],
        result: Dict[str, Any],
        cycle: int,
        campaign: Optional[Dict[str, Any]],
    ) -> None:
        """调用 WorldEnvironmentManager 演化四层环境。

        要求：
          1. 不复制普通天气演化代码
          2. 使用现有天气变化结果同步 physical_weather
          3. 灵气天气、天象和异常环境由新管理器负责
        """
        try:
            from .world_environment_manager import WorldEnvironmentManager
        except ImportError:
            from world_environment_manager import WorldEnvironmentManager

        env_manager = WorldEnvironmentManager()
        env_result = env_manager.evolve_environment(
            group_id="",  # 不需要，环境管理器直接操作 world_state
            world_state=world_state,
            cycle=cycle,
            campaign=campaign,
        )

        # 将环境变化结果合并到 evolution result
        # 构造 environment_changed 列表
        for change in env_result.get("spiritual_changed", []):
            region = change.get("region", "")
            result["environment_changed"].append({
                "region": region,
                "physical_weather": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("physical_weather", ""),
                "spiritual_weather": change.get("new_value", ""),
                "celestial_phenomenon": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("celestial_phenomenon", "无"),
                "anomaly_environment": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("anomaly_environment", "无"),
                "effects": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("effects", []),
            })

        for change in env_result.get("celestial_started", []):
            region = change.get("region", "")
            # 避免与 spiritual_changed 重复添加同一区域
            if not any(e.get("region") == region for e in result["environment_changed"]):
                result["environment_changed"].append({
                    "region": region,
                    "physical_weather": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("physical_weather", ""),
                    "spiritual_weather": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("spiritual_weather", "平稳"),
                    "celestial_phenomenon": change.get("phenomenon", "无"),
                    "anomaly_environment": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("anomaly_environment", "无"),
                    "effects": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("effects", []),
                })

        for change in env_result.get("anomaly_started", []):
            region = change.get("region", "")
            if not any(e.get("region") == region for e in result["environment_changed"]):
                result["environment_changed"].append({
                    "region": region,
                    "physical_weather": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("physical_weather", ""),
                    "spiritual_weather": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("spiritual_weather", "平稳"),
                    "celestial_phenomenon": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("celestial_phenomenon", "无"),
                    "anomaly_environment": change.get("anomaly", "无"),
                    "effects": world_state.get("REGION", {}).get(region, {}).get("environment", {}).get("effects", []),
                })

    # ──────────────────────────────────────────────
    #  势力运行时状态初始化与补全（B-5）
    # ──────────────────────────────────────────────

    def ensure_faction_state(
        self,
        world_state: Dict[str, Any],
        campaign: Optional[Dict[str, Any]] = None,
        factions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """确保 world_state 中存在完整 FACTION_STATE，并返回初始化/补全摘要。

        Args:
            world_state: 世界状态字典（会被修改）
            campaign: 团务状态字典（可选，用于读取 evolution_memory）
            factions: 静态势力数据字典（来自 factions.json），可选

        Returns:
            {
                "added": [{"code", "reason"}],          # 新增的势力条目
                "filled": [{"code", "field"}],           # 补全字段的势力
                "skipped": [{"code", "reason"}],         # 跳过的势力
                "total_added": int,
                "total_filled": int,
                "total_skipped": int,
            }
        """
        if "FACTION_STATE" not in world_state:
            world_state["FACTION_STATE"] = {}

        existing_codes = set(world_state["FACTION_STATE"].keys())

        # 如果传入了 factions 参数，从中获取所有势力代码
        all_faction_codes = set()
        if factions:
            for code in factions:
                all_faction_codes.add(code)

        summary = {
            "added": [],
            "filled": [],
            "skipped": [],
            "total_added": 0,
            "total_filled": 0,
            "total_skipped": 0,
        }

        for code in sorted(all_faction_codes):
            if code in existing_codes:
                # 已有势力条目，检查是否有缺失字段
                entry = world_state["FACTION_STATE"][code]
                missing_fields = []
                if not isinstance(entry, dict):
                    missing_fields.append("root")
                else:
                    for field in ("power", "stability", "stance_overrides", "active_goal", "morale", "reputation", "resources", "influence", "strategic_goal", "internal_state", "faction_relations_runtime"):
                        if field not in entry:
                            missing_fields.append(field)
                if missing_fields:
                    summary["filled"].append({"code": code, "field": "+".join(missing_fields)})
                    continue
                else:
                    summary["skipped"].append({"code": code, "reason": "已完整"})
            else:
                # 缺失势力条目，需要新建
                summary["added"].append({"code": code, "reason": "新势力条目"})
                summary["total_added"] += 1

        # 对每个新增或补全的势力，计算初始值
        for entry_info in summary["added"] + summary["filled"]:
            code = entry_info["code"]

            # 新增势力：创建空条目；已有但非 dict 时转为 dict
            if code not in world_state["FACTION_STATE"]:
                world_state["FACTION_STATE"][code] = {}
                pass
            elif not isinstance(world_state["FACTION_STATE"][code], dict):
                world_state["FACTION_STATE"][code] = {}

            entry = world_state["FACTION_STATE"][code]

            # power：从 factions.json 的 power 字段 ×2，上限 100
            # 只在缺失时设置，不覆盖已有值
            if "power" not in entry:
                if factions and code in factions:
                    raw_power = factions[code].get("power", 50) * 2
                    entry["power"] = min(100, max(0, raw_power))
                else:
                    entry["power"] = 50

            # stability：根据 status_desc 描述性文字推导；无法判断时默认 0.5
            # 只在缺失时设置，不覆盖已有值
            if "stability" not in entry:
                if factions and code in factions:
                    desc = factions[code].get("status_desc", "").strip()
                    if "稳定" in desc or "维持" in desc:
                        entry["stability"] = 0.8
                    elif "扩张" in desc or "拓展" in desc:
                        entry["stability"] = 0.7
                    elif "接近崩溃" in desc or "衰退" in desc:
                        entry["stability"] = 0.3
                    elif "负担" in desc or "压力" in desc:
                        entry["stability"] = 0.6
                    elif "临界" in desc or "失衡" in desc:
                        entry["stability"] = 0.4
                    else:
                        entry["stability"] = 0.5
                else:
                    entry["stability"] = 0.5

            # stance_overrides：缺失时设为空字典
            if "stance_overrides" not in entry:
                entry["stance_overrides"] = {}

            # active_goal：根据 type 和 stability 推导
            # 只在缺失时设置，不覆盖已有值
            if "active_goal" not in entry:
                if factions and code in factions:
                    ftype = factions[code].get("type", "散修网络")
                    stab = entry.get("stability", 0.5)
                    if ftype == "王朝":
                        if stab >= 0.7:
                            entry["active_goal"] = "维持秩序"
                        elif stab < 0.5:
                            entry["active_goal"] = "收缩自保"
                        else:
                            entry["active_goal"] = "内部分化"
                    elif ftype == "宗门":
                        if stab >= 0.7:
                            entry["active_goal"] = "拓展势力"
                        elif stab < 0.4:
                            entry["active_goal"] = "闭关固守"
                        else:
                            entry["active_goal"] = "寻找新脉"
                    elif ftype == "散修网络":
                        entry["active_goal"] = "互助求生"
                    elif ftype == "隐秘组织":
                        if stab >= 0.6:
                            entry["active_goal"] = "守护秘密"
                        else:
                            entry["active_goal"] = "隐藏存续"
                    else:
                        entry["active_goal"] = "维持现状"
                else:
                    entry["active_goal"] = "维持现状"

            # morale：缺失时默认 0.7
            if "morale" not in entry:
                entry["morale"] = 0.7

            if "reputation" not in entry:
                entry["reputation"] = round(max(0.0, min(1.0, (entry.get("stability", 0.5) + entry.get("morale", 0.7)) / 2)), 4)

            if "resources" not in entry:
                base_power = int(entry.get("power", 50) or 50)
                entry["resources"] = max(0, min(100, 20 + base_power // 2))

            if "influence" not in entry:
                power = int(entry.get("power", 50) or 50)
                relation_bonus = 0
                if factions and code in factions:
                    relation_bonus = min(10, len(factions[code].get("relations", []) or []) * 2)
                entry["influence"] = max(0, min(100, power // 2 + relation_bonus))

            if "strategic_goal" not in entry:
                entry["strategic_goal"] = entry.get("active_goal", "缁存寔鐜扮姸")

            if "internal_state" not in entry:
                stab = float(entry.get("stability", 0.5) or 0.5)
                morale = float(entry.get("morale", 0.7) or 0.7)
                if stab < 0.3 or morale < 0.3:
                    entry["internal_state"] = "fragmenting"
                elif stab < 0.5 or morale < 0.5:
                    entry["internal_state"] = "strained"
                else:
                    entry["internal_state"] = "stable"

            if "faction_relations_runtime" not in entry:
                runtime_rel = {}
                if factions and code in factions:
                    for rel in factions[code].get("relations", []) or []:
                        if not isinstance(rel, dict):
                            continue
                        target_code = rel.get("code", "")
                        if not target_code:
                            continue
                        runtime_rel[target_code] = {
                            "stance": rel.get("stance", "涓珛"),
                            "tension": 0.5,
                            "trust": 0.5,
                        }
                entry["faction_relations_runtime"] = runtime_rel

        summary["total_filled"] = len(summary["filled"])
        summary["total_skipped"] = len(summary["skipped"])

        return summary
