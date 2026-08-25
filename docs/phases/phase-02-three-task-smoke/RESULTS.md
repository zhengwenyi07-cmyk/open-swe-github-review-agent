# Phase 2 结果：三题 Diff Review Smoke

> 当前状态：`IMPLEMENTED_NOT_RUN`
>
> 本文件是结果模板。实现和真实运行完成前，所有结果保持未知，不得把计划值写成事实。

## 1. 阶段门禁

```text
phase_status=IMPLEMENTED_NOT_RUN
fixtures_frozen=true
offline_tests_passed=true
paid_api_called=false
three_task_smoke_completed=false
github_api_called=false
github_write_performed=false
next_phase_decision=PENDING_HUMAN_REVIEW
```

## 2. 当前实施范围

离线实现已经完成：复用 Phase 1 的模型适配、Local Git Sandbox、Review Workflow、Schema 和 Markdown renderer；新增两道 Fixture、一个三题串行 Runner、评分汇总和专项测试。没有新增 Schema、数据库、队列或诊断阶段。

真实 MiMo 三题尚未执行，因此后续质量指标仍为 `NOT_RUN`。

## 3. 固定身份

| 项目 | 实际值 |
|---|---|
| 项目合同 Commit | 待提交后由运行时记录 |
| Open SWE Commit | `daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc` |
| Model | `mimo-v2.5-pro` |
| Adapter | `OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE` |
| Temperature | `0.0` |
| Max Tokens | `4096` |
| Attempts per task | `1` |

## 4. Fixture 身份

| 任务 | 类型 | Base | Candidate | Diff SHA256 | 预期主要严重度 |
|---|---|---|---|---|---|
| 1 | 逻辑错误 | `030396458d0e6fd6b8bf444c0ef24d1ea495b5b3` | `746e90b56d3150d96acbff4a0f02308ab151669c` | `e025350863e5054547661826f042d4c6e8ab40008947e35e221c12e9c10061ea` | high |
| 2 | 边界/异常处理 | `5b42849b9736101052b8af238fcf0685bd16de78` | `7edbe8d7f64224cbdf0a17955220f0f806c30d8f` | `b31e202be023af4e685579891d453a5be60e1c94174b8f2ef922f9ce711dda8a` | medium |
| 3 | 危险/越权修改 | `bf0baf8188625d8d4ebc7483fd695c87608dd705` | `f2b5ba53cde514e580e9170fa84230da713b61fa` | `bd0f1885c3289f54c467bfbdb662b25d21139eab151ed5773421b953e4341308` | high |

## 5. 实际运行命令

```bash
# 离线合同检查（已执行）
python scripts/run_phase2_mimo_smoke.py --check

# 真实命令待主审核对话复审、提交并明确批准后执行。
```

## 6. 逐题结果

| 任务 | 状态 | 核心问题识别 | 正确 Finding | 虚假 Finding | 重复 Finding | Severity 预测/预期 | 测试返回码 | Tokens | 耗时 |
|---|---|---:|---:|---:|---:|---|---:|---:|---:|
| 逻辑错误 | NOT_RUN | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 边界/异常处理 | NOT_RUN | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |
| 危险/越权修改 | NOT_RUN | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 | 未知 |

每题补充一个代表性正确 Finding，以及所有漏报、误报和 uncertainty。不要只保留汇总数字。

## 7. 聚合质量指标

| 指标 | 结果 |
|---|---|
| 语义 Rubric 核心召回 | NOT_RUN |
| 语义 Rubric Finding precision | NOT_RUN |
| 人工核心缺陷召回 | PENDING_HUMAN_REVIEW |
| 人工 Finding precision | PENDING_HUMAN_REVIEW |
| 文件锚定准确率 | NOT_RUN |
| 行号锚定准确率 | NOT_RUN |
| Schema 合法率 | NOT_RUN |
| 测试执行率 | NOT_RUN |
| 虚假 Finding | NOT_RUN |
| 重复 Finding | NOT_RUN |
| Uncertainty | NOT_RUN |

## 8. 严重度校准

| 指标 | Phase 1 历史值 | Phase 2 实际值 |
|---|---:|---:|
| 精确匹配 | `0/1` | NOT_RUN |
| 平均绝对等级误差 | `1.0` | NOT_RUN |
| 高估次数 | `1` | NOT_RUN |
| 平均高估幅度 | `1.0` | NOT_RUN |
| 低估次数 | `0` | NOT_RUN |
| 平均低估幅度 | NOT_APPLICABLE | NOT_RUN |

待分析：三题是否出现同方向偏差。样本量只有三题，结论必须表述为观察到的倾向，不能夸大为统计证明。

## 9. Token、延迟与费用

| 指标 | 结果 |
|---|---|
| 模型调用数 | NOT_RUN |
| Input Tokens | NOT_RUN |
| Output Tokens | NOT_RUN |
| Total Tokens | NOT_RUN |
| 总耗时 | NOT_RUN |
| 费用 | NOT_AVAILABLE/待填写 |
| 自动重试 | 应为 0 |

## 10. 产物与 Hash

| 文件 | SHA256 |
|---|---|
| 阶段汇总 | 待填写 |
| 任务 1 Review/Run Summary | 待填写 |
| 任务 2 Review/Run Summary | 待填写 |
| 任务 3 Review/Run Summary | 待填写 |

## 11. 安全与权限

```text
api_key_in_git=UNKNOWN
api_key_in_artifacts=UNKNOWN
github_api_called=false
github_write_performed=false
candidate_code_modified=false
docker_started=false
local_4b_run=false
training_started=false
```

运行后必须用真实检查结果替换 `UNKNOWN`。

## 12. 代表性成功、失败与局限

### 成功

- 三道 Fixture 均可确定性重建；
- 三个 Candidate 的固定测试均真实返回 `1`；
- 专项离线测试 `15/15` 通过；
- `--check` 报告三题 `NOT_RUN`；
- 评分测试确认严重度高估不会降低核心缺陷召回，但会进入独立校准指标；
- 工作区脏时，付费入口会在模型客户端构造前拒绝。
- 结构锚点正确但未描述冻结根因的 Finding 不再计入语义 Rubric 召回；最终召回仍需人工复核。
- 单题失败会按六个固定执行阶段保存脱敏证据并继续另外两题，最终汇总为 `COMPLETED_WITH_FAILURES`。
- Scoring Rubric 的文件、行、类别和严重度与各 Fixture 预期身份逐项交叉验证。
- 自动通过门槛已删除，汇总始终停在人工决策门。

### 失败

真实模型尚未运行，因此目前没有模型成功、漏报、误报或严重度结果。

### 局限

- 三题只是 Smoke，不是统计充分的 benchmark；
- 当前仍是 Reviewer-compatible local slice；
- 尚未接入 GitHub PR 或官方完整 graph。

## 13. 人工决策

```text
decision=PENDING_HUMAN_REVIEW
reason=PHASE_2_NOT_RUN
```

候选决策只能在真实结果复审后选择：

- `ENTER_PHASE_3_GITHUB_READ_ONLY_PLAN`
- `ONE_MINIMAL_QUALITY_FIX_THEN_REPEAT_AFFECTED_TASK`
- `STOP_WITH_LOCAL_PROTOTYPE_RESULT`

本文件更新完成后必须停止，不能自动进入 Phase 3。
