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
- **fix**: 契约只登记可消费状态（冻结常量 `pebs.preconditions.PCK_REQUIRED_STATUS = "SUPPORTED"`，不可配置）；不可消费的显式写入 `excluded_claims`（含状态与原因，不隐藏）；另修正 `usage_scope` 按多值 token 交集匹配
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
- **artifact**: `benchmarks/fixtures/materials/observation_recording_handbook.md`（历史记录：当时 `config/rules.yaml` 中的证据政策开关已在 baseline recovery 中移除）
- **fix**: (1) 证据检索优先选择有摘要/全文的来源（空摘要按 metadata 排序，不占用核验名额）；(2) 【历史/已废止】当时提供过操作者政策 `--allow-qualified-claims` 放行 QUALIFY_REQUIRED —— baseline recovery 已冻结证据契约，该 CLI 开关、`rules.evidence.pck_claim_statuses` 配置键、以及对应的 benchmark 放宽路径全部移除，不再可用；(3) benchmark 材料化证据（教师上传手册/标准 → user_material 可定位引文）
- **current_guidance（baseline recovery 之后的唯一正确做法）**: PCK 因证据不足阻塞时——① 改进来源选择；② 收窄或改写该事实性 Claim，直到它真正获得 SUPPORTED；③ 使用教师提供的权威材料作为可定位证据；④ 删除该不受支持的事实依赖；⑤ 以上都做不到时保持 BLOCK。系统不提供任何放行开关（含空证据与未核验证据）。
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

## 2026-09-20 — Builtin（静态 Pipeline）被凭空判 5 条 PLAN 错误（CHECKS §28）

- **date**: 2026-09-20
- **task**: M6.4 Acceptance 4（Direct/Builtin/Dynamic 三模式对比），真实 run `C/builtin`
- **symptom**: `C/builtin` 的自动问题里出现
  `缺少必需步骤：learning_design / claims / evidence / scripts` 与
  `terminal_outputs 缺少：script`——但静态 Pipeline 明明执行了这些步骤
- **root_cause**: 静态模式**不产出 `build_plan_dynamic`**（DAG 产物是动态专属），
  `runner` 取 `plan = {}` 后 `plan_checks` 拿空计划逐条比对，
  于是每条期望都报"缺少"。Builtin 基线因此被系统性判差，
  直接污染 §28 的三模式对比（也是最不该出现的偏差——它让 Dynamic 显得更好）
- **skill**: `benchmark-checks` / `benchmark-runner`
- **artifact**: `pebs/benchmark/runner.py`、`pebs/benchmark/checks.py`
- **fix**: 新增 `_static_plan()`：用**真实执行过的 step** + 注册表产出合成 plan 形状；
  `plan_checks(static_plan=True)` 跳过 DAG 专属期望（terminal_outputs / 复用率 /
  复用产物类型），但能力类期望（必须包含/排除的步骤与 Skill）照常生效
- **实测影响**: C-builtin 的 plan 问题 5 → **0**
- **regression_test**: `tests/test_benchmark_scaffold.py::test_static_plans_are_not_charged_with_dag_expectations`、
  `::test_static_plan_builder_uses_registry_produces`

## 2026-09-21 — 局部修改打到错误章节：LLM 猜测优先于确定性「8.2」引用（CONVERSATION §26/§36）

- **date**: 2026-09-21
- **task**: M6.4 Acceptance 7 复跑（F：只把 8.2 的案例换掉）
- **symptom**: 同一条指令两次结果不同——`20260919-051411` 正确落在 `sec2`（locality 1.0），
  `20260921-175142` 却落在 `sec1`（locality **0.875**，`preserve_violations: ['script:sec1']`），
  即把"只改 8.2"执行成了"改了 8.1"
- **root_cause**: `conversation/resolver.resolve()` 的定位优先级把
  **LLM 返回的 `targets.section_ids` 排在确定性编号匹配之前**：
  模型这次猜了 `sec1`，`section_ids` 非空，`8.2 → 标题以 "8.2" 开头` 的确定性匹配
  根本没有机会执行。这违反项目硬规则"确定性用户约束优先于 LLM"
- **skill**: `conversation-edit`
- **artifact**: `pebs/conversation/resolver.py`
- **fix**: 定位顺序改为 确定性序数（第N节）→ 确定性编号引用（8.2）→ 确定性标题匹配 →
  **LLM 目标（仅在前述都没有时）** → 文本匹配 → 单章节默认；
  当 LLM 目标与确定性引用冲突时，采用确定性结果并把冲突写入 `unmapped`（不静默丢弃）
- **regression_test**: `tests/test_target_resolution.py::test_deterministic_section_label_beats_a_wrong_llm_guess`
  （并保留 `test_llm_layer_cannot_override_deterministic_intent` 覆盖序数场景）
- **复跑验证（零模型调用，真实产物）**: 在 `20260921-175142` 那个**已建好 C 课程的项目**上重放同一条指令
  （`engine.conversation_edit(..., execute=False)`）：patch plan 目标为
  `case:sec2:1` / `script:sec2` / `gate:G1..G7:script:sec2`，**没有任何 sec1 目标**，锁定 51 个产物
- **未能完成的部分（如实记录）**: 完整 F 场景的端到端复跑两次都卡在**前置课程构建**上：
  `20260921-193240` 是 provider `learning_design: codex exec 超时`（2 次调用）；
  `20260921-202853` 是 `pck-developer` 前置条件"证据索引为空，没有可用的 SUPPORTED Claim"
  （60 次调用）——与 case B 同源（冻结契约 + 证据波动），不是 F 场景本身的问题

## 2026-09-21 — case D 补齐 Direct 基线：四个 case 已具备三模式对照（BENCHMARK §28/§71-4）

- **date**: 2026-09-21
- **task**: M6.4 Acceptance 4（同一任务可比较 Direct / Builtin / Dynamic）
- **结果**: `D/direct_codex` 一次调用即完成（148.9s）。至此 **A / B / C / D** 四个 case
  都同时具备 Direct、Builtin、Dynamic 三种模式（D 另有 4 个外部变体）：
  | D 变体 | 模型调用 | 研究 | 门禁 FAIL | 自动问题 |
  | --- | --- | --- | --- | --- |
  | direct_codex | 1 | 0 | —（无门禁存储） | 0 |
  | builtin（静态） | 17 | 0 | 1 | 1（SAFETY） |
  | dynamic（内置） | 10 | 3 | 2 | 1 |
  | dynamic + 4 个外部变体 | 17–26 | 6–11 | 0–3 | 0–3 |
- **意义**: Direct 只用 1 次调用（无门禁、无证据链、无局部修改能力），
  Builtin/Dynamic 把成本花在证据、门禁与可追溯上；这张表把"多花的调用买到了什么"
  变成可检验的数据，而不是主张
- **artifact**: `benchmarks/runs/20260921-212802-D-direct_codex/`、`benchmark_summary.md` 的 D 行

## 2026-09-21 — case E（已有讲稿审阅）当前代码确认：脚本被复用而非重写（BENCHMARK §25）

- **date**: 2026-09-21
- **task**: M6.4 §25（Existing Course Review）当前代码复测
- **结果**（`20260921-213232-E-dynamic`，20 次调用，证据政策 `['SUPPORTED']`）:
  - trace 里 `script-writer` 为 **`reused: true`、`output_artifacts: []`**——
    已有讲稿被复用，**没有被重写**（这正是 §25 的核心要求）
  - 规划只走 审阅链：requirements → learning_design → claims → evidence → gates → preview → export，
    terminal 为 `gate_result` / `export_manifest`，没有 script/lesson_plan/pptx/storyboard 的再生成
  - 审阅确实发现问题：`G3 FAIL`（教学法）、`G5 FAIL`（UDL），`G6 NEEDS_REVIEW`
- **意义**: 用真实 run 证明"只检查、不重写"在路由与复用两头都成立
- **artifact**: `benchmarks/runs/20260921-213232-E-dynamic/`

## 2026-09-21 — Acceptance 7 在当前代码上直接复测：locality 1.0，只重建被点名的那一节（BENCHMARK §26/§71-7）

- **date**: 2026-09-21
- **task**: Acceptance 7（局部修改 Unrelated Artifact Hash 保持不变）的当前代码确认
- **做法**: 新增 `tools/verify_locality.py`——**复制**一份已建成课程的项目到临时目录，
  在副本上跑真实的 `conversation_edit`（原项目保持不变），再用
  `metrics.locality_report` 度量（与 benchmark 同一套口径）
- **结果（2 次运行，各 4–5 次模型调用）**:
  - 受影响集合只有 `case:sec2:1` / `script:sec2` / `gate:G1..G7:script:sec2` / `claims`
  - `locality_preservation_rate = 1.0`、`preserve_violations = []`、
    `unnecessary_regeneration = []`，锁定 51 个产物
  - 被点名那一节自己的门禁照常生效：`gate:G2:script:sec2` FAIL（新案例引用 PENDING Claim、
    含占位内容）、`gate:G6:script:sec2` NEEDS_REVIEW——失败**限制在改动的那一节**
