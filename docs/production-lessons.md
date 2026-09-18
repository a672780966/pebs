# Production Lessons（M6 §66–§67）

> 规则：任何真实生产 / benchmark 暴露的问题必须走完整四步：
> **Bug → Fix → Regression Test → Production Lesson**。
> 不允许"人工修好了就结束"。每条记录包含：date、task、symptom、root_cause、skill、artifact、fix、regression_test。

## 2026-09-17 — M6 基线冻结与并发工作隔离

- **date**: 2026-09-17
- **task**: M6 §4/§5 冻结 M5 baseline、隔离未提交修改
- **symptom**: M5 完成后，仓库 master 上出现了另一个 worker 的 Stage C 提交（import limits / runtime index / G5 referral / model_hypothesis / PII no-leak），工作区另有未提交的 `preconditions` 功能开发；两股改动都可能污染 M5 stable baseline 的可复现性
- **root_cause**: 多 worker 并行开发同一仓库，缺少显式的 baseline tag 与分支隔离约定
- **skill**: n/a（工程流程）
- **artifact**: tags `v0.5.0` / `m5-stable` @ `5d6b03f`（CI-green M5 baseline）；分支 `m6-production-validation`
- **fix**: (1) 冻结 baseline tag；(2) Stage C 提交经独立审查（CI run 35240731768 全绿）后保留在 master，成为 M6 Security Track 的起点；(3) 当前未提交的 `preconditions` WIP 保持不动、不混入 M6 开发，`git add` 仅暂存 M6 自有文件
- **regression_test**: `tests/test_registry_consistency.py`、`tests/test_input_limits.py`、`tests/test_pii_no_leak.py`（Stage C 自带）；M6 侧由 `tests/test_benchmark_scaffold.py` 固定 fixture / case 完整性

## 2026-09-17 — PII 扫描误报阻断合法教学请求（Gate False Positive）

- **date**: 2026-09-17
- **task**: Golden Benchmark D/E 请求在发送前被 PII 门拦下
- **symptom**: `PiiBlocked: 请求文本包含可识别学生资料`，但请求句为"不得把群体统计写成对具体学生的判断"、"避免儿童标签化表达"等纯教学指令
- **root_cause**: `named_student` 正则把"学生/儿童"之后的任意 2–3 个汉字当作姓名（"的判断"、"标签"），且缺少虚词/通用名词过滤
- **skill**: n/a（安全层）
- **artifact**: `pebs/pii.py`
- **fix**: 增加 `_looks_like_name`（虚词、通用名词、名词后缀三类过滤），正则改为惰性 2–3 字 + 常见谓语前瞻；`mask_text` 使用同一判定，避免误改正文
- **regression_test**: `tests/test_pii.py`（误报句不命中；"学生：小明"/"同学王芳"仍命中）

## 2026-09-17 — audit-only 路由被否定式生产指令击穿（Routing Error）

- **date**: 2026-09-17
- **task**: Golden Benchmark E（已有讲稿审阅）
- **symptom**: 请求"只审核……不要重写"被判为生产任务，Planner 生成完整 Authoring 链（含 script-writer）
- **root_cause**: `PRODUCTION_PATTERN` 命中"重写"里的"写"，覆盖了 `AUDIT_PATTERN`
- **skill**: `gate-runner` / `claim-extractor`（计划层）
- **artifact**: `pebs/routing/intent.py`、`pebs/planner/planner.py`
- **fix**: 先剥离否定式生产短语（`NEGATED_PRODUCTION_PATTERN`）再判定生产意图；审阅任务据此走 `audit_only` 终端（gate_result/export_manifest）
- **regression_test**: `tests/test_golden_benchmark_plan.py::test_benchmark_case_e_is_review_only`

## 2026-09-17 — 脚本类课程静默产出 PPT（Unnecessary Regeneration / Plan Error）

- **date**: 2026-09-17
- **task**: Golden Benchmark C（托育四节脚本，未要求 PPT）
- **symptom**: Plan 与 Changeset 中出现 `slide_plan` / `pptx_deck`，成本与产物超出用户要求
- **root_cause**: `gate-runner` 与 `preview-builder` 把 `pptx_deck` 声明为 optional_requires，任何含门禁/预览的计划都会顺带生产 deck
- **skill**: `presentation-planner` / `presentation-composer`
- **artifact**: `registry/skills.json`
- **fix**: 从二者 optional_requires 中移除 `pptx_deck`；同时 Planner 对"已存在的可选输入"直接复用为零成本节点（§27）
- **regression_test**: `tests/test_golden_benchmark_plan.py`（A/C 的 Plan 不含 pptx；G 显式请求时才生成）

## 2026-09-18 — 执行层没有预算感知，四节课在核验中途 BLOCKED（RUNTIME/COST）

