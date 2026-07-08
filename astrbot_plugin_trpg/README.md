# astrbot_plugin_trpg — QQ 群跑团助手

一个给 QQ 群跑团（TRPG）用的 AstrBot 插件，包含骰子、角色卡、AI 叙事、团务日志、团长权限、
TRPG 模式（可选的无前缀指令）、引导建团（邀请玩家+建卡向导+AI 游戏内外判断）七大功能。

> 想知道具体怎么用（指令示例、常见问题），请看
> [使用说明.md](使用说明.md)——这份文件是给群主/玩家看的操作手册。
> 本文件只讲安装、依赖和数据存储这些技术信息。

## 安装方法

1. 把整个 `astrbot_plugin_trpg` 文件夹复制到 AstrBot 的插件目录：
   ```
   AstrBot/data/plugins/astrbot_plugin_trpg/
   ```
2. 重启 AstrBot，或在管理面板的「插件管理」页面点击刷新/重载。
3. 在群里发送 `/trpg`，如果机器人回复了指令列表，说明安装成功。

> 注意：所有指令前面的 `/` 是 AstrBot 默认的唤醒前缀。如果你改过前缀，就用你自己的前缀。

## 功能一览

骰子、角色卡管理、AI 叙事、团务日志、团长权限。占用的指令前缀：
`/r` `/roll` `/pc` `/gm` `/npc` `/trpg`。指令的具体用法见
[使用说明.md](使用说明.md)。

## 依赖

无第三方依赖，只用 Python 标准库，详见 `requirements.txt`。
`/npc` 功能需要 AstrBot 当前启用了一个 LLM 提供商（比如本地 Ollama）。

## 数据保存在哪里？

全部在 AstrBot 的 `data/plugin_data/astrbot_plugin_trpg/` 目录下，重启不会丢失：

- `characters.json` — 所有群的角色卡（按 群号 → QQ号 两层存放）
- `gm.json` — 每个群的团长名单
- `mode.json` — 每个群是否开启了 TRPG 模式（无前缀指令）
- `sessions.json` — 每个群当前的邀请/建卡/开团进度（引导建团的状态机）
- `logs/群号/日期.log` — 团务日志，纯文本，直接用记事本就能打开

想备份跑团数据，把这个文件夹整个复制走就行。