- **意义**: 同时闭合 Acceptance 7 的当前代码证据、§26 preserve 契约，
  以及上一轮"确定性小节引用优先"修复在真实产物上的效果
- **artifact**: `tools/verify_locality.py`、`benchmarks/runs/20260921-175142-F-scenario/`

## 2026-09-21 — 模型把 `claim_refs` 返回成对象 → `set(...)` 抛 unhashable dict，整条运行 failed（RUNTIME §67）

- **date**: 2026-09-21
- **task**: M6.4 Acceptance 7 复跑（F 场景先构建基线课程 C）
- **symptom**: 基线课程在 `script-writer` 崩溃：
  `未预期错误：unhashable type: 'dict'`（60 次调用后整条 F 场景 failed，locality 无法测量）
- **root_cause**: 与 2026-09-20 的 slide_plan 崩溃**同源**——模型返回的 `claim_refs`
  有时是对象/数组（`[{"id": ..., "version": ...}]`），而下游对引用做
  `set(...)`（script 的待核验汇总）、`sorted(set(...))`（case 登记新事实）；
  字典参与集合运算直接 `unhashable`。另有 `_citation_label` 用 `ref.partition("@v")`，
  拿到 dict 会 AttributeError（尚未触发，但是同一雷）
- **skill**: `script-writer` / `case-designer`
- **artifact**: `pebs/pipeline.py`
- **fix**: 新增 `_claim_refs()` 统一归一化成字符串列表，并在四处入口应用
  （script units、case 的新事实登记 ×2、slide_plan rows）；`_citation_label` 用
  `str(claim_ref)` 兜底。非字符串引用无法构成合法 `id@vN`，归一八成字符串后
  按"未获支持"处理（保守方向：标为待核验占位）
- **regression_test**: `tests/test_pipeline.py::test_claim_refs_returned_as_objects_do_not_crash_the_script`

## 2026-09-21 — case C（4 节）：外部 Backwards Design 成本翻倍且有门禁失败，Builtin 更省（BENCHMARK §17/§18）

- **date**: 2026-09-21
- **task**: M6.4 §17 命名对照（PEBS Builtin Learning Design vs Backwards Design Skill）在**多节课程**上复现
- **背景**: 此前 `C + /backwards-design-unit-planner` 在 90 次调用预算下 blocked；
  提高到 170 次后完成
- **结果**（两者都是当前代码、都 succeeded）:
  | 变体 | 模型调用 | 研究请求 | 门禁 FAIL | 自动问题 |
  | --- | --- | --- | --- | --- |
  | C builtin（静态） | **47** | 0 | **0** | 2（重放后 0，见 §28 条目） |
  | C + backwards-design-unit-planner | 96 | 11 | **2**（G2/G3） | 0 |
- **门禁失败详情**: `G2:script:sec2`——脚本含占位内容且引用
  `clm_549e02319d@v1`（状态 PENDING）的 Claim；`G3:script:sec2`——
  `策略目标指向未知目标：g3、g4`（外部 Skill 生成的教学策略引用了学习设计里不存在的目标 id）
- **可读出的结论（仅记录，§47/§18）**: 在 4 节课程上，外部 Backwards Design 变体
  模型调用约为 Builtin 的 **2×**，并引入两处真实门禁失败（证据未核验 + 目标 id 悬空）。
  这与 D 案例上"外部变体问题更多"的观测一致：**外部 Skill 不是默认更好**，
  §18 的"评分必须来自实际验证"得到真实数据支持
- **artifact**: `benchmarks/runs/20260921-001516-C-dynamic/`、`benchmarks/runs/20260920-182441-C-builtin/`
- **附带发现（值得后续跟进）**: G3 的 `策略目标指向未知目标` 说明外部 Skill 输出的
  策略可以引用不存在的 goal id；当前由门禁兜住（fail closed），但是否应在
  外部 Skill 的输出校验里更早拦截（schema/交叉引用检查）属于 M6.5 compact 的候选

## 2026-09-20 — 报告测试依赖本地 `benchmarks/runs/`，本地绿而 CI 红（TEST §43）

- **date**: 2026-09-20
- **task**: M6.4 报告版本标记改动后的 CI
- **symptom**: 本地 `pytest tests -q` 全绿，CI 的 ubuntu/windows 两个 job 红：
  `test_report_builds_mode_comparison_table`、`test_report_shows_gate_failures_alongside_automatic_issues`
  断言 `"| A | dynamic |"` 失败
- **root_cause**: 两个叠加。(1) 新增的版本标记让变体名变成 `dynamic ?`，
  断言里的尾随 `|` 不再匹配；(2) **更隐蔽**：本地存在 `benchmarks/runs/`，
  `render_markdown()` 的附加小节（质量指标/性能/失败类别）会读**本地真实 run**，
  于是本地 markdown 里额外出现 `| A | dynamic | ...` 行让旧断言"碰巧"通过；
  CI checkout 没有 `runs/`，断言就失败
- **skill**: `benchmark-report`
- **artifact**: `tests/test_benchmark_scaffold.py`
- **fix**: 断言改为不依赖尾随分隔符、也不依赖本地 run 的稳定子串；
  并用"隐藏 `benchmarks/runs/` 后跑全量 `-m 'not integration'`"复现 CI 条件
  （491 passed）确认修复
- **regression_test**: 上述两个测试本身；复核方式为隐藏 runs 目录的 CI 模拟

## 2026-09-20 — case A 同代码版本对照：Dynamic 用更少模型调用达到同等门禁/问题结果（BENCHMARK §28/§73）

- **date**: 2026-09-20
- **task**: M6.4 Acceptance 4（同任务 Direct/Builtin/Dynamic 对比）
- **背景**: A 的 dynamic 代表 run 是 2026-09-18 的旧代码产物（门禁修复前，报告里带 `?`），
  与新的 A/builtin 不可比；因此用**当前代码**重跑 A/dynamic
- **结果**（两者都是当前代码、都 succeeded、都 0 条自动问题、都 0 条门禁 FAIL）:
  | 模式 | 模型调用 | 研究请求 | 时间(s) | 门禁 FAIL | 自动问题 |
  | --- | --- | --- | --- | --- | --- |
  | builtin（静态） | 37 | 0 | 1751 | 0 | 0 |
  | dynamic | **28** | 6 | 949 | 0 | 0 |
- **可读出的结论（仅记录，§47）**: 同一门 3 节课程，Dynamic 少用约 24% 模型调用完成，
  代价是 6 次研究请求；两者在门禁与自动检查上打平。按 §73 的成本项，这一 case 上 Dynamic 更优；
  但样本量=1，不构成"Dynamic 普遍更好"的结论
- **artifact**: `benchmarks/runs/20260920-224226-A-dynamic/`、`benchmarks/runs/20260920-210708-A-builtin/`
- **附带验证**: 该 run 的 `evidence_policy = ["SUPPORTED"]`——`run_case` 写入证据政策的新逻辑
  在真实运行中生效（此前恒为 None）

## 2026-09-20 — case B：Builtin 两次都卡在证据前置，Dynamic 以更多研究请求通过（BENCHMARK §22/§28）

- **date**: 2026-09-20
- **task**: M6.4 为 case B（大学生心理健康第一课）补齐 Builtin 基线
- **symptom**: `B/builtin` 两次尝试都没完成：
  - `20260920-041319`：`claims` 步骤 fail-fast（"Claim 提取结果为空"），2 次调用
  - `20260920-222030`：23 次调用 / **12 次研究请求**后在 `teaching_plan` 被前置条件拦下
    ——"证据索引为空，没有可用的 SUPPORTED Claim"
  同期 `B/dynamic`（`20260919-084324`）以 45 次调用 / **33 次研究请求**完成，
  Router 判定 `research_need=VERIFY`
- **root_cause**: 不是代码缺陷，而是**研究投入差异 + 冻结的证据契约**：
  B 是概念型第一课，本身不含实证 Claim；Builtin 默认研究预算下没能拿到 SUPPORTED 证据，
  而 PCK 的冻结前置条件（`PCK_REQUIRED_STATUS = "SUPPORTED"`）不允许放行。
  Dynamic 侧 Router 给出 `VERIFY` 并实际发出 33 次研究请求（含 `HTTP 403` 全文抓取失败、
  公开语料里"未找到支持证据"等真实限制），才凑出可用证据
- **skill**: `claim-extractor` / `evidence-reviewer` / `pck-developer`
- **artifact**: `benchmarks/runs/20260920-222030-B-builtin/`、`benchmarks/runs/20260919-084324-B-dynamic/`
- **fix**: **不改代码**。这是 M6 要测的东西：同一课程，Dynamic 付出约 2.75× 研究请求后能完成，
  Builtin 在默认预算下不能。**明确不恢复**被上游冻结移除的 `allow_empty_claims` /
  `allow_unverified_pck`——空证据必须 fail closed
