"""
npc_memory_manager.py — NPC 记忆管理器（B-9）

核心概念：
  NPCMemoryManager 负责：
    - 增加/查询/过滤 NPC 记忆
    - 生成 AI 上下文用的简短描述
    - 记忆数据存储在 campaign[group_id]["npc_memory"] 中

设计原则：
  - 不新增第二套关系系统。
  - 复用现有 campaign.json 存储体系。
  - 支持多 group 隔离、旧存档兼容、Snapshot/Rollback 恢复。
  - NPCMemoryManager 不直接读写文件，由 main.py 的 _save_campaign 统一持久化。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from .npc_memory import (
        NPCMemory,
        create_memory,
        MEMORY_IMPORTANCE_THRESHOLD,
        action_to_memory_params,
        EMOTION_TO_ATTITUDE,
        SOURCE_PLAYER_ACTION,
    )
except ImportError:
    from npc_memory import (
        NPCMemory,
        create_memory,
        MEMORY_IMPORTANCE_THRESHOLD,
        action_to_memory_params,
        EMOTION_TO_ATTITUDE,
        SOURCE_PLAYER_ACTION,
    )


# ──────────────────────────────────────────────
#  NPCMemoryManager
# ──────────────────────────────────────────────

class NPCMemoryManager:
    """管理 NPC 记忆数据。

    数据存储在 campaign[group_id]["npc_memory"] 中，
    结构为 {npc_id: [memory_dict, ...], ...}。
    不直接读写文件，由 main.py 的 _save_campaign 统一持久化。
    """

    def add_memory(
        self,
        campaign: Dict[str, Any],
        group_id: str,
        npc_id: str,
        player_id: str,
        memory_type: str,
        summary: str,
        importance: int,
        emotion: str,
        trust_change: int = 0,
        source: str = "manual",
        cycle: int = 0,
    ) -> NPCMemory:
        """添加一条 NPC 记忆到 campaign 数据中。"""
        mem = create_memory(
            npc_id=npc_id,
            player_id=player_id,
            group_id=group_id,
            memory_type=memory_type,
            summary=summary,
            importance=importance,
            emotion=emotion,
            trust_change=trust_change,
            source=source,
            cycle=cycle,
        )
        npc_memory = campaign.setdefault("npc_memory", {})
        npc_memory.setdefault(npc_id, [])
        npc_memory[npc_id].append(mem.to_dict())
        return mem

    def get_memories(
        self,
        campaign: Dict[str, Any],
        npc_id: str,
        player_id: Optional[str] = None,
    ) -> List[NPCMemory]:
        """获取某 NPC 的记忆列表。"""
        npc_memory = campaign.get("npc_memory", {})
        memories = npc_memory.get(npc_id, [])
        if player_id is not None:
            memories = [m for m in memories if m.get("player_id") == player_id]
        return [NPCMemory.from_dict(m) for m in memories]

    def get_recent_memories(
        self,
        campaign: Dict[str, Any],
        npc_id: str,
        limit: int = 5,
    ) -> List[NPCMemory]:
        """获取最近 N 条记忆。"""
        npc_memory = campaign.get("npc_memory", {})
        memories = npc_memory.get(npc_id, [])
        sorted_memories = sorted(
            [NPCMemory.from_dict(m) for m in memories],
            key=lambda m: m.cycle,
            reverse=True,
        )
        return sorted_memories[:limit]

    def build_context(
        self,
        campaign: Dict[str, Any],
        npc_id: str,
        player_id: str,
        max_chars: int = 400,
    ) -> str:
        """为 AI 生成 NPC 对玩家的上下文描述。"""
        memories = self.get_memories(campaign, npc_id, player_id)
        if not memories:
            return ""

        lines = []
        for mem in memories[:10]:
            attitude = EMOTION_TO_ATTITUDE.get(mem.emotion, "中立")
            lines.append(f"- {mem.summary}，当前态度：{attitude}")

        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return f"【{npc_id}眼中的玩家】\n{text}" if text else ""

    def get_player_memories(
        self,
        campaign: Dict[str, Any],
        player_id: str,
    ) -> List[NPCMemory]:
        """获取所有 NPC 对某玩家的记忆。"""
        npc_memory = campaign.get("npc_memory", {})
        all_memories = []
        for npc_id, mem_list in npc_memory.items():
            for m in mem_list:
                if m.get("player_id") == player_id:
                    all_memories.append(NPCMemory.from_dict(m))
        return all_memories

    def get_player_memories_by_npc(
        self,
        campaign: Dict[str, Any],
        player_id: str,
    ) -> Dict[str, List[NPCMemory]]:
        """获取所有 NPC 对某玩家的记忆，按 NPC 分组。"""
        npc_memory = campaign.get("npc_memory", {})
        result: Dict[str, List[NPCMemory]] = {}
        for npc_id, mem_list in npc_memory.items():
            for m in mem_list:
                if m.get("player_id") == player_id:
                    result.setdefault(npc_id, []).append(NPCMemory.from_dict(m))
        return result

    def delete_memory(
        self,
        campaign: Dict[str, Any],
        npc_id: str,
        memory_id: str,
    ) -> bool:
        """删除指定记忆；返回是否成功。"""
        npc_memory = campaign.get("npc_memory", {})
        entries = npc_memory.get(npc_id, [])
        before = len(entries)
        filtered = [m for m in entries if m.get("memory_id") != memory_id]
        if len(filtered) < before:
            npc_memory[npc_id] = filtered
            return True
        return False

    def get_all_memories(
        self,
        campaign: Dict[str, Any],
    ) -> List[NPCMemory]:
        """获取某群组全部记忆。"""
        npc_memory = campaign.get("npc_memory", {})
        all_memories = []
        for npc_id, mem_list in npc_memory.items():
            all_memories.extend([NPCMemory.from_dict(m) for m in mem_list])
        return all_memories

    def generate_memory_from_action(
        self,
        campaign: Dict[str, Any],
        group_id: str,
        action_type: str,
        outcome_type: str,
        target_id: str,
        target_type: str,
        description: str,
        player_id: str,
        cycle: int,
    ) -> Optional[NPCMemory]:
        """根据玩家行动结果，判断是否生成 NPC 记忆。

        规则：
          - assist + resolved/partial → help 记忆
          - oppose + resolved/partial/failed → conflict 记忆
          - negotiate + resolved → trade 记忆
          - investigate / cultivate → 不生成记忆
          - importance < 40 → 不生成记忆

        Returns:
            生成的 NPCMemory（已写入 campaign），或 None
        """
        params = action_to_memory_params(
            action_type=action_type,
            outcome_type=outcome_type,
            target_id=target_id,
            target_type=target_type,
            description=description,
        )
        if params is None:
            return None
        if params["importance"] < MEMORY_IMPORTANCE_THRESHOLD:
            return None

        # target_id 作为 npc_id（如果目标是 NPC/势力）
        npc_id = target_id if target_type in ("npc", "faction") else target_id

        return self.add_memory(
            campaign=campaign,
            group_id=group_id,
            npc_id=npc_id,
            player_id=player_id,
            memory_type=params["memory_type"],
            summary=params["summary"],
            importance=params["importance"],
            emotion=params["emotion"],
            source=SOURCE_PLAYER_ACTION,
            cycle=cycle,
        )
