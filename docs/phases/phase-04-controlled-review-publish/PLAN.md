# Phase 4 计划：受控 GitHub Review 最小写入

> 状态：`OFFLINE_IMPLEMENTATION_COMPLETE_NOT_RUN`
>
> 本文已由阶段分支实现。Phase 4 是一个阶段，不拆成 r01/r02/r03。当前完成了离线 GitHub App 认证、只读准备、确定性 Payload、受控 Publisher、状态检查和 Fake 合同测试；没有创建 GitHub App、测试 PR 或运行产物，也没有调用 GitHub/MiMo。

## 1. 阶段背景

Phase 3 已在公开 PR `pallets/click#3021` 上证明真实 GitHub 只读输入可以复用现有 Review 合同：Base/Head、Files、Diff 和 38 个 changed lines 属于同一稳定快照；MiMo 输出合法的本地 Review；GitHub 写请求为 `0`。

Phase 4 不再评估只读输入，也不向第三方仓库发布 Phase 3 的结果。它只验证最后一段产品闭环：能否把一个已经在本地生成、经过人工复核并锁定 Hash 的 Review，使用最小权限 GitHub App，恰好一次发布到项目所有者控制的测试 PR。

## 2. 研究问题

本阶段必须回答：

1. 现有 PR Snapshot 和 Review 合同能否生成 GitHub `Create a review` 接口接受的 Payload？
2. 如何保证发布内容与人工复核内容逐字节一致，模型不能在批准后再次改写？
3. 如何把 Finding 的 candidate-side changed line 正确转换成 GitHub `path + line + side=RIGHT`？
4. 如何在 Head SHA 漂移、重复 Marker、权限错误或响应丢失时失败关闭？
5. 如何证明运行时只允许一个仓库、一个 PR 和一个 Review 写 endpoint？
6. 如何保证 App 私钥、JWT 和 installation token 不进入日志、Prompt、产物或 Git？
7. 发布后的 GitHub 页面是否与本地 Review、Payload 和回执一致？

## 3. 唯一成功路径

```text
owner-controlled test PR
  -> Phase 3 read-only snapshot protocol
  -> one MiMo structured Review
  -> local Schema + changed-line validation
  -> deterministic publish_payload.json
  -> STOP: human reviews exact payload + SHA256
  -> approval contract binds repository / PR / Head / payload SHA256
  -> mint short-lived GitHub App installation token
  -> re-read PR identity and reject Head drift
  -> reject an existing idempotency marker
  -> exactly one POST /pulls/{number}/reviews, event=COMMENT
  -> GET exact review id and verify body / commit / inline comments
  -> local publish_receipt.json + run_summary.json
  -> human review gate
```

准备与发布属于同一个 Phase 4 的两个动作，不是两个子阶段。准备动作绝不写 GitHub；发布动作绝不再次调用模型。

## 4. 目标 PR

只能使用项目所有者控制的仓库，建议固定为：

```text
repository=zhengwenyi07-cmyk/open-swe-github-review-agent
pull_number=<主对话批准后填写>
visibility=PUBLIC
state=OPEN
draft=false
```

测试 PR 由用户手动创建，不由 Agent 创建。建议只包含一个小型、无秘密、无外部依赖的 Python 改动，并植入一个人工可解释的逻辑缺陷，以提高得到一个可发布 confirmed Finding 的概率。

目标边界：

```text
max_changed_files=3
max_raw_diff_bytes=16_KiB
max_total_diff_lines=300
max_candidate_changed_lines=80
max_confirmed_findings_to_publish=3
```

目标合同必须在联网运行前单独批准并提交，至少绑定 repository、PR number、Base SHA、Head SHA 和认证模式。预期缺陷可以写入仅供人工评分的本地 Fixture/文档，但绝不能进入模型 Prompt。

禁止：

- 在 `pallets/click#3021` 或其他第三方 PR 上发布；
- 为了让模型成功而在运行后修改 PR；
- 自动创建 PR、Branch 或 Commit；
- 使用真实业务、客户或私有代码作为目标。

## 5. 模型与 Review 条件

沿用现有条件，不为测试 PR 调 Prompt：

