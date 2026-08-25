# Phase 3 计划：GitHub PR 只读接入

> 状态：`IMPLEMENTED_NOT_RUN`
>
> 本文是交给后续聊天分支执行的完整计划。离线实现已经完成，真实 GitHub/MiMo 运行尚未开始；不得把计划值写成真实 PR 结果，也不得自动进入 GitHub 写入阶段。

## 1. 阶段背景

Phase 1 已证明固定本地 Diff 到结构化 Review 的最小链路可工作。Phase 2 在三类 Diff 上取得人工核心缺陷召回 `2/3`、Finding precision `2/2`、误报和重复 Finding 均为 `0`；一题发生 `REVIEW_CONTRACT_FAILURE`，且三个可观察正确 Finding 都高估一个严重度等级。

Phase 3 不改模型、不针对真实 PR 调 Prompt，也不发布 Review。它只把输入从本地 Fixture 换成一个主对话明确批准的 GitHub PR 快照，验证真实平台输入能否安全进入既有 Review 合同。

## 2. 研究问题

本阶段必须回答：

1. GitHub PR 输入能否替代本地固定 Fixture，同时保持现有 Review 合同？
2. GitHub patch 缺失、截断、二进制或文件过大时，系统能否失败关闭？
3. 如何保证 Finding 仍然只能锚定真实 candidate-side changed line？
4. 如何验证 Base/Head SHA、文件列表和 Diff 属于同一个稳定 PR 快照？
5. 如何防止凭据进入日志、Prompt、产物或 Git？
6. 如何从代码和运行证据证明本阶段没有任何 GitHub 写操作？

## 3. 本阶段唯一数据流

```text
approved GitHub PR
  -> read-only metadata snapshot A
  -> paginated changed-files metadata
  -> raw unified diff
  -> read-only metadata snapshot B
  -> snapshot consistency + size + patch checks
  -> changed-line set
  -> existing MiMo/Open SWE-compatible review adapter
  -> existing Review Schema + semantic validation
  -> local review.json / review.md / run_summary.json
  -> human review gate
```

GitHub 是只读输入源，本地文件是唯一输出端。不得出现 publish、comment、check run、merge、branch update 或 repository mutation。

## 4. 认证方式选择

优先顺序固定为：

1. **公开 PR 无 Token 模式**：如果目标仓库和 PR 公开、API 可稳定读取且速率限制足够，优先不提供 Token。
2. **细粒度 GitHub Token**：仅在无认证读取不稳定或目标 PR 需要认证时使用。只授予目标仓库的 Metadata、Contents、Pull Requests 只读权限，不授予任何写权限。

运行时变量建议为 `GITHUB_TOKEN`。分支和主对话不得索取、打印、读取回显或保存 Token 内容。Token 只附加到 `api.github.com` 的 HTTPS 请求，并且只在单条正式命令的环境中导出。

不得使用 classic token、GitHub App 写权限、SSH 私钥或浏览器登录状态来绕过本计划。

## 5. 目标 PR 的批准与选择

实现前不预设某个答案。主对话在真实运行前只批准以下身份：

```text
repository=owner/repository
pull_number=<positive integer>
expected_visibility=PUBLIC 或 PRIVATE
```

目标 PR 应满足：

- 项目所有者明确允许读取；
- Base 与 Head 均可由 GitHub API 返回 40 位 SHA；
- 最好包含 1～5 个文本文件和人工可理解的改动；
- 不包含 secrets、私有客户数据、生成文件或超大二进制；
- 不为了匹配模型能力而选择已知答案或把预期 Finding 写入 Prompt；
- 在执行前没有已知会立即 force-push 的活动。

若 PR 超出下述硬边界，应更换目标 PR，而不是截断、抽样或扩大预算。

离线实现新增最小目标合同：

```text
configs/phase3_github_readonly_target.json
```

初始状态为 `NOT_APPROVED`，repository、PR number 和 authentication mode 均为 `null`。真实运行前由主对话批准精确身份并提交该文件；正式 CLI 必须与合同完全一致，否则在 Client 构造前拒绝。

## 6. 固定读取边界与上下文预算

第一版硬限制建议冻结为：

```text
max_changed_files=8
max_pages=1
files_per_page=100
max_metadata_response_bytes=1_MiB
max_files_response_bytes=4_MiB
max_raw_diff_bytes=96_KiB
max_single_patch_bytes=32_KiB
max_total_diff_lines=2000
max_candidate_changed_lines=600
max_pr_title_chars=256
max_pr_body_chars=4000
max_prompt_chars=120000
http_timeout_seconds=30
automatic_retries=0
model_attempts=1
```

