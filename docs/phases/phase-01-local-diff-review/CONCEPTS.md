# Phase 1 讲解：从固定 Diff 到真实本地 Review

> 当前状态：离线实现与测试完成，真实 MiMo 调用尚未开始。
>
> 本文将在分支实现过程中补充实际代码路径。凡标记“计划”的内容都不是已完成结果。

## 1. Phase 1 要连接的两端

Phase 0 已分别验证了两部分：

- 本地 Review 合同能够处理固定 Diff、测试结果、Schema 和 Markdown；
- MiMo 可以通过 `ChatOpenAI` 以 Chat Completions 方式构造。

Phase 1 要做的是把两端真正连起来：

```text
真实 MiMo 模型
      |
      v
Open SWE Reviewer 边界
      |
      v
固定本地 Git Diff + 固定测试
      |
      v
Review JSON -> Markdown
```

这一步的关键不是增加功能，而是证明数据真的经过了模型和 Review workflow。

## 2. 官方 Open SWE Reviewer 做了什么

固定上游 Commit 中，`langgraph.json` 注册：

```text
agent.graphs.reviewer:traced_reviewer_agent
```

该入口指向：

```text
agent.reviewer:get_reviewer_agent
```

官方 Reviewer 的主要边界：

1. 在第一次模型调用前准备 Review 仓库。
2. 获取并物化 PR Diff。
3. 计算 changed-line set。
4. 为模型提供 `fetch_review_diff`、finding 管理和发布工具。
5. `add_finding` 拒绝 Diff 外位置。
6. 最终调用 `publish_review`。

官方产品默认围绕 GitHub PR、Sandbox provider 和发布流程运行。Phase 1 没有 GitHub App，因此必须把输入和输出两端局部替换：输入来自固定本地 Git 仓库，输出写入本地文件。

## 3. 什么叫“使用 Open SWE 路径”

理想实现是直接构造固定官方 `get_reviewer_agent`，传入预配置 MiMo model，并替换仓库/Sandbox/发布依赖。

但如果完整 graph 强制依赖 GitHub metadata、LangSmith Sandbox 或其他部署环境，为一个本地 Fixture 搭建全部云组件会偏离“快速原型”目标。

因此本阶段接受两种实现层级：

### A. 官方 graph 最小本地化

复用官方 Agent factory、Prompt、middleware 和 finding 工具，只替换：

- Repo/Diff provider；
- Sandbox；
- publish sink。

这是优先方案。

### B. 最薄官方兼容 adapter

如果 A 明显超出本阶段成本，则复用官方 Reviewer Prompt 和关键纪律，并用本项目现有 workflow 处理本地 Diff、测试、Schema 和 Markdown。

B 仍然可以形成工作原型，但必须如实称为“Open SWE Reviewer-compatible local slice”，不能称为运行了官方完整 graph。

选择 A 或 B 的依据是实现成本和依赖，而不是为了让结果更好看。

## 4. 为什么 MiMo 不能直接走默认 OpenAI 路由

固定 Open SWE 的 `make_model("openai:...")` 默认启用 OpenAI Responses API。MiMo 提供 OpenAI-compatible Chat Completions 接口，两者请求协议不完全相同。

本项目使用预配置模型实例：

```python
ChatOpenAI(
    model="mimo-v2.5-pro",
    base_url="https://api.xiaomimimo.com/v1",
    temperature=0.0,
    max_tokens=4096,
    max_retries=0,
    use_responses_api=False,
)
```

然后把该实例直接交给 Agent factory 或 adapter。这样避免 Open SWE 的默认 provider router 把 MiMo 请求发送到不兼容的 Responses endpoint。

## 5. 为什么使用结构化 Tool Call

自由文本 Review 很难稳定解析，也难区分 Finding 与 Uncertainty。计划让模型通过一个结构化 Review tool 返回：

- summary；
- findings；
- uncertainties；
- decision。

Workflow 再补入不能由模型决定的字段：

- 精确 Candidate Commit；
- 真实测试命令；
- 真实测试 passed 状态。

