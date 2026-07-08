"""
test_full_regression.py — 一键回归测试入口

作用：
  依次以子进程方式运行 tools/ 目录下所有 test_*.py 脚本（本文件除外），
  汇总每个脚本的通过/失败结果、耗时，并在最后输出总报告。

约定：
  每个 test_*.py 都是 standalone 脚本，assert 失败会抛出未捕获异常，
  子进程退出码非 0；全部通过则退出码为 0 并打印形如
  "🎉 全部 XXX 测试通过！" 的结尾行。本 runner 不解析该文本，只看退出码。

运行方式：
  py tools/test_full_regression.py
  py tools/test_full_regression.py -k npc      # 只跑文件名包含 npc 的测试
  py tools/test_full_regression.py --list      # 只列出会跑哪些文件（带分类标签）
  py tools/test_full_regression.py --no-by-category  # 关闭分类汇总，只看总数

新增测试文件后无需修改本文件：它按 test_*.py 通配自动发现，并按文件名
关键字自动分到 core/world/npc/player/environment/save 六个分类之一
（命中不了任何关键字的归入 core，见 classify()）。
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
SELF_NAME = Path(__file__).name

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


# 分类顺序即优先级：从上到下第一个命中文件名关键字的分类生效。
# "world" 放在关键字判定的最后一档，这样 test_world_environment.py 会先被
# "environment" 关键字命中，而不是被更宽泛的 "world" 关键字命中。
# 新增测试文件不需要在这里注册——命中不了任何关键字的一律归入 core。
_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("save", ("save",)),
    ("environment", ("environment",)),
    ("npc", ("npc",)),
    ("player", ("player",)),
    ("world", ("world", "faction")),
]
_CATEGORY_ORDER = ["core", "world", "npc", "player", "environment", "save"]


def classify(filename: str) -> str:
    name = filename.lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw in name for kw in keywords):
            return category
    return "core"


def discover_tests(keyword: str | None) -> list[Path]:
    files = sorted(TOOLS_DIR.glob("test_*.py"))
    files = [f for f in files if f.name != SELF_NAME]
    if keyword:
        files = [f for f in files if keyword.lower() in f.name.lower()]
    return files


def run_one(path: Path, timeout: float) -> dict:
    import os

    start = time.monotonic()
    # 子进程 stdout 未连接到真实控制台时，Windows 上 Python 会退回系统
    # ANSI 代码页（如 gbk），导致测试脚本里的 emoji（✅ 📌 🧪 等）打印时
    # 抛 UnicodeEncodeError。强制子进程使用 UTF-8，避免"测试逻辑本身没问题，
    # 但一自动化/一重定向就崩"的假失败。
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(TOOLS_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        elapsed = time.monotonic() - start
        return {
            "name": path.name,
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "elapsed": elapsed,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        elapsed = time.monotonic() - start
        return {
            "name": path.name,
            "ok": False,
            "returncode": None,
            "elapsed": elapsed,
            "stdout": e.stdout or "",
            "stderr": (e.stderr or "") + f"\n[超时：超过 {timeout}s]",
            "timed_out": True,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="东荒回归测试一键入口")
    parser.add_argument("-k", "--keyword", default=None, help="只运行文件名包含该关键字的测试")
    parser.add_argument("--list", action="store_true", help="只列出会运行的测试文件，不执行")
    parser.add_argument("--timeout", type=float, default=120.0, help="单个测试文件超时秒数（默认120s）")
    parser.add_argument("-v", "--verbose", action="store_true", help="即使通过也打印子进程 stdout")
    parser.add_argument("--by-category", action="store_true", default=True,
                         help="按 core/world/npc/player/environment/save 分类汇总（默认开启）")
    parser.add_argument("--no-by-category", dest="by_category", action="store_false",
                         help="关闭分类汇总，只看总数")
    args = parser.parse_args()

    tests = discover_tests(args.keyword)
    if not tests:
        print("没有发现匹配的测试文件。")
        return 1

    if args.list:
        for t in tests:
            print(f"[{classify(t.name)}] {t.name}")
        return 0

    print(f"发现 {len(tests)} 个测试文件，开始运行...\n")

    results = []
    total_start = time.monotonic()
    for t in tests:
        category = classify(t.name)
        print(f"▶ [{category}] {t.name} ...", end=" ", flush=True)
        result = run_one(t, args.timeout)
        result["category"] = category
        results.append(result)
        status = "✅ 通过" if result["ok"] else "❌ 失败"
        print(f"{status} ({result['elapsed']:.2f}s)")
        if args.verbose and result["ok"]:
            print(result["stdout"])
        if not result["ok"]:
            print(f"  --- {t.name} stdout ---")
            print(indent(result["stdout"]))
            print(f"  --- {t.name} stderr ---")
            print(indent(result["stderr"]))

    total_elapsed = time.monotonic() - total_start

    passed = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    print("\n" + "=" * 60)
    print("Regression")
    print("=" * 60)

    if args.by_category:
        for category in _CATEGORY_ORDER:
            in_cat = [r for r in results if r["category"] == category]
            if not in_cat:
                continue
            cat_passed = sum(1 for r in in_cat if r["ok"])
            label = category.capitalize()
            print(f"{label}: {cat_passed}/{len(in_cat)}")
        print("-" * 60)

    print(f"Total: {len(passed)}/{len(results)}　耗时 {total_elapsed:.2f}s")

    if failed:
        print("\n失败列表：")
        for r in failed:
            reason = "超时" if r["timed_out"] else f"退出码 {r['returncode']}"
            print(f"  - [{r['category']}] {r['name']} ({reason})")
        print("=" * 60)
        return 1

    print("🎉 全部回归测试通过！")
    print("=" * 60)
    return 0


def indent(text: str, prefix: str = "    ") -> str:
    if not text:
        return prefix + "(空)"
    return "\n".join(prefix + line for line in text.splitlines())


if __name__ == "__main__":
    sys.exit(main())
