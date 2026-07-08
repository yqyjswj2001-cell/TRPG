"""
world_tick_scheduler.py — Tick 调度管理层

管理 Tick 是否应该执行。只做时间判断，不执行 Tick 本身。

规则：
  - 默认 30 分钟允许一次 World Tick
  - 旧存档没有 tick_state 自动初始化

不负责：
  - 执行 Tick（由 WorldTickManager 负责）
  - 后台定时任务
  - NPC 行为
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 默认 Tick 间隔（秒）
DEFAULT_TICK_INTERVAL = 30 * 60  # 30 分钟


class TickScheduler:
    """管理 Tick 调度：判断是否应该执行 Tick。

    Tick 状态持久化在 campaign[group_id]["tick_state"] 中：

    {
        "last_tick_time": float,   # 上次 Tick 的时间戳
        "last_tick_cycle": int,    # 上次 Tick 时的 cycle
        "tick_count": int,         # 总共执行了多少次 Tick
    }
    """

    def __init__(self, tick_interval: int = DEFAULT_TICK_INTERVAL):
        """
        Args:
            tick_interval: Tick 最小间隔（秒），默认 1800（30 分钟）
        """
        self.tick_interval = tick_interval

    def _get_tick_state(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        """获取 tick_state，兼容旧存档。"""
        if "tick_state" not in campaign:
            campaign["tick_state"] = {
                "last_tick_time": 0.0,
                "last_tick_cycle": 0,
                "tick_count": 0,
            }
        return campaign["tick_state"]

    def should_tick(self, group_id: str, campaign: Dict[str, Any],
                    now: Optional[float] = None) -> bool:
        """判断是否应该执行一次 Tick。

        规则：距离上次 Tick 超过 tick_interval 秒则允许。

        Args:
            group_id: 群号
            campaign: 团务状态字典
            now: 当前时间戳（默认 time.time()）

        Returns:
            True 表示可以执行 Tick
        """
        if now is None:
            now = time.time()

        state = self._get_tick_state(campaign)
        last_tick_time = state.get("last_tick_time", 0.0)

        # 从未执行过 Tick
        if last_tick_time == 0.0:
            return True

        elapsed = now - last_tick_time
        return elapsed >= self.tick_interval

    def mark_tick(self, group_id: str, campaign: Dict[str, Any],
                  now: Optional[float] = None) -> None:
        """标记一次 Tick 已执行，更新 tick_state。

        Args:
            group_id: 群号
            campaign: 团务状态字典（会被修改）
            now: 当前时间戳（默认 time.time()）
        """
        if now is None:
            now = time.time()

        state = self._get_tick_state(campaign)
        state["last_tick_time"] = now
        state["last_tick_cycle"] = campaign.get("cycle", 1)
        state["tick_count"] = state.get("tick_count", 0) + 1

        logger.debug(
            f"[TickScheduler] mark_tick({group_id}): "
            f"tick_count={state['tick_count']}, "
            f"last_tick_cycle={state['last_tick_cycle']}"
        )

    def get_last_tick(self, group_id: str,
                      campaign: Dict[str, Any]) -> Dict[str, Any]:
        """获取上次 Tick 的信息。

        Returns:
            tick_state 字典的副本
        """
        state = self._get_tick_state(campaign)
        return {
            "last_tick_time": state.get("last_tick_time", 0.0),
            "last_tick_cycle": state.get("last_tick_cycle", 0),
            "tick_count": state.get("tick_count", 0),
        }

    def reset(self, group_id: str, campaign: Dict[str, Any]) -> None:
        """重置 Tick 状态（用于 rollback 后恢复）。

        注意：调用方应从快照恢复 campaign，此方法用于手动重置。
        """
        campaign["tick_state"] = {
            "last_tick_time": 0.0,
            "last_tick_cycle": 0,
            "tick_count": 0,
        }
        logger.debug(f"[TickScheduler] reset({group_id})")

    def format_status(self, group_id: str, campaign: Dict[str, Any],
                      now: Optional[float] = None) -> str:
        """格式化 Tick 状态为可读文本，供 /dh tick status 输出。

        Args:
            group_id: 群号
            campaign: 团务状态字典
            now: 当前时间戳

        Returns:
            格式化的状态文本
        """
        import datetime

        if now is None:
            now = time.time()

        state = self._get_tick_state(campaign)
        last_tick_time = state.get("last_tick_time", 0.0)
        last_tick_cycle = state.get("last_tick_cycle", 0)
        tick_count = state.get("tick_count", 0)

        lines = ["🕐 世界 Tick 调度状态", "━━━━━━━━━━━━━━"]

        # 总执行次数
        lines.append(f"总执行次数：{tick_count}")

        # 上次执行时间
        if last_tick_time > 0:
            last_dt = datetime.datetime.fromtimestamp(last_tick_time)
            lines.append(f"上次执行：{last_dt.strftime('%Y-%m-%d %H:%M:%S')}（Cycle-{last_tick_cycle:06d}）")

            # 距离下次 Tick 的剩余时间
            elapsed = now - last_tick_time
            remaining = max(0, self.tick_interval - elapsed)

            if remaining > 0:
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                lines.append(f"下次可用：{minutes}分{seconds}秒后")
                can_tick = False
            else:
                lines.append("下次可用：✅ 现在可以执行")
                can_tick = True
        else:
            lines.append("上次执行：从未执行")
            lines.append("下次可用：✅ 现在可以执行")
            can_tick = True

        # Tick 间隔
        interval_min = self.tick_interval // 60
        lines.append(f"最小间隔：{interval_min} 分钟")
        lines.append(f"当前状态：{'可执行' if can_tick else '冷却中'}")

        return "\n".join(lines)
