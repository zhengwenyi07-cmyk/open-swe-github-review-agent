# 上游身份与最小 Review 路径

## 官方依据

本项目固定 Open SWE 官方仓库 `https://github.com/langchain-ai/open-swe.git` 的 Commit `daab5de0baf2d8b16a7e2ae3fadbcb632bace8cc`。固定信息保存在 `upstream_lock.json`，只读源码位于 `/home/zhengwenyi/projects/open-swe-upstream`。

该 Commit 的 `langgraph.json` 注册 Reviewer graph 为 `agent.graphs.reviewer:traced_reviewer_agent`，入口转发到 `agent.reviewer:get_reviewer_agent`。官方 Reviewer 的关键行为是：

1. 在首次模型调用前准备仓库和 Review Diff；
2. 计算允许评论的 changed-line 集合；
3. 使用 Reviewer 专用 finding/publish 工具，而不是 Coding Agent 的 commit/push/开 PR 工具；
4. 对 Diff 外 finding 失败关闭；
5. 维护 findings，最终由 `publish_review` 发布。

官方完整 Reviewer 还依赖 GitHub PR 元数据、Sandbox provider、运行时配置、LangGraph/Deep Agents 中间件和发布工具。Phase 1 不伪造这些外部依赖，也不申请 GitHub 权限。

## 本项目的 Phase 1 最小切片

```text
固定本地 Git Diff
  -> 解析 changed-line 集合
  -> ReviewModel（本轮 Fake；后续 MiMo）
  -> ReviewSandbox（本轮 Fake）执行固定检查
  -> Review JSON Schema + 语义验证
  -> 本地 Markdown
```

这个切片复用了官方 Reviewer 最重要的研究边界：审查而非改码、finding 必须锚定 Diff、发布前结构化验证、模型与 Sandbox 可替换。它刻意没有宣称自己就是完整的官方 graph，也没有复制或改名旧 mini-swe loop。

## 当前与官方 graph 的差距

- 尚未把预配置 MiMo `ChatOpenAI` 实例注入官方 `get_reviewer_agent`；
- 尚未安装/启动官方 Open SWE 完整服务依赖；
- 尚未使用任何真实 Sandbox provider；
- 尚未读取 GitHub PR、Review thread 或 Check Run；
- 尚未调用 `publish_review`；
- 尚未验证官方 graph 在固定本地 fixture 上的真实模型执行。

这些是下一次真实 Smoke 的工作，而不是本轮静态准备已经完成的内容。

## Review 合同

`schemas/review.schema.json` 要求：

- `findings` 只记录有证据的问题或明确标记为 suggestion 的改进；
- 无法确认的问题进入独立 `uncertainties`；
- finding 文件与行必须落在 Candidate Diff 的新增/修改行；
- 同一文件、行、类别不得重复；
- `APPROVE` 不得带 finding；
- `REQUEST_CHANGES` 至少包含一个 confirmed high/critical finding；
- 未知字段直接拒绝。

## 固定 Fixture

`scripts/materialize_phase1_fixture.py` 可确定性重建 `.fixtures/phase1_repo`：

- Base：`030396458d0e6fd6b8bf444c0ef24d1ea495b5b3`
- Candidate：`746e90b56d3150d96acbff4a0f02308ab151669c`
- Diff SHA256：`e025350863e5054547661826f042d4c6e8ab40008947e35e221c12e9c10061ea`

Candidate 把零分母的既定返回行为改成异常；固定单元测试可重复证明回归。Fixture 不含秘密，也不依赖旧项目证据。
