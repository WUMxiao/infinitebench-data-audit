# 失败分析：为什么没拿满

样本：160 条 API 预测（gpt-6-sol，每任务 20 条）

## 失败构成

| 类别 | 含义 | 条数 | 占比 |
|---|---|---|---|
| F0 | API 错误 | 1 | 0.6% |
| F1 | 检索失败 | 9 | 5.6% |
| F2 | 截断丢失 | 1 | 0.6% |
| F3 | 格式失败 | 18 | 11.2% |
| F4 | 拒答 | 5 | 3.1% |
| F5 | 其他(需人工) | 40 | 25.0% |
| F6 | 输出不完整 | 4 | 2.5% |
| OK | 答对 | 82 | 51.2% |

## F3 格式失败（18 条）

- `code_debug` / `57`　gold=`['FilteredResourceObserver._search_resource_creations', 'C']`
  - 模型输出：``FilteredResourceObserver._search_resource_creations``
- `code_debug` / `120`　gold=`['Host.deploy', 'A']`
  - 模型输出：``Host.deploy``
- `code_debug` / `376`　gold=`['_ConstOpMixin.gep', 'D']`
  - 模型输出：``_ConstOpMixin.gep``

## F4 拒答（5 条）

- `longbook_choice_eng` / `276`　gold=`['Ser Hugh, a former squire', 'B']`
  - 模型输出：`The passage does not say.`
- `number_string` / `264`　gold=`['4955588855']`
  - 模型输出：`No digits are present.`
- `number_string` / `334`　gold=`['1130000042']`
  - 模型输出：`No digits.`

## F2 截断丢失（1 条）

- `longbook_qa_chn` / `188`　gold=`['救星行动']`
  - 模型输出：`黑暗战役中。`

## F1 检索失败（9 条）

- `code_debug` / `125`　gold=`['Channel._get', 'B']`
  - 模型输出：``kombu.pidbox.Mailbox._broadcast``
- `longbook_choice_eng` / `128`　gold=`['Doctor', 'C']`
  - 模型输出：`Physician`
- `longbook_choice_eng` / `300`　gold=`['A coffin', 'A']`
  - 模型输出：`Horatio’s coffin, repurposed as a life buoy.`

## F5 其他(需人工)（40 条）

- `code_debug` / `55`　gold=`['ChangeCollector.get_changed', 'A']`
  - 模型输出：`get_names_from_file`
- `longbook_choice_eng` / `100`　gold=`['A silver button from his jacket', 'D']`
  - 模型输出：`A silver button from his coat.`
- `longbook_choice_eng` / `274`　gold=`['Move quickly, since more players are entering the game.', 'C']`
  - 模型输出：`That Ned Stark, the new Hand of the King, could be killed as his predecessor was.`

## F0 API 错误（1 条）

- `longbook_qa_chn` / `124`　gold=`['毛南生']`
  - 模型输出：``

## 复现

```bash
python -m ib_lab baseline api --model gpt-6-sol --n 10
python -m ib_lab failure
```