- **date**: 2026-09-18
- **task**: Golden Benchmark C（托育四节课程）dynamic 真实运行
- **symptom**: 88 次模型调用 / 57 次研究请求后 `evidence-reviewer BLOCKED: research request budget exhausted`；Planner 的降级只改 `research_need`，执行层照旧每 Claim 做 3 来源 + 全文抓取
- **root_cause**: `step_evidence` 直接 `check_budget`，没有读取剩余预算并降级
- **skill**: `evidence-reviewer`
- **artifact**: `pebs/store.py`（budget_remaining）、`pebs/pipeline.py`
- **fix**: 每个 Claim 前读 `budget_remaining`：预算耗尽→跳过文献核验（Claim 保持未支持并排除出证据契约）；预算不足以覆盖完整成本→单来源核验并关闭全文抓取；所有降级写入 step notes
- **regression_test**: `tests/test_evidence.py`、`tests/test_research.py`、`tests/test_pipeline.py`、`tests/test_golden_benchmark_plan.py`（全绿）

## 2026-09-18 — 四节课程运行超过 harness 的固定 3600s 等待上限（RUNTIME）

- **date**: 2026-09-18
- **task**: Golden Benchmark C dynamic 真实运行（第二次）
- **symptom**: run 仍在执行时 harness 已放弃等待，把 run 记为 "running" 并退出，遗留孤立线程与缺失的 run.json
- **root_cause**: `runner._wait` 硬编码 3600s，而四节课程（~150 次模型调用 × ~30s）需要更久
- **skill**: n/a（benchmark harness）
- **artifact**: `pebs/benchmark/runner.py`
- **fix**: `_wait_timeout(run)` = max(3600, run.budget_seconds + 600)，等待上限跟随运行自身的时间预算
- **regression_test**: `tests/test_wait_timeout.py`

## 2026-09-18 — 编号小节（8.1/8.2）被并成一节（ROUTING）

- **date**: 2026-09-18
- **task**: Golden Benchmark C 真实运行（第一次）
- **symptom**: 请求写了 8.1–8.4 四节，`requirements.sections` 只有 1 节（sec1 "四节课程脚本"），最终只产出 script:sec1
- **root_cause**: `parse_section_titles` 只识别"第N节/章"与"任务N"
- **skill**: `requirements-builder`（Router）
- **artifact**: `pebs/router.py`
- **fix**: 识别 `X.Y 标题` 编号小节；存在编号小节时忽略容器式标题（如"第八章四节课程脚本"）
- **regression_test**: `tests/test_section_numbering.py`

## 2026-09-18 — 模型返回 0 条 Claim 时在 PCK 处才失败（EVIDENCE）

- **date**: 2026-09-18
- **task**: Golden Benchmark B（大学生心理健康第一课）dynamic 真实运行
- **symptom**: 运行继续到 PCK 才以"证据索引为空"阻塞，错误信息无法定位到上游提取环节；浪费 31 次模型调用
- **root_cause**: `step_claims` 接受空列表并照常产出 claims_set
- **skill**: `claim-extractor`
- **artifact**: `pebs/pipeline.py`
- **fix**: 0 条 Claim 立即 `StepFailed`，提示"模型未返回可核验的实证性 Claim；请检查请求或补充材料（系统不会用空证据继续生产）"
- **regression_test**: `tests/test_claims_extraction_guard.py`

## 2026-09-18 — 单条未支持 Claim 阻塞整门课程（EVIDENCE）

- **date**: 2026-09-18
- **task**: Golden Benchmark A/B dynamic 真实运行
- **symptom**: 证据索引里有 SUPPORTED Claim，但一条 UNSUPPORTED/PENDING 就让 PCK 拒绝执行
- **root_cause**: `evidence_index.claims` 登记了全部 Claim，而它是"PCK 可消费契约"
- **skill**: `evidence-reviewer` / `pck-developer`
- **artifact**: `pebs/pipeline.py`、`pebs/preconditions.py`
- **fix**: 契约只登记可消费状态（`rules.evidence.pck_claim_statuses`，默认 SUPPORTED）；不可消费的显式写入 `excluded_claims`（含状态与原因，不隐藏）；另修正 `usage_scope` 按多值 token 交集匹配
- **regression_test**: `tests/test_evidence_status_policy.py`、`tests/test_usage_scope_matching.py`

## 2026-09-18 — 真实 Codex 运行：PCK 前置条件因 usage 多值而永远阻塞（EVIDENCE/RUNTIME）

