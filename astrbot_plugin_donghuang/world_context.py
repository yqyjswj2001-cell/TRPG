"""
World context builder.

This module is read-only: it summarizes persisted world, player, NPC, event,
and faction state into a prompt-friendly text block for narration.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .asset_loader import read_text as _al_read_text
except ImportError:
    from asset_loader import read_text as _al_read_text


logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 800


class WorldContextBuilder:
    """Build a concise, read-only world context string."""

    def __init__(self, world_dir: Path, max_chars: int = DEFAULT_MAX_CHARS):
        self.world_dir = world_dir
        self.max_chars = max_chars

    def build(
        self,
        world_state: Dict[str, Any],
        player_profiles: Dict[str, Any],
        event_log: List[Dict[str, Any]],
        campaign: Dict[str, Any],
        region: Optional[str] = None,
        slot_id: Optional[str] = None,
        include_economy: bool = False,
        include_combat: bool = False,
        include_death: bool = False,
        news_text: str = "",
        active_events: str = "",
        factions: Optional[Dict[str, Any]] = None,
        action_log: Optional[List[Dict[str, Any]]] = None,
        appearance_first_time: bool = False,
        npc_memory: Optional[Dict[str, Any]] = None,
        npc_action_log: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        sections: List[str] = []

        if not world_state and not campaign:
            return ""

        current_profile = player_profiles.get(slot_id) if slot_id else None
        current_region = region or (
            current_profile or {}
        ).get("IDENTITY_STATE", {}).get("region")

        for section in (
            self._extract_time(world_state, campaign),
            self._extract_location(world_state, player_profiles, current_region, slot_id),
            self._extract_weather(world_state, current_region),
            self._extract_environment(world_state, current_region),
            self._extract_faction_dynamics(
                world_state, current_profile, factions, region=current_region
            ),
            self._extract_nearby_factions(world_state, current_region),
            self._extract_recent_events(event_log),
            self._extract_recent_outcomes(event_log, current_region),
            self._extract_recent_actions(action_log or [], slot_id),
            self._extract_player_status(player_profiles, slot_id),
            self._extract_player_appearance(
                player_profiles, slot_id, full_display=appearance_first_time
            ),
            self._extract_player_memories(npc_memory, slot_id),
            self._extract_nearby_npc_attitudes(npc_memory, slot_id),
            self._extract_npc_action_log(npc_action_log, slot_id),
            self._extract_npc_life_history(campaign.get("world_history", [])),
            self._extract_causal_state(world_state, player_profiles, slot_id),
        ):
            if section:
                sections.append(section)

        if active_events:
            sections.append(active_events)
        if news_text:
            sections.append(news_text)
        if include_economy:
            section = self._load_rule_summary("economy_rules.md")
            if section:
                sections.append(section)
        if include_combat:
            section = self._load_rule_summary("combat_rules.md")
            if section:
                sections.append(section)
        if include_death:
            section = self._load_rule_summary("death_protocol.md")
            if section:
                sections.append(section)

        full_text = "\n\n".join(sections)
        if len(full_text) > self.max_chars:
            full_text = self._trim_by_priority(full_text, sections)
        return full_text

    def _extract_time(self, ws: Dict[str, Any], campaign: Dict[str, Any]) -> str:
        global_state = ws.get("GLOBAL", {})
        cycle = campaign.get("cycle")
        if not global_state and cycle is None:
            return ""

        lines = [
            f"Cycle: {cycle}" if cycle is not None else "Cycle: 未知",
            f"世界阶段: {global_state.get('phase', '未知')}",
            f"灵气流向: {global_state.get('leyline_flow', '未知')}",
            f"CHAOS: {global_state.get('chaos_level', '未知')}",
            f"天道: {global_state.get('tiandao_activity', '未知')}",
        ]
        return "【时间与世界大势】\n" + " | ".join(lines)

    def _extract_location(
        self,
        ws: Dict[str, Any],
        profiles: Dict[str, Any],
        region: Optional[str],
        slot_id: Optional[str],
    ) -> str:
        lines: List[str] = []

        if slot_id and slot_id in profiles:
            identity = profiles[slot_id].get("IDENTITY_STATE", {})
            reg = identity.get("region", region or "未知")
            sub = identity.get("subregion")
            pos = identity.get("position")
            location = reg
            if sub:
                location += f" / {sub}"
            if pos:
                location += f" / {pos}"
            lines.append(f"所在: {location}")

        if region:
            region_state = ws.get("REGION", {}).get(region, {})
            if region_state:
                if region_state.get("phase"):
                    lines.append(f"区域阶段: {region_state['phase']}")
                if region_state.get("leyline_state"):
                    lines.append(f"灵脉: {region_state['leyline_state']}")
                if region_state.get("spirit_density"):
                    lines.append(f"灵气: {region_state['spirit_density']}")

        if not lines:
            return ""
        return "【地点与区域状态】\n" + " | ".join(lines)

    def _extract_weather(self, ws: Dict[str, Any], region: Optional[str]) -> str:
        if not region:
            return ""
        weather = ws.get("REGION", {}).get(region, {}).get("weather")
        if not weather:
            return ""
        return f"【天气】{weather}"

    def _extract_environment(self, ws: Dict[str, Any], region: Optional[str]) -> str:
        if not region:
            return ""
        env = ws.get("REGION", {}).get(region, {}).get("environment")
        if not isinstance(env, dict):
            return ""

        lines = ["【当前环境】"]
        if env.get("physical_weather"):
            lines.append(f"普通天气：{env['physical_weather']}")
        if env.get("spiritual_weather") and env.get("spiritual_weather") != "稳定":
            lines.append(f"灵气状态：{env['spiritual_weather']}")
        if env.get("celestial_phenomenon") and env.get("celestial_phenomenon") != "无":
            lines.append(f"特殊天象：{env['celestial_phenomenon']}")
        if env.get("anomaly_environment") and env.get("anomaly_environment") != "无":
            lines.append(f"异常环境：{env['anomaly_environment']}")

        effects = env.get("effects") or []
        if effects:
            lines.append("主要影响：" + "、".join(str(effect) for effect in effects[:4]))

        return "\n".join(lines) if len(lines) > 1 else ""

    def _extract_nearby_factions(self, ws: Dict[str, Any], region: Optional[str]) -> str:
        if not region:
            return ""
        factions = ws.get("REGION", {}).get(region, {}).get("factions", [])
        if not factions:
            return ""

        bits = []
        for fac in factions[:3]:
            name = fac.get("name", fac.get("code", "未知势力"))
            status = fac.get("status")
            goal = fac.get("current_goal")
            bit = name
            if status:
                bit += f"({status})"
            if goal:
                bit += f" -> {goal}"
            bits.append(bit)
        return "【附近势力】" + " | ".join(bits)

    def _extract_recent_events(self, event_log: List[Dict[str, Any]]) -> str:
        if not event_log:
            return ""
        lines = ["【近期事件】"]
        for event in event_log[-3:]:
            event_id = event.get("event_id", event.get("id", ""))
            title = event.get("title", event.get("type", event.get("category", "未知事件")))
            lines.append(f"- [{event_id}] {title}".rstrip())
        return "\n".join(lines)

    def _extract_recent_outcomes(
        self, event_log: List[Dict[str, Any]], region: Optional[str] = None
    ) -> str:
        outcomes = []
        for event in event_log:
            outcome = event.get("outcome")
            if isinstance(outcome, dict) and outcome.get("summary"):
                outcomes.append((event.get("region"), outcome["summary"]))

        if not outcomes:
            return ""

        if region:
            outcomes.sort(key=lambda item: 0 if item[0] == region else 1)

        lines = ["【近期事件后果】"]
        for _, summary in outcomes[-5:]:
            lines.append(f"- {summary}")
        return "\n".join(lines)

    def _extract_recent_actions(
        self, action_log: List[Dict[str, Any]], slot_id: Optional[str] = None
    ) -> str:
        if not action_log:
            return ""

        chosen = action_log
        if slot_id:
            mine = [
                entry
                for entry in action_log
                if entry.get("action", {}).get("player_id") == slot_id
            ]
            if mine:
                chosen = mine

        lines = []
        for entry in chosen[-5:]:
            summary = entry.get("outcome", {}).get("summary")
            if summary:
                lines.append(f"- {summary}")

        if not lines:
            return ""
        return "【近期玩家行动】\n" + "\n".join(lines)

    def _extract_player_status(
        self, profiles: Dict[str, Any], slot_id: Optional[str]
    ) -> str:
        if not slot_id or slot_id not in profiles:
            return ""
        profile = profiles[slot_id]

        lines = []
        base = profile.get("BASE_STATE", {})
        identity = profile.get("IDENTITY_STATE", {})
        method = profile.get("METHOD_STATE", {})
        core = profile.get("CORE_STATE", {})
        hp = profile.get("hp", {})
        mp = profile.get("mp", {})

        if identity.get("survival_status"):
            lines.append(f"生存状态：{identity['survival_status']}")
        if hp:
            lines.append(f"气血：{hp.get('current', '?')}/{hp.get('max', '?')}")
        if mp:
            lines.append(f"灵力：{mp.get('current', '?')}/{mp.get('max', '?')}")
        if base.get("realm"):
            lines.append(f"境界：{base['realm']}")
        elif profile.get("cultivation_realm"):
            lines.append(f"境界：{profile['cultivation_realm']}")
        if method.get("cultivation_path"):
            lines.append(f"道途：{method['cultivation_path']}")
        elif method.get("primary_path"):
            lines.append(f"道途：{method['primary_path']}")

        # LONG-A: 修炼状态详情
        progress = method.get("progress", 0)
        if progress > 0 or method.get("growth_stage"):
            stage = method.get("growth_stage", "")
            progress_text = f"进度{progress}/100"
            if progress >= 100:
                progress_text += "（可突破）"
            parts = []
            if stage:
                parts.append(f"阶段：{stage}")
            parts.append(progress_text)
            foundation = method.get("foundation")
            if foundation is not None:
                parts.append(f"根基：{foundation}/200")
            bottleneck = method.get("bottleneck", 0)
            if bottleneck > 0:
                parts.append(f"瓶颈：{'×' * bottleneck}")
            lines.append(" | ".join(parts))

        # LONG-A: 灵根信息
        sr_data = core.get("spiritual_root")
        if sr_data and isinstance(sr_data, dict):
            primary = sr_data.get("primary", "")
            purity = sr_data.get("purity", 0)
            mutation = sr_data.get("mutation", "none")
            eff = sr_data.get("efficiency", 1.0)
            sr_text = f"灵根：{primary}行（纯度{purity:.0%}，效率×{eff:.1f}）"
            if mutation != "none":
                sr_text += f" 异变：{mutation}"
            lines.append(sr_text)
        elif core.get("spirit_root_element"):
            lines.append(f"灵根：{core['spirit_root_element']}")

        if not lines:
            return ""
        return "【玩家状态】\n" + " | ".join(lines)

    def _extract_player_appearance(
        self,
        profiles: Dict[str, Any],
        slot_id: Optional[str],
        full_display: bool = False,
    ) -> str:
        if not slot_id or slot_id not in profiles:
            return ""
        appearance = profiles[slot_id].get("appearance")
        if not isinstance(appearance, dict) or not appearance:
            return ""

        lines = ["【玩家外貌】"]
        if full_display:
            face = appearance.get("face") or {}
            if isinstance(face, dict) and (face.get("age") or face.get("features") or face.get("expression")):
                parts = [p for p in [
                    face.get("age", ""),
                    "、".join(face.get("features") or []),
                    face.get("expression", ""),
                ] if p]
                if parts:
                    lines.append(f"外貌：{'，'.join(parts)}")

            clothing = appearance.get("clothing") or {}
            if isinstance(clothing, dict) and clothing.get("style"):
                origin = clothing.get("origin", "")
                lines.append(f"衣着：{clothing['style']}" + (f"（{origin}）" if origin else ""))

            aura = appearance.get("aura") or {}
            if isinstance(aura, dict) and aura.get("feeling"):
                lines.append(f"气质：{aura['feeling']}")

            hair = appearance.get("hair") or {}
            if isinstance(hair, dict) and (hair.get("color") or hair.get("style")):
                lines.append(f"发型：{hair.get('color', '')}{hair.get('style', '')}")

            eyes = appearance.get("eyes") or {}
            if isinstance(eyes, dict) and eyes.get("color"):
                special = eyes.get("special", "")
                lines.append(f"双眸：{eyes['color']}" + (f"，{special}" if special else ""))

            marks = appearance.get("marks") or []
            if marks:
                lines.append(f"印记：{'、'.join(marks)}")

            if len(lines) == 1 and appearance.get("first_impression"):
                lines.append(f"外貌印象：{appearance['first_impression']}")
        else:
            if appearance.get("first_impression"):
                lines.append(f"外貌印象：{appearance['first_impression']}")
            else:
                face = appearance.get("face") or {}
                clothing = appearance.get("clothing") or {}
                if isinstance(face, dict) and face.get("expression"):
                    lines.append(f"外貌：{face['expression']}")
                elif isinstance(clothing, dict) and clothing.get("style"):
                    lines.append(f"衣着：{clothing['style']}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def _extract_player_memories(
        self, npc_memory: Optional[Dict[str, Any]], slot_id: Optional[str]
    ) -> str:
        if not npc_memory or not slot_id:
            return ""

        relevant = []
        for npc_id, memories in npc_memory.items():
            if not isinstance(memories, list):
                continue
            for memory in memories:
                if memory.get("player_id") != slot_id:
                    continue
                if memory.get("importance", 0) < 40:
                    continue
                relevant.append(
                    (
                        memory.get("importance", 0),
                        memory.get("cycle", 0),
                        npc_id,
                        memory.get("summary", ""),
                    )
                )

        if not relevant:
            return ""

        relevant.sort(key=lambda item: (item[0], item[1]), reverse=True)
        lines = ["【人物关系记忆】"]
        for _, cycle, npc_id, summary in relevant[:5]:
            lines.append(f"- Cycle {cycle}｜{npc_id}：{summary}")
        return "\n".join(lines)

    def _extract_nearby_npc_attitudes(
        self, npc_memory: Optional[Dict[str, Any]], slot_id: Optional[str]
    ) -> str:
        if not npc_memory or not slot_id:
            return ""

        profiles = []
        for npc_id, memories in npc_memory.items():
            if not isinstance(memories, list):
                continue
            mine = [m for m in memories if m.get("player_id") == slot_id]
            if not mine:
                continue

            trust = sum(m.get("trust_change", 0) for m in mine)
            importance = sum(m.get("importance", 0) for m in mine)
            if trust >= 15:
                relation = "友善"
                desc = "愿意提供帮助"
            elif trust <= -10:
                relation = "敌视"
                desc = "不太愿意合作"
            else:
                relation = "中立"
                desc = "态度观望"
            profiles.append((importance, npc_id, relation, desc))

        if not profiles:
            return ""

        profiles.sort(reverse=True)
        lines = ["【附近重要NPC态度】"]
        for _, npc_id, relation, desc in profiles[:3]:
            lines.append(f"{npc_id}：与你关系{relation}，{desc}。")
        return "\n".join(lines)

    def _extract_npc_action_log(
        self,
        npc_action_log: Optional[List[Dict[str, Any]]],
        slot_id: Optional[str],
    ) -> str:
        if not npc_action_log:
            return ""

        relevant = []
        for entry in npc_action_log:
            if not isinstance(entry, dict):
                continue
            if entry.get("consumed", False):
                continue
            if slot_id and entry.get("player_id") not in (None, slot_id):
                continue
            relevant.append(entry)

        if not relevant:
            return ""

        lines = []
        for entry in relevant[-3:]:
            hint = entry.get("hint")
            if hint:
                lines.append(f"- {hint}")

        if not lines:
            return ""
        return "【近期人物动向】\n" + "\n".join(lines)

    def _extract_npc_life_history(
        self, world_history: Optional[List[Dict[str, Any]]]
    ) -> str:
        """提取最近的 NPC 生命周期变化（【近期NPC命运】）。

        只读取已落库的 world_history 事实（npc_life_changed 记录），
        不做任何推测或剧情生成，最多展示最近 3 条。
        """
        if not world_history:
            return ""

        blocks = []
        for entry in world_history:
            if not isinstance(entry, dict):
                continue
            if entry.get("entry_type") != "npc_life_changed":
                continue
            summary = entry.get("summary", "").strip()
            if not summary:
                continue
            npc_id = entry.get("npc_id", "未知人物")
            label_parts = [
                str(entry.get("region", "") or ""),
                str(entry.get("identity", "") or ""),
                str(npc_id),
            ]
            label = "".join(part for part in label_parts if part)
            blocks.append(f"{label}：\n{summary}")

        if not blocks:
            return ""
        return "【近期NPC命运】\n" + "\n\n".join(blocks[-3:])

    def _extract_causal_state(
        self,
        ws: Dict[str, Any],
        profiles: Dict[str, Any],
        slot_id: Optional[str],
    ) -> str:
        if not slot_id or slot_id not in profiles:
            return ""
        causal = profiles[slot_id].get("CAUSAL_STATE", {})

        lines = []
        bound = causal.get("bound_causality", [])
        untriggered = causal.get("untriggered", [])

        if bound:
            lines.append(
                "已绑定因果: " + ", ".join(item.get("source", item.get("name", "")) for item in bound[:2])
            )
        if untriggered:
            lines.append(
                "未兑现因果债: "
                + ", ".join(item.get("source", item.get("name", "")) for item in untriggered[:2])
            )

        if not lines:
            return ""
        return "【因果状态】\n" + " | ".join(lines)

    @staticmethod
    def _resolve_faction_name(code: str, factions: Optional[Dict[str, Any]]) -> str:
        if factions and code in factions:
            return factions[code].get("name", code)
        return code

    @staticmethod
    def _resolve_faction_type(code: str, factions: Optional[Dict[str, Any]]) -> str:
        if factions and code in factions:
            return factions[code].get("type", "")
        return ""

    def _extract_faction_dynamics(
        self,
        ws: Dict[str, Any],
        profile: Optional[Dict] = None,
        factions: Optional[Dict[str, Any]] = None,
        region: Optional[str] = None,
    ) -> str:
        if not ws:
            return ""

        sections = []
        for section in (
            self._extract_affiliation_summary(ws, profile, factions=factions),
            self._extract_local_faction_dynamics(ws, profile, region=region, factions=factions),
            self._extract_stance_changes(ws, factions=factions),
            self._extract_decline_rise_hints(ws, factions=factions),
        ):
            if section:
                sections.append(section)

        if not sections:
            return ""
        result = "【势力动态】\n" + "\n".join(sections)
        if len(result) > self.max_chars:
            kept = []
            for section in sections:
                if section.startswith("【所属势力：") or section.startswith("【本地势力动态】"):
                    kept.append(section)
            result = "【势力动态】\n" + "\n".join(kept or sections[:1])
        return result

    def _extract_affiliation_summary(
        self,
        ws: Dict[str, Any],
        profile: Optional[Dict] = None,
        factions: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not profile:
            return ""
        affiliation = profile.get("FACTION_STATE", {}).get("affiliation")
        if not affiliation:
            return ""

        entry = ws.get("FACTION_STATE", {}).get(affiliation, {})
        if not isinstance(entry, dict):
            return ""

        name = self._resolve_faction_name(affiliation, factions)
        fac_type = self._resolve_faction_type(affiliation, factions)
        return (
            f"【所属势力：{name}｜{fac_type}】\n"
            f"势力当前目标：{entry.get('active_goal', '维持现状')}\n"
            f"势力状态：稳定度 {entry.get('stability', 0.5)}，士气 {entry.get('morale', 0.7)}"
        )

    def _extract_local_faction_dynamics(
        self,
        ws: Dict[str, Any],
        profile: Optional[Dict],
        region: Optional[str],
        factions: Optional[Dict[str, Any]],
    ) -> str:
        if not region or not factions:
            return ""

        entries = ws.get("FACTION_STATE", {})
        affiliation = None
        if profile:
            affiliation = profile.get("FACTION_STATE", {}).get("affiliation")

        candidates = []
        for code, faction in factions.items():
            if faction.get("region") != region:
                continue
            entry = entries.get(code, {})
            if not isinstance(entry, dict):
                continue
            candidates.append(
                {
                    "code": code,
                    "name": faction.get("name", code),
                    "type": faction.get("type", ""),
                    "power": entry.get("power", 0),
                    "stability": entry.get("stability", 0.5),
                    "goal": entry.get("active_goal", "维持现状"),
                    "is_player": code == affiliation,
                }
            )

        candidates.sort(
            key=lambda item: (
                0 if item["is_player"] else 1,
                -item["power"],
                item["stability"],
            )
        )

        if not candidates:
            return ""

        lines = ["【本地势力动态】"]
        for item in candidates[:3]:
            lines.append(
                f"- {item['name']}：{item['type']}，power {item['power']}，目标 {item['goal']}"
            )
        return "\n".join(lines)

    def _extract_stance_changes(
        self, ws: Dict[str, Any], factions: Optional[Dict[str, Any]] = None
    ) -> str:
        if not factions:
            return ""

        changes = []
        for code, entry in ws.get("FACTION_STATE", {}).items():
            overrides = entry.get("stance_overrides", {})
            if not isinstance(overrides, dict) or not overrides:
                continue
            relations = factions.get(code, {}).get("relations", [])
            defaults = {item.get("code"): item.get("stance", "中立") for item in relations}
            for target_code, current in overrides.items():
                default = defaults.get(target_code)
                if default is None or current == default:
                    continue
                target_name = factions.get(target_code, {}).get("name", target_code)
                changes.append(f"- {code} 对 {target_name}：{default} -> {current}")
                if len(changes) >= 5:
                    break
            if len(changes) >= 5:
                break

        if not changes:
            return ""
        return "【势力关系变化】\n" + "\n".join(changes)

    def _extract_decline_rise_hints(
        self, ws: Dict[str, Any], factions: Optional[Dict[str, Any]] = None
    ) -> str:
        if not factions:
            return ""

        hints = []
        for code, entry in ws.get("FACTION_STATE", {}).items():
            if not isinstance(entry, dict):
                continue
            power = entry.get("power", 0)
            stability = entry.get("stability", 0.5)
            name = factions.get(code, {}).get("name", code)

            if power <= 30 or stability <= 0.3:
                hints.append(f"- {name} 正处于衰退或动荡中")
            elif power >= 80 and stability >= 0.7:
                hints.append(f"- {name} 正处于强盛或扩张状态")

            if len(hints) >= 5:
                break

        if not hints:
            return ""
        return "【势力衰退/崛起提示】\n" + "\n".join(hints)

    def _load_rule_summary(self, filename: str) -> str:
        path = self.world_dir / filename
        text = _al_read_text(path)
        if not text:
            return ""

        limit = max(self.max_chars // 4, 200)
        if len(text) > limit:
            text = text[: limit - 3] + "..."
        return f"【规则摘要：{filename}】\n{text}"

    def _trim_by_priority(self, full_text: str, sections: List[str]) -> str:
        priorities = {
            "【规则摘要：": 1,
            "【因果状态】": 2,
            "【近期事件后果】": 2.5,
            "【近期玩家行动】": 2.8,
            "【附近势力】": 3,
            "【势力关系变化】": 3.5,
            "【势力衰退/崛起提示】": 3.6,
            "【本地势力动态】": 4.5,
            "【天气】": 5,
            "【所属势力：": 5.5,
            "【当前环境】": 5.8,
            "【近期事件】": 6,
            "【玩家外貌】": 6.5,
            "【人物关系记忆】": 6.8,
            "【近期人物动向】": 6.9,
            "【近期NPC命运】": 7.0,
            "【附近重要NPC态度】": 7.2,
            "【玩家状态】": 7.5,
            "【地点与区域状态】": 8,
            "【时间与世界大势】": 9,
        }

        def priority(section: str) -> float:
            for label, value in priorities.items():
                if section.startswith(label):
                    return value
            return 3

        kept = list(sections)
        while kept and len("\n\n".join(kept)) > self.max_chars:
            removable = [section for section in kept if priority(section) < 8]
            if not removable:
                break
            lowest = min(removable, key=priority)
            kept.remove(lowest)
        return "\n\n".join(kept)
