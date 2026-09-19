# M6 Benchmark Summary

生成时间：2026-09-19T09:03:59；run 数（每 case×mode 取最新）：14

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
| B | dynamic [+external-media-B] | running | 0/1 | None | None | None | None | None | 40.0 | 7826.67 | 3.0 |
| C | dynamic | succeeded | 3/5 | None | None | None | None | None | 48.0 | 1868.79 | 0.0 |
| D | dynamic | succeeded | 2/3 | None | None | None | None | None | 10.0 | 371.08 | 1.0 |
| F | scenario | succeeded | 2/2 | None | None | None | None | None | 5.0 | 1964.68 | 0.0 |
| G | scenario | succeeded | 1/1 | None | None | None | None | None | 9.0 | 2354.22 | 0.0 |

## Skill Performance Registry（§19/§40；内部 skills 全部记录）

| Skill | Version | Runs | Success | Schema Fail | Human | Edit Ratio | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| assessment-designer | 0.1.0 | 10 | 0.8 | 0.0 | None | None | EXPERIMENTAL |
| case-designer | 0.1.0 | 11 | 0.8182 | 0.0 | None | None | EXPERIMENTAL |
| claim-extractor | 0.1.0 | 16 | 0.875 | 0.0 | None | None | EXPERIMENTAL |
| diagram-designer | 0.1.0 | 6 | 0.1667 | 0.0 | None | None | EXPERIMENTAL |
| docx-exporter | 0.1.0 | 6 | 0.1667 | 0.0 | None | None | EXPERIMENTAL |
| dual-coding-designer | 6bbbce418f82 | 3 | 0.6667 | 0.3333 | None | None | EXPERIMENTAL |
| evidence-indexer | 0.1.0 | 6 | 0.1667 | 0.0 | None | None | EXPERIMENTAL |
| evidence-reviewer | 0.1.0 | 16 | 0.8125 | 0.0 | None | None | EXPERIMENTAL |
| gate-runner | 0.1.0 | 10 | 0.6 | 0.0 | None | None | EXPERIMENTAL |
| learning-designer | 0.1.0 | 16 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| lesson-designer | 0.1.0 | 16 | 0.625 | 0.0 | None | None | EXPERIMENTAL |
| media-router | 0.1.0 | 5 | 0.2 | 0.0 | None | None | EXPERIMENTAL |
| pck-developer | 0.1.0 | 16 | 0.625 | 0.0 | None | None | EXPERIMENTAL |
| presentation-composer | 0.1.0 | 6 | 0.1667 | 0.0 | None | None | EXPERIMENTAL |
| presentation-planner | 0.1.0 | 6 | 0.1667 | 0.0 | None | None | EXPERIMENTAL |
| preview-builder | 0.1.0 | 6 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| requirements-builder | 0.1.0 | 16 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| script-writer | 0.1.0 | 11 | 0.6364 | 0.0 | None | None | EXPERIMENTAL |
| template-parser | 0.1.0 | 16 | 1.0 | 0.0 | None | None | EXPERIMENTAL |