- **留给上游决策的开放问题（不由本 worker 单方面修改，§3/§47）**:
  §22 的 B 是"概念型第一课"，冻结契约要求它提供 empirical SUPPORTED Claim 是否过严？
  若认为过严，应由规则所有者调整契约并在 §85 验收中重新定义，而不是在 benchmark 里放宽
- **regression_test**: 无（基准观测）；数字见 `benchmark_summary.md` 的 B 行
- **重要修正（2026-09-21 复跑）**: 上面的"Builtin 卡住 / Dynamic 通过"是**单次运行**的印象，
  复跑推翻了它：`B/dynamic`（`20260921-215555`，27 次调用 / 12 次研究请求）在**同一条**
  `pck-developer` 前置条件上 blocked（"证据索引为空，没有可用的 SUPPORTED Claim"）。
  准确结论应当是：**两种模式都可能因空证据前置条件而中止**，差别只在研究投入
  （那次成功用了 33 次研究请求，这次只有 12 次），成功并不保证——
  这正是"不追求用叙事代替数据"的提醒
- **顺带确认（路由侧）**: 同一次运行 Router 给出的 knowledge_types 为
  `['concept','distinction','reflection','attitude','critical_thinking','transfer']`，
  即 §21/§36 关心的 attitude / transfer / critical_thinking 都被识别到了，
  这一条**不是** Routing Error

## 2026-09-20 — 报告不区分 run 的代码版本，读者会跨版本比较门禁/检查器结论（REPORT §41）

- **date**: 2026-09-20
- **task**: M6.4 报告可读性（A 行出现 builtin 0 门禁失败 vs dynamic 6 条失败）
- **symptom**: `A | builtin`（本次，修复后）显示 0 条门禁失败，而 `A | dynamic`
  （2026-09-18 的旧 run）显示 6 条——两者代码版本不同、门禁实现也不同，
  放在同一张表里直接比较会得出"builtin 比 dynamic 更干净"的错误结论
- **root_cause**: 报告只按 `(case, mode, experiment)` 分行，没有任何"该 run 由哪个代码版本产生"的标记；
  门禁契约修复（5f99507）与若干检查器修复之后，历史行的口径已经不可比
- **skill**: `benchmark-report`
- **artifact**: `pebs/benchmark/report.py`
- **fix**: 变体名带版本标记：`*` = 已知由不同 commit 产生，
  `?` = 记录中没有 PEBS commit（早于 §41）；表尾附说明并指向
  `tools/reevaluate_gates.py` / `tools/reevaluate_checks.py` 的重放口径
- **regression_test**: 既有报告测试（`test_benchmark_report_renders_status_and_issues`）改为
  兼容版本标记；标记逻辑本身由 `_same_code_version()` 直接可测

## 2026-09-20 — `evidence_policy` 只被读、从未被写（REPORT §35/§41）

- **date**: 2026-09-20
- **task**: M6.4 A/builtin 真实 run 复核
- **symptom**: 报告表格、Evaluation Tab、教师材料包、`/evaluation` API 都在显示
  `evidence_policy`，但所有 run 的该字段恒为 `None`——A/B/C/D 抽查一致
- **root_cause**: 字段在四处被读取，**没有任何一处写入**；证据政策实际由冻结契约的
  `preconditions.PCK_REQUIRED_STATUS` 决定，却没有被记进 run
- **skill**: `benchmark-runner`
- **artifact**: `pebs/benchmark/runner.py`
- **fix**: `run_case()` 记录 `evidence_policy: [PCK_REQUIRED_STATUS]`（从唯一权威常量取值，
  不硬编码字符串）；历史 run 不回填（避免改写已有证据），新旧差异由本条目说明
- **regression_test**: `tests/test_benchmark_scaffold.py::test_benchmark_run_records_the_effective_evidence_policy`

## 2026-09-20 — Builtin 基线首次完整跑通，形成 case D 的 §17 共同对照（BENCHMARK §17）

- **date**: 2026-09-20
- **task**: M6.4 §17 Builtin vs External A/B
- **背景**: 此前 case D 只有 dynamic 与 4 个外部变体，缺少**共同对照**；
  第一次 `D/builtin` 因 `slide_plan` 崩溃失败（见上一条），修复后重跑
- **结果**（`benchmarks/reports/benchmark_summary.md`，D 行）:
  | 变体 | 状态 | 尝试 | 模型调用 | 门禁 FAIL + review | 自动问题 |
  | --- | --- | --- | --- | --- | --- |
  | builtin（静态） | succeeded 1/2 | 17 | 1 FAIL + 1 review | 1（SAFETY） |
  | dynamic（内置） | succeeded 2/3 | 10 | 2 FAIL + 1 review | 1 |
  | + hinge-question-designer | succeeded 1/4 | 22 | 1 FAIL + 1 review | 0 |
  | + backwards-design-unit-planner | succeeded 1/1 | 19 | 0 FAIL + 1 review | 3 |
  | + dual-coding-designer | succeeded 1/1 | 26 | 1 FAIL | 0 |
  | + cognitive-load-analyser | succeeded 1/1 | 17 | 3 FAIL + 1 review | 0 |
- **可读出的结论（仅记录，不做路由调整，§47）**:
  1. Builtin 与 Dynamic 都能完成同一 case，但 Dynamic 用 **10 次**调用、Builtin 用 **17 次**；
     外部 Skill 变体在 17–26 次之间——外部能力不是免费的
  2. `builtin` 与 `dynamic` 都命中同一条 `SAFETY`（脚本里的机制/因果表述），
     且 `builtin` 的 G4 同步 FAIL——两层独立判定一致，属于**真实待人工确认**内容
     （§50 因果基准的作用）
  3. 外部变体并非普遍更好：`+backwards-design` 自动问题最多（3 条），
     印证 §18"不默认外部 Skill 更好"
- **artifact**: `benchmarks/runs/20260920-204124-D-builtin/`、`benchmarks/reports/benchmark_summary.md`

## 2026-09-20 — 模型把标量返回成数组 → `x not in set` 抛 unhashable，整条运行 failed（RUNTIME §67）

- **date**: 2026-09-20
- **task**: M6.4 Builtin 基线真实 run（`D / builtin`，为 §17 三对外部 A/B 补共同对照）
- **symptom**: `slide_plan FAILED：未预期错误：unhashable type: 'list'`，
  15 次调用后运行整体 failed，pptx 与后续步骤全部 BLOCKED
- **root_cause**: `_enforce_slide_plan()` 用集合成员判断校验模型输出
  （`row["section_id"] not in valid_sections`、`diagram_id not in valid_diagrams`），
  模型这次把 `section_id` 返回成了**数组**，列表做集合成员判断直接抛
  `TypeError: unhashable type: 'list'`——本该是"清理脏输出"的函数反而崩了
- **skill**: `presentation-planner`
- **artifact**: `pebs/pipeline.py`、`pebs/engine.py`
- **fix**: 做集合判断前先把这两个字段归一化成字符串（不改变正常输入行为）；
  另外把未预期错误的 step error 附上**最后一帧位置**（`_last_frame()`），
  否则错误信息里只有 `unhashable type`，无从定位（本次排查就卡在这里）
- **regression_test**: `tests/test_pipeline.py::test_slide_plan_enforcement_survives_list_typed_model_fields`、
  `::test_unexpected_step_error_records_the_offending_frame`

## 2026-09-20 — 静态 Pipeline 同样被凭空判 2 条 ROUTING 错误（CHECKS §28/§36）

- **date**: 2026-09-20
- **task**: 同上（`C/builtin` 重跑，验证 plan 修复）
- **symptom**: 修掉 plan 问题后仍有
  `knowledge_types 未命中：['case_analysis','concept','procedure']，实际 []` 与
  `requested_outputs 缺少：script`——但静态 Pipeline 根本不产出 `router_result`
- **root_cause**: 与上一条同源：把**动态专属产物**（Router 决策）的期望套在固定流水线上；
  空 route 让每条路由期望都报未命中
- **skill**: `benchmark-checks`
- **artifact**: `pebs/benchmark/checks.py`
- **fix**: `routing_checks(..., static_pipeline=True)` 直接返回空（路由期望对没有
  Router 的流水线不适用；其交付物仍由 content / plan 检查把关）；
  动态模式行为不变
- **实测影响**: `C/builtin` 的自动问题 11 → **2** → （再修本项后）**0**；
  该 run 同时验证了此前两项修复（plan 合成为 0 条误报）
- **读数注意**: `run.json` 里存的是**运行时**的自动问题数，报告沿用该值；
  修复检查器之前记录的 run（尤其所有 `builtin` 行）其 Auto Issues 偏高，
  需要时用 `python tools/reevaluate_checks.py <case> <project_id>` 取修正后的数字，
  不要跨修复点直接比较 Auto Issues 列
- **regression_test**: `tests/test_benchmark_scaffold.py::test_static_pipeline_is_not_charged_with_router_expectations`

## 2026-09-20 — 模型返回被截断的 JSON 会让整条运行硬失败（RUNTIME A14）

