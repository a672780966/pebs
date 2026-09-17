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

## 2026-09-17 — CI 曾长期为红（M5.1–M5.3）

- **date**: 2026-09-17
- **task**: M5 CI
- **symptom**: GitHub Actions 在 ubuntu/windows 全部失败，本地却全绿
- **root_cause**: `requirements.txt` 未声明 `python-pptx`、`python-multipart`（本地环境已装）；同秒创建的 changeset 排序不稳定（Linux runner 上复现）
- **skill**: n/a
- **artifact**: `requirements.txt`；`pebs/store.py` `list_changesets`
- **fix**: 补齐依赖；`ORDER BY created_at DESC, rowid DESC` 加确定性 tiebreaker
- **regression_test**: `tests/test_store.py::test_changeset_listing_is_newest_first_within_the_same_second`（CI run 35230946294 全绿）
