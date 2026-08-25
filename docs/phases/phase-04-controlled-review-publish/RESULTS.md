# Phase 4 结果：受控 GitHub Review 最小写入

> 当前状态：`IMPLEMENTED_NOT_RUN`
>
> 离线实现与测试结果已经填写；所有 GitHub App、目标 PR、MiMo 调用和发布字段仍保持 `NOT_RUN`。不得把 Fake 合同测试写成真实 GitHub 发布。

## 1. 当前门禁

```text
phase_3_status=COMPLETED
phase_3_retry_allowed=false
phase_4_plan_status=READY
phase_4_implementation_status=IMPLEMENTED_NOT_RUN
phase_4_target_status=NOT_APPROVED
phase_4_prepare_status=NOT_RUN
phase_4_publish_status=NOT_RUN
github_app_created=false
github_review_write_performed=false
github_review_write_requests=0
merge_or_repository_write_performed=false
next_step=MAIN_REVIEW_COMMIT_THEN_CREATE_CONTROLLED_APP_AND_PR
```

## 2. 计划与真实结果

| 项目 | 计划 | 实际结果 |
|---|---|---|
| 目标仓库 | 项目所有者控制的测试仓库 | `NOT_RUN` |
| 目标 PR | 手动创建的小型开放 PR | `NOT_RUN` |
| 模型 | `mimo-v2.5-pro` | `NOT_RUN` |
| 模型尝试 | 1 次、无重试 | `NOT_RUN` |
| GitHub 认证 | 单仓库 GitHub App installation token | `NOT_RUN` |
| App 权限 | Pull requests read/write；其他无写权限 | `NOT_RUN` |
| Event | `COMMENT` | `NOT_RUN` |
| Inline comments | 仅人工批准的 confirmed Finding，最多 3 条 | `NOT_RUN` |
| 仓库内容写请求 | 恰好 1 次 Create Review | `0`（仅 Fake Transport 测试） |
| 测试执行 | 不执行 PR 代码或测试 | `0` |
| 人工 Gate | Target Gate + Payload Hash Gate | `NOT_RUN` |

## 3. 离线实现结果

```text
new_files=9
modified_long_lived_documents=5
phase_4_specialized_tests=32/32_PASS
full_test_suite=96_RUN_95_PASS_1_SKIP
python_compile=PASS
pip_check=PASS
git_diff_check=PASS
credential_scan=PASS
github_write_route_scan=PASS
offline_check=PASS_NOT_RUN
```

离线实现新增：

- `github_app_auth.py`：短期 JWT、单仓库 installation token、准备阶段 read 与发布阶段 write 权限区分；
- `github_review_publisher.py`：唯一 Create Review POST、固定 `COMMENT`、精确 GET 验证与重复 Marker 检查；
- `run_phase4_controlled_publish.py`：准备、人工 Hash Gate、一次发布、歧义结果只读对账和离线检查；
- 两份默认 `NOT_APPROVED` 合同与一份 Fake/拒绝测试套件。

关键拒绝测试覆盖：工作区脏、目标或 Payload 未批准、第三方仓库、私钥位于仓库内、Head 漂移、非法 event/changed line、分页、重复 Marker、Token scope 不符、POST 传输异常和非法 JSON 脱敏，以及歧义 POST 只能 GET 对账而不能再次 POST。终态测试还会同步篡改 Approval 仓库、Receipt Commit/URL/Marker/评论数量并确认离线检查拒绝；远端已验证而本地 Summary 写入失败时，Receipt 必须保留并进入独立人工处理状态。

## 4. GitHub App 配置（不得记录秘密）

```text
app_name=NOT_RUN
installation_scope=NOT_RUN
installed_repository=NOT_RUN
metadata_permission=NOT_RUN
pull_requests_permission=NOT_RUN
contents_permission=NOT_RUN
issues_permission=NOT_RUN
checks_permission=NOT_RUN
webhooks_enabled=NOT_RUN
private_key_stored_in_git=false
```

不得记录 App private key、JWT、installation token 或 Authorization header。

## 5. 目标 PR 身份

```text
repository=NOT_RUN
pull_number=NOT_RUN
base_sha=NOT_RUN
head_sha=NOT_RUN
state=NOT_RUN
draft=NOT_RUN
changed_files=NOT_RUN
raw_diff_bytes=NOT_RUN
candidate_changed_lines=NOT_RUN
target_contract_commit=NOT_RUN
```