```text
model=mimo-v2.5-pro
temperature=0.0
max_tokens=4096
parallel_tool_calls=false
attempts_per_task=1
automatic_retries=0
```

只允许一次模型调用。模型响应必须先通过现有 Schema、语义、重复 Finding 和 changed-line 检查。

只有 `assessment=confirmed` 的 Finding 可以进入发布 Payload。Suggestion 与 Uncertainty 只保留在本地产物中，不作为行内评论发布。

若没有 confirmed Finding、合同失败或人工认为 Review 不应公开，Phase 4 必须停止为 `PREPARED_NOT_PUBLISHED`；不能制造评论来满足阶段成功。

## 6. GitHub App 认证与最小权限

Phase 4 固定采用安装在单一测试仓库上的 GitHub App installation token，不使用 classic PAT。

App Repository permissions：

```text
Metadata: Read-only（GitHub 隐式提供）
Pull requests: Read and write
Contents: No access
Issues: No access
Checks: No access
Actions: No access
Administration: No access
```

不订阅 Webhook；安装范围只能选择测试仓库，不能选择所有仓库。

运行时秘密：

```text
GITHUB_APP_ID
GITHUB_APP_INSTALLATION_ID
GITHUB_APP_PRIVATE_KEY_PATH
MIMO_API_KEY
```

私钥文件保存在 Git 仓库外并限制本地权限，不允许把 PEM 内容放入命令行、环境文件、日志或产物。Runner 在内存中创建短期 JWT，通过固定安装 ID 换取短期 installation token；JWT 与 installation token 均不得持久化。GitHub 文档说明 installation token 默认约一小时过期，代码不得依赖固定 Token 长度。

## 7. 精确 HTTP 边界

允许的 GitHub 请求只有：

### 认证

```text
POST /app/installations/{approved_installation_id}/access_tokens
```

该 POST 只创建临时认证凭据，不修改仓库内容。请求体应进一步把 token 限制到批准仓库和 `pull_requests=write`。

### 只读

```text
GET /repos/{owner}/{repo}/pulls/{number}
GET /repos/{owner}/{repo}/pulls/{number}/files?page=1&per_page=100
GET /repos/{owner}/{repo}/pulls/{number}  Accept: application/vnd.github.v3.diff
GET /repos/{owner}/{repo}/pulls/{number}/reviews
GET /repos/{owner}/{repo}/pulls/{number}/reviews/{review_id}
GET /repos/{owner}/{repo}/pulls/{number}/reviews/{review_id}/comments
```

### 唯一仓库写入

```text
POST /repos/{owner}/{repo}/pulls/{number}/reviews
```

禁止所有其他 POST、PUT、PATCH、DELETE、GraphQL mutation、Issue Comment、单独 Review Comment、Check Run、Merge、Branch、Contents 和 Repository endpoint。

HTTP Client 继续要求 HTTPS、`api.github.com`、无显式端口、无 URL 凭据、无代理、无重定向、无压缩响应、流式字节限制和固定安全错误码。

Reviews 与 review comments 的列表读取固定 `page=1&per_page=100`；出现下一页链接或超过 100 项时失败关闭，不假装已经完成全量去重。

## 8. 发布 Payload

固定使用 GitHub Review：

```json
{
  "commit_id": "<approved 40-char Head SHA>",
  "body": "<fixed disclosure + summary + idempotency marker>",
  "event": "COMMENT",
  "comments": [
    {
      "path": "src/example.py",
      "line": 12,
      "side": "RIGHT",
      "body": "<confirmed finding evidence and recommendation>"
    }
  ]
}
```

选择 `COMMENT` 而不是 `APPROVE` 或 `REQUEST_CHANGES`，避免实验 Review 改变合并门禁。第一版只评论 candidate-side 新增行，因此固定 `side=RIGHT`，不实现多行评论、删除行评论或旧 `position` 参数。

Review body 必须包含固定披露：

- 这是受控实验性自动 Review；
- 已由人工批准发布；
- PR 代码和测试未执行；
- 本地证据 Commit/Hash；
- 机器可识别的幂等 Marker。

Payload 使用确定性 JSON 编码并保存 `publish_payload.json` 与 SHA256。人工批准合同必须精确绑定该 SHA256；发布函数只能读取已批准文件，不得重新调用模型、renderer 或修改字段。