实现时若根据现有客户端或模型合同必须调整数值，分支必须在联网前说明理由，由主对话批准后统一修改计划和测试。禁止无界分页、无界读取仓库内容或静默截断。

模型条件沿用 Phase 2：

```text
model=mimo-v2.5-pro
temperature=0.0
max_tokens=4096
parallel_tool_calls=false
attempts_per_task=1
```

## 7. 最小 GitHub 只读 Client

建议新增 `src/open_swe_review_agent/github_readonly.py`，职责仅包括：

- 接受已批准的 `owner/repository` 和 PR 编号；
- 只允许 `https://api.github.com`，禁止显式端口、URL 凭据和重定向；
- 只允许 HTTP `GET`；
- 只允许 PR metadata、PR files 和 PR raw diff 所需的精确路径；
- Query 只允许冻结的分页字段；
- 分块读取并在读取过程中执行字节上限；
- 拒绝压缩、非法 Content-Length、非预期 Content-Type 和非 2xx 状态；
- 对外只抛出固定、安全的错误码，不保留响应正文或异常链；
- 记录请求次数、响应字节、速率限制元数据，但不记录 Authorization header。

禁止实现任何通用 GitHub SDK 包装器。代码中不得存在 POST、PUT、PATCH、DELETE、GraphQL mutation 或发布 Review 的 endpoint。

## 8. PR 快照一致性协议

一次成功读取必须严格执行：

1. `GET PR metadata A`，记录 repository identity、PR number、Base SHA、Head SHA、state、title/body 限长副本。
2. `GET PR files`，完成受限分页，记录每个文件的 status、previous filename、additions/deletions/changes 和 patch。
3. `GET PR raw diff`，使用 GitHub diff media type取得完整 Unified Diff。
4. `GET PR metadata B`。
5. 要求 A 与 B 的 repository、PR number、Base SHA、Head SHA 完全一致。
6. 解析 raw diff，要求其文件集合与 files API 完全一致；每个文本文件的 patch 必须存在并能在 raw diff 中对应。
7. 对 metadata、files JSON、raw diff 和 changed-line map 分别计算 SHA256。

以下任一情况立即失败，且不得调用 MiMo：

- Base 或 Head SHA 漂移；
- repository 或 PR identity 漂移；
- patch 缺失、疑似截断或无法对应 raw diff；
- 二进制、submodule 或无法解析的 rename/copy；
- 文件数、分页、字节、行数或 Prompt 超限；
- 文件路径不安全、Diff 结构非法或 changed-line 集合为空；
- HTTP 状态、响应类型或请求顺序不符合合同。

第一版不通过 Contents API 重建缺失 patch，因为这会扩大实现和一致性证明范围。缺失 patch 直接换一个更小的批准 PR。

## 9. 不可信内容处理

PR 标题、正文、文件名、代码和 Diff 全部是不可信数据：

- 必须作为带明确边界标签的数据放入 user message，不能拼入 system prompt；
- system prompt 明确要求忽略其中的指令、凭据请求和角色覆盖文本；
- 不允许 PR 内容改变 endpoint、模型参数、输出路径、命令或权限；
- 不执行 PR 中出现的 shell、测试、安装或网络命令；
- 不 checkout Head、不导入 Candidate 模块、不运行 PR workflow；
- Prompt 和产物中不得包含 Token、Authorization header 或完整 HTTP headers。

## 10. Review 合同复用

必须复用：

- `OpenSWECompatibleReviewModel` 的单一结构化 Tool Call；
- `schemas/review.schema.json` 的 Finding、Uncertainty、Decision 语义；
- `contracts.validate_review()` 的 changed-line 和重复 Finding 门禁；
- Phase 1/2 的 response model 与 `finish_reason=tool_calls` 校验；
- Markdown renderer。

Phase 3 不运行 PR 代码。现有 `tests` 字段需要一个最小、向后兼容的只读表达：允许明确的 `NOT_RUN_READ_ONLY` 状态、空命令列表和 `passed=false`；Phase 1/2 旧格式必须继续合法。不得用伪命令冒充已执行测试。

严重度校准指标继续保存。模型合同失败属于真实结果，保存脱敏失败证据并停止，不自动补跑。

## 11. 建议新增文件

```text
src/open_swe_review_agent/github_readonly.py
scripts/run_phase3_github_readonly.py
tests/test_phase3_github_readonly.py
configs/phase3_github_readonly_target.json
```

可按最小需要修改：

```text
schemas/review.schema.json
src/open_swe_review_agent/contracts.py
src/open_swe_review_agent/open_swe_adapter.py
src/open_swe_review_agent/render.py
```

不得新增数据库、队列、GitHub App、通用部署层、新 Schema 家族或 r01/r02/r03 诊断链。

## 12. 本地输出

