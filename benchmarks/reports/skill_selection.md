# M6 Skill Selection Experiment（plan-only）

同一任务在不同 Skill 组合下的 DAG 与选择理由；不调用任何模型，可离线复现（§46/§47）。

| Case | Variant | Nodes | Terminal outputs | Explicit-skill note |
| --- | --- | ---: | --- | --- |
| B | plan [builtin] | 14 | export_manifest、lesson_plan、pptx_deck | — |
| B | plan [+backwards-design-unit-planner] | 14 | export_manifest、learning_design、lesson_plan、pptx_deck | 显式调用 /backwards-design-unit-planner → 加入 ['learning_design'] |
| B | plan [+cognitive-load-analyser] | 15 | export_manifest、lesson_plan、load_review、pptx_deck | 显式调用 /cognitive-load-analyser → 加入 ['load_review'] |
| B | plan [+udl-lesson-auditor] | 15 | export_manifest、lesson_plan、load_review、pptx_deck | 显式调用 /udl-lesson-auditor → 加入 ['load_review'] |
| B | plan [+hinge-question-designer] | 15 | assessment、export_manifest、lesson_plan、pptx_deck | 显式调用 /hinge-question-designer → 加入 ['assessment'] |
| B | plan [+dual-coding-designer] | 14 | export_manifest、lesson_plan、media_plan、pptx_deck | 显式调用 /dual-coding-designer → 加入 ['media_plan'] |
| C | plan [builtin] | 11 | case、script | — |
| C | plan [+backwards-design-unit-planner] | 11 | case、learning_design、script | 显式调用 /backwards-design-unit-planner → 加入 ['learning_design'] |
| C | plan [+cognitive-load-analyser] | 12 | case、load_review、script | 显式调用 /cognitive-load-analyser → 加入 ['load_review'] |
| C | plan [+udl-lesson-auditor] | 12 | case、load_review、script | 显式调用 /udl-lesson-auditor → 加入 ['load_review'] |
| C | plan [+hinge-question-designer] | 11 | assessment、case、script | 显式调用 /hinge-question-designer → 加入 ['assessment'] |
| C | plan [+dual-coding-designer] | 12 | case、media_plan、script | 显式调用 /dual-coding-designer → 加入 ['media_plan'] |
| D | plan [builtin] | 11 | script | — |
| D | plan [+backwards-design-unit-planner] | 11 | learning_design、script | 显式调用 /backwards-design-unit-planner → 加入 ['learning_design'] |
| D | plan [+cognitive-load-analyser] | 12 | load_review、script | 显式调用 /cognitive-load-analyser → 加入 ['load_review'] |
| D | plan [+udl-lesson-auditor] | 12 | load_review、script | 显式调用 /udl-lesson-auditor → 加入 ['load_review'] |
| D | plan [+hinge-question-designer] | 11 | assessment、script | 显式调用 /hinge-question-designer → 加入 ['assessment'] |
| D | plan [+dual-coding-designer] | 12 | media_plan、script | 显式调用 /dual-coding-designer → 加入 ['media_plan'] |

## B / plan [builtin]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| media_plan | media-router | 3.25 | dual-coding-designer(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 media_plan；与次优 dual-coding-designer 并列（3.25）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| preview | preview-builder | 3.5 | — | 为产出 preview；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |

## B / plan [+backwards-design-unit-planner]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | backwards-design-unit-planner | 3.45 | learning-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 learning_design；与次优 learning-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| media_plan | media-router | 3.25 | dual-coding-designer(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 media_plan；与次优 dual-coding-designer 并列（3.25）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| preview | preview-builder | 3.5 | — | 为产出 preview；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |

## B / plan [+cognitive-load-analyser]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| load_review | cognitive-load-analyser | 3.25 | udl-barrier-anticipator(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-lesson-auditor(3.45) — 得分并列；由显式指定或 registry 顺序决定；load-reviewer(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 load_review；与次优 udl-barrier-anticipator 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| media_plan | media-router | 3.25 | dual-coding-designer(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 media_plan；与次优 dual-coding-designer 并列（3.25）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| preview | preview-builder | 3.5 | — | 为产出 preview；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |

## B / plan [+udl-lesson-auditor]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| media_plan | media-router | 3.25 | dual-coding-designer(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 media_plan；与次优 dual-coding-designer 并列（3.25）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| preview | preview-builder | 3.5 | — | 为产出 preview；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| load_review | udl-lesson-auditor | 3.45 | udl-barrier-anticipator(3.45) — 得分并列；由显式指定或 registry 顺序决定；cognitive-load-analyser(3.25) — 综合分更低（主要差距：领域匹配）；得分构成：领域匹配-0.20、产物匹配+0.00、Skill 状态（APPROVED/PATCHED）+0.00；load-reviewer(3.25) — 综合分更低（主要差距：领域匹配）；得分构成：领域匹配-0.20、产物匹配+0.00、Skill 状态（APPROVED/PATCHED）+0.00 | 用户显式指定（Explicit User Choice）；为产出 load_review；与次优 udl-barrier-anticipator 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |

## B / plan [+hinge-question-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| media_plan | media-router | 3.25 | dual-coding-designer(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 media_plan；与次优 dual-coding-designer 并列（3.25）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| preview | preview-builder | 3.5 | — | 为产出 preview；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| assessment | hinge-question-designer | 3.45 | assessment-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 assessment；与次优 assessment-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |

## B / plan [+dual-coding-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| media_plan | dual-coding-designer | 3.25 | media-router(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 media_plan；与次优 media-router 并列（3.25）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| preview | preview-builder | 3.5 | — | 为产出 preview；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |

## C / plan [builtin]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## C / plan [+backwards-design-unit-planner]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | backwards-design-unit-planner | 3.45 | learning-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 learning_design；与次优 learning-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## C / plan [+cognitive-load-analyser]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| load_review | cognitive-load-analyser | 3.25 | udl-barrier-anticipator(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-lesson-auditor(3.45) — 得分并列；由显式指定或 registry 顺序决定；load-reviewer(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 load_review；与次优 udl-barrier-anticipator 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## C / plan [+udl-lesson-auditor]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| load_review | udl-lesson-auditor | 3.45 | udl-barrier-anticipator(3.45) — 得分并列；由显式指定或 registry 顺序决定；cognitive-load-analyser(3.25) — 综合分更低（主要差距：领域匹配）；得分构成：领域匹配-0.20、产物匹配+0.00、Skill 状态（APPROVED/PATCHED）+0.00；load-reviewer(3.25) — 综合分更低（主要差距：领域匹配）；得分构成：领域匹配-0.20、产物匹配+0.00、Skill 状态（APPROVED/PATCHED）+0.00 | 用户显式指定（Explicit User Choice）；为产出 load_review；与次优 udl-barrier-anticipator 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## C / plan [+hinge-question-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | hinge-question-designer | 3.45 | assessment-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 assessment；与次优 assessment-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## C / plan [+dual-coding-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| media_plan | dual-coding-designer | 3.25 | media-router(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 media_plan；与次优 media-router 并列（3.25）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## D / plan [builtin]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## D / plan [+backwards-design-unit-planner]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | backwards-design-unit-planner | 3.45 | learning-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 learning_design；与次优 learning-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## D / plan [+cognitive-load-analyser]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| load_review | cognitive-load-analyser | 3.25 | udl-barrier-anticipator(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-lesson-auditor(3.45) — 得分并列；由显式指定或 registry 顺序决定；load-reviewer(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 load_review；与次优 udl-barrier-anticipator 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## D / plan [+udl-lesson-auditor]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| load_review | udl-lesson-auditor | 3.45 | udl-barrier-anticipator(3.45) — 得分并列；由显式指定或 registry 顺序决定；cognitive-load-analyser(3.25) — 综合分更低（主要差距：领域匹配）；得分构成：领域匹配-0.20、产物匹配+0.00、Skill 状态（APPROVED/PATCHED）+0.00；load-reviewer(3.25) — 综合分更低（主要差距：领域匹配）；得分构成：领域匹配-0.20、产物匹配+0.00、Skill 状态（APPROVED/PATCHED）+0.00 | 用户显式指定（Explicit User Choice）；为产出 load_review；与次优 udl-barrier-anticipator 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## D / plan [+hinge-question-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | hinge-question-designer | 3.45 | assessment-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 assessment；与次优 assessment-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |

## D / plan [+dual-coding-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+1.00 |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.00、regression=+0.00 |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 learning_design；与次优 backwards-design-unit-planner 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；learning-progression-builder(3.45) — 得分并列；由显式指定或 registry 顺序决定；udl-options-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 teaching_plan；与次优 explicit-instruction-sequence-builder 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；experiential-learning-cycle-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；worked-example-fading-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 lesson_plan；与次优 discipline-specific-critical-thinking-task-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定；criterion-referenced-rubric-generator(3.45) — 得分并列；由显式指定或 registry 顺序决定；hinge-question-designer(3.45) — 得分并列；由显式指定或 registry 顺序决定 | 为产出 assessment；与次优 checking-for-understanding-protocol-designer 并列（3.45）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| case | case-designer | 3.45 | — | 为产出 case；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| media_plan | dual-coding-designer | 3.25 | media-router(3.25) — 得分并列；由显式指定或 registry 顺序决定 | 用户显式指定（Explicit User Choice）；为产出 media_plan；与次优 media-router 并列（3.25）；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.30、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| script | script-writer | 3.45 | — | 为产出 script；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.05、regression=+0.00 |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result；得分构成：produces_match=+2.00、status=+1.00、domain_fit=+0.50、risk_fit=+0.00、cost_penalty=-0.10、regression=+0.00 |
