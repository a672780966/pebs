# M6 Benchmark Summary

生成时间：2026-09-20T02:39:38；run 数（每 case×mode 取最新）：18

| Case | Variant | Status | Attempts | Human Score | Edit Ratio | Evidence Errors | Routing Errors | Plan Errors | Model Calls | Runtime(s) | Auto Issues |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | builtin | blocked | 0/5 | None | None | None | None | None | 12.0 | 348.53 | 11.0 |
| A | direct_codex | succeeded | 1/1 | None | None | None | None | None | 1.0 | 167.42 | 0.0 |
| A | dynamic | succeeded | 1/8 | None | None | None | None | None | 22.0 | 770.7 | 3.0 |
| A | dynamic [+external-media-A2] | succeeded | 1/1 | None | None | None | None | None | 22.0 | 1012.21 | 3.0 |
| A | dynamic [+external-media-A] | failed | 0/1 | None | None | None | None | None | 25.0 | 1466.48 | 3.0 |
| A | dynamic [+external-media] | succeeded | 1/1 | None | None | None | None | None | 28.0 | 1020.85 | 3.0 |
| B | direct_codex | succeeded | 1/1 | None | None | None | None | None | 1.0 | 210.04 | 0.0 |
| B | dynamic | succeeded | 1/5 | None | None | None | None | None | 45.0 | 1235.35 | 1.0 |
| B | dynamic [+empty-claims-policy] | blocked | 0/1 | None | None | None | None | None | 33.0 | 925.75 | 3.0 |
| B | dynamic [+external-media-B] | interrupted | 0/1 | None | None | None | None | None | 40.0 | 7826.67 | 3.0 |
| C | dynamic | succeeded | 3/5 | None | None | None | None | None | 48.0 | 1868.79 | 0.0 |
| D | dynamic | succeeded | 2/3 | None | None | None | None | None | 10.0 | 371.08 | 1.0 |
| D | dynamic [+external-assessment] | failed | 0/1 | None | None | None | None | None | 16.0 | 951.75 | 0.0 |
| E | dynamic | succeeded | 2/3 | None | None | None | None | None | 26.0 | 678.8 | 0.0 |
| F | scenario | succeeded | 2/2 | None | None | None | None | None | 5.0 | 1964.68 | 0.0 |
| G | scenario | succeeded | 1/1 | None | None | None | None | None | 9.0 | 2354.22 | 0.0 |
| H | dynamic | succeeded | 6/6 | None | None | None | None | None | 32.0 | 1570.97 | 3.0 |
| I | dynamic | succeeded | 1/1 | None | None | None | None | None | 7.0 | 361.02 | 0.0 |

## 模式对比（§42：Metric × Direct Codex / Builtin / Dynamic）

| Metric | direct_codex | builtin | dynamic | scenario |
| --- | ---: | ---: | ---: | ---: |
| Human Score（1–5 均值） | — | — | — | — |
| Teacher Edit Ratio（均值） | — | — | — | — |
| Evidence Errors（合计） | — | — | — | — |
| Routing Errors（合计） | — | — | — | — |
| Plan Errors（合计） | — | — | — | — |
| Model Calls（合计） | 2.0 | 12.0 | 354.0 | 14.0 |
| Runtime(s)（合计） | 377.46 | 348.53 | 20060.42 | 4318.9 |
| Succeeded / Attempts | 2.0 / 2.0 | 0 / 5.0 | 18.0 / 37.0 | 3.0 / 3.0 |


## 失败类别分布（§65 failure taxonomy；仅统计代表 run 的自动问题）

| 类别 | 次数 |
| --- | ---: |
| CONTENT | 10 |
| SAFETY | 10 |
| ROUTING | 6 |
| PLANNING | 5 |
| EVIDENCE | 3 |


## 质量指标（§53/§54/§58；频度与分布，人工评分参考，不设自动阈值）

| Case | Variant | 机械连接词/千字 | 长句比例 | 口语标记比例 | 密集页比例 | 缺 Teacher Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | dynamic | 0.99 | — | — | — | — |
| A | dynamic [+external-media] | 0.49 | — | — | — | — |
| A | dynamic [+external-media-A2] | 0.81 | — | — | — | — |
| B | dynamic | — | — | — | 0.0 | 0 |
| C | dynamic | 1.13 | — | — | — | — |
| D | dynamic | 0.0 | — | — | — | — |
| E | dynamic | 17.62 | — | — | — | — |
| H | dynamic | 0.0 | — | — | — | — |
| I | dynamic | — | — | — | 0.0 | 0 |


## Skill Performance Registry（§19/§40；内部 skills 全部记录）

| Skill | Version | Runs | Success | Schema Fail | Human | Edit Ratio | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| assessment-designer | 0.1.0 | 16 | 0.875 | 0.0 | None | None | EXPERIMENTAL |
| case-designer | 0.1.0 | 12 | 0.75 | 0.0 | None | None | EXPERIMENTAL |
| claim-extractor | 0.1.0 | 27 | 0.8889 | 0.0 | None | None | EXPERIMENTAL |
| diagram-designer | 0.1.0 | 7 | 0.2857 | 0.0 | None | None | EXPERIMENTAL |
| docx-exporter | 0.1.0 | 16 | 0.625 | 0.0 | None | None | EXPERIMENTAL |
| dual-coding-designer | 6bbbce418f82 | 3 | 0.6667 | 0.3333 | None | None | EXPERIMENTAL |
| evidence-indexer | 0.1.0 | 7 | 0.2857 | 0.0 | None | None | EXPERIMENTAL |
| evidence-reviewer | 0.1.0 | 27 | 0.8519 | 0.0 | None | None | EXPERIMENTAL |
| gate-runner | 0.1.0 | 20 | 0.7 | 0.0 | None | None | EXPERIMENTAL |
| hinge-question-designer | 6bbbce418f82 | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| learning-designer | 0.1.0 | 27 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| lesson-designer | 0.1.0 | 23 | 0.6957 | 0.0 | None | None | EXPERIMENTAL |
| media-router | 0.1.0 | 6 | 0.3333 | 0.0 | None | None | EXPERIMENTAL |
| pck-developer | 0.1.0 | 24 | 0.75 | 0.0 | None | None | EXPERIMENTAL |
| presentation-composer | 0.1.0 | 7 | 0.2857 | 0.0 | None | None | EXPERIMENTAL |
| presentation-planner | 0.1.0 | 7 | 0.2857 | 0.0 | None | None | EXPERIMENTAL |
| preview-builder | 0.1.0 | 16 | 0.9375 | 0.0 | None | None | EXPERIMENTAL |
| requirements-builder | 0.1.0 | 27 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| script-writer | 0.1.0 | 21 | 0.7619 | 0.0 | None | None | EXPERIMENTAL |
| template-parser | 0.1.0 | 27 | 1.0 | 0.0 | None | None | EXPERIMENTAL |

