"""
asset_loader.py — 统一资产读取层

本模块是整个插件读取资产数据的唯一合法入口。
任何地方禁止直接 open(json/jsonl) 读取资产文件，必须通过本模块。

核心原则：
  1. 默认使用 utf-8-sig 编码，兼容 UTF-8 BOM
  2. 所有异常必须记录日志，禁止静默吞掉
  3. 读取失败时返回合理的默认值，不抛异常到业务层
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Generator, List, Optional, Union

logger = logging.getLogger(__name__)

# 默认编码：utf-8-sig 兼容带 BOM 的文件
_DEFAULT_ENCODING = "utf-8-sig"


# ──────────────────────────────────────────────
#  基础读取函数
# ──────────────────────────────────────────────

def read_text(path: Union[str, Path], encoding: str = _DEFAULT_ENCODING) -> str:
    """读取文本文件，默认 utf-8-sig 兼容 BOM。

    Returns:
        文件全文内容。文件不存在或读取失败时返回空字符串并记录日志。
    """
    path = Path(path)
    try:
        if not path.exists():
            logger.warning(f"[AssetLoader] 文件不存在：{path}")
            return ""
        return path.read_text(encoding=encoding)
    except Exception as e:
        logger.error(f"[AssetLoader] 读取文本失败 {path}：{e}")
        return ""


def load_json(path: Union[str, Path], encoding: str = _DEFAULT_ENCODING) -> Any:
    """读取 JSON 文件并解析为 Python 对象。

    Returns:
        解析后的 Python 对象（dict/list 等）。
        文件不存在或解析失败时返回空列表 [] 并记录日志。
    """
    path = Path(path)
    try:
        if not path.exists():
            logger.warning(f"[AssetLoader] JSON 文件不存在：{path}")
            return []
        text = path.read_text(encoding=encoding)
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"[AssetLoader] JSON 解析失败 {path}：{e}")
        return []
    except Exception as e:
        logger.error(f"[AssetLoader] 读取 JSON 失败 {path}：{e}")
        return []


def load_json_with_default(
    path: Union[str, Path],
    default: Any,
    encoding: str = _DEFAULT_ENCODING,
) -> Any:
    """读取 JSON 文件，失败时返回指定的默认值。

    专门用于替换 main.py 中已有的 _load_json(path, default) 模式。
    """
    path = Path(path)
    try:
        if not path.exists():
            return default
        text = path.read_text(encoding=encoding)
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"[AssetLoader] JSON 解析失败 {path}：{e}")
        return default
    except Exception as e:
        logger.error(f"[AssetLoader] 读取 JSON 失败 {path}：{e}")
        return default


def iter_jsonl(
    path: Union[str, Path],
    encoding: str = _DEFAULT_ENCODING,
) -> Generator[dict, None, None]:
    """逐行迭代 JSONL 文件，每行解析为一个 dict。

    遇到无法解析的行时记录警告并跳过该行（不中断整体迭代）。
    文件不存在时记录警告并立即结束迭代。

    Yields:
        每行解析出的 dict 对象。
    """
    path = Path(path)
    try:
        if not path.exists():
            logger.warning(f"[AssetLoader] JSONL 文件不存在：{path}")
            return
        with path.open(encoding=encoding) as f:
            line_no = 0
            for line in f:
                line_no += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(
                        f"[AssetLoader] JSONL 第 {line_no} 行解析失败 {path}：{e}"
                    )
                    continue
    except Exception as e:
        logger.error(f"[AssetLoader] 读取 JSONL 失败 {path}：{e}")


def load_jsonl(
    path: Union[str, Path],
    encoding: str = _DEFAULT_ENCODING,
) -> List[dict]:
    """读取整个 JSONL 文件，返回解析后的列表。

    等价于 list(iter_jsonl(...))，但在日志中会报告总共成功解析了多少条。
    """
    path = Path(path)
    result = []
    try:
        if not path.exists():
            logger.warning(f"[AssetLoader] JSONL 文件不存在：{path}")
            return []
        count = 0
        for item in iter_jsonl(path, encoding=encoding):
            result.append(item)
            count += 1
        logger.debug(f"[AssetLoader] 加载 JSONL {path}：{count} 条记录")
        return result
    except Exception as e:
        logger.error(f"[AssetLoader] 加载 JSONL 失败 {path}：{e}")
        return result


# ──────────────────────────────────────────────
#  辅助查询函数
# ──────────────────────────────────────────────

def exists(path: Union[str, Path]) -> bool:
    """检查资产文件是否存在。"""
    return Path(path).exists()


def list_assets(
    directory: Union[str, Path],
    pattern: str = "*",
    suffix: Optional[str] = None,
) -> List[Path]:
    """列出目录下匹配条件的资产文件。

    Args:
        directory: 目录路径
        pattern: glob 匹配模式，默认 "*"
        suffix: 文件后缀过滤，如 ".jsonl"、".json"

    Returns:
        排序后的 Path 列表。目录不存在时返回空列表并记录警告。
    """
    directory = Path(directory)
    if not directory.exists():
        logger.warning(f"[AssetLoader] 目录不存在：{directory}")
        return []
    if not directory.is_dir():
        logger.warning(f"[AssetLoader] 不是目录：{directory}")
        return []
    paths = sorted(directory.glob(pattern))
    if suffix:
        paths = [p for p in paths if p.suffix == suffix]
    return paths


def glob_jsonl(
    directory: Union[str, Path],
    pattern: str = "*.jsonl",
) -> List[Path]:
    """列出目录下匹配的 JSONL 文件（快捷方式）。"""
    return list_assets(directory, pattern, suffix=".jsonl")


def glob_json(
    directory: Union[str, Path],
    pattern: str = "*.json",
) -> List[Path]:
    """列出目录下匹配的 JSON 文件（快捷方式）。"""
    return list_assets(directory, pattern, suffix=".json")