- **date**: 2026-09-20
- **task**: M6.4 真实 run `C/builtin`（storyboard 步骤）
- **symptom**: `storyboard FAILED：provider JSON parse error: Unterminated string starting at
  line 1 column 6336`——一次长输出被截断就让 71 次模型调用的运行整体 failed，
  后续 gates/preview 全部 BLOCKED
- **root_cause**: `pipeline._llm_json` 把 provider 的 JSON 解析错误一律转成 `StepFailed`，
  没有任何重试；对比之下外部 Skill 路径有 schema 修复重试
- **skill**: `default-llm`
- **artifact**: `pebs/pipeline.py`
- **fix**: 对**畸形 JSON** 做有界重试（`MAX_JSON_RETRIES = 1`），重试时提示"只输出完整合法 JSON"；
  配额/可用性错误不重试；两次调用都记账（§35 成本口径）
- **regression_test**: `tests/test_pipeline.py::test_malformed_json_response_is_retried_once_then_fails`

## 2026-09-20 — 报告只显示 Auto Issues，隐藏门禁 FAIL，出现"0 问题但 G6 FAIL"（REPORT §35/§71-8）

- **date**: 2026-09-20
- **task**: M6.4 §17 第三对 A/B（D + `/dual-coding-designer`）
- **symptom**: 该 run 的报告行是 `Auto Issues = 0`，但 `gate:G6` 实际 **FAIL**
  （媒体计划推荐了 4 张图示，却没有产出对应 SVG 资产）。
  两层结论互不相容，读报告的人会以为这条 run 完全干净
- **root_cause**: 自动检查（case 期望）与门禁（G1–G8）是两条独立链路，
  报告表格只渲染前者；案例期望不一定覆盖门禁关心的点
- **skill**: `benchmark-report`
- **artifact**: `pebs/benchmark/report.py`
- **fix**: per-case 表增加 `Gate FAIL/Review` 列（`FAIL/NEEDS_REVIEW` 计数），
  模式对比表同步；报告中因此能一眼看到"自动 0 问题但有门禁失败"
- **留待观察（不是本次修复）**: 外部媒体 Skill 可以产出"推荐图示"的 media_plan，
  而计划里没有 diagram 节点 → G6 正确地报 FAIL。是否应由 Planner 在
  media_plan 推荐图示时自动纳入 diagram 步骤，属于路由/计划策略问题，
  与 §3（不因单个课程重写固定 Pipeline）一并留到 M6.5/M7 评估
- **regression_test**: `tests/test_benchmark_scaffold.py::test_report_shows_gate_failures_alongside_automatic_issues`

## 2026-09-20 — 外部 Skill 替换内置步骤会被判"缺少必需步骤"，A/B 平白多一条错（CHECKS §46）

- **date**: 2026-09-20
- **task**: M6.4 §17 A/B（D + `/backwards-design-unit-planner`）
- **symptom**: 真实 run `20260920-151226-D-dynamic` 里外部 Skill 成功产出了
  `learning_design:sec1`，但自动检查仍报
  `PLANNING 缺少必需步骤：learning_design`——因为期望里的 `must_include_steps`
  写的是**内置步骤名**，而这一步已被外部 Skill 取代
- **root_cause**: `plan_checks()` 把"能力"与"内置实现"绑死：
  `must_include_steps` 只比对 `node.steps` / `node.skill` 字面值，
  没有考虑"某个 Skill 产出了该步骤对应的 artifact 类型"
- **skill**: `benchmark-checks`
- **artifact**: `pebs/benchmark/checks.py`
- **fix**: 用 registry 建立 `step → produces` 映射（`_step_artifact_types()`），
  包含类期望按"能力是否在"判定；**排除类期望只看本轮执行节点**，
  以免把"复用既有讲稿"（E 审阅、G 只做 PPT）误判成重新执行了 steps
- **实测影响**: 用 `tools/reevaluate_checks.py` 重放该 run，问题数 3 → 2，
  仅剩 `ROUTING research_need=DEEP，期望 LITERATURE`（路由判断，待人工）
  与一条真实 `SAFETY` 命中
- **regression_test**: `tests/test_benchmark_scaffold.py::test_plan_step_expectations_accept_external_skill_equivalents`

## 2026-09-20 — §69 降级只有判定函数，没有基于已记录数据的候选清单（SKILL §69）

- **date**: 2026-09-20
- **task**: M6 §68/§69 Skill Promotion / Demotion
- **symptom**: `demotion_decision()` 存在且被测试覆盖，但 `benchmark --promotions`
  只输出晋升候选与"已禁用"历史，从未用 `registry/performance.json` 里已有的
  schema 失败数据去找出**该降级的 Skill**——§69 的"schema 不稳定 → DISABLED"没有落点
- **root_cause**: 策略函数与数据源（performance registry）之间没有聚合层
- **skill**: `benchmark-report`
- **artifact**: `pebs/benchmark/performance.py`
- **fix**: 新增 `review_demotions()`：对 runs ≥ 3 且
  `schema_failure_rate > 0.3` 的 Skill 给出降级候选（触发原因、建议动作），
  并入 `--promotions` 输出的 `demotion_candidates`；仍然只报告，
  不改注册表（§47：M6 不允许历史表现影响路由/装配）
- **regression_test**: `tests/test_benchmark_scaffold.py::test_review_demotions_flags_schema_instability`

## 2026-09-20 — Direct 基线产物进不了教师材料包，三模式对比少一条腿（EVALUATION §28）

- **date**: 2026-09-20
- **task**: M6 Acceptance 4/5 的人工评分准备
- **symptom**: `export_kit` 只处理有项目 Store 的 run；`direct_codex` 基线不建 Engine、
  没有 Store，于是它的产物（`run_dir/direct_output.md`）从不进入
  `evaluation_kit/`——教师根本无法给 Direct 基线打分，
  「Direct / Builtin / Dynamic」在**人工评分**维度上只有两条腿
- **root_cause**: `export_kit` 把"打开 Store 失败"当成"跳过该 run"
  （`except: continue`），而 Direct 基线恰恰永远打不开 Store
- **skill**: `human-evaluation`
- **artifact**: `pebs/benchmark/evaluation.py`
- **fix**: Store 打不开时不再跳过；无 Store 产物且存在 `run_dir/direct_output.md` 时，
  把该文件正文写进 `course.md` 的「direct_output.md（Direct Codex 基线原始输出）」
- **regression_test**: `tests/test_benchmark_evaluation.py::test_evaluation_kit_includes_the_direct_baseline_output`

## 2026-09-20 — 教师材料包里看不到门禁结论与自动问题（EVALUATION §30–§32/§73）

- **date**: 2026-09-20
- **task**: M6 Acceptance 5 的准备（真实教师评分）
- **symptom**: `export_kit` 生成的 `course.md` 只有 run 头信息 + 产物 JSON；
  教师在评分时看不到系统自己认为哪里不合格（门禁结论），也看不到自动检查命中了什么，
  而这些正是 §73 最高优先级指标（Evidence Error Rate）要教师确认/推翻的对象
- **root_cause**: 材料包只拼接产物，没有把 `gate_result`（按门禁逐条列出）与
  `automatic_issues` 一并带上；门禁结果还不在 changeset 里，
  用 `accepted_content` 读会得到空（必须取该产物的最新 revision）
- **skill**: `human-evaluation`
- **artifact**: `pebs/benchmark/evaluation.py`、`benchmarks/reports/evaluation_kit/`
- **fix**: course.md 增加"自动检查命中的问题"表（要求教师在 comment/must_fix 中说明
  真问题还是误报）与"门禁结论"列表（`G1@script:sec1: FAIL — 原因…`）
- **regression_test**: `tests/test_benchmark_evaluation.py::test_evaluation_kit_shows_gates_and_automatic_issues`

## 2026-09-20 — §55 案例红旗检查只有定义、没有调用点（CHECKS §55）

- **date**: 2026-09-20
- **task**: M6 §55 Case Benchmark
- **symptom**: `safety.case_quality_checks()`（编造研究、把结论写成必然、标签化个体、
  虚构机构、缺少 linked_goal、信息量不足）写好了，但**全仓库没有任何调用点**；
  `checks.evaluate()` 只调 plan/routing/content/safety-fixture/animation/ppt/media 七类检查
- **root_cause**: 检查函数与其调用聚合器分离，新增检查时漏接线（与 §64/§65 同类问题）
- **skill**: `benchmark-checks`
- **artifact**: `pebs/benchmark/checks.py`
- **fix**: 新增 `case_checks(store)` 并接入 `evaluate()`；对每个已接受的 `case` 产物运行红旗检查
- **实测影响**: 对 24 个已存 succeeded 项目回放，**0 条命中**——说明现有真实产物
  没有踩这些红旗，但规则此前从未生效、此后开始生效
- **regression_test**: `tests/test_benchmark_scaffold.py::test_case_quality_checks_are_wired_into_evaluate`

## 2026-09-20 — §29 要求"不故意写差"，但 Direct baseline 拿不到用户材料（BENCHMARK §29）

