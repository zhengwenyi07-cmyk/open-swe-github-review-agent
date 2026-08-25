# Phase 2 结果：三题 Diff Review Smoke

> 最终状态：`COMPLETED_WITH_FAILURES`
>
> 本阶段已执行一次且不补跑。八份原始产物保持不变；人工语义复核与证据解释仅记录在本文。

## 1. 阶段门禁

```text
phase_status=COMPLETED_WITH_FAILURES
fixtures_frozen=true
offline_tests_passed=true
paid_api_called=true
three_task_smoke_completed=true
successful_reviews=2
failed_reviews=1
phase_2_retry_allowed=false
github_api_called=false
github_write_performed=false
next_phase_decision=ENTER_PHASE_3_GITHUB_READ_ONLY_PLAN
```

## 2. 实际范围与固定条件

Phase 2 在合同提交 `25bee229ebfbc24af6b1a63176d073bdc8f698ae` 上串行运行三道冻结 Fixture，每题最多调用一次 MiMo。未调用 GitHub API、未写入 GitHub，也未进入 Phase 3。

```text
model=mimo-v2.5-pro
temperature=0.0
max_tokens=4096
attempts_per_task=1
adapter=OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE
github_write=false
```

| 任务 | Base | Candidate | Diff SHA256 | 预期严重度 |
|---|---|---|---|---|
| 逻辑错误 | `030396458d0e6fd6b8bf444c0ef24d1ea495b5b3` | `746e90b56d3150d96acbff4a0f02308ab151669c` | `e025350863e5054547661826f042d4c6e8ab40008947e35e221c12e9c10061ea` | high |
| 空列表边界错误 | `5b42849b9736101052b8af238fcf0685bd16de78` | `7edbe8d7f64224cbdf0a17955220f0f806c30d8f` | `b31e202be023af4e685579891d453a5be60e1c94174b8f2ef922f9ce711dda8a` | medium |
| viewer 删除权限扩大 | `bf0baf8188625d8d4ebc7483fd695c87608dd705` | `f2b5ba53cde514e580e9170fa84230da713b61fa` | `bd0f1885c3289f54c467bfbdb662b25d21139eab151ed5773421b953e4341308` | high |

## 3. 实际运行

```bash
MIMO_API_KEY="$MIMO_API_KEY" \
MIMO_ACCOUNT_TYPE=PAY_AS_YOU_GO \
OPEN_SWE_PHASE2_ALLOW_NETWORK=YES_ONCE \
python scripts/run_phase2_mimo_smoke.py \
  --run-smoke \
  --acknowledgement OPEN_SWE_PHASE2_THREE_TASK_SMOKE
```

执行终态为 `COMPLETED_WITH_FAILURES`，随后离线 `--check` 通过。正式目录存在后不允许重新启动整组 Smoke。

## 4. 逐题结果

| 任务 | 状态 | 人工核心缺陷判断 | 有效 Finding | 误报 | 预测/预期严重度 | Tokens | 记录耗时 |
|---|---|---:|---:|---:|---|---:|---:|
| 逻辑错误 | `REVIEW_CONTRACT_FAILURE` | 未形成可审计 Review，按漏报计 | 0 | 0 | 不适用 / high | 1548 | 未保存 |
| 空列表边界错误 | `COMPLETED` | 命中 | 1 | 0 | high / medium | 1610 | 13.800 s |
| viewer 删除权限扩大 | `COMPLETED` | 命中 | 1 | 0 | critical / high | 1470 | 12.315 s |

### 逻辑错误

模型调用已发生，但输出在 `REVIEW_VALIDATION` 阶段违反 Review 合同，固定原因是 `REVIEW_CONTRACT_FAILURE`。运行器按失败关闭策略只保存脱敏 `failure.json`，没有保存模型正文，因此不能事后推断模型是否理解了缺陷；人工统计保守记为未召回。

### 空列表边界错误

Finding 正确指出空列表会到达 `tags[0]` 并触发 `IndexError`，文件与 changed line 锚定正确，无额外 Finding。严重度由预期 `medium` 高估为 `high`。

### viewer 删除权限扩大

Finding 正确指出 viewer 被授予删除权限会造成越权删除，文件与 changed line 锚定正确，无额外 Finding。严重度由预期 `high` 高估为 `critical`。

## 5. 聚合指标与人工复核

