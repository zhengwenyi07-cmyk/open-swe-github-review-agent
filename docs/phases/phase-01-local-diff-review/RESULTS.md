# Phase 1 结果：真实 MiMo 本地 Diff Review 原型

> 当前状态：`IMPLEMENTED_COMMITTED_NOT_RUN`
>
> 本文件是结果模板。分支实现和真实运行完成前，不得把预期结果填成事实。

## 1. 阶段结论摘要

```text
phase_status=IMPLEMENTED_COMMITTED_NOT_RUN
real_mimo_call_completed=false
review_json_created=false
review_markdown_created=false
schema_validated=false
core_bug_detected=UNKNOWN
github_write_performed=false
next_phase_decision=PENDING_HUMAN_REVIEW
```

离线实现已经完成，采用 `Open SWE Reviewer-compatible local slice`，24 项测试通过并通过主对话复审。由于真实入口要求用户在终端安全输入 `MIMO_API_KEY`，没有执行付费 Preflight 或真实 Review。当前不能判断模型是否识别核心错误，也不能进入三题 Smoke。

## 2. 实际实施范围

已新增：

- `src/open_swe_review_agent/local_git_sandbox.py`
- `src/open_swe_review_agent/open_swe_adapter.py`
- `scripts/run_phase1_mimo_review.py`
- `tests/test_phase1_mimo_review.py`

已修改：

- Phase 1 的 `PLAN.md`、`CONCEPTS.md` 和本 `RESULTS.md`；
- `PROJECT_HANDOFF.md` 已同步为 `IMPLEMENTED_NOT_RUN`。

实际采用最薄兼容 adapter，没有运行完整官方 graph。该选择符合计划中的方案 B：官方 graph 的 GitHub/Sandbox/publish 依赖对于单个本地 Diff 原型过重。实现复用了 Reviewer Prompt 纪律、changed-line 约束和结构化 finding 边界，并在产物中明确标记 adapter 类型。

## 3. 固定身份

运行后核对并填写：

```text
project_git_commit=TO_BE_CAPTURED_BY_RUNTIME
open_swe_repository=https://github.com/langchain-ai/open-swe.git
open_swe_commit=daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc
fixture_id=phase1_logic_error_v1
base_commit=030396458d0e6fd6b8bf444c0ef24d1ea495b5b3
candidate_commit=746e90b56d3150d96acbff4a0f02308ab151669c
diff_sha256=e025350863e5054547661826f042d4c6e8ab40008947e35e221c12e9c10061ea
model=mimo-v2.5-pro
```

## 4. 实际运行命令

### 4.1 离线检查

```bash
python -m unittest tests.test_phase1_mimo_review -v
python scripts/run_phase1_mimo_review.py --check
python -m unittest discover -s tests -v
```

实际结果：MiMo 身份与 Phase 1 定向测试 `15/15` 通过，完整测试 `24/24` 通过；离线状态为 `preflight=NOT_RUN review=NOT_RUN`。

### 4.2 MiMo Tool Call 预检

```bash
# 待粘贴实际命令；API Key 必须省略
```

### 4.3 固定 Diff Review

```bash
# 待粘贴实际命令；API Key 必须省略
```

### 4.4 最终验证

```bash
# 待粘贴测试、Schema、diff check 和 Git 状态命令
```

## 5. Preflight 结果

| 项目 | 结果 |
|---|---|
| 状态 | NOT_RUN |
| 实际返回模型 | 待填写 |
| Tool Call 数 | 待填写 |
| Tool 语义 | 待填写 |
| Input Tokens | 待填写 |
| Output Tokens | 待填写 |
| 耗时 | 待填写 |
| 费用 | 待填写 |

如果 Preflight 失败，记录脱敏错误、分类和是否进行了唯一一次修复补跑。

当前不是 Preflight 失败，而是按计划停在付费调用前。

## 6. Review 输出

### 6.1 Summary

待填写模型的实际摘要，必要时只摘录短句并链接本地证据。

### 6.2 Findings

| # | File:Line | Severity | Category | Assessment | 是否正确 | 说明 |
|---|---|---|---|---|---|---|
| 1 | 待填写 | 待填写 | 待填写 | 待填写 | 待人工评分 | 待填写 |

### 6.3 Uncertainties

| # | File:Line | Question | 是否合理 |
|---|---|---|---|
| 1 | 待填写 | 待填写 | 待人工评分 |

没有 uncertainty 时明确写 `0`，不要保留空占位行。

