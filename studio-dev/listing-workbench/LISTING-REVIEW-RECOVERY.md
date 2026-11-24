# 原任务审校阶段恢复

正式入口：`POST /api/listing-jobs/resume-review`。登录账号沿用工作台当前会话；不得另建文案任务绕过未知结果。

```json
{"id":"原jobID","requestId":"唯一恢复请求ID","receipts":{"initial":{"id":"原初稿32位回执","sha256":"原文件SHA256"},"polish":{"id":"原润色32位回执","sha256":"原文件SHA256"},"review":{"id":"已返回的无效审校32位回执","sha256":"原文件SHA256"}}}
```

只接受原任务`needs_review`、没有已保存完成稿、且原错误明确为“审校引用无法对应原文”。账号、产品输入摘要、当前文案/锁/审核记录、三份完整响应的阶段/站点/SHA/时间序必须一致。新响应带真实`listingTask`来源；旧响应只在当前账号没有其他重叠文案任务、且未出现后续润色/修订回执的窗口内接受显式哈希对账，标记`explicit_legacy_hash_reconciliation_exclusive_task_window`，不伪造旧请求身份。

同一job只保存一份`reviewRecovery`。API先冻结独立请求及原错误和三份回执，再派发同job后台恢复。初稿和润色直接读原响应，不重发。只对已经返回的无效引用额外核对一次；每一条有效旧问题都保留，之后仍走正常局部五点修订、语义与事实/长度/格式检查，再沿原事务应用到当前文案。无效丢词判断必须在真实初稿命中列表中出现，仅是已选关键词不算曾经使用。

恢复意图、阶段记录和新模型响应ID/SHA均保留。重启、超时、再次无效引用或后续模型未知时只读原journal；重复调用返回`reused`，不发第二次恢复。只有已有完整结果回执时可按原账号、原inputDigest和锁冲突规则找回/应用。原三份响应及旧错误保留，不伪造人工通过。

直接检查：`python -X utf8 -m unittest test_listing_review_recovery test_listing_review_recovery_api test_listing_jobs test_listing_format test_ivyea_listing_trial test_listing_locks test_listing_brand_policy`。


已返回结果接续：`POST /api/listing-jobs/continue-returned-review`，参数`{id,reviewRecoveryId,requestId,returnedReceipt:{id,sha256}}`。这不是第二次重审。仅当同journal只有一份具有真实任务身份的完整重审返回、SHA和`re_review_returned`历史一致、未出现任何后续targeted repair意图，且其中`missing_phrase`能由真实draft-hit/当前词串直接反证时，冻结一份独立`continuation`后继续原有效问题修订。普通resume始终只读；原重审intent、旧错误和全部原响应保留。continuation未知或重复同样只读。

正常审校中，同样仅对可证明为假的missing_phrase记录`sourceDispositions`（原finding、draft/current位置、reviewReceipt）；其他无法对应原文的问题仍阻断，所有有效问题仍必须修订并重新检查。
