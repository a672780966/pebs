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
