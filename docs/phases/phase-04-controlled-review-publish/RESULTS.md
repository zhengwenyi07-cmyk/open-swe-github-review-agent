# Phase 4 结果：受控 GitHub Review 最小写入

> 最终状态：`COMPLETED_WITH_VERIFICATION_FAILURE`
>
> Phase 4 只执行了一次正式发布。GitHub 远端确实创建了一个 `COMMENT` Review 和一条行内评论；发布后合同复核失败，人工检查进一步确认评论锚错一行。没有重试、补发、编辑或删除远端内容。

## 1. 最终门禁

```text
phase_3_status=COMPLETED
phase_4_plan_status=COMPLETED
phase_4_implementation_status=COMPLETED
phase_4_target_status=APPROVED_AND_CONSUMED
phase_4_prepare_status=PASS
phase_4_publish_status=COMPLETED_WITH_VERIFICATION_FAILURE
github_app_created=true
github_review_write_performed=true
github_review_write_requests=1
remote_side_effect_confirmed_by_read_only_audit=true
publish_retry_allowed=false
automatic_post_retries=0
merge_or_repository_write_performed=false
phase_5_allowed=false
next_step=PROJECT_CLOSEOUT_COMPLETE
```

## 2. 计划与实际结果

| 项目 | 计划 | 实际结果 |
|---|---|---|
| 目标仓库 | 所有者控制的测试仓库 | `zhengwenyi07-cmyk/open-swe-github-review-agent` |
| 目标 PR | 手动创建的小型开放 PR | PR #1 |
| 模型 | `mimo-v2.5-pro` | `mimo-v2.5-pro` |
| 模型尝试 | 1 次、无重试 | 1 次、无重试 |
| GitHub 认证 | 单仓库 GitHub App | App ID `4715390`，Installation ID `156504223` |
| 准备权限 | Pull requests: read | 通过 |
| 发布权限 | Pull requests: write | 只在发布动作申请 |
| Event | `COMMENT` | `COMMENT` |
| Review 写请求 | 最多 1 次 | 1 次 |
| 自动 POST 重试 | 0 | 0 |
| PR 代码或测试 | 不执行 | 未执行 |
| 发布后验证 | Review、Commit、Marker、评论锚点和正文一致 | Review/正文/Commit 一致；评论锚点错误，终态失败 |

## 3. GitHub App 与目标身份

```text
app_name=open-swe-review-phase4-zhengwenyi
app_id=4715390
installation_id=156504223
installation_scope=SINGLE_REPOSITORY
installed_repository=zhengwenyi07-cmyk/open-swe-github-review-agent
metadata_permission=READ
pull_requests_permission=READ_WRITE
contents_permission=NONE
issues_permission=NONE
checks_permission=NONE
webhooks_enabled=false
private_key_stored_in_git=false

repository=zhengwenyi07-cmyk/open-swe-github-review-agent
pull_number=1
base_sha=9fe5f09914d62a1dc6d8966e800b5eb43c573fe0
head_sha=df96cd3e49b65e09ec1891cc419e0753e0583958
changed_files=1
candidate_changed_lines=8
target_contract_commit=3bebf17fbc434ee8420c5e2869c13a2751fee739
prepare_fix_commit=5e59e0e8114c5b124fe062ad8ea80d621976281c
payload_approval_commit=d6864a3
```

私钥保存在 Git 仓库之外；JWT、installation token 和 Authorization header 均未进入产物或 Git。

## 4. Prepare 结果

第一次 Prepare 因同一行存在两个不同 Finding、Publisher 拒绝重复行锚点而失败；失败证据已单独冻结，GitHub 写请求为 0。修复只把同一 `(file, line)` 的多个 Finding 合并为一条评论，没有丢弃 Finding。

修复后 Prepare 成功：

```text
status=PREPARED_AWAITING_HUMAN_APPROVAL
response_model=mimo-v2.5-pro
finish_reason=tool_calls
model_calls=1
decision=REQUEST_CHANGES
confirmed_findings=1
publishable_comments=1
tests_status=NOT_RUN_READ_ONLY
github_get_requests=5
github_review_write_requests=0
input_tokens=1208
output_tokens=500
total_tokens=1708
elapsed_seconds=12.379
publish_payload_sha256=94ee086d4d995a558d8fcc67c31e2d80a1d9cd6aecc59099b3697fa9b6a9507a
```

人工 Gate B 将仓库、PR、Base、Head、`COMMENT` event 和上述 Payload SHA256 写入独立批准合同并提交后，才运行 Publish。

## 5. 发布结果

```text
publish_command=EXECUTED_ONCE
github_review_write_requests=1
github_review_write_endpoint=CREATE_PULL_REQUEST_REVIEW
github_review_event=COMMENT
github_review_id=5020924942
github_review_state=COMMENTED
github_review_commit_id=df96cd3e49b65e09ec1891cc419e0753e0583958
github_review_html_url=https://github.com/zhengwenyi07-cmyk/open-swe-github-review-agent/pull/1#pullrequestreview-5020924942
inline_comment_id=3854679061
inline_comment_url=https://github.com/zhengwenyi07-cmyk/open-swe-github-review-agent/pull/1#discussion_r3854679061
automatic_post_retries=0
additional_write_requests=0
```

