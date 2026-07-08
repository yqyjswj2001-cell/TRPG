"""
npc_registry.py — NPC 数据注册中心（B-13）

核心概念：
  NPCRegistry = 统一读取现有 NPC 数据的只读访问层。
  不复制数据，复用 main.py 中已有的 npc_by_name、major_npcs_by_faction、minor_npcs_by_subregion。

设计原则：
  - 只读，不修改任何数据。
  - 提供统一的 NPC 信息查询接口。
  - 支持模糊搜索和区域查找。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .asset_loader import load_json as _al_load_json
except ImportError:
    from asset_loader import load_json as _al_load_json


# ──────────────────────────────────────────────
#  NPCRegistry 数据类
# ──────────────────────────────────────────────

@dataclass
class NPCInfo:
    """NPC 基本信息（简化视图）。"""

    id: str = ""
    name: str = ""
    role: str = ""
    faction_code: str = ""
    faction_name: str = ""
    region: str = ""
    subregion: str = ""
    cultivation_tier: str = ""
    spirit_element: str = ""
    six_dims: Dict[str, int] = field(default_factory=dict)
    description: str = ""
    relations: List[Dict[str, str]] = field(default_factory=list)
    personality: str = ""  # 人格标签
    identity_tier: str = ""  # 身份等级（黄/玄/地/天等）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "role": self.role,
            "faction_code": self.faction_code, "faction_name": self.faction_name,
            "region": self.region, "subregion": self.subregion,
            "cultivation_tier": self.cultivation_tier, "spirit_element": self.spirit_element,
            "six_dims": self.six_dims, "description": self.description,
            "relations": self.relations, "personality": self.personality,
            "identity_tier": self.identity_tier,
        }


# ──────────────────────────────────────────────
#  NPCRegistry
# ──────────────────────────────────────────────

class NPCRegistry:
    """NPC 数据注册中心。

    从 major_npcs.json 和 minor_npcs.json 加载 NPC 数据，
    提供统一的查询接口。
    """

    def __init__(self):
        self._npc_by_name: Dict[str, Dict[str, Any]] = {}
        self._major_by_faction: Dict[str, List[Dict[str, Any]]] = {}
        self._minor_by_subregion: Dict[str, List[Dict[str, Any]]] = {}
        self._path_cache: Dict[str, Path] = {}

    def load(self, plugin_dir: Optional[Path] = None) -> None:
        """加载 NPC 数据文件。"""
        if plugin_dir is None:
            plugin_dir = Path(__file__).resolve().parent

        data_dir = plugin_dir / "data"

        # 加载 major_npcs.json
        major_path = data_dir / "major_npcs.json"
        if not major_path.exists():
            raise FileNotFoundError(f"major_npcs.json not found at {major_path}")

        major_npcs = _al_load_json(major_path)
        for npc in major_npcs:
            name = npc.get("name", "")
            if name:
                self._npc_by_name[name] = npc

            faction = npc.get("faction_code", "")
            if faction:
                self._major_by_faction.setdefault(faction, []).append(npc)

        # 加载 minor_npcs.json
        minor_path = data_dir / "minor_npcs.json"
        if not minor_path.exists():
            raise FileNotFoundError(f"minor_npcs.json not found at {minor_path}")

        minor_npcs = _al_load_json(minor_path)
        for npc in minor_npcs:
            name = npc.get("name", "")
            if name:
                self._npc_by_name[name] = npc

            subregion = npc.get("subregion", "")
            if subregion:
                self._minor_by_subregion.setdefault(subregion, []).append(npc)

    def get_npc(self, npc_id: str) -> Optional[Dict[str, Any]]:
        """根据 NPC ID 获取完整 NPC 数据。"""
        return self._npc_by_name.get(npc_id)

    def search_npc(self, keyword: str) -> List[Dict[str, Any]]:
        """模糊搜索 NPC（按名称匹配关键词）。"""
        keyword_lower = keyword.lower()
        results = []
        for name, npc in self._npc_by_name.items():
            if keyword_lower in name.lower():
                results.append(npc)
        return results

    def get_nearby_npcs(self, region: str, max_count: int = 5) -> List[Dict[str, Any]]:
        """获取指定区域的 NPC 列表。"""
        results = []
        for npc in self._npc_by_name.values():
            npc_region = npc.get("region", "")
            if npc_region == region:
                results.append(npc)
            if len(results) >= max_count:
                break
        return results

    def get_faction_npcs(self, faction_code: str) -> List[Dict[str, Any]]:
        """获取某势力的所有 NPC。"""
        return self._major_by_faction.get(faction_code, [])

    def get_subregion_npcs(self, subregion: str) -> List[Dict[str, Any]]:
        """获取某子区域的 NPC。"""
        return self._minor_by_subregion.get(subregion, [])

    def get_all_npcs(self) -> List[Dict[str, Any]]:
        """获取所有 NPC。"""
        return list(self._npc_by_name.values())

    def npc_exists(self, npc_id: str) -> bool:
        """检查 NPC 是否存在。"""
        return npc_id in self._npc_by_name


# ──────────────────────────────────────────────
#  便捷函数
# ──────────────────────────────────────────────

def create_npc_info(npc_dict: Dict[str, Any]) -> NPCInfo:
    """从 NPC dict 创建 NPCInfo 对象。"""
    return NPCInfo(
        id=npc_dict.get("npc_id", ""),
        name=npc_dict.get("name", ""),
        role=npc_dict.get("role", ""),
        faction_code=npc_dict.get("faction_code", ""),
        faction_name=npc_dict.get("faction_name", ""),
        region=npc_dict.get("region", ""),
        subregion=npc_dict.get("subregion", ""),
        cultivation_tier=npc_dict.get("spirit_root_tier", ""),
        spirit_element=npc_dict.get("spirit_root_element", ""),
        six_dims=npc_dict.get("six_dims", {}),
        description=npc_dict.get("desc", ""),
        relations=npc_dict.get("relations", []),
        personality=npc_dict.get("personality", ""),
        identity_tier=npc_dict.get("spirit_root_tier", ""),
    )