- **date**: 2026-09-20
- **task**: M6 §29 Direct Codex baseline 公平性核查
- **symptom**: `direct_baseline_prompt()` 只注入 `case['request']`；
  PEBS 侧（builtin/dynamic）却能拿到 DOCX 模板与素材文件。
  即 baseline 在"缺模板、缺素材"的条件下作答，比较天然对它不利
- **root_cause**: baseline prompt 只按 case 的 request 拼装，没有复用
  `template_fixture` / `material_fixtures`（虽然 case 里已声明）
- **skill**: `benchmark-runner`
- **artifact**: `pebs/benchmark/runner.py`
- **fix**: baseline prompt 追加模板结构（`parse_template` 摘要）与素材正文
  （`extract_text`，按 `DIRECT_BASELINE_MATERIAL_BUDGET = 12000` 字符上限截断，§60）；
  prompt 依旧对同一 case 完全确定（可复现）
- **影响范围**: 本修复之前记录的 `direct_codex` run（A/B/C）使用的是**较弱**的 baseline
  prompt，因此这些 run 的 Direct 侧被系统性低估；与 PEBS 各模式的差距只能算
  **保守估计**（对 PEBS 有利的方向），不可与修复后的 Direct run 直接混用
- **regression_test**: `tests/test_benchmark_scaffold.py::test_direct_baseline_prompt_receives_the_same_materials_as_pebs`

## 2026-09-20 — 失败的模型调用不记账 / 静态链路 per-step 成本恒为 0（COST §35/§39）

- **date**: 2026-09-20
- **task**: M6.4 真实运行（C + `/backwards-design-unit-planner`）恰逢配额打满
- **symptom**: 外部 Skill 的 `codex exec` 因"usage limit"失败，但
  `run.metrics.model_calls` 把这次真实消耗记成 **0**；同时**静态链路**
  （builtin 基线）的 per-step `model_calls` 永远是 0，因为
  `step_scope` 只在动态执行器里设置
- **root_cause**: 两条路径不一致——`prompt_skill._generate` 是"先记账后调用"，
  而 `pipeline._llm_json` 只在**成功返回后**才 `bump_calls`；
  静态执行循环（`engine.py` 的三处 handler 调用）没有设置线程局部 step 上下文
- **skill**: `default-llm`
- **artifact**: `pebs/pipeline.py`、`pebs/engine.py`
- **fix**: `pipeline._llm_json` 在 `ProviderError` 分支也记账（请求已发出即消耗配额）；
  `engine.py` 三处静态 handler 调用包进 `step_scope(step_id)`
- **regression_test**: `tests/test_pipeline.py::test_failed_provider_call_is_still_counted_as_consumption`

## 2026-09-20 — §35 要求的 Gate FP/FN Rate 没有任何计算口径（METRICS §35）

- **date**: 2026-09-20
- **task**: M6 §35 核心生产指标
- **symptom**: §35 明确要求记录 Gate False Positive Rate 与 Gate False Negative Rate，
  但仓库里没有任何代码/命令能算出这两个数；先前只能靠 ad-hoc 脚本一次性统计
- **root_cause**: 门禁对错只在"用同一套产物重放"时才能判定，而 `gate_result` 一旦写入
  就不再有第二种口径；缺少把"当时结论"与"当前门禁结论"对照的常设工具
- **skill**: `benchmark-report`
- **artifact**: `pebs/benchmark/gates_audit.py`、`pebs/cli.py`、`pebs/benchmark/report.py`、
  `benchmarks/reports/gate_audit.json`
- **fix**: 新增 `python -m pebs.cli benchmark --gate-audit`：用当前门禁重放已存项目，
  输出 `gate_false_negative_rate`（当时 PASS → 重放 FAIL）与
  `gate_false_positive_rate`（当时 FAIL/NEEDS_REVIEW → 重放 PASS），结果写入
  `benchmarks/reports/gate_audit.json`；报告读取该文件渲染"门禁重放审计"小节
- **首次实测**: 175 条判定 / 20 个 run，Gate FN Rate **0.1618**、Gate FP Rate **0.5122**
  （即 5f99507 之前的门禁既漏检也误报）；口径已在报告中标注为"相对当前门禁实现"，
  不是绝对真值
- **regression_test**: `tests/test_benchmark_scaffold.py::test_gate_audit_computes_false_negative_and_positive_rates`、
  `::test_report_renders_gate_audit_section`

## 2026-09-20 — Skill Trace 的 per-skill 产物与调用量全是空的（TRACE §19/§35/§39）

- **date**: 2026-09-20
- **task**: M6 §39 Skill Trace 结构完整性
- **symptom**: trace 里每个 skill 的 `input_artifacts` 恒为 `[]`、
  `output_artifacts` 会把同一产物按 revision 重复列出（`['claims','claims','claims']`）、
  `model_calls` **字段根本不存在**；`registry/performance.json` 的
  `average_model_calls` / `average_latency` 因此永远是 0
- **root_cause**: `build_trace()` 里写了一个空列表 `inputs: list[str] = []` 从未填充；
  outputs 用 `produced_by` 去匹配 `step["step_id"]`，且未去重；
  `steps` 表虽然有 `input_revs/output_revs` 列，但**执行器从不写入**；
  per-skill 调用量没有任何记录点（只有 run 级 `calls_used`）
- **skill**: `external-skill-runtime` / `benchmark-trace`
- **artifact**: `pebs/store.py`、`pebs/runtime/executor.py`、`pebs/runtime/step_context.py`、
  `pebs/runtime/prompt_skill.py`、`pebs/pipeline.py`、`pebs/benchmark/trace.py`、
  `pebs/benchmark/runner.py`
- **fix**: `steps` 增加 `model_calls` 列（`_migrate` 自动补）；
  执行器在节点前后对 `ctx.outputs` 取快照，写入该节点的 input/output revisions
  （三条 runtime 路径通用，失败节点也记）；per-skill 调用量改为
  **线程局部 step 上下文 + `store.bump_calls(step_id=...)` 在调用点精确记账**
  —— 最初用"run 级计数器差分"实现，在并行批次下会把同批节点的调用算进来（测试发现 15 vs 12）
- **regression_test**: `tests/test_benchmark_evaluation.py::test_trace_records_per_skill_inputs_outputs_and_model_calls`
  （断言 input/output 正确、去重、且 per-skill 调用量之和 == run `calls_used`）

## 2026-09-20 — Skill Trace 不带 selection_trace，§63 高级模式永远空白（UI §63/§64）

- **date**: 2026-09-20
- **task**: M6 §63 Skill Trace UI
- **symptom**: Evaluation Tab 高级模式的"Skill 选择理由"表永远为空
- **root_cause**: `trace.build_trace()` 只把 plan 精简成
  `{plan_id, node_count, terminal_outputs, reused_artifacts, degraded}`，
  **没有带上 `selection_trace`**；而 UI 读的是 `data.trace.selection_trace`。
  Planner 里那套"选中理由 + 被拒候选 + 拒选理由"的数据从未进入 trace
- **skill**: `benchmark-trace`
- **artifact**: `pebs/benchmark/trace.py`、`pebs/static/index.html`
- **fix**: trace 的 `plan` 增加 `selection_trace`；UI 兼容读取
  `trace.plan.selection_trace`（旧位置仍可用），并在被拒候选旁显示拒选理由
- **regression_test**: `tests/test_benchmark_evaluation.py::test_trace_carries_selection_trace_for_the_ui`

## 2026-09-20 — 动态链路下门禁读不到产物并静默 PASS（Gate False Negative）（GATES §71-8）

- **date**: 2026-09-20
- **task**: M6.4 真实外部 Skill A/B（D + `/hinge-question-designer`）
- **symptom**: 真实运行为 `gate-runner FAILED：Subagent 契约违规：qa-agent 不允许产出
  artifact 类型：script（契约产出：['gate_result']）`。追查时又发现更严重的问题：
  同一次运行里 G1 对一个 25 字、字数要求 100–200 字的脚本给出 **PASS 且无任何 issue**，
  而在运行外用同一份产物直接调用 `g1_requirements` 却得到 FAIL（"字数 25 不在范围 100–200"）
- **root_cause**: 两个叠加缺陷。
  (1) `RestrictedContext.outputs` 只暴露 `allowed_inputs | produces`，而 gate-runner 的
  `requires` 里没有 `requirements`；`step_gates` 用 `dict(ctx.outputs)` 作为
  `GateContext.overrides`，于是门禁读 `requirements` 时回退到 `store.accepted_content()`
  ——本轮尚未 accept 的 changeset 恒为 None，G1 的字数检查被整体跳过（静默 PASS）。
  受影响的不止 `requirements`：`learning_design`/`teaching_plan`/`assessment`/
  `template_spec` 等同样不在契约内。
  (2) QA 自动修正（AUTO_FIX_GATES = G1/G4/G7）会在门禁节点内 `emit("script:<sec>")`，
  但 gate-runner 只声明了 `produces: [gate_result]`，契约直接拒绝写入
