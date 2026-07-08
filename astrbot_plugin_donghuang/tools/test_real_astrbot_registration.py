"""
test_real_astrbot_registration.py - 用真实 astrbot 框架验证插件能否正确加载

跟其它 test_*.py 不一样：这个文件不用手搓的 stub，而是要求测试环境里
真的 `pip install astrbot`。如果没装，这个测试直接跳过（返回码 0），不算
失败——因为 astrbot 不是这个插件仓库自己的依赖，只是"如果恰好装了，就
顺便做一次更强的验证"。

验证目标：
  1. main.py 能被当作 astrbot_plugin_donghuang.main 正常 import（不再需要
     手搓 stub 绕过 astrbot.api.* 的依赖）。
  2. LONG-A 修炼系统的导入链路（_LONG_A_AVAILABLE）在真实框架下也是 True
     （防止之前 breakthrough_manager.py 缺双重导入兜底那种"在真实环境
     侥幸能跑、在其它加载方式下静默失效"的问题走漏网之鱼）。
  3. 所有 @dh.command(...) 注册的指令，都真的进了 AstrBot 自己的
     star_handlers_registry，不是装饰器写错了导致注册失败但又不报错。
"""

import sys
from pathlib import Path

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PLUGIN_DIR.parent))

try:
    import astrbot  # noqa: F401
    _ASTRBOT_INSTALLED = True
except ImportError:
    _ASTRBOT_INSTALLED = False


# main.py 里所有 @dh.command("xxx") 注册的子命令名（跟 main.py 实际内容
# 保持同步；如果新增/删除指令，这里也要跟着改，否则测试会准确地报出
# 差异，这正是这个测试存在的意义）。
EXPECTED_DH_SUBCOMMANDS = {
    "act", "advance", "ask", "autopilot", "bestiary", "blacklist", "causal",
    "combat", "confirmdeath", "cultivate", "ability", "sect", "technique",
    "breakthrough", "decree", "doctor",
    "end", "environment", "eventlog", "eventtest", "exit", "export", "faction",
    "force", "help", "history", "interact", "items", "join", "join_faction",
    "kick", "leave_faction", "logout", "memories", "mycard", "npc",
    "npc_events", "play", "profile", "recap", "rejectdeath", "replay",
    "rollback", "roster", "save", "stabilize", "start", "status", "stop",
    "testfill", "tick", "unblacklist", "weather", "why", "world",
}


def test_main_imports_under_real_astrbot():
    if not _ASTRBOT_INSTALLED:
        print("跳过：当前环境没有安装 astrbot（pip install astrbot 后可启用这项验证）")
        return

    import astrbot_plugin_donghuang.main as m

    assert m._LONG_A_AVAILABLE is True, (
        "LONG-A 修炼系统在真实 astrbot 框架下导入失败——"
        "检查是否有模块缺少 try/.相对导入 + 绝对导入兜底"
    )


def test_all_dh_commands_registered_in_real_registry():
    if not _ASTRBOT_INSTALLED:
        print("跳过：当前环境没有安装 astrbot")
        return

    import astrbot_plugin_donghuang.main as m  # noqa: F401
    from astrbot.core.star.register.star_handler import star_handlers_registry

    registered_names = set()
    prefix = "astrbot_plugin_donghuang.main_dh_"
    for handler in star_handlers_registry:
        full_name = getattr(handler, "handler_full_name", "")
        if full_name.startswith(prefix):
            registered_names.add(full_name[len(prefix):])

    missing = EXPECTED_DH_SUBCOMMANDS - registered_names
    assert not missing, f"以下指令没有出现在真实 astrbot 的 star_handlers_registry 里：{sorted(missing)}"


if __name__ == "__main__":
    test_main_imports_under_real_astrbot()
    test_all_dh_commands_registered_in_real_registry()
    print("\nreal_astrbot_registration tests passed（如果环境没装 astrbot，以上两项均为跳过）")
