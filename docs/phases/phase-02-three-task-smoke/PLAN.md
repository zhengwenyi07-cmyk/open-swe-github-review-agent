# Phase 2 计划：三题 Diff Review Smoke

> 状态：`IMPLEMENTED_NOT_RUN`
>
> 本文是主审核对话批准前的初步计划。分支对话只实现本阶段，返回结果后停止；不得自动进入 GitHub 接入阶段。

## 1. 本阶段研究问题

Phase 1 已证明 MiMo V2.5 Pro 能在一个固定逻辑回归 Diff 上完成结构化 Review，并取得核心缺陷召回 `1/1`、虚假 Finding `0`。但单题成功不能证明基本泛化，且模型把预期 `high` 评为 `critical`。

本阶段只回答两个问题：

1. 同一模型与同一 Reviewer-compatible local slice 能否在三类小型 Diff 上稳定识别主要问题？
2. Phase 1 的严重度高估是偶发现象，还是可重复的系统性校准偏差？

## 2. 固定实验设计

建立恰好三道人工可读、可确定性重建的小型 Git Fixture：

| 任务类型 | 研究目的 | 最小特征 |
|---|---|---|
| 逻辑错误 | 复核已证明能力并作为跨阶段锚点 | 明确 changed-line 逻辑回归和失败测试 |
| 边界/异常处理 | 检查模型能否发现输入边界或异常路径缺失 | 一个主要问题，测试能直接触发 |
| 危险/越权修改 | 检查安全与作用域判断 | 一个明确危险行为或权限边界破坏 |

优先复用 Phase 1 逻辑错误 Fixture；新增另外两题。每题在模型运行前冻结：

- Base Commit、Candidate Commit 和 Diff SHA256；
- changed-line 集合；
- 一个主要问题及其允许锚点；
- 人工预期 category 和 severity；
- 允许的次要 Finding；
- 明确禁止的虚假 Finding；
- 固定测试命令与预期返回语义。

预期答案只用于运行后评分，不得进入模型 Prompt。

## 3. 固定模型与运行条件

Phase 2 必须与 Phase 1 保持一致：

```text
provider=MiMo
configured_model=mimo-v2.5-pro
response_model=mimo-v2.5-pro
base_url=https://api.xiaomimimo.com/v1
transport=OpenAI-compatible Chat Completions
temperature=0.0
max_tokens=4096
max_retries=0
parallel_tool_calls=false
attempts_per_task=1
adapter_kind=OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE
github_write=false
```

不得因单题正常漏报、误报或严重度错误自动补跑。只有明确的 API/基础设施失败可以在保存失败事实并经主审核对话批准后补跑。

## 4. 预计最小实现

分支对话应优先复用 Phase 1 代码，只做支持三 Fixture 所需的最小泛化：

- 新增两个 Fixture 目录和各自清单；
- 如有必要，让现有本地 Sandbox/Runner 接受冻结 allowlist 中的三个 Fixture；
- 新增一个串行 Smoke 入口；
- 新增一个简单汇总器或直接在 Runner 结束后生成汇总；
- 增加针对 Fixture 身份、单次运行、评分和严重度指标的离线测试；
- 更新本目录 `CONCEPTS.md` 和 `RESULTS.md`。

优先修改既有 Schema 和组件，不为三题新增通用评测平台、数据库、任务队列、状态机家族或 r01/r02/r03 诊断链。

## 5. 输出

每题保存与 Phase 1 同类的最小证据：

```text
review.json
review.md
run_summary.json
```

阶段级汇总至少包含：

```text
task_count
completed_reviews
semantic_rubric_recall
semantic_rubric_precision
human_core_bug_recall
human_finding_precision
file_anchor_accuracy
line_anchor_accuracy
schema_valid_rate
test_execution_rate
duplicate_findings
uncertainty_count
severity_exact_match_rate
severity_mean_absolute_error
severity_overestimation_count
severity_underestimation_count
severity_mean_overestimation_magnitude
severity_mean_underestimation_magnitude
model_calls
input_tokens
output_tokens
total_tokens
elapsed_seconds
cost_or_not_available
github_write_performed
```

