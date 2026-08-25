# STAR 面试讲稿

## 1. 30 秒版本

我做了一个基于 Open SWE Reviewer 约束的 GitHub Diff Review Agent。它把本地 Diff 或 GitHub PR 转成 changed-line 集合，调用 MiMo 输出严格 Review JSON，再通过最小权限 GitHub App 和人工 Payload Hash Gate 控制发布。Phase 1 单题召回 1/1，Phase 2 三类缺陷召回 2/3、precision 2/2，Phase 3 跑通真实 PR 只读快照。Phase 4 的一次受控发布暴露了关键负结果：模型描述对了缺陷，却把评论锚错一行，所以系统失败关闭且没有重试。这让我明确了“属于 Diff”与“语义上属于该行”是两种不同的可靠性要求。

## 2. 两分钟 STAR 版本

### Situation

我之前做过一个执行型软件工程 Agent 项目，发现模型能力和 Agent 协议会共同影响结果。我想换一个更适合静态分析和权限控制的场景，因此选择 GitHub Code Review，并参考固定 Commit 的 Open SWE Reviewer 设计边界。

### Task

我的目标不是做完整平台，而是尽快验证一条可信链路：给定固定 Diff 或 PR 快照，模型只能输出结构化 Finding；每条 Finding 必须锚定真实改动行；只有经过人工审核的精确 Payload 才能用最小权限 GitHub App 发布。同时我要量化召回、precision、合同失败、严重度偏差和 GitHub 副作用。

### Action

我把系统拆成四层：

1. 输入层固定 Base/Head、Diff 和 candidate changed lines；
2. 模型层固定 MiMo V2.5 Pro、一次结构化 Tool Call和零重试；
3. 合同层使用 JSON Schema 加 Python 语义检查，拒绝 Diff 外、重复或决策不一致的 Finding；
4. 发布层用单仓库 GitHub App、Prepare/Publish 分离和独立 Payload SHA256 人工 Gate，唯一写接口是一次 COMMENT Review。

实验按 Phase 1～4 递进：先跑单个本地逻辑回归，再跑三类 Smoke，然后读取真实公开 PR，最后才在自有测试 PR 上开放一次写入。每次失败都不补跑，避免把正常模型失败或外部副作用覆盖掉。

### Result

Phase 1 核心缺陷召回 1/1；Phase 2 人工召回 2/3、precision 2/2、误报 0，但有一次合同失败，三个可观察正确 Finding 都高估一级。Phase 3 用 4 次 GET 验证了真实 PR 的稳定快照，写请求为 0。Phase 4 的最小权限和双 Gate 确实控制住了唯一一次写入，GitHub 创建了 Review，但发布后验证失败；人工确认模型把第 8 行的除数错误锚到第 7 行。最终我保留远端错误 Review、禁止重试并冻结为负结果。结论是系统已证明输入、权限和失败关闭链路，但 changed-line membership 还不足以保证 Evidence 与具体代码行语义一致。

## 3. 5 分钟展开结构

### 先讲问题

- LLM 能写 Review 文本，不代表能安全发布 Review。
- GitHub Review 需要快照身份、行号、权限和幂等边界。
- 可靠性必须同时覆盖模型输出和平台副作用。

### 再讲架构

- Local Fixture 与 GitHub PR 共用统一 Diff/changed-line 合同。
- 模型只负责提出结构化 Review，不拥有 GitHub Client。
- Schema 验证字段，Python 检查上下文语义。
- GitHub App 权限和代码 endpoint allowlist 双重限制。
- 人工 Gate A 批准目标 PR，Gate B 批准 Payload Hash。

### 然后讲实验

- Phase 1：证明最小闭环。
- Phase 2：测试跨类别和失败关闭。
- Phase 3：替换真实 PR 输入，不加写权限。
- Phase 4：只增加受控写入变量。

### 最后讲负结果

- Review 确实发布，但不是 PASS。
- API 回读字段不兼容是一个实现问题。
- 更关键的是模型给错行号，而该行仍属于 Diff。
- 因此下一代合同需要绑定代码片段，而非只验证行号集合。

## 4. 常见追问与回答

### 为什么不把评论改到正确行再发一次？

因为这会改变一次性实验事实，也会绕过“正常模型失败不重试”的原则。目标 PR 是自有测试 PR，保留错误不会影响第三方；它反而是更有价值的可靠性案例。

### 为什么 Phase 2 逻辑题不能根据模型原文人工补分？

运行器只保存了脱敏合同失败证据，没有合法 Review。不可审计输出不能进入召回或 precision 统计，否则指标依赖事后猜测。

### Phase 3 的 APPROVE 能否证明 PR 正确？

不能。Phase 3 没有 Gold Finding，也没有执行 PR 代码或测试。它只证明模型基于静态 Diff 没有确认问题，以及 GitHub 只读快照链路可工作。

### JSON Schema 为什么不够？

Schema 能限制字段、类型和枚举；Finding 是否属于当前 Diff、decision 是否与 Finding 一致需要运行时上下文。Phase 4 又进一步证明，即使运行时验证了 changed-line membership，也仍需要 Evidence 与代码片段的语义绑定。

### 为什么使用强 API 模型？

先用强模型验证 Scaffold，可以减少“模型太弱还是框架有问题”的归因混淆。即使使用强模型，项目仍观察到合同失败、严重度偏差和行号错误，这说明可靠性不能只靠更强模型。

### 你本人做了什么，AI 做了什么？

这是 AI-assisted engineering 项目。AI 负责大量代码和文档生成；我负责研究问题、权限边界、阶段设计、外部调用批准、代码和证据复审、指标口径以及是否继续实验。Phase 4 锚点错误就是通过人工复核发现并决定停止的。

### 如果再做一版，最先改什么？

我会让 Finding 同时绑定规范化目标代码片段或行内容 Hash，并在 Gate B 展示行号与实际代码；然后实现 GitHub position 到 blob line 的确定性转换。不会先扩展多仓库、Webhook 或自动修复。

## 5. 面试中不可夸大的说法

不要说：

- “我运行了官方完整 Open SWE Reviewer graph。”
- “Phase 4 发布成功。”
- “真实 PR 的准确率是多少。”
- “系统已经可以无人值守自动 Review。”
- “所有代码都是我逐行手写。”

可以说：

- “我实现了 Open SWE Reviewer-compatible local slice。”
- “我用真实 GitHub PR 验证了只读快照，并在自有 PR 上执行了一次受控写入。”
- “远端 Review 创建成功，但终态验证和人工语义复核失败，所以最终记为负结果。”
- “项目明确暴露了 changed-line 合法与语义锚点正确之间的差距。”

## 6. 面试前速记

```text
Phase 1: recall 1/1, false finding 0, severity +1
Phase 2: recall 2/3, precision 2/2, one contract failure, severity +1 on both valid findings
Phase 3: pallets/click#3021, 4 GET, 3 files, 38 changed lines, APPROVE, 0 write
Phase 4: own PR #1, one COMMENT POST, review 5020924942, wrong anchor 7 vs defect 8, no retry
```
