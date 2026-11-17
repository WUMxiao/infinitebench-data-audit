"""数据读取与规范化：只负责“把 jsonl 变成样本对象”，不做统计。

实现放到第 2 步（迁移 analyze_data.py 的流式读取逻辑）。
"""
import json
from pathlib import Path
from typing import Iterable, Iterator


def iter_jsonl(path: Path) -> Iterator[dict]:
    """逐行读 jsonl，不把整个文件读进内存（单文件最大 862 MB）。"""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def normalize_answers(raw) -> list:
    """answer 字段实际有 list[str] / str / int / float 三种形态，统一成 list[str]。"""
    raise NotImplementedError("第 2 步实现")


def gold_letter(answer, options) -> str:
    """选择题：把 gold 答案对回选项字母；对不上返回空串。"""
    raise NotImplementedError("第 2 步实现")


def est_tokens(text: str) -> int:
    """粗估 token：CJK 约 1.6 字/token，其余约 4 字符/token。只看量级。"""
    raise NotImplementedError("第 2 步实现")


def truncate_middle(text: str, max_tokens: int) -> tuple:
    """按官方 middle 策略保头尾、砍中间；返回 (截断后文本, 保留比例)。"""
    raise NotImplementedError("第 2 步实现")


def load_task(cfg, task: str) -> Iterable[dict]:
    """读取某个任务的全部样本，补上 task 字段。"""
    raise NotImplementedError("第 2 步实现")
