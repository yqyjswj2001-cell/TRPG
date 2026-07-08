# -*- coding: utf-8 -*-
"""
数值曲线体检脚本(平衡性哨兵)
================================
干什么用的:
  这个脚本判断不了"好不好玩",但能算出一件客观的事:
  同一个品阶/境界分组里,数值是不是明显有一个离群的,
  比如某件"下品法宝"的攻击力居然比"极品法宝"还高。
  这种情况大概率是策划失误或者手滑打错数字,不一定是
  你故意设计的"隐藏神器",所以脚本会把它列出来提醒你去看一眼。

  重要:这不是"对错检查",是"提醒检查"。
  它从不会因为发现离群项就报错让流程失败(不会亮红叉),
  只会打印出来给你参考——最终"这个数值到底合不合理"
  永远是你自己判断,机器只负责替你把可疑的地方标出来,
  省得你几百个条目一条条自己翻。

怎么用(在自己电脑上也能跑):
  python scripts/check_balance.py

新手只需要改下面"你只需要改这里"那一块,
把它配置成符合你数据文件真实字段名的样子。
"""

import json
import statistics
from pathlib import Path

# ============ 你只需要改这里(开始) ============

# 每一项配置代表"一类要检查的数值曲线"。
# file: 数据文件路径(相对于仓库根目录)
# group_by: 用来分组的字段名,比如"品阶"或"境界"
# value_field: 要比较强弱的数值字段名,比如"攻击力"或"威力"
# name_field: 用来在提醒里显示条目名字的字段名,比如"名称"
BALANCE_CHECKS = [
    # 示例,按你项目真实字段改:
    # {
    #     "file": "data/法宝库.json",
    #     "group_by": "品阶",
    #     "value_field": "攻击力",
    #     "name_field": "名称",
    # },
    # {
    #     "file": "data/功法库.json",
    #     "group_by": "品阶",
    #     "value_field": "威力",
    #     "name_field": "名称",
    # },
]

# 离群判定的敏感度:数值超出"该分组平均值 ± 这个倍数的标准差"就会被标记。
# 数字越小抓得越严格(提醒越多),数字越大越宽松(只抓特别离谱的)。
# 新手不熟悉统计概念的话,先保持默认值 2.0 就好。
SENSITIVITY = 2.0

# ============ 你只需要改这里(结束) ============


def load_records(file_path):
    """把 JSON 内容统一摊平成一条条记录(字典列表)。"""
    data = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.values())
    return []


def check_one(config):
    file_path = config["file"]
    group_field = config["group_by"]
    value_field = config["value_field"]
    name_field = config.get("name_field", "名称")

    path = Path(file_path)
    if not path.exists():
        print(f"提示:找不到文件 [{file_path}],跳过这一项检查。")
        return []

    records = load_records(path)

    # 按分组字段(比如"品阶")把记录分桶
    groups = {}
    for r in records:
        if group_field not in r or value_field not in r:
            continue
        groups.setdefault(r[group_field], []).append(r)

    warnings = []
    for group_name, items in groups.items():
        if len(items) < 3:
            continue  # 样本太少算不出有意义的平均和标准差,跳过

        values = [item[value_field] for item in items]
        avg = statistics.mean(values)
        try:
            stdev = statistics.stdev(values)
        except statistics.StatisticsError:
            continue
        if stdev == 0:
            continue  # 这组数值全都一样,没有离群可言

        threshold = SENSITIVITY * stdev
        for item in items:
            v = item[value_field]
            if abs(v - avg) > threshold:
                方向 = "偏强" if v > avg else "偏弱"
                name = item.get(name_field, "(未命名)")
                warnings.append(
                    f"[{file_path}] 分组「{group_name}」里的「{name}」"
                    f"{value_field}={v},该分组平均约 {avg:.1f},明显{方向},建议人工复核。"
                )
    return warnings


def main():
    if not BALANCE_CHECKS:
        print("还没有配置任何数值曲线检查项,请打开本脚本修改 BALANCE_CHECKS。")
        return

    all_warnings = []
    for config in BALANCE_CHECKS:
        all_warnings.extend(check_one(config))

    if not all_warnings:
        print("数值曲线体检完成,没有发现明显离群项。")
        return

    print(f"数值曲线体检完成,发现 {len(all_warnings)} 处建议人工复核的离群项(仅提醒,不影响流程):")
    for w in all_warnings:
        print("  -", w)


if __name__ == "__main__":
    main()