模型不能通过输出文本伪造测试成功。

## 6. Changed-line 约束

Unified Diff hunk header 包含 Base 和 Candidate 的起始行号。解析器逐行推进：

- 上下文行同时推进 Base 和 Candidate；
- 删除行只推进 Base；
- 新增行记录 Candidate `(file, line)` 并推进 Candidate。

最终 Finding 的 `file` 和 `line` 必须在这个集合中。Fixture 的主要改动锚点是 `calculator.py:2`。

该约束解决的是评论位置问题，不自动证明缺陷内容正确。Finding 的证据仍需由代码和测试支持。

## 7. 固定测试为何由 Sandbox 执行

模型可以建议测试，但不能自报“测试通过”。本阶段固定运行：

```bash
python -m unittest test_calculator.py
```

命令应在固定 Candidate checkout 中执行。返回码由执行层写入 Review：

```json
{
  "commands": ["python -m unittest test_calculator.py"],
  "passed": false
}
```

对于这个故意含回归的 Fixture，测试失败是预期证据，不代表 Review workflow 运行失败。

## 8. JSON 与 Markdown 的关系

`review.json` 是规范结果，`review.md` 是展示层。正确顺序是：

```text
模型结构输出
  -> 加入真实 Commit/测试
  -> Schema 与语义验证
  -> 保存 review.json
  -> 从同一 JSON 渲染 review.md
```

不能让模型另外生成一份 Markdown，因为两份结果可能出现 Finding、Decision 或测试状态不一致。

## 9. 真实调用与 Fake 测试的区别

Fake workflow 已经证明：

- 控制流可以运行；
- 拒绝规则有效；
- 固定 Finding 可以渲染。

Fake workflow 没有证明：

- MiMo 能理解 Diff；
- MiMo 能稳定产生结构化 Tool Call；
- 官方 Reviewer Prompt 与 MiMo 兼容；
- 模型会找到核心回归；
- 模型不会产生虚假问题。

Phase 1 的意义就是取得这些第一手真实结果。

## 10. 凭据边界

`MIMO_API_KEY` 只能存在于调用进程环境和 HTTPS 请求头。不得进入：

- 项目文件；
- Prompt；
- Review JSON/Markdown；
- 异常正文；
- Git；
- 本地 Fixture；
- 未来 Sandbox。

脚本应避免打印完整环境和请求对象。运行后由用户 `unset MIMO_API_KEY`。

## 11. 错误分类

### 基础设施错误

- API 鉴权或网络失败；
- 依赖导入失败；
- 官方 graph 无法构造；
- Tool Call 无法被 adapter 读取；
- 输出文件写入失败。

允许最小修复后补跑一次。

### 模型正常失败

- 漏掉核心缺陷；
- 产生误报；
- 严重度不合理；
- Decision 不合理；
- 将 uncertainty 写成 confirmed finding。

这些是研究结果，不自动重跑。

### 合同错误

- Finding 不在 changed line；
- 未知字段；
- 重复 Finding；
- `REQUEST_CHANGES` 没有高严重度 confirmed finding。

应判断是模型输出问题还是 adapter 解析问题。不能直接删除约束以获得 PASS。

## 12. 实际采用的实现

本阶段选择方案 B：`Open SWE Reviewer-compatible local slice`。

没有直接启动官方完整 graph，原因是固定官方 Reviewer 在工厂构造和运行时依赖 GitHub PR metadata、Sandbox provider、Deep Agents middleware 和 publish 工具。为一个固定本地 Diff 配齐这些外部系统会延迟第一版原型。

实际复用的官方边界：

- Reviewer 只审查 Candidate Diff；
- Diff 内容被视为不可信数据；
- Finding 必须锚定 changed line；
- 只报告可命名具体 failure mode 的问题；
- speculation、style nit、pre-existing 和 out-of-diff 问题禁止作为 confirmed finding；
- uncertainty 与 finding 分离；
- 通过单一结构化 Review tool 完成输出。

没有运行的官方组件：

