# Phase 3 结果：GitHub PR 只读接入

> 当前状态：`COMPLETED`
>
> Phase 3 已完成唯一一次正式公开只读运行并通过人工复审。六份原始产物按运行时字节原样冻结；没有补跑、执行 PR 代码或向 GitHub 写入。

## 1. 当前门禁

```text
phase_2_status=COMPLETED_WITH_FAILURES
phase_2_retry_allowed=false
phase_3_plan_status=COMPLETED
phase_3_execution_status=COMPLETED
github_read_performed=true
github_write_performed=false
review_publish_allowed=false
next_step=HUMAN_DECISION_GATE
target_contract_status=APPROVED_AND_CONSUMED
```

## 2. 计划与真实结果分离

| 项目 | 计划 | 实际结果 |
|---|---|---|
| 输入 | 一个主对话批准的 GitHub PR | `pallets/click#3021` |
| 模型 | `mimo-v2.5-pro` | `mimo-v2.5-pro` |
| Temperature | `0.0` | `0.0` |
| Max output tokens | `4096` | `4096` |
| Attempts | `1` | `1`，无补跑 |
| GitHub 权限 | 只读 | `PUBLIC`，4 次 GET |
| GitHub 写入 | 禁止 | 0 次 |
| PR 代码执行 | 禁止 | 未执行 |
| 输出 | 本地 JSON/Markdown/Summary | 六份本地产物 |

## 3. 批准的 PR 身份

```text
repository=pallets/click
pull_number=3021
visibility=PUBLIC
authentication_mode=PUBLIC
base_sha=27aaed3fe5bcd6adedd6e91de234914af9859cf1
head_sha=27de74af68bfd967c639ad4beb330fa4ed0d470f
```

不得在此记录 Token 内容。

## 4. 实际实现范围

离线实现已完成：

- 新增只读 Client、Phase 3 Runner 和专项 Fake 测试；
- 复用现有 Diff parser、MiMo Adapter、Review Schema/语义校验和 renderer；
- 向后兼容增加 `tests.status=NOT_RUN_READ_ONLY`；
- URL 只允许 `api.github.com` 的 PR metadata/files/diff，方法固定为 GET；
- 实现计划中的 8 文件、96 KiB raw diff、32 KiB 单 patch、600 candidate changed lines 等硬限制；
- 真实目标经独立提交批准后，只读读取公开 PR 并调用 MiMo 一次；始终未执行 PR 代码。
- 最小目标合同在运行前固定为 `APPROVED`，CLI repository、PR number 和认证模式与合同完全一致。

以下离线验证数字来自运行前合同复审；真实快照与 Review 指标见后续章节。

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
phase_3_artifacts=FROZEN_6_FILES
```

历史生命周期跳过项来自正式 Phase 2 已消费后的既有测试，不是 Phase 3 失败。

## 5. 实际运行命令

```bash
MIMO_API_KEY="$MIMO_API_KEY" \
MIMO_ACCOUNT_TYPE=PAY_AS_YOU_GO \
OPEN_SWE_PHASE3_ALLOW_NETWORK=YES_ONCE \
python scripts/run_phase3_github_readonly.py \
  --execute-once \
  --repository pallets/click \
  --pull-number 3021 \
  --auth-mode PUBLIC \
  --acknowledgement OPEN_SWE_PHASE3_GITHUB_READ_ONLY_REVIEW