| 指标 | 结果 |
|---|---:|
| 成功生成合法 Review | `2/3` |
| 人工核心缺陷召回 | `2/3` |
| 人工 Finding precision | `2/2` |
| 机器语义 Rubric 召回 | `2/3` |
| 机器语义 Rubric precision | `2/2` |
| 虚假 Finding | `0` |
| 重复 Finding | `0` |
| 有效 Review 的文件/行号准确率 | `2/2` |
| Schema 合法率 | `2/3` |

机器 Rubric 与人工复核在本次三题上结论一致，但机器关键词规则不替代人工语义判断。

## 6. 严重度校准

| 样本 | 预测 | 预期 | 偏差 |
|---|---|---|---:|
| Phase 1 逻辑回归 | critical | high | +1 |
| Phase 2 空列表边界 | high | medium | +1 |
| Phase 2 权限扩大 | critical | high | +1 |

Phase 2 两个有效 Review 的严重度精确匹配率为 `0/2`、平均绝对等级误差为 `1.0`、高估 `2` 次、低估 `0` 次。结合 Phase 1，当前三个可观察正确 Finding 均高估一级。这是小样本中稳定出现的上偏现象，不应表述为统计上已证明的普遍规律。

## 7. Token、延迟与证据口径

```text
model_calls=3
input_tokens=3155
output_tokens=1473
total_tokens=4628
automatic_retries=0
recorded_success_elapsed_seconds=26.115
```

`26.115` 秒只合计两个成功任务，未包含逻辑题失败调用，不能当作整个 Phase 2 的总墙钟时间。原始汇总中的 `test_execution_rate=2/3` 按“成功 Review 数/任务数”计算；控制流显示三题都已进入测试阶段，但逻辑题失败证据没有保留测试返回码，因此本文不补造该值。

## 8. 冻结的八份产物

| 文件 | SHA256 |
|---|---|
| `artifacts/phase2/logic_error/failure.json` | `9f082c43aa247cb8ba53c4358b6fa2643cdb0291292099c61ad72045ff915871` |
| `artifacts/phase2/boundary_error/review.json` | `45dcb331705fa5b427515b7e4fad4a3c20e9947f833ebca1655bdcdf73bcdd9d` |
| `artifacts/phase2/boundary_error/review.md` | `716df75ba330361f93130788fca45603b170b7308e266e9ac14a2d39eaee2723` |
| `artifacts/phase2/boundary_error/run_summary.json` | `412b6c566159d4633a96390b1537c0db9204eb495a4417ebf8c8eed873dea464` |
| `artifacts/phase2/permission_error/review.json` | `e1615fd3cabf99f2e8592db139a74b2c53263f976fd09a79bfb0a3ca42010a9f` |
| `artifacts/phase2/permission_error/review.md` | `8f9716c81427c4f52f083de664d4c84ac1f392b53cb1ed5489156fe4307b0bba` |
| `artifacts/phase2/permission_error/run_summary.json` | `c2f510d94aac5ac622f5a9cd2d9f378882a38e9cdb9d124cc87c099898e57765` |
| `artifacts/phase2/summary.json` | `80ef503e3aa2dfb658b783775cc1439cc0257094589fc63802e1ef891cef3d10` |

原始 `summary.json` 及逐题产物没有因人工复核而修改。

## 9. 安全与范围

```text
api_key_in_git=false
api_key_in_artifacts=false
github_api_called=false
github_write_performed=false
candidate_code_modified=false
docker_started=false
local_4b_run=false
training_started=false
```

## 10. 结论与下一步

Phase 2 证明原型可在不同缺陷类型上生成两个准确、可定位、无误报的 Review，同时暴露了两个真实局限：结构化输出合同仍可能失败，严重度存在一致的一级高估倾向。

人工决策为：

```text
decision=ENTER_PHASE_3_GITHUB_READ_ONLY_PLAN
phase_3_execution_allowed=false
reason=TWO_VALID_CROSS_CATEGORY_REVIEWS_SUPPORT_READ_ONLY_INPUT_INTEGRATION_WHILE_FAIL_CLOSED_CONTRACT_HANDLING_REMAINS_REQUIRED
```

下一步只创建并复审 Phase 3 的 GitHub 只读计划。不得补跑 Phase 2，不得发布评论，也不得自动进入 GitHub 写入流程。