## 9. 两个人工决策门

### Gate A：允许本地准备

主对话先批准测试 PR 身份。分支才可以执行 GitHub 只读获取和一次 MiMo Review，生成本地 Review 与 Payload。

Gate A 后必须停止并回报：Finding、评论文本、目标行、Head SHA、Payload SHA256、Token/耗时和凭据扫描。

### Gate B：允许单次发布

主对话逐字审核 `review.json`、`review.md` 和 `publish_payload.json`，随后把 approval contract 从 `NOT_APPROVED` 改为 `APPROVED`，绑定：

```text
repository
pull_number
base_sha
head_sha
payload_sha256
event=COMMENT
max_write_requests=1
```

Gate B 合同必须单独提交且工作区干净。没有该提交，不得构造 App token Client，更不得 POST Review。

## 10. 幂等、漂移与不确定写入

Marker 绑定目标与本地 Review，而不是绑定 Payload 自身，避免 Payload Hash 的自引用循环：

```text
marker_id=SHA256(repository + NUL + pr + NUL + head_sha + NUL + review_json_sha256)
<!-- open-swe-review-agent:phase4:<marker_id> -->
```

最终 `publish_payload.json` 的 SHA256 仍由 Gate B 单独批准；Marker 负责远端去重，Payload Hash 负责保证人工批准内容逐字节不变。

发布前：

1. 重新读取 PR metadata，要求 Base/Head、open/draft 状态与批准合同一致。
2. 列出已有 Reviews；发现同 Marker 时拒绝发布。
3. 重新验证每个 inline comment 仍属于批准 Head 的 candidate changed-line。
4. 取得进程级独占锁，确认本地发布回执不存在。

写入后：

1. 保存 POST 返回的 review id、HTML URL、state、commit id、submitted time 和安全统计。
2. GET exact review id 及其 comments，核对 Marker、commit id、发布身份、每条 path/line/side/body 和评论数量。
3. 不执行第二次 POST。

若 POST 发生连接中断而结果未知，只允许进行一次只读 reconciliation：按 Marker 查询已有 Reviews。找到唯一匹配项则记录为已发布；没有或多个匹配项则记为 `AMBIGUOUS_WRITE_STATE` 并停止。禁止盲目重试。

## 11. 建议实现文件

```text
src/open_swe_review_agent/github_app_auth.py
src/open_swe_review_agent/github_review_publisher.py
scripts/run_phase4_controlled_publish.py
tests/test_phase4_controlled_publish.py
configs/phase4_target.json
configs/phase4_publish_approval.json
```

按最小需要复用或修改 Phase 3 Client/Runner。不要建立通用 GitHub SDK、数据库、服务端、Webhook Worker、队列或新的 Schema 家族。

## 12. 本地产物

建议目录：

```text
artifacts/phase4/
  pr_snapshot.json
  diff.patch
  changed_lines.json
  review.json
  review.md
  prepare_summary.json
  publish_payload.json
  publish_receipt.json       # 发布成功后
  run_summary.json
  failure.json               # 与对应成功终态互斥
```

原始密钥、JWT、installation token、Authorization header、完整 HTTP headers 和 GitHub App 私钥路径不得进入产物。

## 13. 离线测试要求

Fake Opener/Client 至少覆盖：

- App JWT 与 installation token 成功路径，Token 不落盘；
- App/installation/repository/PR 身份不匹配；
- 非允许 host、port、method 和 endpoint 拒绝；
- PR Head 在准备后或发布前漂移；
- approved payload Hash 不匹配；
- inline Finding 不属于 changed line；
- `side != RIGHT`、多行、删除行或评论数超限；
- event 为 `APPROVE`/`REQUEST_CHANGES` 时拒绝；
- existing Marker 拒绝重复发布；
- Review 列表或 comments 列表出现第二页时失败关闭；
- 成功路径恰好一个仓库写 POST；
- POST 响应丢失后的只读 Marker reconciliation；
- 模糊写入状态禁止重试；
- 私钥/JWT/token/模拟秘密不进入异常、traceback、产物；
- Gate A/Gate B、干净工作区和已提交合同均在网络 Client 前验证；
- Phase 1～3 历史检查继续通过。

