"""
test_save_integrity.py — 存档数据完整性 / 恢复能力测试（C-0 第二/三节）

覆盖目标：
  campaign.json / world_state.json / event_log.json / action_log.json
  这类运行时存档，在下列"损坏场景"下是否仍能安全加载：
    1. 正常 JSON（基线）
    2. 带 UTF-8 BOM 的 JSON
    3. 空文件
    4. 文件不存在
    5. 截断/语法损坏的 JSON
    6. 顶层类型不对（比如期待 dict 却是 list）
    7. 保存时"半写入"（模拟进程在 tmp 文件写完、rename 之前崩溃）
    8. 旧版本存档缺字段（campaign 级自愈 setdefault 是否还在）

约束：
  main.py 里的 DonghuangPlugin 依赖 astrbot.api（AstrBot 框架包），
  本机/CI 环境通常没有装这个包，无法直接实例化 DonghuangPlugin 来做
  端到端测试。所以本文件分两部分：
    (a) 直接测试 asset_loader.py 里真正被 main.py 复用的加载函数
        （这部分是可以直接跑的真实代码路径）。
    (b) 用"源码静态断言"验证 main.py 里 _get_campaign() 的自愈
        setdefault 清单没有被意外删减——这不是理想的单元测试替代品，
        但在不能导入 main.py 的约束下，是能捕捉"自愈逻辑被删掉"这种
        回归的最低成本手段。如果未来 main.py 可以脱离 astrbot 单独
        导入了，应该把 (b) 换成真正实例化 _get_campaign() 的测试。

运行方式：
  python tools/test_save_integrity.py
"""

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from asset_loader import load_json, load_json_with_default, read_text

MAIN_PY = Path(__file__).resolve().parent.parent / "main.py"


def _tmpfile(content: bytes, suffix=".json") -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / f"sample{suffix}"
    p.write_bytes(content)
    return p


# ──────────────────────────────────────────────
#  (a) asset_loader 加载函数的容错性
# ──────────────────────────────────────────────

def test_load_valid_json():
    """基线：正常 JSON 能正确解析。"""
    p = _tmpfile('{"cycle": 3, "state": "active"}'.encode("utf-8"))
    data = load_json_with_default(p, {})
    assert data == {"cycle": 3, "state": "active"}
    print("✅ 测试1通过：正常 JSON 正确解析")


def test_load_bom_json():
    """campaign 类存档如果被某些编辑器/工具带上 BOM 保存，仍要能读出来。"""
    content = "﻿" + json.dumps({"cycle": 1}, ensure_ascii=False)
    p = _tmpfile(content.encode("utf-8"))
    data = load_json_with_default(p, {})
    assert data == {"cycle": 1}, f"BOM 文件解析结果不对：{data}"
    print("✅ 测试2通过：带 BOM 的 JSON 正确解析")


def test_load_empty_file():
    """空文件（比如磁盘写满导致 0 字节）不应该让加载抛异常，应退回默认值。"""
    p = _tmpfile(b"")
    data = load_json_with_default(p, {"fallback": True})
    assert data == {"fallback": True}, f"空文件应返回默认值，实际：{data}"

    lst = load_json(p)
    assert lst == [], f"load_json 对空文件应返回 []，实际：{lst}"
    print("✅ 测试3通过：空文件安全退回默认值，不抛异常")


def test_load_missing_file():
    """文件不存在（比如首次运行、新群从没存过档）要返回默认值，不报错。"""
    missing = Path(tempfile.mkdtemp()) / "does_not_exist.json"
    data = load_json_with_default(missing, {"cycle": 1, "state": "not_started"})
    assert data == {"cycle": 1, "state": "not_started"}
    print("✅ 测试4通过：文件不存在时安全返回默认值")


def test_load_corrupted_json():
    """截断/语法错误的 JSON（比如保存到一半进程被杀）不应该抛异常到业务层。"""
    p = _tmpfile('{"cycle": 3, "state": "acti'.encode("utf-8"))  # 故意截断
    data = load_json_with_default(p, {"cycle": 0, "state": "recovered"})
    assert data == {"cycle": 0, "state": "recovered"}, f"损坏 JSON 应退回默认值，实际：{data}"
    print("✅ 测试5通过：损坏/截断 JSON 安全退回默认值")


def test_load_wrong_top_level_type():
    """JSON 语法本身没错，但顶层类型跟调用方预期不一致（期待 dict 结果却是
    list）。asset_loader 这一层依然不做类型校验，只负责"能不能解析"——
    类型校验现在由调用方（DonghuangPlugin._load_json，见测试14）负责，
    不是这一层的职责。"""
    p = _tmpfile(json.dumps([1, 2, 3]).encode("utf-8"))
    data = load_json_with_default(p, {})
    assert data == [1, 2, 3], "确认当前行为：asset_loader 这一层类型不匹配不会被拦截"
    print("✅ 测试6通过：asset_loader 加载层本身不做顶层类型校验（按设计，"
          "类型校验交给调用方），类型错误的数据会原样透传给调用方")


