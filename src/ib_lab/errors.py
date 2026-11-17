"""模型错题分类（第 6 步实现）。

类别草案：
    E1 检索失败     答案在文中但没找到
    E2 截断丢失     答案被截断砍掉
    E3 格式失败     输出无法解析成答案
    E4 推理错误     找到证据但算错/推错
    E5 聚合错误     多跳/指代/汇总出错
    E6 拒答/空输出  模型明确不答

规则可判 E2/E3/E6/E1，E4/E5 需人工抽检 50 条。
"""


def classify(task: str, item: dict, pred: str, gold: str) -> str:
    raise NotImplementedError("第 6 步实现")


def run(cfg) -> int:
    raise NotImplementedError("第 6 步实现：对 out/api 的预测做错题分类")
