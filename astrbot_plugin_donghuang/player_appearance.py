"""
player_appearance.py — 玩家角色外观数据模型与生成器（B-8）

核心概念：
  PlayerAppearance = 角色的外貌、衣着、气质、印记等稳定档案。
  AppearanceGenerator = 基于身份/修为/势力生成外观（不调用 LLM）。

设计原则：
  - 同一角色生成一次后固定，不每次重新随机。
  - 必须可序列化、可持久化、可回滚。
  - AI 只负责叙事描述，不保存角色事实。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
#  PlayerAppearance 数据类
# ──────────────────────────────────────────────

@dataclass
class PlayerAppearance:
    """角色外观数据。生成后固定不变，除非通过 appearance_modifier 修改。"""

    face: Dict[str, Any] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)
    hair: Dict[str, Any] = field(default_factory=dict)
    eyes: Dict[str, Any] = field(default_factory=dict)
    clothing: Dict[str, Any] = field(default_factory=dict)
    aura: Dict[str, Any] = field(default_factory=dict)
    marks: List[str] = field(default_factory=list)
    first_impression: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face": dict(self.face),
            "body": dict(self.body),
            "hair": dict(self.hair),
            "eyes": dict(self.eyes),
            "clothing": dict(self.clothing),
            "aura": dict(self.aura),
            "marks": list(self.marks),
            "first_impression": self.first_impression,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlayerAppearance":
        return cls(
            face=d.get("face", {}),
            body=d.get("body", {}),
            hair=d.get("hair", {}),
            eyes=d.get("eyes", {}),
            clothing=d.get("clothing", {}),
            aura=d.get("aura", {}),
            marks=d.get("marks", []),
            first_impression=d.get("first_impression", ""),
        )

    def format_brief(self) -> str:
        """格式化为简短外貌描述，供 AI Prompt 使用。"""
        parts = []
        age = self.face.get("age", "")
        features = self.face.get("features", [])
        expression = self.face.get("expression", "")

        if age:
            parts.append(age)
        if features:
            parts.append("，".join(features))
        if expression:
            parts.append(f"神情{expression}")

        clothing_style = self.clothing.get("style", "")
        if clothing_style:
            parts.append(f"身穿{clothing_style}")

        aura_feeling = self.aura.get("feeling", "")
        if aura_feeling:
            parts.append(f"气质{aura_feeling}")

        if self.marks:
            parts.append("印记：" + "、".join(self.marks))

        if self.first_impression:
            parts.append(f"第一印象：{self.first_impression}")

        return "。".join(p for p in parts if p)

    def format_short(self) -> str:
        """格式化为极短外貌印象，用于后续压缩展示。"""
        if self.first_impression:
            return self.first_impression
        age = self.face.get("age", "")
        aura = self.aura.get("feeling", "")
        if age and aura:
            return f"{age}，气质{aura}"
        if age:
            return age
        return ""


# ──────────────────────────────────────────────
#  外观生成器模板池
# ──────────────────────────────────────────────

# 年龄模板（按性别）
_AGE_TEMPLATES = {
    "男": ["十六七岁的少年", "二十余岁的青年", "三十余岁的男子", "四十余岁的中年人", "年过半百的老者"],
    "女": ["十六七岁的少女", "二十余岁的女子", "三十余岁的妇人", "四十余岁的女子", "年过半百的老妪"],
}

# 身高模板
_HEIGHT_TEMPLATES = {
    "男": ["身量修长", "中等身材", "身材魁梧", "清瘦高挑"],
    "女": ["身量纤细", "中等身材", "身姿窈窕", "清瘦灵动"],
}

# 体型模板
_BUILD_TEMPLATES = ["体态匀称", "身形清瘦", "体格结实", "身形瘦削"]

# 发色模板
_HAIR_COLORS = ["黑", "青黑", "墨色", "灰白", "银白", "深棕"]

# 发型模板（按修为路径）
_HAIR_STYLES = {
    "剑修": ["长发束冠", "高马尾", "短发利落", "束发整齐"],
    "医修": ["简单挽髻", "长发披肩", "发簪别髻"],
    "阵修": ["散发", "束带扎发", "发冠正装"],
    "魔修": ["散发披面", "乱发束带", "半束半散"],
    "default": ["长发束冠", "简单挽髻", "束发整齐", "散发"],
}

# 瞳色模板
_EYE_COLORS = ["深黑", "漆黑", "深褐", "浅灰", "墨绿"]

# 瞳色特效（按灵根元素）
_EYE_SPECIAL = {
    "金": "瞳中隐现金色微光",
    "木": "瞳色略带翠意",
    "水": "瞳色深沉如渊",
    "火": "瞳中似有火光闪烁",
    "土": "瞳色沉稳厚重",
    "": "",
}

# 衣着风格（按修为路径）
_CLOTHING_STYLES = {
    "剑修": ["青色剑修袍", "素白剑衣", "玄色窄袖剑装", "灰蓝剑袍"],
    "医修": ["药绿色长袍", "米白素衣", "淡青药修衫", "赭色采药服"],
    "阵修": ["靛蓝阵袍", "灰色法衣", "墨色阵纹长袍"],
    "魔修": ["暗红黑袍", "深紫长衣", "漆黑窄袍", "血色暗纹衣"],
    "default": ["灰色素袍", "青色布衣", "褐色短衫", "白色道袍"],
}

# 衣着来源（按势力）
_CLOTHING_ORIGIN = {
    "王朝": "官制裁衣", "宗门": "宗门制式", "散修网络": "自备简服", "隐秘组织": "来源不明",
    "": "自备简服",
}

# 气质感受（按修为路径）
_AURA_FEELINGS = {
    "剑修": ["锋锐克制", "冷峻内敛", "凌厉沉稳", "锐利如剑"],
    "医修": ["温和宁静", "沉稳从容", "慈悲柔善", "药香缭绕"],
    "阵修": ["深沉内敛", "玄奥莫测", "从容淡泊"],
    "魔修": ["危险诡谲", "阴沉压抑", "危险气息", "诡谲难测"],
    "default": ["平和淡定", "沉稳内敛", "不怒自威", "普通"],
}

# 脸部特征
_FACE_FEATURES_MALE = ["眉目冷峻", "面容清秀", "五官刚毅", "面庞棱角分明", "面容平凡"]
_FACE_FEATURES_FEMALE = ["眉目如画", "面容清丽", "五官柔和", "容貌端秀", "面容平凡"]

# 表情
_EXPRESSIONS = ["冷静", "淡然", "温和", "肃穆", "沉静"]

# 印记模板
_MARKS_TEMPLATES = {
    "剑修": ["左肩一道旧剑伤", "右手虎口剑茧", "颈侧细长疤痕"],
    "医修": ["指尖常年药渍", "左手腕药痕", "手背烫伤痕迹"],
    "阵修": ["掌心阵纹烙印", "额角细小阵痕"],
    "魔修": ["左臂暗纹", "眼角诡异纹路", "胸口封印痕迹"],
    "default": [],
}

# 第一印象
_FIRST_IMPRESSIONS = {
    "剑修": ["像一柄尚未出鞘的剑", "仿佛随时会拔剑而起", "锋芒内敛，不出手则已"],
    "医修": ["像一株安静的药草", "让人忍不住想靠近", "目光温润如泉水"],
    "阵修": ["像一道未解的谜题", "气息深沉难以捉摸", "仿佛身周有看不见的纹路"],
    "魔修": ["像一团危险的暗雾", "让人本能想远离", "目光阴沉如深渊"],
    "default": ["看起来平平无奇", "不引人注目", "平凡中带着些许不寻常"],
}


# ──────────────────────────────────────────────
#  AppearanceGenerator
# ──────────────────────────────────────────────

class AppearanceGenerator:
    """角色外观生成器。

    不调用 LLM，使用模板池 + 身份权重 + 随机组合。
    同一种子生成相同结果（通过固定 random seed）。
    """

    def generate(
        self,
        identity: str = "",
        cultivation_path: str = "",
        faction: str = "",
        element: str = "",
        gender: str = "男",
        seed: Optional[int] = None,
    ) -> PlayerAppearance:
        """生成角色外观。

        Args:
            identity: 身份文本（如"剑修"）
            cultivation_path: 修为路径（剑修/医修/阵修/魔修等）
            faction: 所属势力 code（如"STATE-01"）
            element: 灵根元素（金/木/水/火/土）
            gender: 性别（男/女）
            seed: 随机种子（可选，用于确定性生成）

        Returns:
            PlayerAppearance 对象
        """
        if seed is not None:
            rng = random.Random(seed)
        else:
            rng = random.Random()

        # 确定修为路径（优先用 cultivation_path，其次从 identity 推断）
        path = cultivation_path or self._infer_path(identity)
        path_key = path if path in _CLOTHING_STYLES else "default"

        # 生成各字段
        appearance = PlayerAppearance(
            face=self._generate_face(rng, gender, path_key),
            body=self._generate_body(rng, gender),
            hair=self._generate_hair(rng, path_key),
            eyes=self._generate_eyes(rng, element),
            clothing=self._generate_clothing(rng, path_key, faction),
            aura=self._generate_aura(rng, path_key, element),
            marks=self._generate_marks(rng, path_key),
            first_impression=rng.choice(
                _FIRST_IMPRESSIONS.get(path_key, _FIRST_IMPRESSIONS["default"])
            ),
        )

        return appearance

    def _infer_path(self, identity: str) -> str:
        """从身份文本推断修为路径。"""
        identity_lower = identity.lower() if identity else ""
        for path in ["剑修", "医修", "阵修", "魔修"]:
            if path in identity:
                return path
        return "default"

    def _generate_face(self, rng: random.Random, gender: str, path_key: str) -> Dict:
        age_pool = _AGE_TEMPLATES.get(gender, _AGE_TEMPLATES["男"])
        feature_pool = _FACE_FEATURES_MALE if gender != "女" else _FACE_FEATURES_FEMALE
        return {
            "age": rng.choice(age_pool),
            "features": rng.sample(feature_pool, min(2, len(feature_pool))),
            "expression": rng.choice(_EXPRESSIONS),
        }

    def _generate_body(self, rng: random.Random, gender: str) -> Dict:
        height_pool = _HEIGHT_TEMPLATES.get(gender, _HEIGHT_TEMPLATES["男"])
        return {
            "height": rng.choice(height_pool),
            "build": rng.choice(_BUILD_TEMPLATES),
            "presence": "",
        }

    def _generate_hair(self, rng: random.Random, path_key: str) -> Dict:
        style_pool = _HAIR_STYLES.get(path_key, _HAIR_STYLES["default"])
        return {
            "color": rng.choice(_HAIR_COLORS),
            "style": rng.choice(style_pool),
        }

    def _generate_eyes(self, rng: random.Random, element: str) -> Dict:
        special = _EYE_SPECIAL.get(element, "")
        return {
            "color": rng.choice(_EYE_COLORS),
            "special": special,
        }

    def _generate_clothing(self, rng: random.Random, path_key: str, faction: str) -> Dict:
        style_pool = _CLOTHING_STYLES.get(path_key, _CLOTHING_STYLES["default"])
        # 推断势力类型
        fac_type = ""
        if faction:
            # 从 faction code 推断类型前缀
            for prefix, fac_type_val in [("STATE", "王朝"), ("CULT", "宗门"), ("FREE", "散修网络"), ("HIDDEN", "隐秘组织")]:
                if faction.startswith(prefix):
                    fac_type = fac_type_val
                    break
        origin = _CLOTHING_ORIGIN.get(fac_type, _CLOTHING_ORIGIN[""])
        return {
            "style": rng.choice(style_pool),
            "origin": origin,
        }

    def _generate_aura(self, rng: random.Random, path_key: str, element: str) -> Dict:
        feeling_pool = _AURA_FEELINGS.get(path_key, _AURA_FEELINGS["default"])
        return {
            "element": element,
            "feeling": rng.choice(feeling_pool),
        }

    def _generate_marks(self, rng: random.Random, path_key: str) -> List[str]:
        marks_pool = _MARKS_TEMPLATES.get(path_key, [])
        if not marks_pool:
            return []
        # 30% 概率有一个印记
        if rng.random() < 0.3:
            return [rng.choice(marks_pool)]
        return []