def test_load_non_utf8_bytes():
    """完全不是文本编码的垃圾字节（比如磁盘故障写入乱码）不应该让整个
    加载流程崩溃。"""
    p = _tmpfile(b"\xff\xfe\x00\x01broken")
    data = load_json_with_default(p, {"recovered": True})
    assert data == {"recovered": True}, f"非法字节流应安全退回默认值，实际：{data}"
    print("✅ 测试7通过：非法字节流不会让加载流程崩溃")


# ──────────────────────────────────────────────
#  (b) 保存路径的原子性（复刻 main.py _save_json 的 tmp+replace 模式）
# ──────────────────────────────────────────────

def _atomic_save(path: Path, data) -> None:
    """跟 main.py 里 _save_json 完全一致的落盘方式：先写 .tmp 再 os.replace。"""
    import os
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def test_atomic_save_round_trip():
    """保存后重新加载，数据（含中文）应完整还原。"""
    d = Path(tempfile.mkdtemp())
    p = d / "campaign.json"
    payload = {"cycle": 5, "world_history": [{"entry_type": "seed", "note": "东荒开团"}]}
    _atomic_save(p, payload)
    loaded = load_json_with_default(p, {})
    assert loaded == payload, f"保存/加载往返数据不一致：{loaded}"
    print("✅ 测试8通过：原子保存 + 加载往返数据一致（含中文）")


def test_atomic_save_interrupted_write_does_not_corrupt_original():
    """模拟"保存到一半进程被杀"：只写了 .tmp 文件，还没执行 os.replace。
    此时原文件应该完全不受影响，仍然可以正常加载出旧数据。"""
    d = Path(tempfile.mkdtemp())
    p = d / "campaign.json"
    good_payload = {"cycle": 7, "state": "active"}
    _atomic_save(p, good_payload)

    # 模拟中断：只写 tmp，不 replace（相当于进程在 os.replace 前被杀掉）
    tmp = p.with_suffix(".tmp")
    tmp.write_text("这是一段写到一半就断电的垃圾内容 {不是合法json", encoding="utf-8")

    # 原文件必须完好无损
    loaded = load_json_with_default(p, {})
    assert loaded == good_payload, f"中断写入不应影响原文件，实际读到：{loaded}"
    print("✅ 测试9通过：模拟保存中断后，原存档文件不受损坏，数据仍然完整")


def test_atomic_save_overwrite_replaces_cleanly():
    """正常连续两次保存，第二次应该完全替换第一次的内容，不残留旧字段。"""
    d = Path(tempfile.mkdtemp())
    p = d / "world_state.json"
    _atomic_save(p, {"region_a": {"weather": "晴"}})
    _atomic_save(p, {"region_a": {"weather": "雨"}, "region_b": {"weather": "阴"}})
    loaded = load_json_with_default(p, {})
    assert loaded == {"region_a": {"weather": "雨"}, "region_b": {"weather": "阴"}}
    print("✅ 测试10通过：连续保存正确覆盖，无残留旧数据")


# ──────────────────────────────────────────────
#  (c) 旧版本存档缺字段：源码静态断言 _get_campaign 自愈清单未被删减
# ──────────────────────────────────────────────

# 这份清单来自当前 main.py `_get_campaign()` 里的 setdefault 调用
# （详见 SYSTEM_ARCHITECTURE.md 第4节）。如果未来确实要移除某个字段的
# 自愈逻辑，应该是一次有意识的决定，而不是改代码时不小心带掉的——
# 这个测试失败时不代表"这次改动错了"，而是提醒"回来同步这份清单和
# SYSTEM_ARCHITECTURE.md"。
_EXPECTED_CAMPAIGN_SELF_HEAL_FIELDS = [
    "combat",
    "npc_memory",
    "npc_action_cooldown",
    "npc_action_log",
    "world_clock",
    "tick_ledger",
    "npc_world_queue",
    "world_action_proposals",
    "world_history",
]