- **skill**: `gate-runner`
- **artifact**: `pebs/pipeline.py`、`pebs/agents/base.py`、`registry/skills.json`
- **fix**:
  (a) `_run_overrides()`：overrides 改为"本轮 run 产出的全部产物（最新 revision）"，
  门禁不再受节点契约过滤影响；用 `emits: [gate_result, script]`（不进 `produces`，
  以免 Planner 以为 gate-runner 能生产 script 而污染 DAG）放行自动修正写入；
  (b) 契约输入纳入 `optional_requires`（已声明的可选输入不该被当成未声明）；
  (c) 预算不足时自动修正降级（保留 FAIL 待人工），而不是把"内容已产出、只剩重试"的
  运行判为 BLOCKED
- **regression_test**: `tests/test_autofix.py::test_dynamic_gate_reads_artifacts_outside_its_contract`、
  `::test_dynamic_auto_fix_survives_the_subagent_contract`
- **影响范围（重要）**: 本修复之前完成的真实 benchmark run（A–I 的全部既有记录）其门禁结论
  **由偏弱的门禁得出**，凡"读契约外产物的检查"（G1 字数/术语、G3 教学法、G6 媒体、
  G7 模板……）都可能被静默跳过。这些 run 的 `run_status`/产物仍然有效，
  但**门禁状态不可与修复后的 run 直接比较**；`benchmark_summary.md` 不区分修复前后，
  比较时需按本节日期切分
- **量化审计（零模型调用）**: `tools/reevaluate_gates.py` 用当前门禁代码重放已存项目。
  对 23 个 succeeded 且保留项目的 run 重放，**17 个 run 的门禁结论发生变化**：
  `G1 PASS→FAIL ×12`（静默漏检，真实缺陷被放过）、`G3 FAIL→PASS ×27` 与
  `G5 FAIL→PASS ×31`（因读不到产物而误报失败）、`G4 NEEDS_REVIEW→FAIL ×5`、
  `G6 NEEDS_REVIEW→FAIL ×3`。即同一根因同时造成**假阴性**与**假阳性**
- **修复后的验证状态**: hermetic（FakeLLM）验证 + 重放审计 + **真实链路验证**
  （2026-09-20 09:16，配额短暂恢复）：`D / dynamic [+external-assessment]`
  （外部 patched skill `hinge-question-designer@hinge-question-designer-pebs-1`，
  provider SHA `6bbbce41…`）一次跑通，run `20260920-091629-D-dynamic`：
  - 外部 Skill 产出声明产物（`assessment:sec1`、`case:sec1:1`）；trace 里 per-skill
    `input_artifacts`/`model_calls` 均为真实值（此前恒为空）
  - **门禁真正生效**：G1/G3/G4/G5 PASS，**G2 = FAIL**（脚本含占位内容且引用了
    `clm_2c6750773f@v1` 状态 UNSUPPORTED 的 Claim），G6 NEEDS_REVIEW
  - 该 run 此前失败过两次（先是契约违规、后是配额）；G2 FAIL 正是 §71-8 期望的结果——
    动态 Skill 不能绕过 Evidence Gate

## 2026-09-20 — provider 的 `_usage` 元数据被 emit 进外部 Skill 产物（RUNTIME §11/§39）

- **date**: 2026-09-20
- **task**: M6.4 真实外部 Skill 运行（D + `/cognitive-load-analyser`）
- **symptom**: 真实运行的 `load_review:sec1` 产物里带着 `"_usage": {}`；
  这是 provider 的用量元数据，却成了教学内容的一部分，会一路进入教师评分材料包
  （`course.md`）与 run.json
- **root_cause**: 内置路径在 `pipeline._llm()` 里已经 `data.pop("_usage", None)`，
  但**外部 Skill 路径没有**（`prompt_skill._generate` 原样返回 provider 结果）；
  同类问题还存在于语义路由（→ `router_result`）、对话意图（→ `patch_plan`）
  与隐私语义复核（→ 隐私判定记录）
- **skill**: `external-skill-runtime` / `semantic-router`
- **artifact**: `pebs/runtime/prompt_skill.py`、`pebs/routing/semantic.py`、
  `pebs/conversation/interpreter.py`、`pebs/pii.py`
- **fix**: 四条会产生产物的 LLM 路径统一剔除 `_usage`（不在 provider 层剔除，
  以免将来做成本核算时无处可取）
- **regression_test**: `tests/test_external_skill_acceptance.py::test_provider_usage_metadata_never_reaches_the_artifact`

## 2026-09-20 — 失败的 run 也会生成教师评分表（EVALUATION §30/§32）

- **date**: 2026-09-20
- **task**: M6.4 教师评分工作表生成
- **symptom**: `B / builtin` 失败后（第 2 次调用即 fail-closed，0 产物、12 条自动问题），
  `benchmark --report` 仍然为它生成了 `B-builtin-human_eval.yaml`；
  已提交的 `A-builtin-human_eval.yaml`（blocked、0 产物）同样存在，
  教师打开后会被要求给一份**不存在的课程**打 14 个维度分
- **root_cause**: `write_worksheets()` 对 `load_runs()` 的每个代表 run 生成工作表，
  没有区分"完成并产出课程"与"失败/阻塞"
- **skill**: `benchmark-report`
- **artifact**: `pebs/benchmark/report.py`、`benchmarks/reports/worksheets/`
- **fix**: 新增 `is_evaluable(run)`：只对 `succeeded` 且真正有产物的 run 生成工作表
  （PEBS 看 `artifact_hashes`，direct_codex 看 `run_dir/direct_output.md`）；
  删除已提交的 A-builtin 工作表；失败 run 的信息保留在报告的 Status / Attempts / Auto Issues 列
- **regression_test**: `tests/test_benchmark_evaluation.py::test_worksheets_are_only_written_for_runs_that_produced_a_course`

## 2026-09-20 — Builtin 基线在 case B 上 fail-closed，Dynamic 可完成（BENCHMARK §17/§28）

- **date**: 2026-09-20
- **task**: M6.4 真实三模式对照（Acceptance 4）
- **symptom**: `B / builtin`（静态 Pipeline 基线）在第 2 次模型调用后失败：
  `claims` 步骤报"Claim 提取结果为空；模型未返回可核验的实证 Claim"，
  后续 18 个步骤全部 BLOCKED，run 记为 failed（12 条自动问题）；
  同一 case 的 `B / dynamic` 第 41 次运行成功提取 3 条 Claim（descriptive / speculative）并完成全链路
- **root_cause**: 不是结构缺陷，而是**模型波动 + fail-closed 契约**：
  `claims` 一次返回空集合即按冻结的 Stage E 证据契约失败（`PCK_REQUIRED_STATUS=SUPPORTED`，
  空契约不允许放行）；动态侧同一 Skill 在成功那次返回了非空 Claim。
  证据：`B / dynamic` 记录为 `1/5`（五次里只成功一次），`A / builtin` 为 `0/5`
- **skill**: `claim-extractor` / `evidence-reviewer`
- **artifact**: `benchmarks/runs/20260920-041319-B-builtin/run.json`、
  `benchmarks/reports/benchmark_summary.md`
- **fix**: 不改代码。**明确不恢复**被上游冻结移除的 `allow_empty_claims` 开关——
  空 Claim 必须 fail closed；此处的正确处置是如实记录基线失败与尝试次数，
  而不是放宽证据门禁（§48/§67 的反面教训）
- **regression_test**: 无（这是基准观测，不是代码缺陷）；对照数据由
  `benchmarks/reports/benchmark_summary.md` 的 `Attempts` 列持续跟踪

## 2026-09-20 — Resolver 的拒选理由为空话，且并列时谎称"分数更高"（ROUTER §64）

- **date**: 2026-09-20
- **task**: M6 §63/§64 Resolver Explainability
- **symptom**: `selection_trace` 里每个被拒候选的理由都是同一句模板
  "更低的 contract/status/domain/risk/cost/regression 综合分"，
  无法回答"为什么没选它"；更严重的是当候选分数**并列**时
  （内置 Skill 与外部 Skill 常常同为 3.45），理由写成
  "综合分 3.45 高于次优 xxx（3.45）"——一个不成立的比较
- **root_cause**: `rank_report()` 只返回总分，没有得分构成；
  `_selection_trace()` 直接用 `selected > runner_up` 的模板描述，
  没有区分 `>` 与 `==`
- **skill**: `skill-resolver`
- **artifact**: `pebs/planner/resolver.py`、`pebs/planner/planner.py`、`pebs/benchmark/report.py`
- **fix**: `_breakdown()` 输出产生分数的各项（产物匹配/状态/领域/风险/成本/回归），
  `rejection_reason()` 给出主要差距与构成；并列时明确写"得分并列；由显式指定或
  registry 顺序决定"；选中理由附带得分构成；报告里被拒候选最多展示 3 个并带理由
- **regression_test**: `tests/test_golden_benchmark_plan.py::test_rejection_reasons_are_honest_about_ties`
  （以及 golden plan 测试新增"被拒候选必须有理由"）