## 6. 本地 Review 与 Payload

```text
response_model=NOT_RUN
finish_reason=NOT_RUN
model_calls=0
decision=NOT_RUN
confirmed_findings=NOT_RUN
suggestions=NOT_RUN
uncertainties=NOT_RUN
schema_valid=NOT_RUN
changed_line_validation=NOT_RUN
publishable_findings=NOT_RUN
publish_payload_sha256=NOT_RUN
publish_approval_commit=NOT_RUN
human_payload_review=NOT_RUN
```

在此列出每条拟发布评论：文件、行号、Finding 摘要和人工判断。不要复制 Token 或无关 PR 内容。

## 7. 发布结果

```text
publish_command=NOT_RUN
github_auth_token_requests=0
github_review_write_requests=0
github_review_write_endpoint=NOT_RUN
github_review_event=NOT_RUN
github_review_id=NOT_RUN
github_review_state=NOT_RUN
github_review_commit_id=NOT_RUN
github_review_html_url=NOT_RUN
idempotency_marker_unique=NOT_RUN
verification_get_passed=NOT_RUN
ambiguous_write_state=false
automatic_post_retries=0
```

## 8. 安全复核

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
```

## 9. Token、耗时与费用

```text
github_get_requests=NOT_RUN
github_response_bytes=NOT_RUN
input_tokens=NOT_RUN
output_tokens=NOT_RUN
total_tokens=NOT_RUN
prepare_elapsed_seconds=NOT_RUN
publish_elapsed_seconds=NOT_RUN
cost=NOT_RUN
```

## 10. 产物与 SHA256

| 文件 | SHA256 |
|---|---|
| `pr_snapshot.json` | `NOT_RUN` |
| `diff.patch` | `NOT_RUN` |
| `changed_lines.json` | `NOT_RUN` |
| `review.json` | `NOT_RUN` |
| `review.md` | `NOT_RUN` |
| `prepare_summary.json` | `NOT_RUN` |
| `publish_payload.json` | `NOT_RUN` |
| `publish_receipt.json` | `NOT_RUN` |
| `run_summary.json` | `NOT_RUN` |

离线合同文件：

| 文件 | SHA256 |
|---|---|
| `configs/phase4_target.json` | `4144c298b0e32e8095f5e78bbbfc1dee8a79149881e49c5ea9c74d82c007f43e` |
| `configs/phase4_publish_approval.json` | `505af920262573d7d9df85dc044ff0c83a447bea34ff23add47361938a92afec` |
| `src/open_swe_review_agent/github_app_auth.py` | `9cccadd14e522d7b31549655424ae4d2708ac3045eb4c550a201365e0737cb01` |
| `src/open_swe_review_agent/github_review_publisher.py` | `0a181cbe90d529bc11566dad05483102667c12a4ed7669c2f9acffb69952fdf4` |
| `scripts/run_phase4_controlled_publish.py` | `69b64dd56c0994de27e005d710799e35b788054e25b48350a18f827bb123c313` |
| `tests/test_phase4_controlled_publish.py` | `c43b981be66f7087b3d60e59fff2e64e2f6ae42daa02f85a728c50f919e7332c` |

## 11. 人工 GitHub 页面复核

待填写：

- Review 是否显示在正确 PR；
- 发布者是否为预期 GitHub App；
- 总体披露文本是否完整；
- 每条行内评论是否在正确文件和行；
- 是否出现重复评论；
- PR 合并门禁是否未被改变；
- GitHub 页面与本地 Payload/Receipt 是否一致。

## 12. 真实成功、失败与局限

### 成功

`NOT_RUN`

### 失败

`NOT_RUN`

### 局限

计划阶段已知局限：只验证一个所有者控制的 PR 和一次 COMMENT Review；不代表生产多仓库可用性，不执行 PR 测试，不实现自动修复、Webhook 或自动 Merge。

## 13. 人工决策

```text
human_review_status=PENDING_IMPLEMENTATION_REVIEW
phase_4_final_status=IMPLEMENTED_NOT_RUN
evidence_freeze_allowed=false
phase_5_allowed=false
next_step=MAIN_REVIEW_COMMIT_THEN_CREATE_CONTROLLED_APP_AND_PR
```

本文件没有真实结果前，不得写入 review id、成功率或“已完成 GitHub 发布”。Phase 4 完成后也必须停在人工决策门，不能自动进入 Phase 5。