def test_get_campaign_self_heal_fields_present():
    """静态核对 main.py 的 _get_campaign() 是否还在给这些字段做
    setdefault 自愈（旧存档兼容）。不实例化 DonghuangPlugin（依赖
    astrbot，这里装不了），只做源码级正则核对。"""
    source = MAIN_PY.read_text(encoding="utf-8")
    match = re.search(r"def _get_campaign\(self, group_id: str\).*?return self\.campaign\[group_id\]",
                       source, re.DOTALL)
    assert match, "main.py 里没找到 _get_campaign 函数，存档自愈逻辑可能被移除或改名了"
    body = match.group(0)

    missing = []
    for field in _EXPECTED_CAMPAIGN_SELF_HEAL_FIELDS:
        if f'setdefault("{field}"' not in body:
            missing.append(field)

    assert not missing, (
        f"_get_campaign() 里少了这些字段的自愈 setdefault：{missing}——"
        f"如果是有意移除，请同步更新本测试清单和 SYSTEM_ARCHITECTURE.md；"
        f"如果不是有意的，这是一次存档兼容性回归。"
    )
    print(f"✅ 测试11通过：_get_campaign() 仍对 {len(_EXPECTED_CAMPAIGN_SELF_HEAL_FIELDS)} "
          f"个旧存档字段做自愈 setdefault")


def test_player_profile_has_centralized_migration_function():
    """`_ensure_profile_defaults()` 现在是 player_profile 缺字段自愈的
    统一入口（整合了此前分散的 hp/mp/afflictions/combat_status setdefault
    以及五个 LONG-A migrate_profile_* 函数），在读档时（__init__ 里遍历
    全部已有 profile）和角色创建时都会调用。这个测试锁住"这个函数确实
    存在且被调用"，防止以后被误删又变回分散状态。"""
    source = MAIN_PY.read_text(encoding="utf-8")
    assert "def _ensure_profile_defaults(" in source, (
        "_ensure_profile_defaults() 不见了——player_profile 缺字段自愈"
        "又变回分散在各业务函数里的状态了吗？如果是有意为之，请更新本"
        "测试和 DATA_INTEGRITY_AUDIT.md 相关描述。"
    )
    assert "self._ensure_profile_defaults(profile)" in source, (
        "读档时的批量迁移循环看起来被改动了——确认 __init__ 里仍然对"
        "每份已有 profile 调用 _ensure_profile_defaults()。"
    )
    print("✅ 测试12通过：_ensure_profile_defaults() 作为统一入口存在，"
          "且在读档时被调用")


def test_doctor_load_warning_flags_corrupted_but_not_missing_file():
    """DonghuangPlugin._load_json 现在会在"文件存在但解析失败"时把文件名
    记进 self._save_load_warnings（供 /dh doctor 提示用），但"文件根本
    不存在"（全新安装的正常情况）不应该被当成警告。用真实 astrbot 框架
    （如果装了）或退回 stub 来实例化调用，两种情况都测。"""
    import types
    import importlib

    plugin_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(plugin_dir.parent))

    if "astrbot" not in sys.modules:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api_event = types.ModuleType("astrbot.api.event")
        astrbot_api_star = types.ModuleType("astrbot.api.star")

        class _Group:
            def __init__(self, func):
                self._func = func

            def command(self, name):
                def deco(f):
                    return f
                return deco

            def __call__(self, *a, **kw):
                return self._func(*a, **kw)

        class _EventMessageType:
            GROUP_MESSAGE = "group_message"

        class _Filter:
            EventMessageType = _EventMessageType

            @staticmethod
            def command_group(name):
                def deco(func):
                    return _Group(func)
                return deco

            @staticmethod
            def event_message_type(*a, **kw):
                def deco(func):
                    return func
                return deco

        class _AstrMessageEvent:
            pass

        class _Context:
            pass

        class _Star:
            def __init__(self, *a, **kw):
                pass

        def _register(*a, **kw):
            def deco(cls):
                return cls
            return deco

        class _Logger:
            def info(self, *a, **kw): pass
            def warning(self, *a, **kw): pass
            def error(self, *a, **kw): pass
            def debug(self, *a, **kw): pass

        astrbot_api_event.filter = _Filter()
        astrbot_api_event.AstrMessageEvent = _AstrMessageEvent
        astrbot_api_star.Context = _Context
        astrbot_api_star.Star = _Star
        astrbot_api_star.register = _register
        astrbot_api.logger = _Logger()

        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api
        sys.modules["astrbot.api.event"] = astrbot_api_event
        sys.modules["astrbot.api.star"] = astrbot_api_star

    m = importlib.import_module("astrbot_plugin_donghuang.main")

    class _FakeSelf:
        def __init__(self):
            self._save_load_warnings = []

    fake_self = _FakeSelf()

    with tempfile.TemporaryDirectory() as tmp:
        good_path = Path(tmp) / "good.json"
        good_path.write_text('{"a": 1}', encoding="utf-8")
        bad_path = Path(tmp) / "bad.json"
        bad_path.write_text('{this is not valid json', encoding="utf-8")
        missing_path = Path(tmp) / "missing.json"

        m.DonghuangPlugin._load_json(fake_self, good_path, {})
        m.DonghuangPlugin._load_json(fake_self, bad_path, {})
        m.DonghuangPlugin._load_json(fake_self, missing_path, {})

    assert fake_self._save_load_warnings == ["bad.json"], (
        f"应该只有 bad.json 被记为警告，实际记录：{fake_self._save_load_warnings}"
    )
    print("✅ 测试13通过：_load_json 只对'存在但解析失败'的文件记警告，"
          "文件不存在（正常场景）不会被误报")


