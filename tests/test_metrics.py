"""口径回归测试：这三个用例挡住过“随机基线 42%”那类假分。

每个用例对应一处官方口径，改坏了会立刻红。
"""
import pytest

from ib_lab import metrics


def test_passkey_takes_first_integer():
    assert metrics.score("passkey", "The pass key is 71432.", ["71432"]) == 1.0
    assert metrics.score("passkey", "The pass key is 71432, not 999.", ["71432"]) == 1.0
    assert metrics.score("passkey", "I don't know.", ["71432"]) == 0.0


def test_math_calc_is_prefix_ratio_not_all_or_nothing():
    assert metrics.score("math_calc", "1 2 3", ["1", "2", "3"]) == 1.0
    assert metrics.score("math_calc", "1 2 9", ["1", "2", "3"]) == pytest.approx(2 / 3)
    assert metrics.score("math_calc", "9 9 9", ["1", "2", "3"]) == 0.0
    # 只输出前两个数：分母仍是答案长度 3
    assert metrics.score("math_calc", "1 2", ["1", "2", "3"]) == pytest.approx(2 / 3)


def test_choice_ground_truth_needs_letter():
    options = ["use put", "use get", "use post", "use delete"]
    golds = metrics.make_ground_truth("code_debug", ["use get"], options)
    assert golds == ["use get", "B"]
    assert metrics.score("code_debug", "Option B", golds) == 1.0
    assert metrics.score("code_debug", "Answer: A", golds) == 0.0


def test_choice_letter_scored_by_letter_only():
    golds = metrics.make_ground_truth("longbook_choice_eng", ["Walking Georgie"],
                                      ["Walking Georgie", "Running", "Sleeping", "Eating"])
    assert golds[1] == "A"
    assert metrics.score("longbook_choice_eng", "A", golds) == 1.0
    assert metrics.score("longbook_choice_eng", "C", golds) == 0.0
