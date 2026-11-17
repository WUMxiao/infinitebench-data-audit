"""数据读取与规范化：只负责“把 jsonl 变成样本对象”，不做统计。"""
import hashlib
import json
import re
from pathlib import Path
from typing import Iterator

_CJK = re.compile(r"[\u4e00-\u9fff]")


def iter_jsonl(path: Path) -> Iterator[dict]:
    """逐行读 jsonl，不把整个文件读进内存（单文件最大 862 MB）。"""
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def normalize_answers(raw) -> list:
    """answer 字段实际有 list[str] / str / int / float 三种形态，统一成 list[str]。"""
    if raw is None:
        return []
    if isinstance(raw, (str, int, float)):
        return [str(raw)]
    return [str(x) for x in raw]


def gold_letter(answer, options) -> str:
    """选择题：把 gold 答案对回选项字母；对不上返回空串。"""
    if not options:
        return ""
    a = (answer or "").strip().lower()
    for i, opt in enumerate(options):
        o = (opt or "").strip().lower()
        if o == a or o.startswith(a + ".") or a.startswith(o):
            return chr(ord("A") + i)
    return ""


def est_tokens(text: str) -> int:
    """粗估 token：CJK 约 1.6 字/token，其余约 4 字符/token。只看量级。"""
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    other = len(text) - cjk
    return int(cjk / 1.6 + other / 4)


def truncate_middle(text: str, max_tokens: int) -> tuple:
    """按官方 middle 策略保头尾、砍中间。

    官方按 token 截断；这里按字符近似（est_tokens 的逆），只用于“保住多少原文”的估计。
    返回 (截断后文本, 保留比例)；未超预算时比例为 1.0 且原文不变。
    """
    total = est_tokens(text)
    if total <= max_tokens or total == 0:
        return text, 1.0
    keep_ratio = max_tokens / total
    keep_chars = int(len(text) * keep_ratio)
    head = keep_chars // 2
    tail = keep_chars - head
    return text[:head] + "\n...[middle truncated]...\n" + text[-tail:], keep_ratio


def sha1_16(text: str) -> str:
    """上下文指纹：必须用全文哈希，用前 N 字符会把填充文本相同的样本误判成复用。"""
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]


def load_task(cfg, task: str) -> Iterator[dict]:
    """读取某个任务的全部样本，统一补上 task 字段。"""
    path = cfg.data_dir / f"{task}.jsonl"
    if not path.exists():
        return
    for d in iter_jsonl(path):
        d["task"] = task
        yield d