def test_doctor_load_json_rejects_wrong_top_level_type():
    """DonghuangPlugin._load_json 现在会校验顶层类型跟 default 参数是否
    一致（DATA_INTEGRITY_AUDIT.md 第4.1节指出的缺口）：期待 dict 却读到
    list 时，当成"解析失败"处理——记警告 + 回退 default，不会把类型错误
    的数据原样透传给后续业务逻辑。"""
    import types
    import importlib

    plugin_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(plugin_dir.parent))

    if "astrbot" not in sys.modules:
        astrbot = types.ModuleType("astrbot")
        astrbot_api = types.ModuleType("astrbot.api")
        astrbot_api_event = types.ModuleType("astrbot.api.event")
        astrbot_api_star = types.ModuleType("astrbot.api.star")

        class _Group:
            def __init__(self, func):
                self._func = func

            def command(self, name):
                def deco(f):
                    return f
                return deco

            def __call__(self, *a, **kw):
                return self._func(*a, **kw)

        class _EventMessageType:
            GROUP_MESSAGE = "group_message"

        class _Filter:
            EventMessageType = _EventMessageType

            @staticmethod
            def command_group(name):
                def deco(func):
                    return _Group(func)
                return deco

            @staticmethod
            def event_message_type(*a, **kw):
                def deco(func):
                    return func
                return deco

        class _AstrMessageEvent:
            pass

        class _Context:
            pass

        class _Star:
            def __init__(self, *a, **kw):
                pass

        def _register(*a, **kw):
            def deco(cls):
                return cls
            return deco

        class _Logger:
            def info(self, *a, **kw): pass
            def warning(self, *a, **kw): pass
            def error(self, *a, **kw): pass
            def debug(self, *a, **kw): pass

        astrbot_api_event.filter = _Filter()
        astrbot_api_event.AstrMessageEvent = _AstrMessageEvent
        astrbot_api_star.Context = _Context
        astrbot_api_star.Star = _Star
        astrbot_api_star.register = _register
        astrbot_api.logger = _Logger()

        sys.modules["astrbot"] = astrbot
        sys.modules["astrbot.api"] = astrbot_api
        sys.modules["astrbot.api.event"] = astrbot_api_event
        sys.modules["astrbot.api.star"] = astrbot_api_star

    m = importlib.import_module("astrbot_plugin_donghuang.main")

    class _FakeSelf:
        def __init__(self):
            self._save_load_warnings = []

    fake_self = _FakeSelf()

    with tempfile.TemporaryDirectory() as tmp:
        wrong_type_path = Path(tmp) / "campaign.json"
        wrong_type_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        right_type_path = Path(tmp) / "action_log.json"
        right_type_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        result_dict = m.DonghuangPlugin._load_json(fake_self, wrong_type_path, {})
        result_list = m.DonghuangPlugin._load_json(fake_self, right_type_path, [])

    assert result_dict == {}, f"期待 dict 却读到 list，应回退默认值，实际：{result_dict}"
    assert result_list == [1, 2, 3], "期待 list 且读到 list，应正常返回解析结果"
    assert fake_self._save_load_warnings == ["campaign.json"], (
        f"应该只有类型不匹配的 campaign.json 被记为警告，实际：{fake_self._save_load_warnings}"
    )
    print("✅ 测试14通过：_load_json 会拦截顶层类型不匹配的存档，回退默认值并记警告")


if __name__ == "__main__":
    test_load_valid_json()
    test_load_bom_json()
    test_load_empty_file()
    test_load_missing_file()
    test_load_corrupted_json()
    test_load_wrong_top_level_type()
    test_load_non_utf8_bytes()
    test_atomic_save_round_trip()
    test_atomic_save_interrupted_write_does_not_corrupt_original()
    test_atomic_save_overwrite_replaces_cleanly()
    test_get_campaign_self_heal_fields_present()
    test_player_profile_has_centralized_migration_function()
    test_doctor_load_warning_flags_corrupted_but_not_missing_file()
    test_doctor_load_json_rejects_wrong_top_level_type()
    print("\n🎉 全部存档完整性测试通过！")
