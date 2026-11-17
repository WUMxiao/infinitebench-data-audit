"""InfiniteBench 数据体检工具包。

模块职责（一个模块一件事）：
    data       读取与规范化，不做统计
    metrics    官方评测口径，一个函数一个任务
    analyze    体检：长度/模板/复用/答案形态
    diagnose   数据缺陷 P1–P7
    baselines  离线基线 + API 基线
    errors     模型错题分类
    table      汇总成实验表
"""

__version__ = "0.1.0"
