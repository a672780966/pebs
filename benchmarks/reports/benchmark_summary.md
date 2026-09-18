# M6 Benchmark Summary

生成时间：2026-09-18T21:40:12；run 数（每 case×mode 取最新）：6

| Case | Mode | Status | Attempts | Human Score | Edit Ratio | Evidence Errors | Routing Errors | Plan Errors | Model Calls | Runtime(s) | Auto Issues |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | direct_codex | succeeded | 1/1 | None | None | None | None | None | 1.0 | 167.42 | 0.0 |
| A | builtin | blocked | 0/5 | None | None | None | None | None | 12.0 | 348.53 | 11.0 |
| A | dynamic | succeeded | 2/10 | None | None | None | None | None | 28.0 | 1020.85 | 3.0 |
| B | direct_codex | succeeded | 1/1 | None | None | None | None | None | 1.0 | 210.04 | 0.0 |
| B | dynamic | running | 0/5 | None | None | None | None | None | 40.0 | 7826.67 | 3.0 |
| C | dynamic | succeeded | 3/5 | None | None | None | None | None | 48.0 | 1868.79 | 0.0 |

## Skill Performance Registry（§19/§40；内部 skills 全部记录）

| Skill | Version | Runs | Success | Schema Fail | Human | Edit Ratio | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| assessment-designer | 0.1.0 | 6 | 0.8333 | 0.0 | None | None | EXPERIMENTAL |
| case-designer | 0.1.0 | 7 | 0.8571 | 0.0 | None | None | EXPERIMENTAL |
| claim-extractor | 0.1.0 | 10 | 0.9 | 0.0 | None | None | EXPERIMENTAL |
| diagram-designer | 0.1.0 | 4 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| docx-exporter | 0.1.0 | 4 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| dual-coding-designer | 6bbbce418f82 | 2 | 0.5 | 0.5 | None | None | EXPERIMENTAL |
| evidence-indexer | 0.1.0 | 4 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| evidence-reviewer | 0.1.0 | 10 | 0.8 | 0.0 | None | None | EXPERIMENTAL |
| gate-runner | 0.1.0 | 6 | 0.5 | 0.0 | None | None | EXPERIMENTAL |
| learning-designer | 0.1.0 | 10 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| lesson-designer | 0.1.0 | 10 | 0.6 | 0.0 | None | None | EXPERIMENTAL |
| media-router | 0.1.0 | 3 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| pck-developer | 0.1.0 | 10 | 0.6 | 0.0 | None | None | EXPERIMENTAL |
| presentation-composer | 0.1.0 | 4 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| presentation-planner | 0.1.0 | 4 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| preview-builder | 0.1.0 | 4 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| requirements-builder | 0.1.0 | 10 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| script-writer | 0.1.0 | 7 | 0.5714 | 0.0 | None | None | EXPERIMENTAL |
| template-parser | 0.1.0 | 10 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| 写教案 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 动画决策与教学分镜 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 媒体选型（Media Router） |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 导出 DOCX/Markdown/PPTX |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 幻灯片沟通计划（Production Planning Table） |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 提取待核验心理学结论 |  | 1 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| 教学设计（PCK/UDL） |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 整理课程要求 |  | 1 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| 核验结论（用户材料/研究来源） |  | 1 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| 生成可编辑 PPTX |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 生成教学图示（SVG） |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 生成课程脚本 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 生成预览 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 补充核验新增事实 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 解析模板与材料 |  | 1 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| 认知负荷与双重编码检查 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 设计学习单 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 设计学习目标与理解难点 |  | 1 | 1.0 | 0.0 | None | None | EXPERIMENTAL |
| 设计形成性评价 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 设计案例 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 证据资产索引（Evidence Index） |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |
| 质量门禁 G1–G7 |  | 1 | 0.0 | 0.0 | None | None | EXPERIMENTAL |

