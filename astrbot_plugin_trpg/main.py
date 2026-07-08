# -*- coding: utf-8 -*-
"""
astrbot_plugin_trpg —— QQ 群跑团（TRPG）助手插件

功能一览（所有指令都要加上机器人的唤醒前缀，默认是 / ）：
  /r 2d6+3        掷骰子（也可以用 /roll）
  /pc new 名字    创建角色卡
  /pc show        查看自己的角色卡（后面加 QQ号 可以看别人的）
  /pc set 力量 14 修改自己角色卡的属性（团长可在最后加 QQ号 改别人的）
  /pc del         删除自己的角色卡
  /gm add QQ号    任命团长（只有 AstrBot 管理员或现有团长能用）
  /gm del QQ号    撤销团长
  /gm list        查看本群团长名单
  /npc 描述       让 AI 生成一段 NPC / 场景叙事
  /trpg           显示帮助
  /trpg on        （仅团长/管理员）开启本群 TRPG 模式
  /trpg off       （仅团长/管理员）关闭本群 TRPG 模式
  /trpg invite QQ号...  （仅团长/管理员）邀请玩家加入本团，走建卡向导
  /trpg start     （仅团长/管理员）正式开始跑团
  /trpg end       （仅团长/管理员）结束本团，重置邀请/建卡状态

TRPG 模式（可选，默认关闭）：
  某个群开启后，该群里的指令可以不带唤醒前缀“/”，也可以用数字“1”代替“/”，
  例如 "r 1d20"、"1r 1d20"、"pc show" 都能用，跟 "/r 1d20" 效果一样。
  这是为了方便高频跑团场景连续发指令；开着的时候要注意别在聊天里凑巧打出
  以 r/roll/pc/gm/npc/trpg 开头的整句话，否则可能被误判成指令。

引导建团流程（可选）：
  团长 /trpg invite 邀请玩家后，每位玩家在群里回复 1（完全随机建卡）或
  2（引导式建卡，逐项询问属性）。全部或部分玩家建完卡后，团长发
  /trpg start 正式开始。开始后，受邀玩家说的每句话都会被 AI 判断一次是
  游戏内行动还是场外聊天，游戏内的话会自动接一段 AI 叙事。

数据都保存在 AstrBot 的 data/plugin_data/astrbot_plugin_trpg/ 目录下：
  characters.json   所有群的角色卡（按 群号 -> QQ号 两层存放）
  gm.json           每个群的团长名单
  mode.json         每个群是否开启了 TRPG 模式
  sessions.json     每个群当前的邀请/建卡/开团进度
  logs/群号/日期.log 团务日志，纯文本，可直接用记事本打开
"""

import json
import os
import random
import re
import datetime
from pathlib import Path

# ===== AstrBot 官方插件接口（不要改这几行）=====
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# StarTools 是较新版本 AstrBot 提供的工具，用来拿到插件专属的数据目录。
# 老版本没有它，所以用 try 包一下：拿不到就退回到手动拼路径。
try:
    from astrbot.api.star import StarTools
except ImportError:
    StarTools = None

# 插件名（必须和文件夹名、metadata.yaml 里的 name 一致）
PLUGIN_NAME = "astrbot_plugin_trpg"

# 骰子表达式的“正则表达式”：匹配 1d20、2d6+3、d100、3d8-1 这类写法
#   第1组 = 骰子个数（可省略，省略算1个）
#   第2组 = 骰子面数
#   第3组 = 结尾的 +3 / -1 修正值（可省略）
DICE_RE = re.compile(r"^(\d*)[dD](\d+)([+\-]\d+)?$")

# 防止有人恶意刷 /r 99999d99999 把机器人卡死，做个上限
MAX_DICE = 100     # 一次最多掷 100 个骰子
MAX_SIDES = 1000   # 骰子最多 1000 面

# TRPG 模式下，无前缀 / "1"前缀 指令识别的关键词表
# 只有整段文字第一个词精确等于这些词之一，才会被当成指令处理，
# 避免把普通聊天误判成指令。
RAW_KEYWORDS = {"r", "roll", "pc", "gm", "npc", "trpg"}

# 交给 AI 的“人设”说明，让它专心当跑团叙事助手
NPC_SYSTEM_PROMPT = (
    "你是一名桌面跑团（TRPG）游戏主持人的叙事助手。"
    "请根据用户给出的描述，用中文生成一段生动的 NPC 描写或场景叙事。"
    "要求：150~250字，有画面感，直接输出叙事正文，"
    "不要任何解释、开场白或列表。"
)

# 引导建团时，随机/引导两种建卡方式共用的属性模板（COC 风格六项属性）
ATTR_TEMPLATE = ["力量", "敏捷", "智力", "体质", "魅力", "运气"]

# 开团后（/trpg start 之后），判断玩家发言是“游戏内”还是“游戏外”用的提示词。
# 要求模型第一行只回答 IN_GAME 或 OUT_OF_GAME，方便代码解析；
# 解析失败或明确是场外聊天时，代码会静默跳过，不回复也不报错。
SESSION_CLASSIFY_SYSTEM_PROMPT = (
    "你是一名桌面跑团（TRPG）游戏主持人的助手，正在旁听一场进行中的跑团。"
    "玩家会在群里发消息，你需要判断这句话是角色在游戏世界里的行动/发言，"
    "还是玩家本人在游戏外的闲聊、吐槽、讨论规则等场外内容。\n"
    "请严格按下面的格式回答：\n"
    "如果是游戏内行动/发言，第一行写 IN_GAME，然后另起一行，"
    "用中文续写 100~200 字的剧情反馈，直接写正文，不要解释。\n"
    "如果是游戏外聊天，只回复一行 OUT_OF_GAME，不要有任何其它内容。"
)

