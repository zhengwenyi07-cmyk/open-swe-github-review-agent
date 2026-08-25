# Phase 2 讲解：用三题 Smoke 检查 Review 泛化与严重度校准

> 当前状态：`IMPLEMENTED_NOT_RUN`
>
> 本文解释计划中的技术概念。真实实现、命令和结果必须在分支完成后更新，不能把预期写成成果。

## 1. 为什么 Phase 1 成功后仍要做三题

Phase 1 只包含一个逻辑错误。模型正确回答可能来自真实 Review 能力，也可能只是该错误非常显眼。三题 Smoke 不是追求统计显著性，而是用最低成本检查能力是否跨越三种常见 Review 场景：逻辑、边界和安全作用域。

Smoke 的价值是及时暴露“只会一种题”的问题。它不能代表真实世界精度，也不能被描述为正式 benchmark。

## 2. 为什么每题只运行一次

`temperature=0.0` 可以降低随机性，但服务端实现仍可能存在细微变化。对同一题反复运行并挑最好结果会造成选择偏差。Phase 2 固定每题一次，正常模型失败保留为事实；只有网络或服务基础设施失败才可能经人工批准补跑。

## 3. Fixture 如何避免答案泄漏

每道 Fixture 包含两类信息：

- 模型可见：Repository identity、Base/Candidate Commit 和原始 Unified Diff；
- 评分专用：主要问题、允许锚点、预期 category/severity、允许次要问题和禁止的虚假问题。

评分专用字段不能出现在 Prompt。测试也由 Sandbox 独立运行，模型只能提出 Review，不能声称某个测试已经通过或失败来替代真实执行。

## 4. Finding 质量的几个维度

### 4.1 Recall 与 Precision

Recall 回答“预设核心问题找到了多少”；Precision 回答“模型报告的问题中有多少是真的”。只看 Recall 会鼓励模型罗列大量猜测，只看 Precision 又可能奖励沉默，因此二者必须同时报告。

### 4.2 文件和行号锚定

Finding 内容正确但锚定错行，会降低 PR Review 的可用性。现有合同先强制 Finding 位于 changed-line set，Phase 2 再由人工判断它是否落在该问题的合理行上。

### 4.3 重复与 Uncertainty

多个 Finding 若描述同一根因，只算一个有效发现，其余计为重复。无法从 Diff 确认的问题应进入 uncertainty；把猜测写成 confirmed defect 会被计为误报或分类错误。

## 5. 严重度校准为什么单独评估

Phase 1 正确发现缺陷，但将预期 `high` 评成 `critical`。这不影响 Recall，却会影响真实团队对 Review Agent 的信任：持续高估会制造告警疲劳，持续低估则会掩盖风险。

Phase 2 使用有序等级：

```text
low < medium < high < critical
```

严重度只对“正确匹配到预设问题”的 Finding 计算。指标包括：

- exact match：预测与人工预期是否相同；
- absolute error：相差几个等级；
- direction：高估还是低估；
- systematic bias：三题是否多数向同一方向偏移。

三题样本很小，因此只能说“观察到倾向”，不能声称统计上证明系统性偏差。

## 6. 三类任务分别检查什么

### 6.1 逻辑错误

检查模型能否从局部条件变化推导运行时后果，并与失败测试对应。它也提供与 Phase 1 的连续性对照。

### 6.2 边界或异常处理

检查模型是否能关注空值、越界、错误输入或异常传播，而不是只总结代码表面变化。Fixture 应只有一个明确主问题，避免把任务变成大型代码理解。

### 6.3 危险或越权修改

检查模型是否识别权限扩大、输入信任边界破坏或危险默认行为。该题评估安全判断，不应依赖模型猜测仓库之外的威胁模型。

## 7. 计划中的执行流

```text
verify clean committed contract
  -> verify three fixture identities
  -> for each fixture, serially:
       read exact diff
       call MiMo once
       validate response identity and one review tool call
       run allowlisted test
       validate schema and changed-line semantics
       write review.json / review.md / run_summary.json
  -> score against hidden fixture expectations
  -> aggregate quality, calibration, token and latency metrics
  -> stop at human decision gate
```

“隐藏”在这里仅表示不进入 Prompt，并非需要建立秘密服务器或复杂数据系统。

## 8. 复用与新增边界

应复用 Phase 1 的：