## 14. 分支执行顺序

范围时间盒：离线实现建议 2～4 小时；人工配置 App/PR、本地准备与发布建议再用 30～60 分钟。若需要 Webhook、服务端、队列、数据库、通用重试平台或第二个写 endpoint 才能继续，应停止并回主对话缩小方案，而不是扩建框架。

### A. 离线实现

1. 阅读 Phase 3 的 PLAN/CONCEPTS/RESULTS 和六份冻结证据。
2. 实现最小 App Auth、Publisher、Runner 和 Fake 测试。
3. 保持两个合同为 `NOT_APPROVED`。
4. 更新 `CONCEPTS.md`，保持 `RESULTS.md` 为未运行模板。
5. 跑专项/完整测试、Schema、`pip check`、凭据扫描和 `git diff --check`。
6. 停止，交主对话复审；不得创建 App、PR 或联网。

### B. 受控测试 PR 与本地准备

1. 用户手动注册 App、仅安装到测试仓库，并手动创建受控 PR。
2. 主对话批准并提交精确目标合同。
3. 工作区干净后，一次性只读获取 PR 并调用 MiMo 一次。
4. 生成本地 Review 与确定性 Payload，执行离线检查。
5. 停在 Gate B，不发布。

### C. 单次发布

1. 主对话人工审核评论文本和目标行。
2. 单独批准并提交 Payload Hash 合同。
3. 单命令注入 App 身份/私钥路径；执行唯一一次发布。
4. 只读复核 GitHub Review，保存 Receipt。
5. 清除秘密环境变量，人工查看 GitHub 页面。
6. 冻结证据并停止，不自动进入 Phase 5。

## 15. 完成门槛

只有同时满足以下条件，Phase 4 才能记为 `COMPLETED`：

- 目标是项目所有者控制的测试 PR；
- App 只安装于该仓库，权限不超过 Pull requests read/write；
- 本地 Review 与 Payload 通过 Schema、语义和 changed-line 复核；
- Payload Hash 经人工批准并单独提交；
- 只发生一次仓库内容写请求，endpoint 为 Create Review；
- event 为 `COMMENT`，未改变合并门禁；
- 发布后的 Review id、commit id、Marker 和内容可只读验证；
- 没有重复评论、代码执行、Merge、Branch/Contents/Issue/Check 写入；
- 凭据扫描通过；
- 主对话人工查看 GitHub 页面并批准冻结。

模型未生成可发布 Finding 时，不满足“真实写入”目标，但也不得伪造评论；阶段应以诚实的 `PREPARED_NOT_PUBLISHED` 结束或由主对话重新设计，不能自动补跑。

## 16. 明确禁止

- 不在第三方仓库写入；
- 不发布 Phase 3 的 `pallets/click#3021` Review；
- 不使用 `APPROVE` 或 `REQUEST_CHANGES`；
- 不创建 Issue Comment、Check Run 或独立 Review Comment；
- 不更新、删除或回复已有评论；
- 不创建/修改 PR、Branch、Commit、Contents 或 Repository 设置；
- 不自动 Merge；
- 不运行 PR 代码、测试、workflow 或 shell 指令；
- 不让模型直接访问 GitHub Client；
- 不在人工批准后再次调用模型；
- 不盲目重试不确定的 POST；
- 不把秘密写入仓库或产物；
- 不补跑 Phase 1～3；
- 不开始本地 4B、训练或 Phase 5。

## 17. 分支回报格式

```text
实现状态：
修改文件：
GitHub App 权限（不含秘密）：
目标 repository/PR/Base/Head：
准备阶段是否调用 GitHub/MiMo：
Review Findings/Uncertainties/Decision：
publish_payload 路径与 SHA256：
人工发布批准状态：
仓库写请求数与精确 endpoint：
GitHub review id / html_url：
Marker 与 commit_id 复核：
是否出现重复或模糊写入：
Token/耗时/费用：
凭据扫描：
专项与完整测试：
Git 状态：
明确未执行内容：
建议的人工决策：
```

分支必须先完成 A 并停止。没有主对话分别批准目标 PR 和最终 Payload，不得执行 B 或 C。