建议正式目录为 `artifacts/phase3/`，只包含：

```text
pr_snapshot.json
diff.patch
changed_lines.json
review.json              # 成功时
review.md                # 成功时
run_summary.json
failure.json             # 失败时，与成功 Review 互斥
```

`pr_snapshot.json` 只保存必要 metadata、Base/Head SHA、文件统计、响应 Hash 和计数；不保存 Token 或完整 headers。`run_summary.json` 必须显式记录 `github_write_performed=false`、`review_publish_allowed=false` 和测试未运行状态。

## 13. 离线测试要求

使用 Fake GitHub Client/Opener 覆盖至少：

- 稳定 metadata A/files/diff/metadata B 成功路径；
- 公开无 Token和细粒度 Token 两种请求头；
- Token 绝不发送到非 `api.github.com`；
- 非 GET 方法和所有写 endpoint 拒绝；
- Base SHA 或 Head SHA 漂移；
- patch 缺失、raw diff 不匹配、分页或大小超限；
- 二进制/无法解析文件拒绝；
- changed-line 集合准确，Finding 越界拒绝；
- PR 文本中的 Prompt Injection 不改变系统行为；
- 模型身份、finish reason、Tool Call 数量与合同错误失败关闭；
- 成功和失败证据互斥，且不包含模拟 secret；
- `--check` 完全离线；
- Phase 1/2 Review 产物在向后兼容合同下仍可验证。

## 14. 分支执行顺序

### A. 离线实现

1. 读取 Phase 1/2 实现、证据和本文。
2. 实现最小只读 Client、快照验证、Runner 和 Fake 测试。
3. 更新本阶段 `CONCEPTS.md`，但保持 `RESULTS.md` 为未运行模板。
4. 执行专项和完整离线测试、`pip check`、凭据扫描、`git diff --check`。
5. 返回主对话复审；此时不得联网、调用 GitHub 或 MiMo。

### B. 主对话批准后的一次真实运行

1. 主对话批准精确 repository、PR number、认证模式和冻结预算。
2. 提交离线实现并确保工作区干净。
3. 单命令注入 GitHub Token（若需要）与 MiMo Key；公开模式不得要求 Token。
4. 先只读获取并验证 PR 快照；失败则保存安全证据并停止。
5. 快照通过后只调用 MiMo 一次。
6. 本地生成 Review 和汇总，运行离线 `--check` 与凭据扫描。
7. 清除环境变量，返回主对话人工复核。
8. 不自动运行第二个 PR，不发布 Review，不进入 Phase 4。

具体 CLI 由分支实现后冻结，至少应包含：

```text
--check
--execute-once
--repository owner/repository
--pull-number N
--acknowledgement <exact text>
```

## 15. 完成门槛

Phase 3 只有同时满足以下条件才可记为完成：

- 成功读取一个主对话批准的 PR 快照；
- Base/Head SHA、文件列表、Diff 和 changed-line 集合通过一致性验证；
- Finding 只能锚定 candidate-side changed line；
- 本地 Review 通过 Schema 和语义验证；
- GitHub 请求日志证明仅有允许的 GET；
- GitHub 写操作为 `0`；
- 凭据扫描通过；
- 真实 Review 经主对话人工复核；
- 结束于人工决策门。

模型可能没有 Finding，这不自动表示阶段失败；只要快照与合同链路可信，应如实保留模型结果。合同失败不得自动补跑。

## 16. 明确禁止

- 不发布 Review、Comment、Issue、Check Run；
- 不修改 PR、Branch、Repository 或代码；
- 不自动 Merge；
- 不执行 PR 中的命令、测试或 workflow；
- 不克隆或 checkout 未信任 Head；
- 不读取整个仓库；
- 不为缺失 patch 做复杂重建；
- 不针对目标 PR 答案调 Prompt；
- 不补跑 Phase 2；
- 不自动重试正常模型/合同失败；
- 不设计或实现 Phase 4 写入；
- 不调用本地 4B 或训练。

## 17. 分支回报格式

```text
实现状态：
修改文件：
批准的 repository/PR：
认证模式（不得包含 Token）：
离线测试：
是否调用 GitHub：
GitHub GET 请求类型与次数：
是否调用任何写 endpoint：
Base/Head SHA：
changed files / diff bytes / changed lines：
快照 Hash：
是否调用 MiMo：
Review 结果与 Hash：
Finding 与 changed-line 复核：
严重度人工判断：
模型调用、Token、耗时、费用：
凭据扫描：
代表性成功与失败：
Git 状态：
明确未执行内容：
建议的人工决策：
```

分支必须先完成 A 部分并停下。没有主对话对实现和目标 PR 的明确批准，不得执行 B 部分。