GitHub 远端 Review body、Marker、Commit、状态和行内评论正文与批准 Payload 一致。Runner 随后的远端评论验证返回：

```text
failure_stage=REMOTE_VERIFICATION
failure_reason=REMOTE_COMMENTS_MISMATCH
```

原因有两层：

1. GitHub `List review comments` 返回 `position/original_position`，没有返回 Runner 期待的 `line/side` 字段，因此合同验证失败。
2. 更重要的是，人工对照冻结 Diff 后确认 Payload 本身要求评论第 7 行，但真正有缺陷的 `return sum(values) / (len(values) - 1)` 位于第 8 行。第 7 行是 `raise ValueError("values must not be empty")`。远端评论因此实际锚在错误代码行。

第二点意味着本次不能被标记为发布成功。changed-line 门禁只能证明“第 7 行属于 Diff”，不能证明 Finding 文本所描述的语句真的位于第 7 行。

## 6. 原始 Runner 证据与人工复核的区别

原始 `failure.json` 在验证抛错时写入：

```text
remote_side_effect_confirmed=false
remote_review_id=null
remote_review_html_url=null
```

该文件作为原始运行证据保持不变。发布后通过 GitHub 公共只读 API 独立观察到 Review `5020924942` 和评论 `3854679061`，因此新增 `post_publish_audit.json` 记录人工复核事实。它是派生的人工审计摘要，不冒充 Runner 原始回执。

## 7. 安全复核

```text
third_party_repository_write=false
approve_event_sent=false
request_changes_event_sent=false
issue_comment_created=false
check_run_created=false
branch_or_contents_modified=false
merge_performed=false
pr_code_executed=false
credentials_in_prompt=false
credentials_in_artifacts=false
credentials_in_git=false
automatic_post_retries=0
```

本次唯一仓库内容写入是批准的 Create Review。发现失败后没有第二次 POST，也没有通过编辑、删除或补发来掩盖错误。

## 8. 冻结产物与 SHA256

| 文件 | SHA256 |
|---|---|
| `artifacts/phase4/pr_snapshot.json` | `ad2a509606afc17a1010cd6eee56855b5a7a9c8c62d76119173b8986e569eb0c` |
| `artifacts/phase4/diff.patch` | `fbd3e235940bf558bb4d701ed928ad09357ae7d8c73dc3f988bfa3a6c7a49502` |
| `artifacts/phase4/changed_lines.json` | `1c4f7df712089950115d2da24bb04fc27e4b5a1146316b446e69369f11629dad` |
| `artifacts/phase4/review.json` | `a219daa324c10b23faa5a94e0b598db73db27b7d0a5e6f74b637253251a91106` |
| `artifacts/phase4/review.md` | `e93ed8e6f37e7a913d0e100ac5357715c03a7e30f8397023c4f873381779003d` |
| `artifacts/phase4/prepare_summary.json` | `02ef66fd3bec002f7307e8ab8a31999394d4afa4f4d51ade848de1de19c8f570` |
| `artifacts/phase4/publish_payload.json` | `94ee086d4d995a558d8fcc67c31e2d80a1d9cd6aecc59099b3697fa9b6a9507a` |
| `artifacts/phase4/failure.json` | `42f1f047df31d96ae248d96e51def77e720e5878cf6af4fad568dfdf4952d4f0` |
| `artifacts/phase4/post_publish_audit.json` | `401e0e4acf7ef038a7b38bdb43137c3bce39c86abefaeb5b0292b3799c96e2b1` |

没有生成 `publish_receipt.json` 或 `run_summary.json`，因为远端验证没有通过。

## 9. 成功、失败与研究结论

### 成功

- 最小权限 GitHub App、双人工门、固定 Payload Hash 和唯一写路由真实运行。
- 受控 PR 收到恰好一个 `COMMENT` Review；没有重复写入或其他仓库副作用。
- Review body、Marker、Commit 和评论正文与人工批准 Payload 一致。
- 发布后验证确实阻止系统把不满足合同的远端状态记录为成功。

### 失败

- Runner 未兼容 GitHub 返回的 `position` 型评论表示，终态验证失败。
- 模型 Finding 的自然语言证据与所填行号相差一行；现有 changed-line 验证没有发现这种语义锚点错误。
- 因此 Phase 4 最终状态是 `COMPLETED_WITH_VERIFICATION_FAILURE`，不是 `PASS`。

### 局限

- 只测试一个所有者控制的 PR 和一次写入。
- 没有执行 PR 测试，也没有运行官方完整 Reviewer graph。
- GitHub 写入闭环已证明可达，但行号语义仍需更强的代码片段绑定；本项目不通过补跑来消除这个负结果。

## 10. 人工决策

```text
human_review_status=COMPLETED
phase_4_final_status=COMPLETED_WITH_VERIFICATION_FAILURE
evidence_freeze_allowed=true
phase_4_retry_allowed=false
phase_5_allowed=false
next_step=PROJECT_CLOSEOUT_COMPLETE
```

本阶段到此结束。后续若继续研究，应把“Finding 证据中的代码片段与锚点行一致性”作为独立改进问题，而不是重跑本 PR 或再发一条评论。
