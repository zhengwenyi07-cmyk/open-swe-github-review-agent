# Open SWE GitHub Review Agent：最终技术复盘

## 1. 项目一句话定义

这是一个 AI-assisted GitHub Diff Review 原型：它借鉴固定版本 Open SWE Reviewer 的约束，把本地 Fixture 或 GitHub PR Diff 转换成 changed-line 集合，调用 MiMo V2.5 Pro 生成结构化 Review，经过 Schema 与语义校验后输出 JSON/Markdown，并用最小权限 GitHub App 验证一次受控发布。

最终结果不是“自动 Code Review 已可生产使用”，而是：只读链路和权限受控写入路径已经跑通；模型在小样本上能识别多类缺陷，但存在合同失败、严重度上偏和错误行号锚定，真实发布未通过终态验证。

## 2. 为什么做这个项目

旧 mini-swe 项目研究的是执行型 Agent：模型通过 Tool Call 修改代码并运行测试。该项目暴露了模型能力和 Agent 协议两个不同瓶颈。新项目改为 Code Review 场景，希望回答：

1. 能否把模型输出限制为可机器消费的 Review，而不是自由文本？
2. 能否证明每个 Finding 只指向真实 Diff 行？
3. 从本地固定 Diff 迁移到 GitHub PR 时，如何保持 Base/Head 和 Diff 快照一致？
4. 模型输出什么时候才允许产生 GitHub 外部副作用？
5. 当发布后验证失败时，系统是否能停止而不盲目重试？

这是求职作品集原型，因此优先完成一条可工作的研究链，没有建设 Webhook 服务、队列、数据库、多租户或自动修复平台。

## 3. 上游依据与实现边界

项目固定参考：

```text
repository=https://github.com/langchain-ai/open-swe.git
commit=daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc
reviewer_graph=agent.graphs.reviewer:traced_reviewer_agent
reviewer_factory=agent.reviewer:get_reviewer_agent
```

实际运行的是 `OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE`，复用了以下思想：

- Diff 是审查边界；
- PR 内容是不可信数据；
- Finding 必须绑定 changed line；
- confirmed Finding、Suggestion 和 Uncertainty 分离；
- 模型只通过一个命名 Tool Call 提交 Review。

没有运行官方完整 Pregel graph、官方 Sandbox provider 或 `publish_review`。面试时必须明确这一点。

## 4. 核心架构

### 4.1 输入层

本地模式通过 `LocalGitSandbox` 读取固定 Base/Candidate Diff，并运行冻结测试。GitHub 模式通过 `GitHubReadOnlyClient` 执行：

```text
metadata A
  -> files page 1
  -> raw diff
  -> metadata B
  -> Base/Head/PR identity 一致性
  -> files 与 raw diff 交叉验证
  -> candidate changed-line set
```

任何 SHA 漂移、patch 缺失、分页、二进制文件、路径异常或预算超限都会失败关闭。

### 4.2 模型层

MiMo 使用 OpenAI-compatible Chat Completions，不走 Open SWE 默认的 Responses API：

```text
model=mimo-v2.5-pro
temperature=0.0
max_tokens=4096
parallel_tool_calls=false
max_retries=0
```

API 返回的真实模型身份和 `finish_reason=tool_calls` 都必须验证。模型只能调用一次 `submit_local_review`。

### 4.3 合同层

Review 先通过 Draft 2020-12 JSON Schema，再做运行时语义检查：

- 字段集合与枚举合法；
- Finding 文件和行属于 changed lines；
- Finding 不重复；
- decision 与 confirmed Finding 严重度一致；
- 真实测试状态不能由模型伪造。

Phase 4 证明该合同仍有缺口：它能验证“行属于 Diff”，不能验证 Evidence 描述的代码表达式确实位于该行。

### 4.4 输出与发布层

合法 Review 保存为 `review.json`，再确定性渲染 `review.md`。Phase 4 进一步从 Review 生成固定 `publish_payload.json`，由人工审核其精确 SHA256。

发布使用只安装在项目仓库的 GitHub App：

- Prepare：installation token 只申请 Pull requests read；
- Publish：才申请 Pull requests write；
- 唯一仓库内容写路由：Create Pull Request Review；
- event 固定为 `COMMENT`；
- 发布前重读 PR Head 并检查重复 Marker；
- POST 不自动重试；
- 发布后 GET Review 和 Comments 做逐项验证。

## 5. 关键代码地图

| 文件 | 作用 | 面试重点 |
|---|---|---|
| `src/open_swe_review_agent/diff_parser.py` | 解析 Unified Diff 并跟踪 Candidate 行号 | Base/Candidate 行号如何推进 |
| `src/open_swe_review_agent/contracts.py` | Schema 后的语义验证 | 为什么 Schema 不能表达所有约束 |
| `src/open_swe_review_agent/workflow.py` | 编排 Sandbox、Model、测试和 Review | 模型文本与真实测试证据如何分离 |
| `src/open_swe_review_agent/mimo.py` | MiMo Chat Completions 适配与响应身份校验 | 为什么禁用 Responses API |
| `src/open_swe_review_agent/github_readonly.py` | 安全 GET Client 与 PR 快照 | 双 metadata 读取和预算限制 |
| `src/open_swe_review_agent/github_app_auth.py` | GitHub App JWT/installation token | 最小权限不只靠平台设置 |
| `src/open_swe_review_agent/github_review_publisher.py` | Payload、Marker、唯一 POST 和远端验证 | 幂等、歧义写入和失败关闭 |

