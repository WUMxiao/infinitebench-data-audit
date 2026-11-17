"""数据缺陷分诊：P1–P7，每类一个问题 + 一个可量化证据。

P1 输入模板化      P5 长度超窗 / 截断
P2 上下文复用      P6 指标与任务不匹配
P3 标注口径矛盾    P7 元数据与数据不一致
P4 零模型可解

产出（第 2 步实现）：
    out/problem_summary.csv
"""


def run(cfg) -> int:
    raise NotImplementedError("第 2 步实现：迁移 diagnose_problems.py")