HELP_TEXT = """🎲 跑团助手指令一览（前缀以你的机器人设置为准，默认 /）
━━━━━━━━━━━━━━
【骰子】
/r 1d20        掷一个20面骰
/r 2d6+3       掷两个6面骰再加3（/roll 也可以）
【角色卡】
/pc new 角色名      创建角色卡（角色名不要带空格）
/pc show            查看自己的角色卡
/pc show QQ号       查看别人的角色卡
/pc set 属性 数值   修改自己角色卡，如 /pc set 力量 14
/pc set 属性 数值 QQ号   （仅团长）修改别人的角色卡
/pc del             删除自己的角色卡
【团长】
/gm add QQ号   任命团长（仅 AstrBot 管理员或现有团长可用）
/gm del QQ号   撤销团长
/gm list       查看本群团长
【AI 叙事】
/npc 一个独眼的兽人铁匠   让 AI 生成 NPC/场景描写
【TRPG 模式】（仅团长/管理员可开关）
/trpg on    开启后本群指令可以不带“/”，也可以用“1”代替“/”
/trpg off   关闭 TRPG 模式，恢复只认“/”前缀
【引导建团】（仅团长/管理员）
/trpg invite QQ号1 QQ号2 ...   邀请玩家加入本团，让他们选建卡方式
/trpg start                     正式开始跑团（未建完卡也能强制开始）
/trpg end                       结束本团，重置邀请状态（不影响角色卡/团长/TRPG模式）
━━━━━━━━━━━━━━
开团期间（/trpg start 之后），受邀玩家在群里说话，AI 会自动判断是不是
游戏内发言，是的话会顺手接一段剧情叙述（前面带 🎭）；纯聊天不会打扰。
⚠️ 这个判断每条消息都要问一次 AI，如果用的是本地跑的 AI（比如 Ollama），
可能会有延迟，长团建议留意一下响应速度。
━━━━━━━━━━━━━━
群内所有发言会自动记录到团务日志，供团长查阅。"""


