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

## 2026-09-17 — CI 曾长期为红（M5.1–M5.3）


- **date**: 2026-09-17
- **task**: M5 CI
- **symptom**: GitHub Actions 在 ubuntu/windows 全部失败，本地却全绿
- **root_cause**: `requirements.txt` 未声明 `python-pptx`、`python-multipart`（本地环境已装）；同秒创建的 changeset 排序不稳定（Linux runner 上复现）
- **skill**: n/a
- **artifact**: `requirements.txt`；`pebs/store.py` `list_changesets`
- **fix**: 补齐依赖；`ORDER BY created_at DESC, rowid DESC` 加确定性 tiebreaker
- **regression_test**: `tests/test_store.py::test_changeset_listing_is_newest_first_within_the_same_second`（CI run 35230946294 全绿）
