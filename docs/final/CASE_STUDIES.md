# 三个代表性案例

## 案例一：正确 Finding——零分母保护回归

### 输入

Phase 1 的固定 Fixture 把：

```python
if denominator == 0:
```

错误改成：

```python
if numerator == 0:
```

这导致 `ratio(5, 0)` 不再走保护分支，而是抛出 `ZeroDivisionError`。

### Agent 输出

- 文件与行号：`calculator.py:2`
- Assessment：`confirmed`
- Category：`correctness`
- 模型严重度：`critical`
- 预期严重度：`high`
- Decision：`REQUEST_CHANGES`

### 复核

Finding 正确定位根因，真实 Fixture 测试返回码为 1，误报和重复 Finding 均为 0。唯一偏差是严重度高估一级。

### 面试价值

这个案例说明项目不是只让模型输出自然语言，而是把 Finding 绑定到 Commit、Diff changed line 和真实测试结果。它同时展示了为什么还要单独统计严重度校准。

## 案例二：合同失败——模型调用成功不等于可用 Review

### 输入

Phase 2 的逻辑错误题与 Phase 1 使用同类零分母回归，但作为三题 Smoke 的一部分独立运行。

### 实际结果

模型调用发生了，但响应在 `REVIEW_VALIDATION` 阶段违反结构化 Review 合同：

```text
failure_stage=REVIEW_VALIDATION
failure_reason=REVIEW_CONTRACT_FAILURE
```

Runner 只保存脱敏 `failure.json`，没有保存不合规模型正文，也没有补跑。

### 统计处理

- 合法 Review：否
- 人工核心缺陷召回：保守记为未召回
- Finding precision：不把不可审计输出计入分母
- 自动重试：0

### 面试价值

这个案例说明“模型可能理解了问题”不能代替可消费的工程输出。只要结构合同失败，系统就不能发布或事后根据猜测给模型补分。这是失败关闭与可审计性的实际体现。

## 案例三：错误锚点——changed-line 合法仍可能语义错误

### 输入

Phase 4 受控 PR 新增：

```python
def average(values: list[float]) -> float:
    """Return the arithmetic mean of a non-empty sequence."""
    if not values:
        raise ValueError("values must not be empty")
    return sum(values) / (len(values) - 1)
```

真正缺陷是最后一行除数写成 `len(values) - 1`，在冻结 Diff 中位于第 8 行。

### Agent 与 Payload

模型 Evidence 正确描述了除数错误，但 Finding 填写：

```text
file=examples/phase4_average.py
line=7
```

第 7 行属于 changed-line 集合，所以现有合同通过；但第 7 行实际是 `raise ValueError(...)`。

### 远端结果

- GitHub Review ID：`5020924942`
- 行内评论 ID：`3854679061`
- 写请求：1
- 自动重试：0
- 远端评论 position：7
- 真正缺陷行：8

发布后回读首先因 GitHub 返回 `position/original_position`、而验证器期待 `line/side`，触发 `REMOTE_COMMENTS_MISMATCH`。人工对照 Diff 后进一步确认这是实际错误锚点，而不仅是 API 字段差异。

### 处理决定

- 保留远端错误 Review；
- 不编辑、不删除、不补发；
- 原始 `failure.json` 不改写；
- 另存只读人工审计摘要；
- Phase 4 标记为 `COMPLETED_WITH_VERIFICATION_FAILURE`；
- 禁止重试，Phase 5 暂不启动。

### 面试价值

这是项目最重要的负结果。它说明两层校验必须区分：

1. 结构锚点校验：文件和行是否属于 Diff；
2. 语义锚点校验：Evidence 中描述的代码片段是否真的位于该行。

项目完成了第一层，但真实写入暴露第二层缺口。保留错误结果比补发一条正确评论更能说明工程判断和实验诚信。