## 6. 指标定义

### 6.1 缺陷质量

- 核心缺陷召回：识别出的预设主要问题数 / 3。
- Finding precision：人工判定正确的 Finding 数 / 全部 Finding 数。
- 文件锚定准确率：正确文件的 Finding 数 / 全部 Finding 数。
- 行锚定准确率：落在允许 changed line 的 Finding 数 / 全部 Finding 数。
- 虚假 Finding：与预设主要/允许次要问题均不匹配的 Finding。
- 重复 Finding：语义上重复报告同一根因。

### 6.2 严重度校准

映射固定为：

```text
low=1
medium=2
high=3
critical=4
```

报告：

- 精确匹配率；
- 平均绝对等级误差；
- 高估次数与平均高估幅度；
- 低估次数与平均低估幅度；
- Phase 1 的 `critical` 对预期 `high` 作为历史对照，不混入三题分母，另行并列展示。

机器先用冻结的结构与根因词组 rubric 做保守筛选，但最终核心召回和 precision 必须由主审核对话阅读 Finding 后填写。只有通过语义 rubric 且经人工确认的问题才用于最终严重度结论。误报单独计入 precision，避免把两个概念混合。

### 6.3 运行与安全

- Schema 合法率；
- 固定测试真实执行率；
- 模型身份和 finish reason 一致率；
- 调用数、Token、耗时、费用；
- GitHub API/写入次数，应始终为 `0`；
- 凭据泄漏数，应始终为 `0`。

## 7. 成功标准与人工决策门

本阶段不设“为了通过而补跑”的硬分数。完成三道单次运行、保存可信证据并能解释差异，即完成实验。

主审核对话可参考以下条件决定是否进入 Phase 3 GitHub 只读计划：

- 三题均完成合同链路；
- Schema 合法率 `3/3`；
- 没有 GitHub 写入或凭据泄漏；
- 核心缺陷召回至少 `2/3`；
- Finding precision 不低于 `2/3`；
- 没有无法解释的系统性严重度高估或低估。

Runner 不生成 `automated_thresholds_met`，也不自动批准下一阶段。所有结果都停在 `HUMAN_REVIEW_REQUIRED`。

若质量不达标，先在结果中定位是 Prompt、上下文、类别覆盖还是模型校准问题。最多提出一个最小修正建议，不自动开始新实验。

## 8. 安全、费用与权限边界

- Key 只通过单命令环境变量注入，不写文件、不进 Prompt、不提交 Git。
- 账户类型保持 `PAY_AS_YOU_GO`。
- 三题串行运行，每题一次模型调用，禁止自动重试正常模型失败。
- 运行前先通过离线测试和工作区干净检查。
- 不调用 GitHub API，不创建 App，不发布 Review。
- 不修改 Candidate 代码。
- 不运行 Docker、本地 4B 或训练。
- 单题执行失败时写入脱敏 `failure.json` 并继续后续题；固定区分本地 Fixture、模型客户端、模型响应、测试执行、Review 合同和证据写入阶段，禁止保存异常正文，失败题不得静默补跑。

## 9. 明确不做

- 不运行官方完整 Open SWE Pregel graph；
- 不接入真实 GitHub PR；
- 不设计 Phase 3/4 实现；
- 不增加本地模型对照；
- 不扩大到更多任务；
- 不为严重度调参后反复重跑三题；
- 不把测试预期或主要问题泄漏给模型；
- 不提交 API Key、缓存或临时 Fixture 工作区。

## 10. 分支对话交付格式

实现完成后必须返回：

```text
实现状态：
修改文件：
三道 Fixture 身份与 Hash：
离线测试：
是否调用付费 API：
是否运行三题：
每题 Review/测试结果：
核心缺陷召回：
Finding precision：
文件/行号准确率：
严重度校准指标：
Token/耗时/费用：
虚假与重复 Finding：
GitHub API/写入：
凭据检查：
代表性成功与失败：
Git 状态：
明确未执行内容：
建议的下一阶段：
```

分支应先完成离线实现并停在付费运行前，由主审核对话复审。没有明确批准时不得调用 MiMo。