## 2026-09-20 — Schema 修复发生了却不可观测，§35 的 Schema Repair Rate 拿不到数（BENCHMARK §35）

- **date**: 2026-09-20
- **task**: M6 核心生产指标（§35）
- **symptom**: 外部 Skill 第一次输出没通过 Schema 校验时会自动重生成一次
  （`prompt_skill._execute_one`），但这次修复**不留任何痕迹**：
  trace 里只有成功/失败，`performance.json` 只有 `schema_failure_rate`，
  §35 明确要求的 **Schema Repair Rate** 无法计算
- **root_cause**: 修复逻辑写在执行器内部，结果只用于"通过/放弃"，没有回写 step note，
  也没有进入 trace/registry 的字段
- **skill**: `external-skill-runtime` / `benchmark-trace`
- **artifact**: `pebs/runtime/prompt_skill.py`、`pebs/runtime/executor.py`、
  `pebs/benchmark/{trace,metrics,performance,report}.py`
- **fix**: 修复次数记在 plan node 上（不是 executor 实例，避免并行节点互相污染），
  executor 把它追加到 step note（`Schema 修复 N 次`）；trace 解析出 `schema_repairs`，
  `summarize_run` 产出 `schema_repair_rate`，`performance.json` 记录 `schema_repair_rate`，
  §42 模式对比表增加 `Schema Repair Rate` 行
- **regression_test**: `tests/test_external_skill_acceptance.py::test_schema_repair_is_visible_in_trace_and_performance`、
  `tests/test_benchmark_scaffold.py::test_schema_repair_rate_is_recorded_from_step_notes`

## 2026-09-20 — failure taxonomy 只是文档：没有代码引用，类别写错也不会被发现（BENCHMARK §35/§65）

- **date**: 2026-09-20
- **task**: M6 失败分类
- **symptom**: `benchmarks/failure_taxonomy.yaml` 定义了 15 个类别，但只有
  `test_failure_taxonomy_covers_required_categories` 校验"类别齐全"；
  检查器产出的 `kind` 与 taxonomy 之间**没有任何代码关联**，
  报告也没有按类别分布（只有一列 `Auto Issues` 总数），
  Routing Error Rate / Plan Error Rate 无法从报告直接读出
- **root_cause**: taxonomy 被当成文档资产而不是被消费的契约；`evaluate()` 直接用 kind 计数，
  拼错一个 kind（如 `PLANING`）会静默生成一个永不被统计的孤儿类别
- **skill**: `benchmark-checks`
- **artifact**: `pebs/benchmark/checks.py`、`pebs/benchmark/report.py`
- **fix**: `taxonomy_categories()` 从 YAML 读取唯一定义；`evaluate()` 增加
  `by_category` 与 `unknown_categories`；报告增加"失败类别分布（§65）"章节，
  并把不在 taxonomy 里的 kind 显式列出（不静默丢弃）
- **regression_test**: `tests/test_benchmark_scaffold.py::test_failure_taxonomy_categories_match_emitted_issue_kinds`、
  `::test_report_lists_failure_categories_and_surfaces_unknown_ones`

## 2026-09-20 — run 记录里没有 PEBS commit / provider SHA / patch，§41 复现信息不完整（BENCHMARK §41）

- **date**: 2026-09-20
- **task**: M6.4 benchmark 可复现性
- **symptom**: `run.json` 的 `reproducibility` 只有 pebs_version（`0.6.0-dev`）、registry hash、
  rules version、fixture hash；缺少 §41 明确要求的 **PEBS commit** 与 **Skill provider SHA / Skill patches**
- **root_cause**: `pebs_version()` 返回的是包版本号（开发期恒为 `0.6.0-dev`），不能定位代码版本；
  provider SHA / patch 只存在于 trace 的 per-skill 条目里，run 级 `reproducibility` 没带
- **skill**: `benchmark-trace`
- **artifact**: `pebs/benchmark/trace.py`、`pebs/benchmark/runner.py`
- **fix**: 新增 `pebs_commit()`（`PEBS_COMMIT` 环境变量优先，否则 `git rev-parse HEAD`，失败返回空）；
  `reproducibility()` 接受 skill 列表并输出 `skill_provider_shas` / `skill_patches` / `skill_package_sha256`；
  `build_trace()` 增加 `fixture_hashes` 参数，默认 provenance 由 trace 自身计算，
  `run_case()` 直接采用 trace 的（含 skill 版本）而不是另算一份不含 skill 的
- **regression_test**: `tests/test_benchmark_scaffold.py::test_reproducibility_records_commit_and_skill_provenance`

## 2026-09-20 — Acceptance 1/2 只有"隐含"证据：没有断言新增外部 Skill 未改 pipeline.py（INTEGRATION §16/§71-1）

- **date**: 2026-09-20
- **task**: M6 Acceptance 1+2 的独立证明
- **symptom**: `pipeline.py` 里没有任何外部 Skill 的名字，但这只是"碰巧没人加"；
  既有测试只验证外部 Skill 能跑通，没有断言"它没有变成 pipeline 的专用 step"，
  也没有覆盖"下游消费 + Gate 运行"这两段链路
- **root_cause**: 缺少对 `pipeline.STEPS` 注册表的显式断言；
  且 `STEPS` 在 import 时捕获函数对象，只 monkeypatch `pipeline.step_*` 属性是**无效的**
  （第一版测试因此是空转的，必须替换 `STEPS` 本身才有效）
- **skill**: `external-skill-runtime`
- **artifact**: `tests/test_external_skill_acceptance.py`
- **fix**: 用 spy 包住 `pipeline.STEPS` 记录实际走 Legacy Step Adapter 的 step，
  断言 (a) 外部 Skill 不在 `STEPS` 中、(b) 它从未经静态 pipeline 执行、
  (c) 内置 Skill 仍经由既有 step 复用、(d) 其产物被下游节点消费、(e) Gate 在动态链路上运行
- **regression_test**: `tests/test_external_skill_acceptance.py::test_acceptance_1_and_2_external_skill_needs_no_pipeline_change`

## 2026-09-20 — 报告只有 per-case 明细，缺 §42 要求的 Metric × 模式对比表（BENCHMARK §42）

- **date**: 2026-09-20
- **task**: M6.4 benchmark 报告
- **symptom**: §42 要求报告至少给出 `Metric × Direct Codex / Builtin / Dynamic` 的对比表，
  实际只有 per-case 明细行；"Dynamic 是否优于 Builtin/Direct" 需要人工跨行累加才能回答
- **root_cause**: `render_markdown()` 只渲染 case×variant 明细，没有把 §46 的实验变体
  （`dynamic [+external-media]`）归回基础模式做汇总
- **skill**: `benchmark-report`
- **artifact**: `pebs/benchmark/report.py`
- **fix**: 新增 `mode_comparison()` / `render_mode_comparison()`：按基础模式汇总，
  Human Score 与 Edit Ratio 取 case 均值（避免调用量大的 case 压过其他 case），
  计数类指标求和；结果同时写入 `benchmark_summary.json` 的 `mode_comparison` 字段
- **regression_test**: `tests/test_benchmark_scaffold.py::test_report_builds_metric_by_mode_comparison_table`

## 2026-09-20 — 教师评分写进了 Store，却从未回到报告 / 也从未绑定 Skill 版本（EVALUATION §33/§40/§42）

- **date**: 2026-09-20
- **task**: M6.3/M6.4 人工评价闭环（Acceptance 5/6）
- **symptom**: 提交教师评分后（CLI `--submit-eval` 或 `POST /evaluation`），
  `benchmark_summary.md` 的 Human Score / Edit Ratio / Evidence Errors / Routing Errors 列
  仍然全部是 `None`；`registry/performance.json` 里的 `human_score` 也一直是空的
- **root_cause**: 两处断链。
  (1) 评分以 Artifact 落在**项目 Store**（`human_eval`），而报告只读 `benchmarks/runs/*/run.json`，
  从不回读 Store —— 指标列永远拿不到数据，M6 §73 的前三项核心指标实际不可观测；
  (2) `evaluation.update_performance()`（§40 要求的 skill 版本绑定）**只在测试里被调用**，
  真实提交路径（CLI `--submit-eval`、`POST /api/projects/<id>/evaluation`）从不触发它，
  所以 §19/§68 的 promotion/demotion 判定拿不到人工分
- **skill**: `benchmark-report` / `human-evaluation`
- **artifact**: `pebs/benchmark/report.py`、`pebs/benchmark/evaluation.py`
- **fix**: `summarize()` 通过 `config.project_dir(project_id)` 回读 `human_eval` Artifact 并按 run_id 绑定；
  评分指向另一版产物时标记 `human_eval_stale`（显示但不静默丢弃）；
  `evaluation.record()` 在落库后自动调用 `update_performance()` 绑定 skill 版本
- **regression_test**: `tests/test_benchmark_evaluation.py::test_report_reads_teacher_scores_back_from_the_project`、
  `::test_human_eval_is_recorded_as_artifact_and_updates_performance`（改为断言 record() 自身完成绑定）

