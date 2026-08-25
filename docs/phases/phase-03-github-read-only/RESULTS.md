# Phase 3 结果：GitHub PR 只读接入

> 当前状态：`IMPLEMENTED_NOT_RUN`
>
> 本文件是结果模板。下面所有计划值和待填项都不是实际成果；真实运行后必须以证据替换，不能删除失败或把计划写成事实。

## 1. 当前门禁

```text
phase_2_status=COMPLETED_WITH_FAILURES
phase_2_retry_allowed=false
phase_3_plan_status=READY
phase_3_execution_status=IMPLEMENTED_NOT_RUN
github_read_performed=false
github_write_performed=false
review_publish_allowed=false
next_step=MAIN_REVIEW_COMMIT_THEN_APPROVE_TARGET_PR
target_contract_status=NOT_APPROVED
```

## 2. 计划与真实结果分离

| 项目 | 计划 | 实际结果 |
|---|---|---|
| 输入 | 一个主对话批准的 GitHub PR | NOT_RUN |
| 模型 | `mimo-v2.5-pro` | NOT_RUN |
| Temperature | `0.0` | NOT_RUN |
| Max output tokens | `4096` | NOT_RUN |
| Attempts | `1` | NOT_RUN |
| GitHub 权限 | 只读 | NOT_RUN |
| GitHub 写入 | 禁止 | NOT_RUN |
| PR 代码执行 | 禁止 | NOT_RUN |
| 输出 | 本地 JSON/Markdown/Summary | NOT_RUN |

## 3. 批准的 PR 身份

```text
repository=NOT_SELECTED
pull_number=NOT_SELECTED
visibility=NOT_SELECTED
authentication_mode=NOT_SELECTED
```

不得在此记录 Token 内容。

## 4. 实际实现范围

离线实现已完成：

- 新增只读 Client、Phase 3 Runner 和专项 Fake 测试；
- 复用现有 Diff parser、MiMo Adapter、Review Schema/语义校验和 renderer；
- 向后兼容增加 `tests.status=NOT_RUN_READ_ONLY`；
- URL 只允许 `api.github.com` 的 PR metadata/files/diff，方法固定为 GET；
- 实现计划中的 8 文件、96 KiB raw diff、32 KiB 单 patch、600 candidate changed lines 等硬限制；
- 未选择真实 PR，未读取 GitHub，未调用 MiMo，未执行 PR 代码。
- 最小目标合同保持 `NOT_APPROVED`；真实运行前必须由主对话填写并提交精确目标。

离线验证的实际数字由分支交付时填写；PR 快照及 Review 指标继续保持 `NOT_RUN`。

### 离线验证结果

```text
phase_3_specialized_tests=25/25 PASS
full_test_suite=64 tests, PASS, 1 historical lifecycle skip
resource_warning_strict_mode=PASS
review_schema_draft_2020_12=PASS
python_compile=PASS
pip_check=PASS
git_diff_check=PASS
credential_pattern_scan=PASS
github_write_route_scan=PASS
phase_3_artifacts=ABSENT
```

历史生命周期跳过项来自正式 Phase 2 已消费后的既有测试，不是 Phase 3 失败。

## 5. 实际运行命令

```bash
# NOT_RUN：由实现分支在合同冻结后填写精确命令。
```

## 6. PR 快照结果

| 字段 | 实际值 |
|---|---|
| Repository | NOT_RUN |
| PR number | NOT_RUN |
| Base SHA | NOT_RUN |
| Head SHA | NOT_RUN |
| Metadata A/B 一致 | NOT_RUN |
| Changed files | NOT_RUN |
| Raw diff bytes | NOT_RUN |
| Total diff lines | NOT_RUN |
| Candidate changed lines | NOT_RUN |
| Missing patch | NOT_RUN |
| Unsupported files | NOT_RUN |
| Snapshot SHA256 | NOT_RUN |
| Diff SHA256 | NOT_RUN |
| Changed-lines SHA256 | NOT_RUN |

## 7. Review 结果

| 指标 | 实际值 |
|---|---|
| Response model | NOT_RUN |
| Finish reason | NOT_RUN |
| Tool Call count | NOT_RUN |
| Schema valid | NOT_RUN |
| Semantic validation | NOT_RUN |
| Finding count | NOT_RUN |
| Changed-line anchor valid | NOT_RUN |
| False findings | PENDING_HUMAN_REVIEW |
| Duplicate findings | NOT_RUN |
| Uncertainties | NOT_RUN |
| Decision | NOT_RUN |
| Severity calibration | PENDING_HUMAN_REVIEW |

运行后必须逐条列出 Finding，并由主对话人工判断其正确性、证据、严重度和是否属于 PR 改动引入的问题。

## 8. 调用、Token、耗时与费用

```text
github_get_requests=NOT_RUN
github_write_requests=NOT_RUN
github_response_bytes=NOT_RUN
model_calls=NOT_RUN
input_tokens=NOT_RUN
output_tokens=NOT_RUN
total_tokens=NOT_RUN
elapsed_seconds=NOT_RUN
cost=NOT_AVAILABLE
automatic_retries=0
```

## 9. 本地产物与 Hash

| 文件 | SHA256 |
|---|---|
| `pr_snapshot.json` | NOT_RUN |
| `diff.patch` | NOT_RUN |
| `changed_lines.json` | NOT_RUN |
| `review.json` 或 `failure.json` | NOT_RUN |
| `review.md` | NOT_RUN |
| `run_summary.json` | NOT_RUN |

## 10. 权限与安全复核

```text
github_read_performed=false
github_write_performed=false
review_publish_allowed=false
pr_code_executed=false
token_in_git=UNKNOWN
token_in_artifacts=UNKNOWN
prompt_injection_changed_control_flow=UNKNOWN
credentials_scan=NOT_RUN
```

真实运行后必须用检查结果替换 `UNKNOWN`，但禁止把 Token 值写入本文。

## 11. 代表性成功、失败与局限

### 成功

NOT_RUN

### 失败

NOT_RUN

### 局限

- 计划只读取一个批准的 PR，不能代表所有 GitHub 仓库或 Diff 形态；
- 不执行 PR 代码，因此不能提供动态测试证据；
- 仍使用 Reviewer-compatible local slice，不等同于官方完整 Open SWE Pregel graph；
- GitHub 写入明确不在本阶段范围内；
- Phase 2 已观察到结构化合同失败和严重度上偏，Phase 3 必须继续如实记录。

## 12. 人工决策门

```text
human_review_status=PENDING
decision=PENDING
phase_4_execution_allowed=false
```

真实结果复核后只能由主对话选择下一步，例如：

- `PLAN_MINIMAL_GITHUB_REVIEW_WRITE`
- `ONE_MINIMAL_READ_ONLY_FIX_WITHOUT_RERUNNING_VALID_MODEL_RESULT`
- `STOP_WITH_READ_ONLY_PROTOTYPE`

本文件完成后必须停止，不能自动发布 Review 或进入 Phase 4。
