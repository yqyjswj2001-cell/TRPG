# -*- coding: utf-8 -*-
"""
数据文件体检脚本
================
干什么用的:
  东荒修仙有大量 JSON 数据文件(功法、法宝、NPC、区域……)。
  这些文件只要有一处多写/少写一个逗号、括号没配对,
  机器人读取时就可能直接报错甚至启动失败。
  这个脚本会把指定文件夹里的所有 JSON 文件挨个打开检查,
  哪个文件、第几行坏了,一目了然。

怎么用(在自己电脑上也能跑):
  python scripts/check_data.py

新手只需要改一个地方:下面的 DATA_DIRS,
把它改成你自己存放数据文件的文件夹名字。
"""

import json
import sys
from pathlib import Path

# ============ 你只需要改这里(开始) ============

# 存放游戏数据的文件夹,可以写多个。
# 按你的实际项目改,比如 ["data", "resources/功法库"]。
DATA_DIRS = ["data"]

# (进阶功能,可以先不管)必填字段检查:
# 如果某类文件里的每一条记录都必须有某些字段,可以在这里登记。
# 例子:文件名里带"功法"的文件,每条记录必须有"名称"和"品阶"。
# REQUIRED_FIELDS = {
#     "功法": ["名称", "品阶"],
#     "法宝": ["名称", "品阶", "属性"],
# }
REQUIRED_FIELDS = {}

# ============ 你只需要改这里(结束) ============


def iter_records(data):
    """把 JSON 内容摊平成一条条记录,方便做必填字段检查。"""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item
    elif isinstance(data, dict):
        # 形如 {"编号1": {...}, "编号2": {...}} 的字典
        for value in data.values():
            if isinstance(value, dict):
                yield value


def main():
    problems = []
    checked = 0

    for folder in DATA_DIRS:
        root = Path(folder)
        if not root.exists():
            print(f"提示:找不到文件夹 [{folder}],请打开本脚本修改最上方的 DATA_DIRS。")
            continue

        for file in sorted(root.rglob("*.json")):
            checked += 1

            # 检查一:文件能不能正常打开、JSON 格式对不对
            # 这里用 utf-8-sig 而不是 utf-8:
            # 有些编辑器(比如 Windows 记事本)保存 UTF-8 文件时会在开头
            # 偷偷加一个看不见的标记(叫 BOM),内容其实是好的,
            # 但普通 utf-8 读取方式会被这个标记绊一下、误判成"格式坏了"。
            # utf-8-sig 遇到这个标记会自动跳过,遇不到也完全不受影响,
            # 兼容两种情况,不会漏判真正的格式错误。
            try:
                data = json.loads(file.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as e:
                problems.append(f"[格式坏了] {file} 第 {e.lineno} 行附近:{e.msg}")
                continue
            except UnicodeDecodeError:
                problems.append(f"[编码不对] {file}:不是 UTF-8 编码,建议用 UTF-8 重新保存。")
                continue

            # 检查二:必填字段抽查(只有你在上面 REQUIRED_FIELDS 登记过才会检查)
            for keyword, fields in REQUIRED_FIELDS.items():
                if keyword in file.name:
                    for i, record in enumerate(iter_records(data)):
                        missing = [f for f in fields if f not in record]
                        if missing:
                            problems.append(
                                f"[缺字段] {file} 第 {i + 1} 条记录缺少:{'、'.join(missing)}"
                            )

    print(f"共检查 {checked} 个 JSON 文件。")
    if checked == 0:
        print("注意:一个文件都没检查到,数据体检目前是空转状态,记得改 DATA_DIRS。")

    if problems:
        print(f"发现 {len(problems)} 个问题:")
        for p in problems:
            print("  -", p)
        sys.exit(1)  # 用"失败"状态退出,让 GitHub 显示红叉

    print("全部数据文件体检通过。")


if __name__ == "__main__":
    main()
