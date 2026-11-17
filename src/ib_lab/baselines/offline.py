"""离线基线：不需要模型、不需要 key，用来建立 chance level。

五个基线（第 3 步实现）：
    random         随机猜 / 随机抽词      —— 绝对下界
    first_option   永远选 A               —— 选项位置偏置
    majority       永远猜最高频标签        —— 标签先验
    question_echo  把问题里最长的词当答案  —— 答案是否被问题泄露
    regex_read     正则从上下文抽         —— 任务是否只是表层匹配

产出：out/baseline_results.csv + out/preds/<task>.csv
"""


def run(cfg, tasks=None) -> int:
    raise NotImplementedError("第 3 步实现：迁移 run_baseline.py")