## 6. 四阶段实验如何递进

### Phase 1：最小真实 Review

固定逻辑回归上，MiMo 一次调用正确定位 `calculator.py:2`，召回 `1/1`、误报 0。严重度从预期 high 高估为 critical。结论是链路可工作，但单题不能证明泛化。

### Phase 2：三类 Smoke

三道任务各调用一次。边界和权限题命中，逻辑题合同失败。人工召回 `2/3`、precision `2/2`、误报 0；两个有效 Finding 都高估一级。结论是跨类别能力存在，但结构化输出和严重度校准仍不稳定。

### Phase 3：GitHub 只读 PR

公开 PR `pallets/click#3021` 的 Base/Head、3 个文件、4,659 bytes Diff 和 38 个 changed lines 形成一致快照。MiMo 输出 `APPROVE`、0 Finding、1 Uncertainty；因为没有 Gold 且未运行测试，不能声称准确率或运行时正确性。

### Phase 4：受控写入

GitHub App、目标合同、Prepare 和 Payload Hash Gate 均真实执行。唯一 POST 创建了 Review `5020924942`，没有其他副作用或重试。随后回读因 API 坐标表示不兼容而失败；人工进一步发现 Finding 锚到第 7 行，真正缺陷位于第 8 行。最终冻结为 `COMPLETED_WITH_VERIFICATION_FAILURE`。

## 7. 三类失败及处理原则

### 模型/合同失败

Phase 2 模型调用后没有形成合法 Review。处理方式是保存脱敏失败原因、保守计为漏报、不补跑。

### 平台表示不兼容

Phase 4 Payload 使用 `line/side`，GitHub 回读返回 `position/original_position`。这要求验证器支持安全、确定的坐标转换，但不能通过放宽校验直接忽略字段。

### 语义锚点错误

模型 Evidence 描述第 8 行表达式，却给出第 7 行。因为第 7 行也是 changed line，结构门禁没有拒绝。这类错误需要把目标代码片段或行内容 Hash 与 Finding 一起验证，而不是只检查集合成员关系。

## 8. 安全与权限设计的真实效果

已经证明：

- API Key 和 GitHub 私钥未进入 Git；
- PR 内容没有进入 system instruction；
- GitHub App 安装范围为单仓库；
- 写入前存在目标身份 Gate 和 Payload Hash Gate；
- 唯一写请求是 Create Review，event 为 COMMENT；
- Head 漂移与重复 Marker 有拒绝测试；
- 失败后没有第二次 POST。

没有证明：

- 多仓库或私有仓库生产可用性；
- Webhook 并发处理；
- 所有 GitHub Diff 类型的坐标映射；
- 自动 Review 可以无人值守发布。

## 9. 为什么保留错误远端 Review

删除、编辑或补发会改变实验事实，并可能让最终仓库看起来像一次成功演示。项目选择保留错误锚点，原因是：

1. 写入发生在用户控制的测试 PR，不影响第三方仓库；
2. Review body 明确披露这是受控实验且未运行代码；
3. 远端错误与本地冻结证据共同展示了真实失败；
4. 禁止重试验证了幂等与失败处理原则不是口号。

## 10. 如果继续研究，最小改进是什么

Phase 5 当前不启动。如果未来独立继续，优先级应是：

1. 在 Finding 中绑定目标行原文或规范化代码片段 Hash；
2. 在人工 Gate 中同时展示行号和该行实际代码；
3. 基于冻结 Diff 实现 `position ↔ blob line` 的确定性转换；
4. 用新的受控 PR 验证，而不是重写或补跑当前 PR。

不应立即扩展为多仓库服务、自动修复、Webhook 队列或更多模型对照，因为当前最小失败已经明确指出首要缺口。

## 11. AI 辅助开发的诚实边界

项目由 AI 大量生成代码和文档。我的责任是：选择研究问题、定义权限和实验边界、批准外部调用、复审代码与结果、识别错误锚点并决定停止重试。面试时不应声称所有实现逐行手写；应展示自己能够解释关键组件、验证证据并根据负结果调整路线。

## 12. 最终结论

这个项目最有价值的结果不是“一次 GitHub 自动 Review”，而是建立并验证了一条分层可信链：固定输入、结构化输出、changed-line 门禁、只读 PR 快照、最小权限 App、人工 Hash Gate 和失败关闭。

同时，Phase 4 证明结构正确不等于语义正确。模型可以正确描述一个缺陷，却把评论放在相邻的 changed line。项目因此停在可解释的负结果，而没有通过补跑制造成功。这一判断比继续堆功能更适合作为面试中讨论工程可靠性、实验设计和 AI 系统边界的材料。

## 13. 离线复核命令

以下命令不会调用 MiMo 或写 GitHub：

```bash
cd /home/zhengwenyi/projects/open-swe-github-review-agent
source .venv/bin/activate

python -m unittest discover -s tests
python -m pip check
python scripts/run_phase3_github_readonly.py --check
python scripts/run_phase4_controlled_publish.py --check
git diff --check
git status --short
```

Phase 4 `--check` 正确输出失败状态，不应为了得到 PASS 而修改原始证据。