## 2026-09-20 — 带 BOM 的 run.json 让该 run 从报告中静默消失（BENCHMARK §41）

- **date**: 2026-09-20
- **task**: M6.4 benchmark 报告生成
- **symptom**: `benchmarks/runs/20260918-190433-B-dynamic/run.json`（`external-media-B` 实验，
  interrupted）在报告中完全不存在，`B` 的 external-media 变体凭空少了一行
- **root_cause**: 该文件带 UTF-8 BOM（Windows 工具写入），`load_runs()` 用 `encoding="utf-8"` 读取时
  `json.loads` 抛 `JSONDecodeError`，被 `except JSONDecodeError: continue` 静默吞掉
- **skill**: `benchmark-report`
- **artifact**: `pebs/benchmark/report.py`
- **fix**: 改用 `encoding="utf-8-sig"`（无 BOM 时行为不变），并把 `OSError` 一并计入跳过
- **regression_test**: `tests/test_benchmark_evaluation.py::test_run_json_with_utf8_bom_is_still_loaded`

## 2026-09-20 — `benchmark --report` 会覆盖教师已填写的工作表 / 代表 run 漂移 / 实验变体撞名（EVALUATION §30/§32/§41/§46）

- **date**: 2026-09-20
- **task**: M6.3/M6.4 教师评分工作表（Acceptance 5 的外部输入）
- **symptom**: 跑一次 `python -m pebs.cli benchmark --report` 之后，`benchmarks/reports/worksheets/D-dynamic-human_eval.yaml`
  的 `run` 绑定被改写（succeeded → failed，21 个产物 → 2 个）；任何已填的 14 维评分会被静默清空
- **root_cause**: 三个叠加缺陷。(1) `write_worksheets()` 无条件重写每个 `(case, mode)` 的工作表，
  教师填写内容是**不可再生的外部输入**，却被当成可重生成的派生物；
  (2) `load_runs()` 用 run.json 的 **文件 mtime** 判断"最新成功 run"，而复评工具
  （`tools/reevaluate_checks.py`）会重写旧 run.json，mtime 一变代表 run 就漂移；
  (3) 工作表文件名不含 `experiment`，§46 的实验变体（`D-dynamic-external-assessment`）
  直接覆盖该 case 的主工作表
- **skill**: `benchmark-report`
- **artifact**: `pebs/benchmark/report.py`、`benchmarks/reports/worksheets/`
- **fix**: `write_worksheets(preserve_filled=True)` 遇到已填写（reviewer/comment/scores/edits 任一非空）
  的工作表直接跳过；文件名带上 experiment（`<case>-<mode>-<experiment>-human_eval.yaml`）；
  `load_runs()` 改用 run 目录名里的时间戳排序，mtime 只作兜底
- **regression_test**: `tests/test_benchmark_evaluation.py::test_worksheet_regeneration_never_overwrites_teacher_scores`、
  `::test_representative_run_uses_run_timestamp_not_file_mtime`

## 2026-09-19 — 导入限制只覆盖文件数与体积，缺文档级/解压级防护（SECURITY §59）

- **date**: 2026-09-19
- **task**: M6 Security Track（§59：Stage C 的导入限制合并后必须独立成项）
- **symptom**: Stage C 只检查文件数/单文件体积/总量；DOCX 正文字数、PDF 页数、模板表格数、解压炸弹（zip 压缩比/解压总量）均无上限；损坏文档抛原始异常
- **root_cause**: 限制只做在"字节入口"，没有做在"解析入口"
- **skill**: `template-parser`
- **artifact**: `pebs/template_parse.py`、`config/rules.yaml`
- **fix**: 新增 `max_docx_chars` / `max_pdf_pages` / `max_template_tables` / `max_decompression_ratio` /
  `max_decompressed_mib`；`check_archive_safety()` 只读 zip 中央目录声明的大小即可拒绝炸弹；
  损坏 zip → 明确的 ParseError；上传文件名只取 basename（路径穿越）；全部**显式拒绝，不静默截断**
- **regression_test**: `tests/test_document_security_limits.py`（8 项：炸弹、损坏文档、DOCX 字数、
  模板表格、PDF 页数、上传文件名穿越、正常文件通过与既有 Stage C 限制）

## 2026-09-19 — Codex 配额耗尽：真实运行暂时不可用（RUNTIME/COST）

- **date**: 2026-09-19
- **task**: §17/§46 的第三个 A/B（case D + `/hinge-question-designer`）
- **symptom**: `codex exec 失败 rc=1: You've hit your usage limit … try again at Sep 23rd, 2026 5:48 PM`；case-designer / hinge-question-designer / lesson-designer 全部 FAILED
- **root_cause**: 本机 Codex 账号配额用尽（外部约束）
- **skill**: n/a
- **artifact**: `benchmarks/runs/20260919-222735-D-dynamic/run.json`（如实记录失败原因，未伪造产物、未静默降级）
- **fix（在配额之外仍可推进的部分）**: 新增零模型调用的 §46 对照 `benchmark --plan-only`，用确定性路由 + Planner 输出
  `benchmarks/reports/skill_selection.md`（Builtin vs 显式外部 Skill 的 DAG 与选择理由）；配额恢复后按同一 case×mode×experiment 约定补跑真实对照
- **regression_test**: `tests/test_benchmark_scenarios.py::test_plan_only_selection_experiment_swaps_the_producer`

## 2026-09-19 — 安全基准把"被审阅对象"误判为违规：139 → 0（Gate False Positive）

- **date**: 2026-09-19
- **task**: Golden Benchmark H（对 5 条对抗性说法做安全与证据审查）
- **symptom**: 同一次成功运行报出 139 条 SAFETY/EVIDENCE/PEDAGOGY 问题；被对照的原文、练习选项、审阅引文全部被当成"产物在主张该说法"
- **root_cause**: 四类误报叠加——(1) 扫描了请求/计划/Claim 登记表等**输入与元数据**产物；
  (2) 选择题 `options`/`distractors`（本就是故意错误的待判定项）未剔除，且产物内容既有 JSON 文本（双引号）
  又有 Python mapping repr（单引号），只处理了前者；
  (3) 引号内反例、否定语境之外缺少"练习/审阅引导语"（练习/说明/圈出/审查/原句…）判定；
  (4) mechanism_overclaim 的限定语词汇过窄，只承认一种措辞。
- **skill**: n/a（benchmark 检查器）
- **artifact**: `pebs/benchmark/checks.py`、`benchmarks/fixtures/safety/adversarial.yaml`
- **fix**: 只扫描内容产物；选项/干扰项字段先擦除（兼容两种引号）；引号/否定/练习/审阅语境视为引用；
  限定语词汇扩充为研究限制/不确定/不能替代/辅助/过强
- **regression_test**: `tests/test_benchmark_scaffold.py`（选项擦除双引号形态、练习引导语、引号反例）、
  `tests/test_benchmark_safety.py`；用 `tools/reevaluate_checks.py H <project>` 对同一份已存产物复评为 0 问题

## 2026-09-19 — 审阅类任务从"学习设计"提取 Claim，导致空证据阻塞全流程（EVIDENCE）

- **date**: 2026-09-19
- **task**: Golden Benchmark E（已有讲稿审阅，不要重写）
- **symptom**: `claim-extractor FAILED: Claim 提取结果为空`，evidence/gates 级联阻塞；被审讲稿就在材料里，但模型说"没有可核验的实证性 Claim"
- **root_cause**: `_claims_prompt` 只给"学习设计 + 材料摘录"。audit-only 任务没有新学习设计，被审对象是已有讲稿/论文，模型看不到待审内容
- **skill**: `claim-extractor`
- **artifact**: `pebs/pipeline.py`
- **fix**: 已有 script 时把分节正文（截断 4000 字）加入 Claim 提取 prompt，并注明"审阅任务的事实性 Claim 必须来自这里"
- **regression_test**: `tests/test_claims_extraction_guard.py`、`tests/test_qualify.py`；E 真实运行（script-writer 复用、无 pptx/storyboard、gates 执行）

## 2026-09-19 — 长文步骤在 240s 超时（RUNTIME）

- **date**: 2026-09-19
- **task**: Golden Benchmark F（在四节托育课程上做局部修改）
- **symptom**: 基线课程运行中 `lesson-designer FAILED: lesson_plan: codex exec 超时`、`case-designer FAILED: case: codex exec 超时`，级联阻塞脚本与门禁
- **root_cause**: `config/providers.yaml` 的 `llm.timeout_seconds=240` 对四节课程的长文产物偏紧（单节教案/案例在低 reasoning effort 下也可能超过 4 分钟）
- **skill**: `lesson-designer` / `case-designer`
- **artifact**: `config/providers.yaml`
- **fix**: 单次 `codex exec` 上限提高到 480s；超时仍记为 FAILED（不静默降级、不伪造产物）
- **regression_test**: 既有超时/失败路径测试（`tests/test_provider_codex.py`、`tests/test_provider_fallback.py`）；四节课程运行复测

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
