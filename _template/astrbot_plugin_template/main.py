# -*- coding: utf-8 -*-
"""
astrbot_plugin_template —— 新插件脚手架

复制这个文件夹改名之后，请依次修改：
  1. metadata.yaml 里的 name / desc / author / repo
  2. 本文件里的 PLUGIN_NAME 常量
  3. 本文件里 @register(...) 的第一个参数
  4. 类名 TemplatePlugin
这四处必须和新的文件夹名保持一致（PLUGIN_NAME 和 @register 的名字要跟文件夹名相同）。

规则详见仓库根目录的 PROJECT_PLAN.md / CLAUDE.md：
  - 不允许 import 其它 astrbot_plugin_* 文件夹的代码
  - 数据只能读写自己的 data_dir，不要硬编码路径
"""

from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

try:
    from astrbot.api.star import StarTools
except ImportError:
    StarTools = None

# 【必改】插件名，必须和文件夹名、metadata.yaml 里的 name 一致
PLUGIN_NAME = "astrbot_plugin_template"


@register(PLUGIN_NAME, "yqyjswj", "一句话描述这个插件", "v0.1.0")
class TemplatePlugin(Star):

    def __init__(self, context: Context):
        super().__init__(context)

        if StarTools is not None:
            self.data_dir = Path(StarTools.get_data_dir(PLUGIN_NAME))
        else:
            self.data_dir = Path("data") / "plugin_data" / PLUGIN_NAME
        self.data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[{PLUGIN_NAME}] 插件已加载，数据目录：{self.data_dir}")

    @filter.command("template")
    async def template_cmd(self, event: AstrMessageEvent):
        """示例指令，写完功能后记得改成实际的指令名。"""
        yield event.plain_result("这是模板插件的示例回复，请替换成真正的功能。")

    async def terminate(self):
        logger.info(f"[{PLUGIN_NAME}] 插件已卸载")
