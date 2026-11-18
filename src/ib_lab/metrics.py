"""与 InfiniteBench 官方 src/compute_scores.py + eval_utils.get_answer 对齐的评测。

为什么要单独一个文件：按 README 自己写指标，随机基线在 Math.Calc 上能拿到 42%，
而官方口径下应该接近 0。指标实现错了，整张实验表都是废的。

官方口径要点：
1) 选择题 (code_debug / longbook_choice_eng) 的 ground_truth 要转成 [选项文本, 字母]；
   直接把数据里的 answer 丢给打分器会 IndexError。
2) passkey / number_string: 取预测里出现的第一个整数。
3) kv_retrieval: 答案 token 必须出现在预测的词表里。
4) code_run: 取预测的最后一个词转 int。
5) code_debug: 先找最后一个单独出现的 A-J 字母，再退化到前缀匹配。
6) math_find: 取预测里第一个数字，按数值比较。
7) math_calc: 最长正确前缀 / 答案长度（不是全对才算对）。
8) longdialogue_qa_eng: 任一参考答案是预测的子串。
9) longbook_choice_eng: 字母命中。
10) longbook_qa_*: token-F1（中文按字切）；longbook_sum_eng: rougeLsum。
"""
import re
import string
from collections import Counter

_CN_PUNC = "！？｡。＂＃＄％＆＇（）＊＋，－／：；＜＝＞＠［＼］＾＿｀｛｜｝～｟｠｢｣､、〃》「」『』【】〔〕〖〗〘〙〚〛〜〝〞〟〰〾〿–—‘’‛“”„‟…‧﹏."
_ROUGE = None
_PUNCT = ["\n", ":", '"', "'", ".", ",", "?", "!", "{", "}"]


def _rouge():
    """延迟导入：只有 longbook_sum_eng 需要 rouge_score。"""
    global _ROUGE
    if _ROUGE is None:
        from rouge_score import rouge_scorer
        _ROUGE = rouge_scorer.RougeScorer(["rougeLsum"], use_stemmer=True)
    return _ROUGE


def normalize_answer(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\b(a|an|the)\b", " ", s)
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    return " ".join(s.split())


def normalize_zh_answer(s: str) -> str:
    s = s.lower()
    s = "".join(ch for ch in s if ch not in set(string.punctuation + _CN_PUNC))
    return "".join(s.split())


def _f1(a, b) -> float:
    common = Counter(a) & Counter(b)
    same = sum(common.values())
    if same == 0:
        return 0.0
    p, r = same / len(a), same / len(b)
    return 2 * p * r / (p + r)


def qa_f1(pred: str, golds, zh: bool = False) -> float:
    norm = normalize_zh_answer if zh else normalize_answer
    best = 0.0
    for g in golds:
        a = list(norm(pred)) if zh else norm(pred).split()
        b = list(norm(g)) if zh else norm(g).split()
        if a and b:
            best = max(best, _f1(a, b))
    return best


# 这些任务的参考答案可能用 ';' 分隔多个可接受答案，例如 ['four;4']
# 官方数据里 answer 是 list[str]，但个别元素是 "a;b" 的合并写法。
SPLIT_TASKS = {"longbook_qa_eng", "longbook_qa_chn", "longdialogue_qa_eng"}


def make_ground_truth(task: str, answer: list, options: list) -> list:
    """复刻 eval_utils.get_answer：选择题要补上字母；QA 类要拆多答案。"""
    if task in SPLIT_TASKS:
        out = []
        for a in answer:
            parts = [p.strip() for p in str(a).split(";") if p.strip()]
            out.extend(parts or [a])
        return out
    if task in ("code_debug", "longbook_choice_eng"):
        opts = "ABCD"
        if len(answer) == 2 and answer[1] in list("ABCD"):
            return answer
        a0 = answer[0] if answer else ""
        try:
            return [a0, opts[options.index(a0)]]
        except ValueError:
            return [a0, ""]
    return answer


def first_int_match(pred: str) -> str:
    for item in re.split("[^0-9]", pred):
        if item != "":
            return item
    return ""


def _clean_words(pred: str) -> list:
    for c in _PUNCT:
        pred = pred.replace(c, " ")
    return pred.split()


def score(task: str, pred: str, golds: list, options=None) -> float:
    pred = pred or ""
    gold = golds[0] if golds else ""

    if task in ("passkey", "number_string"):
        return float(first_int_match(pred) == gold)

    if task == "kv_retrieval":
        return float(gold in _clean_words(pred))

    if task == "code_run":
        words = _clean_words(pred.strip().replace("`", " "))
        if not words:
            return 0.0
        try:
            return float(int(words[-1]) == int(gold))
        except (ValueError, TypeError):
            return 0.0

    if task == "code_debug":
        label_c = golds[1] if len(golds) > 1 else ""
        fn_name = golds[0] if golds else ""
        m = re.search(r"\b[A-J]\b(?!.*\b[A-J]\b)", pred.strip())
        if m and label_c and m.group(0) == label_c:
            return 1.0
        p = pred.strip()
        for c in ["\n", "`", "'", '"', "-", "*", "Option", "option"]:
            p = p.replace(c, " ")
        while "  " in p:
            p = p.replace("  ", " ")
        if (label_c and p.startswith(label_c)) or (fn_name and p.startswith(fn_name)):
            return 1.0
        return 0.0

    if task == "math_find":
        m = re.search(r"\d+\.\d+|\d+", pred)
        if not m:
            return 0.0
        try:
            if isinstance(gold, float) or "." in str(gold):
                return float(m.group(0)) == float(gold)
            return int(m.group(0)) == int(float(gold))
        except (ValueError, TypeError):
            return 0.0

    if task == "math_calc":
        label = golds
        try:
            nums = [int(x) for x in re.split("[^0-9]", pred) if x != ""]
        except ValueError:
            return 0.0
        cnt = 0
        for i in range(len(label)):
            if i >= len(nums):
                break
            if int(label[i]) == nums[i]:
                cnt += 1
            else:
                break
        return cnt / len(label) if label else 0.0

    if task == "longdialogue_qa_eng":
        return float(any(g.upper() in pred.upper() for g in golds))

    if task == "longbook_sum_eng":
        if not pred.strip():
            return 0.0
        return max(_rouge().score(g, pred)["rougeLsum"].fmeasure for g in golds)

    if task == "longbook_qa_eng":
        return qa_f1(pred, golds)

    if task == "longbook_qa_chn":
        return qa_f1(pred, golds, zh=True)

    if task == "longbook_choice_eng":
        label_c = golds[1] if len(golds) > 1 else ""
        p = pred.strip()
        m = re.search(r"\b[A-D]\b(?!.*\b[A-D]\b)", p)
        if m and label_c and m.group(0) == label_c:
            return 1.0
        if p and p[0].upper() in list("ABCD") and label_c:
            return float(p[0].upper() == label_c)
        return 0.0

    return float(normalize_answer(pred) == normalize_answer(gold))