# @register 是 AstrBot 的“注册插件”标记，四个参数依次是：
# 插件名、作者、简介、版本号
@register(PLUGIN_NAME, "yqyjswj", "QQ 群跑团助手：骰子/角色卡/AI叙事/团务日志/团长权限/TRPG模式/引导建团", "v1.2.0")
class TRPGPlugin(Star):

    def __init__(self, context: Context):
        super().__init__(context)

        # ---------- 第一步：确定数据保存在哪个文件夹 ----------
        if StarTools is not None:
            # 新版 AstrBot：官方推荐的方式，自动得到
            # data/plugin_data/astrbot_plugin_trpg/ 这个目录
            self.data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        else:
            # 老版 AstrBot：手动拼出同样的路径
            self.data_dir = Path("data") / "plugin_data" / PLUGIN_NAME
        # 目录不存在就创建（parents=True 表示上级目录也一起建）
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 角色卡文件、团长名单文件、TRPG模式开关文件、开团进度文件、日志目录
        self.char_file = self.data_dir / "characters.json"
        self.gm_file = self.data_dir / "gm.json"
        self.mode_file = self.data_dir / "mode.json"
        self.session_file = self.data_dir / "sessions.json"
        self.log_dir = self.data_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # ---------- 第二步：启动时把 JSON 文件读进内存 ----------
        # characters 的结构：{ "群号": { "QQ号": {角色卡内容} } }
        self.characters = self._load_json(self.char_file, {})
        # gms 的结构：{ "群号": ["团长QQ号1", "团长QQ号2"] }
        self.gms = self._load_json(self.gm_file, {})
        # trpg_mode 的结构：{ "群号": True/False }，没记录就当 False（默认关闭）
        self.trpg_mode = self._load_json(self.mode_file, {})
        # sessions 的结构：{ "群号": {"state":..., "players": {...}} }，
        # 没记录或 state 不是 "in_progress"/"inviting" 就当没有进行中的团
        self.sessions = self._load_json(self.session_file, {})

        logger.info(f"[{PLUGIN_NAME}] 跑团插件已加载，数据目录：{self.data_dir}")

    # ==================================================
    # 工具函数（下划线开头的都是内部小帮手，不是指令）
    # ==================================================

    def _load_json(self, path: Path, default):
        """从 JSON 文件读取数据；文件不存在或损坏时返回默认值，保证插件不会崩。"""
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"[{PLUGIN_NAME}] 读取 {path} 失败：{e}")
        return default

    def _save_json(self, path: Path, data):
        """把数据写回 JSON 文件。
        先写到临时文件再整体替换，这样即使写到一半断电，原文件也不会损坏。"""
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            # ensure_ascii=False 让中文按中文存，方便你直接打开文件看
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _save_characters(self):
        """保存所有角色卡。每次修改后都立刻调用，所以重启不会丢数据。"""
        self._save_json(self.char_file, self.characters)

    def _save_gms(self):
        """保存团长名单。"""
        self._save_json(self.gm_file, self.gms)

    def _save_mode(self):
        """保存每个群的 TRPG 模式开关状态。"""
        self._save_json(self.mode_file, self.trpg_mode)

    def _save_sessions(self):
        """保存每个群的邀请/建卡/开团进度。"""
        self._save_json(self.session_file, self.sessions)

    def _is_gm(self, group_id: str, user_id: str) -> bool:
        """判断某个 QQ 号是不是这个群的团长。"""
        return str(user_id) in self.gms.get(str(group_id), [])

    @staticmethod
    def _clean_qq(text: str) -> str:
        """清理用户输入的 QQ 号：去掉可能带的 @ 和空格。"""
        return text.strip().lstrip("@").strip()

    @staticmethod
    def _now_str() -> str:
        """当前时间，格式如 2026-07-03 21:05:33"""
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _get_card(self, group_id: str, user_id: str):
        """取出某群某人的角色卡，没有就返回 None。"""
        return self.characters.get(str(group_id), {}).get(str(user_id))

    def _format_card(self, card: dict, owner_id: str) -> str:
        """把角色卡整理成好看的文字，用于发回群里。"""
        lines = [
            f"📜 角色卡：{card.get('name', '未命名')}",
            f"👤 玩家QQ：{owner_id}",
            "━━━━━━━━━━━━━━",
        ]
        attrs = card.get("attrs", {})
        if attrs:
            for key, value in attrs.items():
                lines.append(f"{key}：{value}")
        else:
            lines.append("（还没有设置任何属性，用 /pc set 属性名 数值 来添加）")
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f"创建于：{card.get('created_at', '未知')}")
        return "\n".join(lines)

    def _finalize_session_character(self, group_id: str, user_id: str,
                                     name: str, attrs: dict):
        """引导建团流程专用：把建好的角色卡写进 self.characters 并保存。
        跟 /pc new 不同，这里刻意允许覆盖玩家在本群已有的旧卡——
        邀请建团本来就是为了给这场新团建一张新角色卡。"""
        self.characters.setdefault(group_id, {})[user_id] = {
            "name": name or "未命名",
            "attrs": attrs,
            "created_at": self._now_str(),
            "updated_at": self._now_str(),
        }
        self._save_characters()

    @staticmethod
    def _roll_attr_template() -> dict:
        """按 ATTR_TEMPLATE 随机生成一整套属性，每项 3d6*5（COC风格，15~90）。"""
        return {
            attr: sum(random.randint(1, 6) for _ in range(3)) * 5
            for attr in ATTR_TEMPLATE
        }

    # ==================================================
    # 功能 1：骰子指令 /r 或 /roll
    # ==================================================

    @filter.command("r", alias={"roll"})
    async def roll_dice(self, event: AstrMessageEvent, expr: str = "1d20"):
        """掷骰子。用法：/r 2d6+3（不写参数时默认掷 1d20）"""
        async for r in self._roll_impl(event, expr):
            yield r

    async def _roll_impl(self, event: AstrMessageEvent, expr: str):
        """掷骰子的实际逻辑，供 /r 指令和 TRPG 模式下的无前缀指令共用。"""
        expr = (expr or "1d20").strip()
        m = DICE_RE.match(expr)
        if not m:
            yield event.plain_result(
                "❌ 骰子格式不对哦～正确示例：/r 1d20、/r 2d6+3、/r d100"
            )
            return

        # 从正则匹配结果里取出：骰子个数、面数、修正值
        num = int(m.group(1)) if m.group(1) else 1   # 没写个数就算 1 个
        sides = int(m.group(2))
        mod = int(m.group(3)) if m.group(3) else 0   # 没写修正值就算 0

        # 防刷上限检查
        if not (1 <= num <= MAX_DICE):
            yield event.plain_result(f"❌ 骰子个数要在 1~{MAX_DICE} 之间")
            return
        if not (2 <= sides <= MAX_SIDES):
            yield event.plain_result(f"❌ 骰子面数要在 2~{MAX_SIDES} 之间")
            return

        # 真正掷骰子：每个骰子随机出 1~面数 的一个整数
        rolls = [random.randint(1, sides) for _ in range(num)]
        total = sum(rolls) + mod

        # 拼出结果文字，比如：🎲 张三 掷出 2d6+3：[4, 5] +3 = 12
        sender = event.get_sender_name()
        mod_text = f"{'+' if mod > 0 else ''}{mod}" if mod != 0 else ""
        if num > 1 or mod != 0:
            # 多个骰子或有修正值时，把每个骰子的点数也列出来
            detail = f"{rolls} {mod_text} = {total}"
        else:
            detail = f"{total}"
        yield event.plain_result(f"🎲 {sender} 掷出 {num}d{sides}{mod_text}：{detail}")

    # ==================================================
    # 功能 2：角色卡管理 /pc 指令组
    # ==================================================

    # 这是“指令组”的入口：/pc 后面跟子指令，比如 /pc new、/pc show
    @filter.command_group("pc")
    def pc(self):
        pass

    @pc.command("new")
    async def pc_new(self, event: AstrMessageEvent, name: str = ""):
        """创建角色卡。用法：/pc new 阿尔萨斯（角色名不要带空格）"""
        async for r in self._pc_new_impl(event, name):
            yield r

    async def _pc_new_impl(self, event: AstrMessageEvent, name: str):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 角色卡功能只能在群聊里使用")
            return
        if not name:
            yield event.plain_result("❌ 请带上角色名，例如：/pc new 阿尔萨斯")
            return

        user_id = str(event.get_sender_id())

        # 一个人在一个群里只能有一张卡，防止误操作覆盖
        if self._get_card(group_id, user_id):
            yield event.plain_result(
                "❌ 你在本群已经有角色卡了。想重建请先 /pc del 删除旧卡。"
            )
            return

        # setdefault 的意思：这个群还没有记录就先建一个空的
        self.characters.setdefault(group_id, {})[user_id] = {
            "name": name,          # 角色名
            "attrs": {},           # 属性表（力量、敏捷……），一开始是空的
            "created_at": self._now_str(),   # 创建时间
            "updated_at": self._now_str(),   # 最后修改时间
        }
        self._save_characters()  # 立刻写进文件，重启不丢
        yield event.plain_result(
            f"✅ 角色卡「{name}」创建成功！\n用 /pc set 属性名 数值 来设置属性，"
            f"例如：/pc set 力量 14"
        )

    @pc.command("show")
    async def pc_show(self, event: AstrMessageEvent, target: str = ""):
        """查看角色卡。/pc show 看自己；/pc show QQ号 看别人。"""
        async for r in self._pc_show_impl(event, target):
            yield r

    async def _pc_show_impl(self, event: AstrMessageEvent, target: str):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 角色卡功能只能在群聊里使用")
            return

        # 没写目标就看自己
        target_id = self._clean_qq(target) if target else str(event.get_sender_id())
        card = self._get_card(group_id, target_id)
        if not card:
            if target:
                yield event.plain_result(f"❌ {target_id} 在本群还没有角色卡")
            else:
                yield event.plain_result("❌ 你还没有角色卡，用 /pc new 角色名 创建一张吧")
            return
        yield event.plain_result(self._format_card(card, target_id))

    @pc.command("set")
    async def pc_set(self, event: AstrMessageEvent,
                     attr: str = "", value: str = "", target: str = ""):
        """修改角色卡属性。
        普通玩家：/pc set 力量 14        （只能改自己的）
        团长专用：/pc set 力量 14 QQ号   （可以改别人的）"""
        async for r in self._pc_set_impl(event, attr, value, target):
            yield r

    async def _pc_set_impl(self, event: AstrMessageEvent,
                            attr: str, value: str, target: str):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 角色卡功能只能在群聊里使用")
            return
        if not attr or not value:
            yield event.plain_result(
                "❌ 用法：/pc set 属性名 数值，例如 /pc set 力量 14"
            )
            return

        sender_id = str(event.get_sender_id())

        # ---------- 权限判断：改自己 or 改别人 ----------
        if target:
            target_id = self._clean_qq(target)
            # 想改别人的卡，且目标不是自己 → 必须是团长
            if target_id != sender_id and not self._is_gm(group_id, sender_id):
                yield event.plain_result("⛔ 只有团长才能修改别人的角色卡哦")
                return
        else:
            target_id = sender_id  # 没写目标就是改自己

        card = self._get_card(group_id, target_id)
        if not card:
            who = "你" if target_id == sender_id else f"{target_id}"
            yield event.plain_result(f"❌ {who}还没有角色卡，先用 /pc new 创建一张吧")
            return

        # 数值能转成整数就按整数存（方便以后做加减），转不了就按文字存（比如职业）
        try:
            stored_value = int(value)
        except ValueError:
            stored_value = value

        card["attrs"][attr] = stored_value
        card["updated_at"] = self._now_str()
        self._save_characters()

        whose = "自己" if target_id == sender_id else f"{card.get('name', target_id)}"
        yield event.plain_result(
            f"✅ 已把{whose}的「{attr}」设置为 {stored_value}"
        )

    @pc.command("del")
    async def pc_del(self, event: AstrMessageEvent, target: str = ""):
        """删除角色卡。/pc del 删自己的；团长可以 /pc del QQ号 删别人的。"""
        async for r in self._pc_del_impl(event, target):
            yield r

    async def _pc_del_impl(self, event: AstrMessageEvent, target: str):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 角色卡功能只能在群聊里使用")
            return

        sender_id = str(event.get_sender_id())
        if target:
            target_id = self._clean_qq(target)
            if target_id != sender_id and not self._is_gm(group_id, sender_id):
                yield event.plain_result("⛔ 只有团长才能删除别人的角色卡哦")
                return
        else:
            target_id = sender_id

        card = self._get_card(group_id, target_id)
        if not card:
            yield event.plain_result("❌ 没有找到对应的角色卡")
            return

        name = card.get("name", "未命名")
        del self.characters[group_id][target_id]
        self._save_characters()
        yield event.plain_result(f"🗑️ 角色卡「{name}」已删除")

    # ==================================================
    # 功能 5：团长（GM）管理 /gm 指令组
    # ==================================================

    @filter.command_group("gm")
    def gm(self):
        pass

    def _can_manage_gm(self, event: AstrMessageEvent, group_id: str) -> bool:
        """谁有资格任命/撤销团长？
        1. AstrBot 管理员（在 AstrBot 配置文件里设置的管理员 QQ 号）
        2. 本群现有的团长"""
        try:
            if event.is_admin():
                return True
        except Exception:
            pass  # 个别老版本可能没有 is_admin 方法，忽略即可
        return self._is_gm(group_id, str(event.get_sender_id()))

    @gm.command("add")
    async def gm_add(self, event: AstrMessageEvent, target: str = ""):
        """任命团长。用法：/gm add 12345678"""
        async for r in self._gm_add_impl(event, target):
            yield r

    async def _gm_add_impl(self, event: AstrMessageEvent, target: str):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 团长功能只能在群聊里使用")
            return
        if not target:
            yield event.plain_result("❌ 用法：/gm add QQ号")
            return
        if not self._can_manage_gm(event, group_id):
            yield event.plain_result("⛔ 只有 AstrBot 管理员或现有团长才能任命团长")
            return

        target_id = self._clean_qq(target)
        gm_list = self.gms.setdefault(group_id, [])
        if target_id in gm_list:
            yield event.plain_result(f"ℹ️ {target_id} 已经是团长了")
            return
        gm_list.append(target_id)
        self._save_gms()
        yield event.plain_result(f"👑 已任命 {target_id} 为本群团长！")

    @gm.command("del")
    async def gm_del(self, event: AstrMessageEvent, target: str = ""):
        """撤销团长。用法：/gm del 12345678"""
        async for r in self._gm_del_impl(event, target):
            yield r

    async def _gm_del_impl(self, event: AstrMessageEvent, target: str):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 团长功能只能在群聊里使用")
            return
        if not target:
            yield event.plain_result("❌ 用法：/gm del QQ号")
            return
        if not self._can_manage_gm(event, group_id):
            yield event.plain_result("⛔ 只有 AstrBot 管理员或现有团长才能撤销团长")
            return

        target_id = self._clean_qq(target)
        gm_list = self.gms.get(group_id, [])
        if target_id not in gm_list:
            yield event.plain_result(f"ℹ️ {target_id} 本来就不是团长")
            return
        gm_list.remove(target_id)
        self._save_gms()
        yield event.plain_result(f"✅ 已撤销 {target_id} 的团长身份")

    @gm.command("list")
    async def gm_list(self, event: AstrMessageEvent):
        """查看本群团长名单。用法：/gm list"""
        async for r in self._gm_list_impl(event):
            yield r

    async def _gm_list_impl(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            yield event.plain_result("❌ 团长功能只能在群聊里使用")
            return
        gm_list = self.gms.get(group_id, [])
        if not gm_list:
            yield event.plain_result(
                "本群还没有团长。请 AstrBot 管理员用 /gm add QQ号 任命一位。"
            )
            return
        yield event.plain_result("👑 本群团长：" + "、".join(gm_list))

    # ==================================================
    # 功能 3：AI 叙事助手 /npc
    # ==================================================

    @filter.command("npc")
    async def npc(self, event: AstrMessageEvent):
        """让 AI 生成 NPC / 场景叙事。用法：/npc 一个独眼的兽人铁匠"""
        # event.message_str 是这条消息的纯文字，形如 "npc 一个独眼的兽人铁匠"
        # 把开头的指令词 "npc" 去掉，剩下的就是玩家写的描述
        desc = event.message_str.strip()
        if desc.lower().startswith("npc"):
            desc = desc[3:].strip()
        async for r in self._npc_impl(event, desc):
            yield r

    async def _npc_impl(self, event: AstrMessageEvent, desc: str):
        """AI 叙事的实际逻辑，供 /npc 指令和 TRPG 模式下的无前缀指令共用。"""
        if not desc:
            yield event.plain_result("❌ 请带上描述，例如：/npc 一个神秘的酒馆老板")
            return

        # 拿到 AstrBot 当前启用的 LLM 提供商（也就是你配置好的 Ollama）
        provider = self.context.get_using_provider()
        if provider is None:
            yield event.plain_result(
                "❌ 当前没有可用的 LLM 提供商，请先在 AstrBot 管理面板里"
                "配置并启用一个（比如 Ollama）"
            )
            return

        # 本地 Ollama 生成可能要几秒到几十秒，先回一句让大家别急
        yield event.plain_result("🎭 正在酝酿剧情，请稍候……")

        try:
            # text_chat 就是“把文字发给 AI，拿回 AI 的回答”
            try:
                llm_response = await provider.text_chat(
                    prompt=desc,                       # 玩家的描述
                    session_id=None,                   # 不关联到某个会话
                    contexts=[],                       # 不带历史聊天记录
                    system_prompt=NPC_SYSTEM_PROMPT,   # AI 的角色设定
                )
            except TypeError:
                # 万一 AstrBot 版本较老、参数不一样，就用最简单的调用方式兜底
                llm_response = await provider.text_chat(
                    prompt=f"{NPC_SYSTEM_PROMPT}\n\n描述：{desc}"
                )

            # 从 AI 的回复对象里取出文字内容
            text = getattr(llm_response, "completion_text", "") or str(llm_response)
            text = text.strip()
            if not text:
                yield event.plain_result("❌ AI 没有返回内容，请稍后再试")
                return
            yield event.plain_result(f"🎭 {text}")

        except Exception as e:
            # 任何异常（比如 Ollama 没启动）都不让插件崩溃，只提示错误
            logger.error(f"[{PLUGIN_NAME}] 调用 LLM 失败：{e}")
            yield event.plain_result(
                f"❌ AI 叙事生成失败：{e}\n请检查 Ollama 是否正在运行。"
            )

    # ==================================================
    # 功能 4：团务日志 —— 自动记录群里的每条消息
    # 功能 6：TRPG 模式 —— 无前缀 / "1"前缀 指令识别
    # 功能 7：引导建团 —— 建卡向导 + 开团后游戏内/外发言判断
    # ==================================================

    # 这个装饰器的意思是：只要收到“群消息”就会触发这个函数
    # 处理优先级（从上到下）：
    #   1. 团务日志：永远记录，不受下面任何逻辑影响
    #   2. 建卡向导：如果发送者正处在"等待选建卡方式/等待填角色名/
    #      等待填属性"的状态，这条消息就是在回答向导，直接吃掉，
    #      不会被当成指令或聊天
    #   3. TRPG 模式的无前缀/1前缀指令识别（跟以前一样）
    #   4. 开团后（/trpg start 之后）对受邀玩家发言做游戏内/外判断
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id() or "")
        if not group_id:
            return

        self._log_group_message(group_id, event)

        handled = False
        async for r in self._handle_session_input(event, group_id):
            handled = True
            yield r
        if handled:
            return

        raw_text = event.message_str or ""
        is_slash_command = raw_text.strip().startswith("/")
        matched_raw = self._extract_raw_command(raw_text)

        if self.trpg_mode.get(group_id) and matched_raw:
            async for r in self._dispatch_raw_command(event, group_id):
                yield r
            return

        # 走到这里说明：不是建卡向导的回答、不是斜杠指令、也不是无前缀指令，
        # 只有开团进行中、且发送者是本团受邀玩家时，才交给 AI 判断游戏内外
        if not is_slash_command and not matched_raw:
            session = self.sessions.get(group_id)
            sender_id = str(event.get_sender_id())
            if session and session.get("state") == "in_progress" \
                    and sender_id in session.get("players", {}):
                async for r in self._classify_and_narrate_impl(event, group_id, raw_text):
                    yield r

    def _log_group_message(self, group_id: str, event: AstrMessageEvent):
        """把这条群消息追加写进团务日志。只记录，不回复，出错也不影响其它功能。"""
        try:
            sender_name = event.get_sender_name() or "未知"
            sender_id = event.get_sender_id()
            # 把消息里的换行替换成 \n 字样，保证日志文件里一条消息占一行
            content = (event.message_str or "").replace("\r", "").replace("\n", "\\n")
            if not content:
                return  # 纯图片、表情等没有文字的消息就不记了

            # 每个群一个文件夹，每天一个日志文件，例如 logs/12345/2026-07-03.log
            group_log_dir = self.log_dir / group_id
            group_log_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.date.today().strftime("%Y-%m-%d")
            log_file = group_log_dir / f"{today}.log"

            # 追加写入一行，格式：[时间] 昵称(QQ号): 内容
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {sender_name}({sender_id}): {content}\n")

        except Exception as e:
            # 记日志失败绝不能影响机器人正常聊天，所以只在后台报个错
            logger.error(f"[{PLUGIN_NAME}] 写团务日志失败：{e}")

    async def _handle_session_input(self, event: AstrMessageEvent, group_id: str):
        """建卡向导：判断这条消息是不是某个受邀玩家在回答"选建卡方式/填角色名/
        填属性"。是的话就处理并 yield 回复；不是的话什么都不 yield（调用方靠
        有没有 yield 过东西来判断"是否已处理"）。"""
        session = self.sessions.get(group_id)
        if not session or session.get("state") != "inviting":
            return

        sender_id = str(event.get_sender_id())
        player = session.get("players", {}).get(sender_id)
        if not player or player.get("status") == "ready":
            return

        text = (event.message_str or "").strip()
        status = player.get("status")

        if status == "awaiting_choice":
            if text == "1":
                player["status"] = "awaiting_name"
                player["path"] = "random"
                self._save_sessions()
                yield event.plain_result("✏️ 请回复你的角色名（不要带空格）：")
            elif text == "2":
                player["status"] = "awaiting_name"
                player["path"] = "guided"
                player["step"] = 0
                self._save_sessions()
                yield event.plain_result("✏️ 请回复你的角色名（不要带空格）：")
            else:
                yield event.plain_result("❓ 请回复 1（完全随机建卡）或 2（引导式建卡）")
            return

        if status == "awaiting_name":
            if not text:
                yield event.plain_result("❌ 角色名不能是空的，请重新回复：")
                return
            player["draft"]["name"] = text
            if player.get("path") == "random":
                attrs = self._roll_attr_template()
                player["draft"]["attrs"] = attrs
                self._finalize_session_character(group_id, sender_id, text, attrs)
                player["status"] = "ready"
                self._save_sessions()
                attr_text = "  ".join(f"{k}：{v}" for k, v in attrs.items())
                yield event.plain_result(
                    f"🎲 角色「{text}」建好啦！属性已随机生成：\n{attr_text}"
                )
                async for r in self._notify_if_all_ready(event, group_id):
                    yield r
            else:
                player["status"] = "awaiting_attr"
                player["step"] = 0
                self._save_sessions()
                yield event.plain_result(f"✏️ 请输入「{ATTR_TEMPLATE[0]}」的数值（整数）：")
            return

        if status == "awaiting_attr":
            try:
                value = int(text)
            except ValueError:
                yield event.plain_result("❌ 请输入一个整数数字，例如 14")
                return  # 不推进 step，同一项重新问

            step = player.get("step", 0)
            player["draft"]["attrs"][ATTR_TEMPLATE[step]] = value
            step += 1
            player["step"] = step

            if step < len(ATTR_TEMPLATE):
                self._save_sessions()
                yield event.plain_result(f"✏️ 请输入「{ATTR_TEMPLATE[step]}」的数值（整数）：")
            else:
                name = player["draft"].get("name", "未命名")
                attrs = player["draft"]["attrs"]
                self._finalize_session_character(group_id, sender_id, name, attrs)
                player["status"] = "ready"
                self._save_sessions()
                attr_text = "  ".join(f"{k}：{v}" for k, v in attrs.items())
                yield event.plain_result(
                    f"✅ 角色「{name}」建好啦！\n{attr_text}"
                )
                async for r in self._notify_if_all_ready(event, group_id):
                    yield r
            return

    async def _notify_if_all_ready(self, event: AstrMessageEvent, group_id: str):
        """某玩家建完卡后调用：如果本团所有受邀玩家都建完了，提醒团长可以开团了。"""
        session = self.sessions.get(group_id)
        if not session:
            return
        players = session.get("players", {})
        if players and all(p.get("status") == "ready" for p in players.values()):
            yield event.plain_result(
                "🎉 所有受邀玩家都完成建卡啦！团长可以发 /trpg start 正式开始跑团。"
            )

    def _extract_raw_command(self, text: str):
        """判断这段文字是不是 TRPG 模式下的“无前缀”或“1前缀”指令。
        是的话返回 (指令词, 剩余参数文字)；不是就返回 None。
        只有整段文字的第一个词精确匹配 RAW_KEYWORDS 才会命中，
        避免把普通聊天误判成指令。"""
        text = (text or "").strip()
        if not text or text.startswith("/"):
            # 以 "/" 开头的已经走 AstrBot 自带的指令前缀系统处理了，
            # 这里不重复处理，否则会回复两遍。
            return None

        # 先试“不带任何前缀”，再试“把开头的数字1当前缀去掉”
        candidates = [text]
        if text[0] == "1" and len(text) > 1:
            candidates.append(text[1:].strip())

        for candidate in candidates:
            head, _, rest = candidate.partition(" ")
            if head.lower() in RAW_KEYWORDS:
                return head.lower(), rest.strip()
        return None

    async def _dispatch_raw_command(self, event: AstrMessageEvent, group_id: str):
        """把无前缀/1前缀指令分发给对应功能的内部实现（_xxx_impl）。"""
        parsed = self._extract_raw_command(event.message_str)
        if not parsed:
            return
        head, rest = parsed

        if head in ("r", "roll"):
            async for r in self._roll_impl(event, rest):
                yield r
        elif head == "pc":
            sub, _, sub_rest = rest.partition(" ")
            sub = sub.strip().lower()
            sub_rest = sub_rest.strip()
            if sub == "new":
                async for r in self._pc_new_impl(event, sub_rest):
                    yield r
            elif sub == "show":
                async for r in self._pc_show_impl(event, sub_rest):
                    yield r
            elif sub == "set":
                args = sub_rest.split()
                attr = args[0] if len(args) > 0 else ""
                value = args[1] if len(args) > 1 else ""
                target = args[2] if len(args) > 2 else ""
                async for r in self._pc_set_impl(event, attr, value, target):
                    yield r
            elif sub == "del":
                async for r in self._pc_del_impl(event, sub_rest):
                    yield r
        elif head == "gm":
            sub, _, sub_rest = rest.partition(" ")
            sub = sub.strip().lower()
            sub_rest = sub_rest.strip()
            if sub == "add":
                async for r in self._gm_add_impl(event, sub_rest):
                    yield r
            elif sub == "del":
                async for r in self._gm_del_impl(event, sub_rest):
                    yield r
            elif sub == "list":
                async for r in self._gm_list_impl(event):
                    yield r
        elif head == "npc":
            async for r in self._npc_impl(event, rest):
                yield r
        elif head == "trpg":
            # 注意：rest 是 _extract_raw_command 返回的，只有 head 被转过小写，
            # rest 本身保持原样——所以这里只把子指令词转小写用来比较，
            # invite 后面的 QQ号/@ 内容原样传下去，不能整体 .lower()。
            sub, _, sub_rest = rest.partition(" ")
            sub = sub.strip().lower()
            async for r in self._trpg_help_impl(event, sub, sub_rest.strip()):
                yield r

    # ==================================================
    # 帮助指令 / TRPG 模式开关 / 引导建团 /trpg [on|off|invite|start|end]
    # ==================================================

    @filter.command("trpg")
    async def trpg_help(self, event: AstrMessageEvent, action: str = ""):
        """显示跑团助手的全部指令说明。
        团长/管理员可以用 /trpg on、/trpg off 开关本群的 TRPG 模式；
        /trpg invite、/trpg start、/trpg end 用于引导建团流程。"""
        # 不依赖框架自动填的 action 参数（/trpg invite @A @B @C 这种多词参数，
        # 框架具体怎么切分不确定），照抄 /npc 的做法：直接从
        # event.message_str 里手动去掉开头的 "trpg"，自己切出子指令和参数。
        text = event.message_str.strip()
        if text.lower().startswith("trpg"):
            text = text[4:].strip()
        sub, _, raw_args = text.partition(" ")
        sub = sub.strip().lower()
        async for r in self._trpg_help_impl(event, sub, raw_args.strip()):
            yield r

    async def _trpg_help_impl(self, event: AstrMessageEvent, action: str,
                               raw_args: str = ""):
        group_id = str(event.get_group_id() or "")

        if action in ("on", "开", "开启"):
            if not group_id:
                yield event.plain_result("❌ TRPG 模式只能在群聊里开启")
                return
            if not self._can_manage_gm(event, group_id):
                yield event.plain_result("⛔ 只有 AstrBot 管理员或团长才能开启 TRPG 模式")
                return
            self.trpg_mode[group_id] = True
            self._save_mode()
            yield event.plain_result(
                "✅ 本群已开启 TRPG 模式！\n"
                "现在指令可以不带“/”，也可以用数字“1”代替“/”，例如：\n"
                "r 1d20 、 1r 1d20 、pc show 、1npc 一个神秘的商人\n"
                "⚠️ 开启期间请注意不要在闲聊里凑巧打出以 r/roll/pc/gm/npc/trpg "
                "开头的整句话，可能会被误判成指令。团结束后建议发 /trpg off 关闭。"
            )
            return

        if action in ("off", "关", "关闭"):
            if not group_id:
                yield event.plain_result("❌ TRPG 模式只能在群聊里关闭")
                return
            if not self._can_manage_gm(event, group_id):
                yield event.plain_result("⛔ 只有 AstrBot 管理员或团长才能关闭 TRPG 模式")
                return
            self.trpg_mode[group_id] = False
            self._save_mode()
            yield event.plain_result("✅ 已关闭本群的 TRPG 模式，指令恢复只认“/”前缀。")
            return

        if action == "invite":
            async for r in self._trpg_invite_impl(event, group_id, raw_args):
                yield r
            return

        if action == "start":
            async for r in self._trpg_start_impl(event, group_id):
                yield r
            return

        if action == "end":
            async for r in self._trpg_end_impl(event, group_id):
                yield r
            return

        yield event.plain_result(HELP_TEXT)

    async def _trpg_invite_impl(self, event: AstrMessageEvent, group_id: str,
                                 raw_args: str):
        """邀请玩家加入本团，进入建卡向导。用法：/trpg invite QQ号1 QQ号2 ..."""
        if not group_id:
            yield event.plain_result("❌ 邀请功能只能在群聊里使用")
            return
        if not self._can_manage_gm(event, group_id):
            yield event.plain_result("⛔ 只有 AstrBot 管理员或团长才能邀请玩家")
            return

        session = self.sessions.get(group_id)
        if session and session.get("state") == "in_progress":
            yield event.plain_result("❌ 本团已经开始了，请先 /trpg end 结束当前团再邀请新玩家")
            return

        target_ids = []
        for token in raw_args.split():
            qq = self._clean_qq(token)
            if qq and qq not in target_ids:
                target_ids.append(qq)

        if not target_ids:
            yield event.plain_result("❌ 用法：/trpg invite QQ号1 QQ号2 ...（可以带@，也可以不带）")
            return

        now = self._now_str()
        self.sessions[group_id] = {
            "state": "inviting",
            "invited_by": str(event.get_sender_id()),
            "players": {
                uid: {
                    "status": "awaiting_choice",
                    "path": "",
                    "step": 0,
                    "draft": {"name": "", "attrs": {}},
                    "joined_at": now,
                }
                for uid in target_ids
            },
            "created_at": now,
            "updated_at": now,
        }
        self._save_sessions()

        yield event.plain_result(
            f"📣 团长邀请以下玩家加入本团：{'、'.join(target_ids)}\n"
            "请每位被邀请的玩家在群里直接回复：\n"
            "1 —— 完全随机建卡（自动帮你随机好所有属性）\n"
            "2 —— 引导式建卡（一步步问你，自己填属性）"
        )

    async def _trpg_start_impl(self, event: AstrMessageEvent, group_id: str):
        """正式开始跑团。用法：/trpg start"""
        if not group_id:
            yield event.plain_result("❌ 开团功能只能在群聊里使用")
            return
        if not self._can_manage_gm(event, group_id):
            yield event.plain_result("⛔ 只有 AstrBot 管理员或团长才能开始跑团")
            return

        session = self.sessions.get(group_id)
        if not session or session.get("state") not in ("inviting", "in_progress"):
            yield event.plain_result("❌ 还没有邀请任何玩家，请先用 /trpg invite QQ号... 邀请玩家")
            return
        if session.get("state") == "in_progress":
            yield event.plain_result("ℹ️ 本团已经在进行中了")
            return

        players = session.get("players", {})
        not_ready = [uid for uid, p in players.items() if p.get("status") != "ready"]
        session["state"] = "in_progress"
        session["updated_at"] = self._now_str()
        self._save_sessions()

        msg = "✅ 跑团正式开始！祝大家玩得开心 🎲"
        if not_ready:
            msg += f"\n（还有 {len(not_ready)} 位玩家未完成建卡，但团长选择直接开始）"
        yield event.plain_result(msg)

    async def _trpg_end_impl(self, event: AstrMessageEvent, group_id: str):
        """结束本团，重置邀请/建卡状态。用法：/trpg end"""
        if not group_id:
            yield event.plain_result("❌ 结束跑团功能只能在群聊里使用")
            return
        if not self._can_manage_gm(event, group_id):
            yield event.plain_result("⛔ 只有 AstrBot 管理员或团长才能结束跑团")
            return

        session = self.sessions.get(group_id)
        if not session or session.get("state") == "idle":
            yield event.plain_result("ℹ️ 本群目前没有进行中的团")
            return

        self.sessions[group_id] = {
            "state": "idle",
            "players": {},
            "updated_at": self._now_str(),
        }
        self._save_sessions()
        yield event.plain_result(
            "🔚 本团已结束，邀请/建卡状态已重置。\n"
            "角色卡、团长名单、TRPG 模式开关都不受影响。"
        )

    async def _classify_and_narrate_impl(self, event: AstrMessageEvent,
                                          group_id: str, text: str):
        """开团进行中（/trpg start 之后），判断受邀玩家这句话是游戏内行动还是
        场外聊天；是游戏内的话调用 AI 续写一段剧情。这是自动挂在每条消息上的
        判断，跟 /npc 不同：LLM 不可用或出错时只记日志，不发群消息刷屏；
        判断为场外/解析不出格式时，静默跳过，不回复也不报错。"""
        text = (text or "").strip()
        if not text:
            return

        provider = self.context.get_using_provider()
        if provider is None:
            logger.error(f"[{PLUGIN_NAME}] 开团判断跳过：当前没有可用的 LLM 提供商")
            return

        try:
            try:
                llm_response = await provider.text_chat(
                    prompt=text,
                    session_id=None,
                    contexts=[],
                    system_prompt=SESSION_CLASSIFY_SYSTEM_PROMPT,
                )
            except TypeError:
                llm_response = await provider.text_chat(
                    prompt=f"{SESSION_CLASSIFY_SYSTEM_PROMPT}\n\n玩家发言：{text}"
                )

            result = getattr(llm_response, "completion_text", "") or str(llm_response)
            result = result.strip()
            if not result:
                return

            first_line, _, remainder = result.partition("\n")
            if first_line.strip().upper() != "IN_GAME":
                return  # OUT_OF_GAME 或格式解析不出来，都当场外处理，静默跳过

            narrative = remainder.strip()
            if not narrative:
                return
            yield event.plain_result(f"🎭 {narrative}")

        except Exception as e:
            # 这是挂在每条消息上的自动判断，出错不能打扰玩家聊天，只记日志
            logger.error(f"[{PLUGIN_NAME}] 开团游戏内/外判断失败：{e}")

    # ==================================================
    # 插件被卸载/停用时会调用这个函数（官方规范建议实现）
    # ==================================================

    async def terminate(self):
        # 数据在每次修改时都已经保存过了，这里只记录一下卸载事件
        logger.info(f"[{PLUGIN_NAME}] 跑团插件已卸载")