- MiMo Chat Completions adapter；
- response model/finish reason 校验；
- Local Git Sandbox；
- Review JSON Schema；
- changed-line 语义验证；
- Markdown renderer；
- 单命令密钥注入方式。

只新增三题所需的 Fixture、串行入口、评分和汇总。若实现开始出现通用任务平台、数据库或多层状态机，应回到本计划收缩范围。

## 9. 如何解释可能出现的结果

- 高 Recall、高 Precision、校准合理：支持进入 GitHub 只读接入计划。
- 高 Recall、低 Precision：模型倾向过度报告，需要约束 confirmed Finding。
- 低 Recall、高 Precision：模型保守，可能需要改善上下文或 Prompt。
- 缺陷识别正确但严重度持续偏高：主要是校准问题，不应误判为核心 Review 能力失败。
- Schema/Tool Call 失败：属于适配或模型结构输出问题，应与 Review 内容质量分开。
- 测试命令失败：若与 Fixture 预期一致，是缺陷证据；若命令无法运行，才是基础设施问题。

## 10. 实际离线实现

本阶段最终采用一个串行 Runner，没有建立通用平台：

- `scripts/materialize_phase2_fixtures.py`：确定性生成边界和权限两道新 Fixture；
- `scripts/run_phase2_mimo_smoke.py`：复用 Phase 1 模型、Sandbox、Workflow、合同与 renderer，串行执行三题并汇总；
- `tests/test_phase2_mimo_smoke.py`：验证 Fixture 身份、真实失败测试、评分、严重度偏差、答案隔离和付费入口门禁；
- `fixtures/phase2_boundary_error/`：空列表边界回归；
- `fixtures/phase2_permission_error/`：viewer 被错误授予删除权限。

Runner 的 `--check` 完全离线，当前输出：

```text
VALID phase2-smoke model=mimo-v2.5-pro tasks=3 smoke=NOT_RUN github_write=false
```

真实入口要求实现已提交、工作区干净、Preflight 证据有效、账户与 acknowledgement 精确匹配。三题按逻辑、边界、权限顺序各调用一次；每题立即保存 JSON、Markdown 和运行摘要，全部完成后才生成阶段汇总。

评分器要求 Finding 同时匹配预设文件、行、类别、confirmed assessment 和冻结根因词组，才记为 `semantic_rubric_match`。这只是机器筛选，不代替人工理解自然语言；阶段汇总中的最终核心召回和 precision 保持 `PENDING_HUMAN_REVIEW`，由主审核对话阅读 Finding 后确认。严重度误差只对 rubric 匹配项计算，并同时报告高估/低估次数与平均幅度。

单题模型或 Review 失败不会丢失整个阶段：Runner 写入不含异常正文的 `failure.json`，继续执行剩余任务，最后生成 `COMPLETED_WITH_FAILURES` 汇总。失败阶段固定区分为 `LOCAL_FIXTURE`、`MODEL_CLIENT`、`MODEL_RESPONSE`、`TEST_EXECUTION`、`REVIEW_VALIDATION` 和 `EVIDENCE_WRITE`；模型身份、finish reason、Tool Call 数量及语义还有更具体的安全原因码。失败题被计入三题总分母，但不会伪造 Finding、测试或 Token。

`phase2_scoring.json` 的 file、line、category 和 severity 会逐题与 Fixture 中的 `expected_primary_finding` 交叉验证；两份身份任一漂移都会在离线检查阶段拒绝。

Runner 不包含自动进入 Phase 3 的布尔门槛，最终 `next_step` 始终为 `HUMAN_REVIEW_REQUIRED`。

## 11. 半年后阅读代码的顺序

分支实现后按以下顺序补充具体文件和行号：

1. 三道 Fixture 的 Base/Candidate 和评分元数据；
2. Phase 2 串行 Runner；
3. 评分函数，尤其是 Finding 匹配和 severity ordinal；
4. 汇总生成逻辑；
5. 离线拒绝测试；
6. `RESULTS.md` 中的真实逐题结果。

## 12. 当前未知

- 两道新 Fixture 的最终代码和 Hash；
- 三题实际模型输出；
- 严重度高估是否重复；
- 三题 Token、耗时和费用；
- 是否足以进入 GitHub 只读阶段。

这些问题必须通过 Phase 2 的单次真实运行回答，不能在计划阶段提前填写。
