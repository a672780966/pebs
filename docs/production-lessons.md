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

## 2026-09-17 — CI 曾长期为红（M5.1–M5.3）


- **date**: 2026-09-17
- **task**: M5 CI
- **symptom**: GitHub Actions 在 ubuntu/windows 全部失败，本地却全绿
- **root_cause**: `requirements.txt` 未声明 `python-pptx`、`python-multipart`（本地环境已装）；同秒创建的 changeset 排序不稳定（Linux runner 上复现）
- **skill**: n/a
- **artifact**: `requirements.txt`；`pebs/store.py` `list_changesets`
- **fix**: 补齐依赖；`ORDER BY created_at DESC, rowid DESC` 加确定性 tiebreaker
- **regression_test**: `tests/test_store.py::test_changeset_listing_is_newest_first_within_the_same_second`（CI run 35230946294 全绿）
