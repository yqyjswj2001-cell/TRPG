"""
npc_perception.py — NPC 对玩家的感知系统（B-8）

核心概念：
  NPC 根据自身修为境界和身份，对玩家外貌、气息、气质产生不同的感知。
  不允许直接读取玩家隐藏数据（如 hidden_hook）。
  感知结果用于 AI 叙事中 NPC 对玩家的反应描述。

设计原则：
  - 感知基于可见特征（衣着、气质、印记），不读取隐藏字段。
  - 不同境界 NPC 感知深度不同。
  - 感知结果可缓存，避免重复计算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────
#  NPC PerceptionResult 数据类
# ──────────────────────────────────────────────

@dataclass
class NPCPerceptionResult:
    """NPC 对玩家的感知结果。"""

    npc_name: str = ""
    perception_depth: str = "normal"  # normal / subtle / keen / insightful
    observations: List[str] = field(default_factory=list)
    overall_impression: str = ""
    warning_flags: List[str] = field(default_factory=list)
    relationship_state: str = "unknown"  # B-10: unknown/familiar/friendly/respectful/suspicious/hostile

    def to_dict(self) -> Dict[str, Any]:
        return {
            "npc_name": self.npc_name,
            "perception_depth": self.perception_depth,
            "observations": self.observations,
            "overall_impression": self.overall_impression,
            "warning_flags": self.warning_flags,
            "relationship_state": self.relationship_state,
        }


# ──────────────────────────────────────────────
#  感知等级定义
# ──────────────────────────────────────────────

PERCEPTION_LEVELS = {
    "凡人": {"max_cultivation": 0, "label": "普通"},
    "练气": {"max_cultivation": 10, "label": "低阶"},
    "筑基": {"max_cultivation": 30, "label": "中阶"},
    "金丹": {"max_cultivation": 60, "label": "高阶"},
    "元婴": {"max_cultivation": 90, "label": "顶尖"},
    "化神": {"max_cultivation": 100, "label": "传奇"},
}

# 感知深度标签映射
PERCEPTION_LABELS = {
    "keen": "敏锐",
    "insightful": "洞察",
    "subtle": "细微",
    "normal": "正常",
}


# ──────────────────────────────────────────────
#  NPC 类型与默认感知深度
# ──────────────────────────────────────────────

DEFAULT_NPC_TYPES = {
    "百姓": "凡人",
    "散修": "练气~筑基",
    "外门弟子": "筑基~金丹",
    "内门弟子": "金丹~元婴",
    "长老": "元婴~化神",
    "宗主": "化神",
    "隐士": "金丹~元婴",
    "商人": "凡人~练气",
    "游侠": "筑基~金丹",
}


# ──────────────────────────────────────────────
#  perceive_player()
# ──────────────────────────────────────────────

def perceive_player(
    player_profile: Dict[str, Any],
    npc_info: Dict[str, Any],
    appearance_cache: Optional[Dict[str, Any]] = None,
) -> NPCPerceptionResult:
    """NPC 观察玩家外貌和气息。

    Args:
        player_profile: 玩家档案（包含 CORE_STATE, METHOD_STATE, IDENTITY_STATE 等）
        npc_info: NPC 信息字典，需包含以下键：
            - name: NPC 名称
            - cultivation: NPC 修为境界（字符串或数字）
            - type: NPC 类型（对应 DEFAULT_NPC_TYPES）
        appearance_cache: 可选的外观缓存字典，避免重复生成 PlayerAppearance

    Returns:
        NPCPerceptionResult 对象
    """
    result = NPCPerceptionResult(npc_name=npc_info.get("name", "未知"))

    # 获取玩家修为境界
    player_cultivation = _extract_cultivation_level(player_profile)

    # 确定 NPC 感知深度
    npc_type = npc_info.get("type", "散修")
    npc_cultivation = _extract_cultivation_level(npc_info)
    perception_depth = _determine_perception_depth(npc_cultivation, player_cultivation)
    result.perception_depth = perception_depth

    # 获取玩家外观（优先使用缓存）
    if appearance_cache is None:
        # 尝试从 profile 中读取已保存的外观
        saved = player_profile.get("appearance")
        if saved and isinstance(saved, dict) and saved.get("face"):
            appearance_cache = saved
        else:
            try:
                from .player_appearance import AppearanceGenerator
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from player_appearance import AppearanceGenerator

            gen = AppearanceGenerator()
            pa = gen.generate(
                identity="",
                cultivation_path=player_profile.get("METHOD_STATE", {}).get("primary_path", ""),
                faction="",
                element=player_profile.get("CORE_STATE", {}).get("spirit_root_element", ""),
                gender=player_profile.get("gender", "男"),
            )
            appearance_cache = pa.to_dict()

    appearance = appearance_cache

    # 提取感知内容
    observations = []
    warning_flags = []

    # 基础观察：衣着
    clothing = appearance.get("clothing", {})
    style = clothing.get("style", "")
    origin = clothing.get("origin", "")
    if style:
        observations.append(f"身着{style}")
    if origin:
        observations.append(f"衣着来源：{origin}")

    # 印记观察
    marks = appearance.get("marks", [])
    if marks:
        for mark in marks:
            observations.append(f"发现印记：{mark}")

    # 根据感知深度增加观察
    if perception_depth == "keen":
        # 敏锐：可以看到更多细节
        face = appearance.get("face", {})
        age = face.get("age", "")
        features = face.get("features", [])
        if age:
            observations.append(f"年龄约{age}")
        if features:
            observations.append(f"面部特征：{'、'.join(features)}")

        # 可以感知灵力波动
        method = player_profile.get("METHOD_STATE", {})
        stage = method.get("growth_stage", "")
        if stage:
            observations.append(f"修为阶段：{stage}")

        # LONG-A: 感知修炼状态细节
        progress = method.get("progress", 0)
        if progress >= 100:
            observations.append("此人修为火候已足，似有突破之意")
        foundation = method.get("foundation", 100)
        if foundation < 50:
            observations.append("此人根基不稳，气息虚浮")
        bottleneck = method.get("bottleneck", 0)
        if bottleneck >= 3:
            observations.append("此人似遇修为瓶颈，气息凝滞")

    elif perception_depth == "insightful":
        # 洞察：可以感知气质
        aura = appearance.get("aura", {})
        feeling = aura.get("feeling", "")
        if feeling:
            observations.append(f"气质：{feeling}")

        # LONG-A: 洞察灵根和修炼状态
        core = player_profile.get("CORE_STATE", {})
        sr_data = core.get("spiritual_root")
        if sr_data and isinstance(sr_data, dict):
            mutation = sr_data.get("mutation", "none")
            if mutation != "none":
                observations.append(f"此人灵根有异变之气：{mutation}属")
            purity = sr_data.get("purity", 0.5)
            if purity >= 0.9:
                observations.append("此人灵根极为纯净，天赋异禀")

        # 可能感知到危险信号
        first_imp = appearance.get("first_impression", "")
        if any(word in first_imp.lower() for word in ["危险", "诡异", "邪恶"]):
            warning_flags.append("此人可能心怀恶意")

    elif perception_depth == "subtle":
        # 细微：只能看到模糊印象
        first_imp = appearance.get("first_impression", "")
        if first_imp:
            observations.append(f"整体印象：{first_imp[:30]}...")

    # 综合判断
    if observations:
        result.observations = observations
        result.overall_impression = "、".join(observations[:3])

    if warning_flags:
        result.warning_flags = warning_flags

    return result


# ──────────────────────────────────────────────
#  辅助函数
# ──────────────────────────────────────────────

def _extract_cultivation_level(profile: Dict[str, Any]) -> int:
    """从档案提取修为境界数值。

    支持两种格式：
      - 玩家 profile：METHOD_STATE.spirit_root_tier
      - NPC info：cultivation（直接数值）
    """
    # NPC 格式：直接数值
    if "cultivation" in profile and isinstance(profile["cultivation"], (int, float)):
        return max(0, int(profile["cultivation"]))

    # 玩家 profile 格式
    method = profile.get("METHOD_STATE", {})
    tier = method.get("spirit_root_tier", 1)  # 默认炼气期

    # 如果 tier 是字符串格式（如"一阶"），转换为数值
    if isinstance(tier, str):
        try:
            tier = int(tier.split("阶")[0].strip())
        except (ValueError, IndexError):
            tier = 1

    return max(0, int(tier))


def _determine_perception_depth(
    npc_cultivation: int,
    player_cultivation: int,
) -> str:
    """根据 NPC 和玩家修为差距确定感知深度。

    规则：
      - NPC 远强于玩家（差≥40阶）→ insightful
      - NPC 略强于玩家（差20~39阶）→ keen
      - NPC 与玩家相当（差<20）→ subtle
      - NPC 弱于玩家 → normal（无法看透更弱者的气息）
    """
    diff = player_cultivation - npc_cultivation  # 正数 = 玩家更强

    if diff <= -40:  # NPC 远强于玩家
        return "insightful"
    elif diff <= -20:  # NPC 略强于玩家
        return "keen"
    elif diff < 0:  # NPC 与玩家相当或稍弱
        return "subtle"
    else:
        return "normal"


# ──────────────────────────────────────────────
#  B-9/B-10: 带记忆的 NPC 感知
# ──────────────────────────────────────────────

def observe_player_with_memory(
    player_profile: Dict[str, Any],
    npc_info: Dict[str, Any],
    memories: List[Dict[str, Any]],
) -> NPCPerceptionResult:
    """NPC 基于记忆对玩家产生感知描述（B-10 增强）。

    与 perceive_player 不同，本函数基于 NPC 自身的记忆，
    而非实时外貌观察。NPC 只能看到自己的记忆。

    B-10 增强：
      - 返回 NPCPerceptionResult（包含 relationship_state）
      - relationship_state 由 npc_relationship.calculate_relationship() 计算
      - 特殊记忆触发叙事提示标签

    Args:
        player_profile: 玩家档案
        npc_info: NPC 信息（name, cultivation, type）
        memories: 该 NPC 对该玩家的记忆列表（dict 格式）

    Returns:
        NPCPerceptionResult 对象
    """
    result = NPCPerceptionResult(npc_name=npc_info.get("name", "未知"))

    if not memories:
        result.perception_depth = "normal"
        result.relationship_state = "unknown"
        return result

    # 计算关系状态（B-10）
    try:
        from .npc_relationship import calculate_relationship, detect_special_memories, REL_LABELS, SPECIAL_MEMORY_NARRATIVE
    except ImportError:
        from npc_relationship import calculate_relationship, detect_special_memories, REL_LABELS, SPECIAL_MEMORY_NARRATIVE

    relationship = calculate_relationship(memories)
    result.relationship_state = relationship

    # 按重要性排序，取最重要的记忆
    sorted_mems = sorted(memories, key=lambda m: m.get("importance", 0), reverse=True)
    top_mem = sorted_mems[0]

    emotion = top_mem.get("emotion", "neutral")
    summary = top_mem.get("summary", "")
    memory_type = top_mem.get("memory_type", "encounter")

    # 构建观察描述
    observations = []

    # 关系态度描述
    rel_label = REL_LABELS.get(relationship, "陌生")
    observations.append(f"当前态度：{rel_label}")

    # 根据情绪和记忆类型生成描述
    if emotion == "grateful":
        observations.append(f"此人曾帮助过我：{summary}")
    elif emotion == "hostile":
        if memory_type == "betrayal":
            observations.append(f"此人曾背叛过我：{summary}")
        else:
            observations.append(f"此人曾与我发生冲突：{summary}")
    elif emotion == "afraid":
        observations.append(f"此人让我感到畏惧：{summary}")
    elif emotion == "respectful":
        observations.append(f"此人值得敬重：{summary}")
    else:
        if memory_type == "trade":
            observations.append(f"此人与我有过交涉：{summary}")
        elif memory_type == "major_event":
            observations.append(f"此人曾参与重大事件：{summary}")
        elif memory_type == "rescue":
            observations.append(f"此人曾救过我：{summary}")
        else:
            observations.append(f"此人曾有过交集：{summary}")

    result.observations = observations
    result.overall_impression = observations[-1] if observations else ""

    # 检测特殊记忆触发（B-10）
    special_tags = detect_special_memories(memories)
    for tag in special_tags:
        narrative = SPECIAL_MEMORY_NARRATIVE.get(tag, "")
        if narrative:
            result.warning_flags.append(narrative)

    # 感知深度基于记忆数量
    if len(memories) >= 5:
        result.perception_depth = "insightful"
    elif len(memories) >= 3:
        result.perception_depth = "keen"
    elif len(memories) >= 1:
        result.perception_depth = "subtle"

    return result