### 6.4 Decision

```text
decision=
decision_is_reasonable=
reason=
```

## 7. 测试结果

```text
command=python -m unittest test_calculator.py
returncode=
passed=
```

说明测试失败是否与预期逻辑回归一致。不要把 Fixture 的预期测试失败误记为基础设施失败。

## 8. Review 质量评分

| 指标 | 结果 |
|---|---|
| 核心逻辑错误召回 | NOT_RUN |
| 核心 Finding 文件准确 | 待填写 |
| 核心 Finding 行号准确 | 待填写 |
| 虚假 Finding 数 | 待填写 |
| 重复 Finding 数 | 待填写 |
| Uncertainty 分类合理 | 待填写 |
| Schema 合法 | 待填写 |
| Markdown 与 JSON 一致 | 待填写 |

## 9. 运行指标

| 指标 | 结果 |
|---|---|
| 模型调用数 | 待填写 |
| Input Tokens | 待填写 |
| Output Tokens | 待填写 |
| Total Tokens | 待填写 |
| 总耗时 | 待填写 |
| 实际或估算费用 | 待填写 |
| 自动重试 | 应为 0 |

无法从 API 取得的字段写 `NOT_AVAILABLE`，不能估造数字。

## 10. 产物与 Hash

| 文件 | 路径 | SHA256 |
|---|---|---|
| Review JSON | 待填写 | 待填写 |
| Review Markdown | 待填写 | 待填写 |
| Run Summary | 待填写 | 待填写 |
| Preflight Evidence | 待填写 | 待填写 |

只记录理解和复现需要的产物。不要为本阶段创建复杂证据树。

## 11. 安全与权限

运行后逐项填写：

```text
api_key_in_git=false
api_key_in_logs=false
api_key_in_prompt=false
github_api_called=false
github_write_performed=false
code_modified_by_agent=false
old_mini_swe_project_modified=false
local_4b_run=false
training_started=false
docker_long_task_started=false
```

## 12. 代表性成功与失败

### 成功

- 本地 Git Sandbox 读取的 Diff 与冻结文件逐字节一致。
- 固定 Candidate 单元测试真实返回 `1`，证明测试不是模型伪造。
- Fake Chat Model 通过真实 Local Sandbox 完成完整合同，最终 `tests.passed=false` 且 Finding 锚定 `calculator.py:2`。
- Adapter 强制一个命名 Tool Call，拒绝多个 Tool Call，并记录 usage/model/finish reason。
- Preflight 和 Review 都从 API response metadata 读取实际模型身份，错误模型或错误 finish reason 会被拒绝。
- 离线 `--check` 会复核已保存的 configured model、response model 和 finish reason，不会仅因文件存在就报告 PASS。
- Prompt 包含真实 Diff，但不包含 `expected_primary_finding`。

### 失败或局限

- 完整官方 graph 依赖 GitHub PR、Sandbox provider 和 publish 链，本阶段没有运行。
- 当前环境没有 MiMo Key，付费 Preflight 与真实 Review 均未运行。
- 因未运行真实模型，Review 质量、Token、耗时和费用仍未知。
- 离线实现已经通过主对话复审并准备提交；真实入口运行时仍会记录准确合同 Commit。

不要只写成功，也不要把基础设施与模型质量混在一起。

## 13. 对下一阶段的决策

当前临时决策：

```text
FIX_ONE_INFRASTRUCTURE_BLOCKER_THEN_REVIEW
```

这里的 blocker 不是代码缺陷，而是人工付费决策门：离线实现提交后，由用户在终端安全输入 Key，依次运行 Preflight 和一次固定 Diff Review。

真实运行完成后再从以下选项作最终选择：

```text
ENTER_PHASE_2_THREE_TASK_SMOKE
FIX_ONE_INFRASTRUCTURE_BLOCKER_THEN_REVIEW
REVISE_PHASE_2_BASED_ON_MODEL_RESULT
STOP_PROJECT
```

说明依据：

- 链路是否稳定；
- Review 是否基本可信；
- 哪些问题值得在三题 Smoke 中继续测；
- 是否需要修改后续任务、指标或 Prompt。

不得由分支自动开始 Phase 2，最终决定由主审核对话作出。

## 14. 明确未执行内容

运行后确认：

- 未创建 GitHub App；
- 未发布 GitHub Review；
- 未自动修改代码；
- 未运行三题 Smoke；
- 未运行本地 4B；
- 未训练；
- 未修改旧项目；
- 未进入下一阶段。