- `get_reviewer_agent` 完整 Pregel graph；
- GitHub PR metadata 获取；
- LangSmith/Daytona/其他 Sandbox provider；
- finding 存储和 `publish_review`；
- GitHub Review thread reconcile。

这一区分已经固化在运行摘要字段：

```text
adapter_kind=OPEN_SWE_REVIEWER_COMPATIBLE_LOCAL_SLICE
```

### 12.1 `local_git_sandbox.py`

本地 Sandbox 只接受 Fixture 清单中的测试命令。Git 和测试均通过 argv、`shell=False` 运行：

- 验证当前 HEAD 精确等于 Candidate Commit；
- 验证 Base Commit 存在；
- 读取 Base 到 Candidate 的 exact diff；
- 将允许的 `python` 替换成当前 `.venv` 的 Python；
- 保存测试命令和真实 return code。

测试故意返回 `1`，因为 Candidate 包含已知零分母回归。该失败随后被记录为 `tests.passed=false`。

### 12.2 `open_swe_adapter.py`

该模块定义单一 `submit_local_review` tool。MiMo 必须返回恰好一个调用；并行调用被关闭。Adapter 保存标准化 usage metadata、实际响应模型和 finish reason，但不保存原始响应或 Tool Call ID。

Prompt 中只有 Repository identity、Base/Candidate Commit 和原始 Diff，没有 Fixture 的 `expected_primary_finding`，因此离线预期答案不会泄漏给模型。

### 12.3 `run_phase1_mimo_review.py`

真实入口提供：

- `--check`：完全离线，仅检查固定身份和当前运行状态；
- `--execute-once`：要求精确 acknowledgement、网络环境变量和账户类型；
- 真实调用前要求工作区干净且关键合同文件已被 Git 跟踪；
- 要求已有 MiMo Preflight PASS 证据；
- 只允许固定 Phase 1 Fixture；
- 成功后原子写入 `review.json`、`review.md` 和 `run_summary.json`；
- 输出目录在 `artifacts/phase1/`，默认不进入 Git。

当前离线输出：

```text
VALID phase1-review model=mimo-v2.5-pro preflight=NOT_RUN review=NOT_RUN
```

### 12.4 模型身份闭环

付费运行前复审发现，最初 Preflight 把本地配置常量当作模型身份，Review 也只记录、没有强制验证 API 返回身份。这会使服务端错误路由仍被归因给 MiMo。

修复后，`validate_mimo_response_identity()` 只读取真实 response metadata：

```text
response_metadata.model_name 或 response_metadata.model
response_metadata.finish_reason
```

Preflight 和 Review 均要求：

```text
response_model=mimo-v2.5-pro
finish_reason=tool_calls
```

Preflight 证据同时保存 configured model 与 response model；后续 `--check` 会重新读取并校验。Review 的 `run_summary.json` 同样保存并复核这两个返回字段。错误模型身份、缺失身份或 `finish_reason=stop` 均失败关闭。

## 13. 实际代码阅读路线

分支实现后，本文应补充精确行号。当前建议阅读顺序：

1. `src/open_swe_review_agent/mimo.py`：模型构造。
2. `src/open_swe_review_agent/open_swe_adapter.py`：官方 Review 纪律如何映射为本地 Tool Call。
3. `src/open_swe_review_agent/local_git_sandbox.py`：如何锁定 Diff 和测试。
4. `workflow.py`：结果如何组合。
5. `contracts.py`：如何拒绝不可信结果。
6. `render.py`：如何从同一 JSON 生成 Markdown。
7. `scripts/run_phase1_mimo_review.py`：真实执行门禁和产物。

## 14. 真实运行后本文还要补什么

- 实际采用 A 还是 B，以及原因；
- 真实控制流图；
- 新增文件及职责；
- Tool schema 和模型返回结构；
- API usage metadata 的实际形状；
- 输出保存策略；
- 遇到的兼容性问题；
- 关键代码行号；
- 与计划不同的设计选择。

这些内容应来自真实运行，不应在运行前猜测完成。