```

终端结果：`PASS`，退出码 `0`，下一步为 `HUMAN_REVIEW_REQUIRED`。

## 6. PR 快照结果

| 字段 | 实际值 |
|---|---|
| Repository | `pallets/click` |
| PR number | `3021` |
| Base SHA | `27aaed3fe5bcd6adedd6e91de234914af9859cf1` |
| Head SHA | `27de74af68bfd967c639ad4beb330fa4ed0d470f` |
| Metadata A/B 一致 | 是 |
| Changed files | 3 |
| Raw diff bytes | 4,659 |
| Total diff lines | 118 |
| Candidate changed lines | 38 |
| Missing patch | 0 |
| Unsupported files | 0 |
| Snapshot SHA256 | `ecaf49325c674fa84c6b5ed6a048b9e6d9d330e7f0ba3391de456288c61799c5` |
| Diff SHA256 | `f3f127e2a1347b94edae445837f140d849585f15dd3801e7092eeeb9b74f6cb2` |
| Changed-lines SHA256 | `dbeade9a5930c0898b7ae58b89dc5867771e34f4f5fa5c0dbac6e3d15d2f09a0` |

## 7. Review 结果

| 指标 | 实际值 |
|---|---|
| Response model | `mimo-v2.5-pro` |
| Finish reason | `tool_calls` |
| Tool Call count | 1 |
| Schema valid | `true` |
| Semantic validation | 通过 |
| Finding count | 0 |
| Changed-line anchor valid | 是；唯一 Uncertainty 位于 `src/click/termui.py:122` |
| False findings | 不适用；没有 Finding，也没有人工 Gold |
| Duplicate findings | 0 |
| Uncertainties | 1 |
| Decision | `APPROVE` |
| Severity calibration | 不适用；没有 Finding |

本次没有 Finding；主对话已人工确认唯一 Uncertainty 的文件与行号属于真实 changed-line 集合。

## 8. 调用、Token、耗时与费用

```text
github_get_requests=4
github_write_requests=0
github_response_bytes=52622
model_calls=1
input_tokens=2937
output_tokens=2987
total_tokens=5924
elapsed_seconds=63.601
cost=NOT_AVAILABLE
automatic_retries=0
```

## 9. 本地产物与 Hash

| 文件 | SHA256 |
|---|---|
| `pr_snapshot.json` | `ecaf49325c674fa84c6b5ed6a048b9e6d9d330e7f0ba3391de456288c61799c5` |
| `diff.patch` | `f3f127e2a1347b94edae445837f140d849585f15dd3801e7092eeeb9b74f6cb2` |
| `changed_lines.json` | `dbeade9a5930c0898b7ae58b89dc5867771e34f4f5fa5c0dbac6e3d15d2f09a0` |
| `review.json` | `280c27d0df8b5167d287dd7345cda07ffb3e68efd0a2d6b2a182a4c5275db4be` |
| `review.md` | `efcc7fe6c379d647d382b3095643c9c903d3bd79476db3a3c39eea21a0e20b69` |
| `run_summary.json` | `e3986a562a140d942009a042488f7b1c4406f171e9aa691d390b81d80ccb7280` |

## 10. 权限与安全复核

```text
github_read_performed=true
github_write_performed=false
review_publish_allowed=false
pr_code_executed=false
token_in_git=false
token_in_artifacts=false
prompt_injection_changed_control_flow=false
credentials_scan=PASS
```

凭据检查只记录是否命中，不记录 Token 内容。

## 11. 代表性成功、失败与局限

### 成功

- GitHub PR 输入成功替代本地 Fixture，同时保持原有 Review Schema、语义检查和 Markdown renderer；
- Base/Head、metadata、files、raw diff 与 38 个 candidate changed lines 构成同一快照闭环；
- MiMo 返回合同合法的 `APPROVE`，0 个 Finding、1 个锚定真实改动行的 Uncertainty；
- GitHub 写请求、Review 发布和 PR 代码执行均为 0。

### 失败

没有基础设施或合同失败。只读模式按设计未运行测试；这不是测试通过。

### 局限

- 计划只读取一个批准的 PR，不能代表所有 GitHub 仓库或 Diff 形态；
- 不执行 PR 代码，因此不能提供动态测试证据；
- 该 PR 没有冻结人工 Gold Finding，不能据此计算或声称召回率、Finding precision；
- `APPROVE` 只代表模型基于静态 Diff 未确认问题，不是运行时正确性证明；
- 仍使用 Reviewer-compatible local slice，不等同于官方完整 Open SWE Pregel graph；
- GitHub 写入明确不在本阶段范围内；
- Phase 2 已观察到结构化合同失败和严重度上偏，Phase 3 必须继续如实记录。

## 12. 人工决策门

```text
human_review_status=APPROVED
decision=FREEZE_PHASE_3_AND_STOP
phase_4_execution_allowed=false
```

真实结果复核后只能由主对话选择下一步，例如：

- `PLAN_MINIMAL_GITHUB_REVIEW_WRITE`
- `ONE_MINIMAL_READ_ONLY_FIX_WITHOUT_RERUNNING_VALID_MODEL_RESULT`
- `STOP_WITH_READ_ONLY_PROTOTYPE`

本文件完成后必须停止，不能自动发布 Review 或进入 Phase 4。
