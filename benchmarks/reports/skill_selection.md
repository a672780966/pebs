# M6 Skill Selection Experiment（plan-only）

同一任务在不同 Skill 组合下的 DAG 与选择理由；不调用任何模型，可离线复现（§46/§47）。

| Case | Variant | Nodes | Terminal outputs | Explicit-skill note |
| --- | --- | ---: | --- | --- |
| D | plan [builtin] | 11 | script | — |
| D | plan [+hinge-question-designer] | 11 | assessment、script | 显式调用 /hinge-question-designer → 加入 ['assessment'] |
| D | plan [+dual-coding-designer] | 12 | media_plan、script | 显式调用 /dual-coding-designer → 加入 ['media_plan'] |
| B | plan [builtin] | 14 | export_manifest、lesson_plan、pptx_deck | — |
| B | plan [+hinge-question-designer] | 15 | assessment、export_manifest、lesson_plan、pptx_deck | 显式调用 /hinge-question-designer → 加入 ['assessment'] |
| B | plan [+dual-coding-designer] | 14 | export_manifest、lesson_plan、media_plan、pptx_deck | 显式调用 /dual-coding-designer → 加入 ['media_plan'] |

## D / plan [builtin]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) | 为产出 learning_design；综合分 3.45 高于次优 backwards-design-unit-planner（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45)、criterion-referenced-rubric-generator(3.45)、hinge-question-designer(3.45) | 为产出 assessment；综合分 3.45 高于次优 checking-for-understanding-protocol-designer（3.45） |
| case | case-designer | 3.45 | — | 为产出 case |
| script | script-writer | 3.45 | — | 为产出 script |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result |

## D / plan [+hinge-question-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) | 为产出 learning_design；综合分 3.45 高于次优 backwards-design-unit-planner（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| case | case-designer | 3.45 | — | 为产出 case |
| assessment | hinge-question-designer | 3.45 | assessment-designer(3.45)、checking-for-understanding-protocol-designer(3.45)、criterion-referenced-rubric-generator(3.45) | 用户显式指定（Explicit User Choice）；为产出 assessment；综合分 3.45 高于次优 assessment-designer（3.45） |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |
| script | script-writer | 3.45 | — | 为产出 script |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result |

## D / plan [+dual-coding-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) | 为产出 learning_design；综合分 3.45 高于次优 backwards-design-unit-planner（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45)、criterion-referenced-rubric-generator(3.45)、hinge-question-designer(3.45) | 为产出 assessment；综合分 3.45 高于次优 checking-for-understanding-protocol-designer（3.45） |
| case | case-designer | 3.45 | — | 为产出 case |
| media_plan | dual-coding-designer | 3.25 | media-router(3.25) | 用户显式指定（Explicit User Choice）；为产出 media_plan；综合分 3.25 高于次优 media-router（3.25） |
| script | script-writer | 3.45 | — | 为产出 script |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result |

## B / plan [builtin]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) | 为产出 learning_design；综合分 3.45 高于次优 backwards-design-unit-planner（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| media_plan | media-router | 3.25 | dual-coding-designer(3.25) | 为产出 media_plan；综合分 3.25 高于次优 dual-coding-designer（3.25） |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck |
| preview | preview-builder | 3.5 | — | 为产出 preview |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |

## B / plan [+hinge-question-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) | 为产出 learning_design；综合分 3.45 高于次优 backwards-design-unit-planner（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| media_plan | media-router | 3.25 | dual-coding-designer(3.25) | 为产出 media_plan；综合分 3.25 高于次优 dual-coding-designer（3.25） |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck |
| preview | preview-builder | 3.5 | — | 为产出 preview |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest |
| assessment | hinge-question-designer | 3.45 | assessment-designer(3.45)、checking-for-understanding-protocol-designer(3.45)、criterion-referenced-rubric-generator(3.45) | 用户显式指定（Explicit User Choice）；为产出 assessment；综合分 3.45 高于次优 assessment-designer（3.45） |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |

## B / plan [+dual-coding-designer]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) | 为产出 learning_design；综合分 3.45 高于次优 backwards-design-unit-planner（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| media_plan | dual-coding-designer | 3.25 | media-router(3.25) | 用户显式指定（Explicit User Choice）；为产出 media_plan；综合分 3.25 高于次优 media-router（3.25） |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck |
| preview | preview-builder | 3.5 | — | 为产出 preview |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |
