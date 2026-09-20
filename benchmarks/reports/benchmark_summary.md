# M6 Benchmark Summary

生成时间：2026-09-20T20:15:13；run 数（每 case×mode 取最新）：26

| Case | Variant | Status | Attempts | Human Score | Edit Ratio | Evidence Errors | Routing Errors | Plan Errors | Model Calls | Runtime(s) | Auto Issues | Gate FAIL/Review |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | builtin | blocked | 0/5 | None | None | None | None | None | 12.0 | 348.53 | 11.0 | 0/0 |
| A | direct_codex | succeeded | 1/1 | None | None | None | None | None | 1.0 | 167.42 | 0.0 | 0/0 |
| A | dynamic | succeeded | 1/8 | None | None | None | None | None | 22.0 | 770.7 | 3.0 | 6.0/3.0 |
| A | dynamic [+external-media-A2] | succeeded | 1/1 | None | None | None | None | None | 22.0 | 1012.21 | 3.0 | 6.0/3.0 |
| A | dynamic [+external-media-A] | failed | 0/1 | None | None | None | None | None | 25.0 | 1466.48 | 3.0 | 0/0 |
| A | dynamic [+external-media] | succeeded | 1/1 | None | None | None | None | None | 28.0 | 1020.85 | 3.0 | 6.0/3.0 |
| B | builtin | failed | 0/1 | None | None | None | None | None | 2.0 | 114.26 | 12.0 | 0/0 |
| B | direct_codex | succeeded | 1/1 | None | None | None | None | None | 1.0 | 210.04 | 0.0 | 0/0 |
| B | dynamic | succeeded | 1/5 | None | None | None | None | None | 45.0 | 1235.35 | 1.0 | 0/1.0 |
| B | dynamic [+empty-claims-policy] | blocked | 0/1 | None | None | None | None | None | 33.0 | 925.75 | 3.0 | 0/0 |
| B | dynamic [+external-media-B] | interrupted | 0/1 | None | None | None | None | None | 40.0 | 7826.67 | 3.0 | 0/0 |
| C | builtin | succeeded | 1/2 | None | None | None | None | None | 47.0 | 2569.12 | 2.0 | 0/4.0 |
| C | direct_codex | succeeded | 1/1 | None | None | None | None | None | 1.0 | 190.24 | 0.0 | 0/0 |
| C | dynamic | succeeded | 3/5 | None | None | None | None | None | 48.0 | 1868.79 | 0.0 | 10.0/4.0 |
| C | dynamic [+external-backwards-design] | blocked | 0/2 | None | None | None | None | None | 90.0 | 2276.17 | 5.0 | 0/0 |
| D | builtin | failed | 0/1 | None | None | None | None | None | 15.0 | 775.31 | 0.0 | 0/0 |
| D | dynamic | succeeded | 2/3 | None | None | None | None | None | 10.0 | 371.08 | 1.0 | 2.0/1.0 |
| D | dynamic [+external-assessment] | succeeded | 1/4 | None | None | None | None | None | 22.0 | 717.01 | 0.0 | 1.0/1.0 |
| D | dynamic [+external-backwards-design] | succeeded | 1/1 | None | None | None | None | None | 19.0 | 602.48 | 3.0 | 0/1.0 |
| D | dynamic [+external-dual-coding] | succeeded | 1/1 | None | None | None | None | None | 26.0 | 772.31 | 0.0 | 1.0/0 |
| D | dynamic [+external-load] | succeeded | 1/1 | None | None | None | None | None | 17.0 | 720.33 | 0.0 | 3.0/1.0 |
| E | dynamic | succeeded | 2/3 | None | None | None | None | None | 26.0 | 678.8 | 0.0 | 2.0/1.0 |
| F | scenario | succeeded | 2/2 | None | None | None | None | None | 5.0 | 1964.68 | 0.0 | 0/0 |
| G | scenario | succeeded | 1/1 | None | None | None | None | None | 9.0 | 2354.22 | 0.0 | 0/0 |
| H | dynamic | succeeded | 6/6 | None | None | None | None | None | 32.0 | 1570.97 | 3.0 | 3.0/2.0 |
| I | dynamic | succeeded | 1/1 | None | None | None | None | None | 7.0 | 361.02 | 0.0 | 0/1.0 |

## 模式对比（§42：Metric × Direct Codex / Builtin / Dynamic）

| Metric | direct_codex | builtin | dynamic | scenario |
| --- | ---: | ---: | ---: | ---: |
| Human Score（1–5 均值） | — | — | — | — |
| Teacher Edit Ratio（均值） | — | — | — | — |
| Evidence Errors（合计） | — | — | — | — |
| Routing Errors（合计） | — | — | — | — |
| Plan Errors（合计） | — | — | — | — |
| Skill Failure Rate（均值） | — | 0.022 | 0.01 | — |
| Schema Repair Rate（均值） | — | 0.0 | 0.0 | — |
| Model Calls（合计） | 3.0 | 76.0 | 512.0 | 14.0 |
| Runtime(s)（合计） | 567.7 | 3807.22 | 24196.97 | 4318.9 |
| Succeeded / Attempts | 3.0 / 3.0 | 1.0 / 9.0 | 22.0 / 45.0 | 3.0 / 3.0 |


## 失败类别分布（§65 failure taxonomy；仅统计代表 run 的自动问题）

| 类别 | 次数 |
| --- | ---: |
| CONTENT | 16 |
| PLANNING | 13 |
| ROUTING | 13 |
| SAFETY | 11 |
| EVIDENCE | 3 |


## 门禁重放审计（§35 Gate FP/FN；以当前门禁实现为准，非绝对真值）

- 重放覆盖：182 条 gate 判定 / 22 个 run；9 个 run 结论发生变化
- Gate False Negative Rate（当时 PASS，重放 FAIL）：0.1528（11 条）
- Gate False Positive Rate（当时 FAIL/NEEDS_REVIEW，重放 PASS）：0.5（42 条）
- 口径说明：重放口径：以当前门禁实现为准衡量历史 run 的门禁结论漂移，不是绝对真值


## 质量指标（§53/§54/§58；频度与分布，人工评分参考，不设自动阈值）

| Case | Variant | 机械连接词/千字 | 长句比例 | 口语标记比例 | 密集页比例 | 缺 Teacher Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | dynamic | 0.99 | — | — | — | — |
| A | dynamic [+external-media] | 0.49 | — | — | — | — |
| A | dynamic [+external-media-A2] | 0.81 | — | — | — | — |
| B | dynamic | — | — | — | 0.0 | 0 |
| C | builtin | 0.66 | 0.27 | 0.046 | 0.0 | 0 |
| C | dynamic | 1.13 | — | — | — | — |
| D | dynamic | 0.0 | — | — | — | — |
| D | dynamic [+external-assessment] | 0.0 | — | — | — | — |
| D | dynamic [+external-backwards-design] | 0.0 | — | — | — | — |
| D | dynamic [+external-dual-coding] | 0.0 | — | — | — | — |
| D | dynamic [+external-load] | 0.0 | — | — | — | — |
| E | dynamic | 17.62 | — | — | — | — |
| H | dynamic | 0.0 | — | — | — | — |
| I | dynamic | — | — | — | 0.0 | 0 |


## Skill Performance Registry（§19/§40；内部 skills 全部记录）

| Skill | Version | Runs | Success | Schema Fail | Human | Edit Ratio | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| animation-gate | 0.1.0 | 4 | 0.5 | 0.0 | None | None | EXPERIMENTAL |
| assessment-designer | 0.1.0 | 25 | 0.8 | 0.0 | None | None | EXPERIMENTAL |
| backwards-design-unit-planner | 6bbbce418f82 | 3 | 0.6667 | 0.0 | None | None | EXPERIMENTAL |
| case-designer | 0.1.0 | 24 | 0.7083 | 0.0 | None | None | EXPERIMENTAL |
| claim-extractor | 0.1.0 | 39 | 0.8462 | 0.0 | None | None | EXPERIMENTAL |
| cognitive-load-analyser | 6bbbce418f82 | 1 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| diagram-designer | 0.1.0 | 11 | 0.4545 | 0.0 | None | None | EXPERIMENTAL |
| docx-exporter | 0.1.0 | 20 | 0.6 | 0.0 | None | None | EXPERIMENTAL |
| dual-coding-designer | 6bbbce418f82 | 4 | 0.75 | 0.25 | None | None | EXPERIMENTAL |
| evidence-indexer | 0.1.0 | 11 | 0.4545 | 0.0 | None | None | EXPERIMENTAL |
| evidence-reviewer | 0.1.0 | 43 | 0.814 | 0.0 | None | None | EXPERIMENTAL |
| gate-runner | 0.1.0 | 32 | 0.625 | 0.0 | None | None | EXPERIMENTAL |
| hinge-question-designer | 6bbbce418f82 | 4 | 0.5 | 0.0 | None | None | EXPERIMENTAL |
| learning-designer | 0.1.0 | 36 | 0.9722 | 0.0 | None | None | EXPERIMENTAL |
| lesson-designer | 0.1.0 | 35 | 0.6857 | 0.0 | None | None | EXPERIMENTAL |
| load-reviewer | 0.1.0 | 4 | 0.75 | 0.0 | None | None | EXPERIMENTAL |
| media-router | 0.1.0 | 10 | 0.5 | 0.0 | None | None | EXPERIMENTAL |
| pck-developer | 0.1.0 | 36 | 0.75 | 0.0 | None | None | EXPERIMENTAL |
| presentation-composer | 0.1.0 | 11 | 0.3636 | 0.0 | None | None | EXPERIMENTAL |
| presentation-planner | 0.1.0 | 11 | 0.3636 | 0.0 | None | None | EXPERIMENTAL |
| preview-builder | 0.1.0 | 20 | 0.85 | 0.0 | None | None | EXPERIMENTAL |
| requirements-builder | 0.1.0 | 39 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| script-writer | 0.1.0 | 33 | 0.7273 | 0.0 | None | None | EXPERIMENTAL |
| template-parser | 0.1.0 | 39 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| worksheet-designer | 0.1.0 | 4 | 0.75 | 0.0 | None | None | EXPERIMENTAL |