- **date**: 2026-09-18
- **task**: Golden Benchmark A（融合教育三节脚本）dynamic/builtin 真实运行
- **symptom**: PCK 被前置条件阻塞，理由"证据契约范围内没有可消费的 PCK Claim"，但证据索引里明明有 SUPPORTED Claim
- **root_cause**: `preconditions.check_supported_claims` 用整串比较 `usage`（真实值是"讲解/案例/评价"）与 `usage_scope`（"讲解"），永远不匹配
- **skill**: `pck-developer`（前置条件）
- **artifact**: `pebs/preconditions.py`
- **fix**: `usage_tokens()` 按 `/、,，;；|` 切分后取交集；默认政策保持只允许 SUPPORTED
- **regression_test**: `tests/test_usage_scope_matching.py`

## 2026-09-18 — 实践型课程需要材料化证据，否则被证据门正确阻塞（EVIDENCE）

- **date**: 2026-09-18
- **task**: Golden Benchmark A/B 真实运行（Codex + Crossref/OpenAlex/Semantic Scholar/PubMed）
- **symptom**: B/dynamic 与 A/builtin 在 PCK 处 blocked；A/dynamic 只有加入合成材料 fixture 后才成功
- **root_cause**: 实践型断言（"观察记录应区分事实与判断"）在真实文献中通常只能到 QUALIFY_REQUIRED 或无直接引文；严格 quote-grounding 下没有可用 SUPPORTED 证据
- **skill**: `evidence-reviewer` / `pck-developer`
- **artifact**: `benchmarks/fixtures/materials/observation_recording_handbook.md`、`config/rules.yaml`（`evidence.pck_claim_statuses`）
- **fix**: (1) 证据检索优先选择有摘要/全文的来源（空摘要按 metadata 排序，不占用核验名额）；(2) 提供操作者显式政策 `--allow-qualified-claims`（放行 QUALIFY_REQUIRED，限定语必须保留，写入 run.json 的 evidence_policy）；(3) benchmark 材料化证据（教师上传手册/标准 → user_material 可定位引文）
- **regression_test**: `tests/test_evidence_status_policy.py`；真实运行记录见 `benchmarks/reports/benchmark_summary.md`

## 2026-09-18 — 预算感知只在规划层，执行层仍会中途耗尽（RUNTIME）

- **date**: 2026-09-18
- **task**: A/dynamic 真实运行（research 预算 20）
- **symptom**: `evidence-reviewer BLOCKED: research request budget exhausted`；Plan 未降级
- **root_cause**: benchmark runner 未把 budgets 传给 Planner；即使传入，Planner 的降级只改 `research_need`，不减少每 Claim 的全文抓取次数
- **skill**: `evidence-reviewer`
- **artifact**: `pebs/benchmark/runner.py`、`pebs/cli.py benchmark`
- **fix**: runner 默认传 `config.RULES.budgets` 并支持 `--max-research/--max-model-calls/--max-seconds`；执行层按预算跳过全文抓取的改进列为 M6.5 后续项
- **regression_test**: `tests/test_benchmark_scaffold.py`（预算入 Plan 的降级路径）

## 2026-09-18 — 禁用表达的教学反例被误判为违规（Gate False Positive）

- **date**: 2026-09-18
- **task**: A/dynamic 真实运行（脚本中出现"不要使用'这个孩子就是…'这类标签化表达"）
- **symptom**: Auto Issues 报 SAFETY 命中禁用表达
- **root_cause**: banned_regex 检查不考虑否定语境
- **skill**: n/a（benchmark 检查器）
- **artifact**: `pebs/benchmark/checks.py`
- **fix**: 匹配前看前 14 字符是否含"不要/避免/禁止/不得/拒绝/不将/不应"，是则视为教学反例
- **regression_test**: `tests/test_benchmark_scaffold.py::test_banned_regex_ignores_negative_examples`

## 2026-09-18 — Skill Trace 用步骤标题当 skill 名，性能数据无法绑定版本（SKILL/§40）

- **date**: 2026-09-18
- **task**: M6 性能注册表（`registry/performance.json`）首次积累数据
- **symptom**: 注册表里出现"生成可编辑 PPTX""教案设计（PCK/UDL）"这类中文步骤标题作为 skill 名；§40 要求的历史数据无法按 skill+版本 归因
- **root_cause**: `trace.build_trace` 在静态模式下拿不到 skill 名时退化为 `step.title`（散文），而不是把 pipeline step id 反查回 Registry Skill
- **skill**: n/a（telemetry）
- **artifact**: `pebs/benchmark/trace.py`、`registry/performance.json`
- **fix**: `_skill_for_step()` 先按 skill 名查 Registry，再按 `handler.steps` 反查；仍无法解析时记为 `step:<id>`（可诊断）；已作废的 22 条中文名记录清除并在文件 note 中说明
- **regression_test**: `tests/test_benchmark_evaluation.py::test_trace_resolves_pipeline_steps_to_registry_skills`

## 2026-09-18 — 显式 `/skill-name` 不进入 DAG，外部 Skill 永远不被选中（PLANNING/§16）

- **date**: 2026-09-18
- **task**: §46 Skill Selection Experiment（case A + `/dual-coding-designer`）
- **symptom**: 请求里显式写了外部 Skill，Plan 里仍只有 11 个节点、完全没有 media 链（media_plan 从未进入 DAG）
- **root_cause**: Planner 的 `prefer` 只影响"同类候选之间选谁"，不会把该 Skill 的产出加入终端/可选集合；没有消费者时该产物类型根本不在 DAG 里
- **skill**: `dual-coding-designer`（外部）
- **artifact**: `pebs/planner/planner.py`
- **fix**: 解析显式 Skill 的 `produces/emits` 并加入 `terminals`，同时把原因写入 `plan.route_notes.explicit_skills`
- **regression_test**: `tests/test_explicit_skill_planning.py`

## 2026-09-18 — §17 A/B 首轮数据：外部 Skill 的分节内容不分节（SKILL/PEDAGOGY）

- **date**: 2026-09-18
- **task**: §46 Skill Selection Experiment：case A `dynamic`（builtin media-router）vs `dynamic [+dual-coding-designer]`（external）
- **symptom**: 两次运行都 succeeded（同任务/同材料/同模型；22 次调用），但外部 Skill 产出的 `media_plan:sec1/sec2/sec3` **11 个 item 完全相同**（functions/mediums 一致）——外部 Skill 只被调用一次，随后 `_emit_external_artifacts` 把同一 payload 复制到每一节；builtin media-router 是分节调用的
- **root_cause**: 外部 Prompt Skill 的执行粒度是"节点一次"，而分节产物（`{section_id}` 模板）需要分节调用与分节最小上下文（§21/§27）
- **skill**: `dual-coding-designer`（外部，provider SHA 6bbbce41…）
- **artifact**: `pebs/runtime/prompt_skill.py`、`pebs/runtime/executor.py`
- **fix（待实施，M6.5 后续）**: 当产物模板包含 `{section_id}` 且项目有多节时，按节调用并逐节校验（修复后需重跑 A/B）
- **当前决策（§18/§76）**: 在补齐分节执行与人工评分之前，外部 Skill 保持 **不默认优先**，Builtin 仍是生产默认；性能注册表记录 provider SHA 与 patch 以便 M7 决策
- **regression_test**: `tests/test_explicit_skill_planning.py`、`tests/test_external_skill_acceptance.py`（机制层）；质量结论需重跑 A/B

## 2026-09-18 — 概念/态度型课程没有实证 Claim：证据门与课程定位的冲突（EVIDENCE/PEDAGOGY）

- **date**: 2026-09-18
- **task**: Golden Benchmark B（大学生心理健康第一课：理解心理学有什么用、愿意继续学）
- **symptom**: Router 正确识别为 concept/reflection/attitude/critical_thinking/transfer，但 claim-extractor 返回 0 条实证 Claim（该课的目标是概念与态度，不是实证结论）→ 证据契约为空 → PCK 阻塞
- **root_cause**: 系统把"有 PCK"与"有实证 Claim"绑定；对概念/态度型课程缺少"基于教学法（无实证断言）"的显式路径
- **skill**: `claim-extractor` / `pck-developer`
- **artifact**: `pebs/pipeline.py`（fail-fast）、`pebs/preconditions.py`
- **fix（已完成部分）**: 0 条 Claim 立即明确失败并提示补充材料/改请求；错误信息不再误导到下游
- **待决策（需要教学判断，不在 M6 自动化范围）**: 是否允许"无实证 Claim"的课程走标注了限制的 PCK 路径（`declared_no_empirical_claims`），或要求教师提供可核验材料。当前默认：阻塞（保守）
- **regression_test**: `tests/test_claims_extraction_guard.py`

## 2026-09-18 — CI 曾长期为红（M5.1–M5.3）


- **date**: 2026-09-17
- **task**: M5 CI
- **symptom**: GitHub Actions 在 ubuntu/windows 全部失败，本地却全绿
- **root_cause**: `requirements.txt` 未声明 `python-pptx`、`python-multipart`（本地环境已装）；同秒创建的 changeset 排序不稳定（Linux runner 上复现）
- **skill**: n/a
- **artifact**: `requirements.txt`；`pebs/store.py` `list_changesets`
- **fix**: 补齐依赖；`ORDER BY created_at DESC, rowid DESC` 加确定性 tiebreaker
- **regression_test**: `tests/test_store.py::test_changeset_listing_is_newest_first_within_the_same_second`（CI run 35230946294 全绿）
