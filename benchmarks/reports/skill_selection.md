# M6 Skill Selection Experiment（plan-only）

同一任务在不同 Skill 组合下的 DAG 与选择理由；不调用任何模型，可离线复现（§46/§47）。

| Case | Variant | Nodes | Terminal outputs | Explicit-skill note |
| --- | --- | ---: | --- | --- |
| B | plan [builtin] | 14 | export_manifest、lesson_plan、pptx_deck | — |
| B | plan [+backwards-design-unit-planner] | 14 | export_manifest、learning_design、lesson_plan、pptx_deck | 显式调用 /backwards-design-unit-planner → 加入 ['learning_design'] |
| B | plan [+cognitive-load-analyser] | 15 | export_manifest、lesson_plan、load_review、pptx_deck | 显式调用 /cognitive-load-analyser → 加入 ['load_review'] |
| B | plan [+udl-lesson-auditor] | 15 | export_manifest、lesson_plan、load_review、pptx_deck | 显式调用 /udl-lesson-auditor → 加入 ['load_review'] |
| B | plan [+hinge-question-designer] | 15 | assessment、export_manifest、lesson_plan、pptx_deck | 显式调用 /hinge-question-designer → 加入 ['assessment'] |
| C | plan [builtin] | 11 | case、script | — |
| C | plan [+backwards-design-unit-planner] | 11 | case、learning_design、script | 显式调用 /backwards-design-unit-planner → 加入 ['learning_design'] |
| C | plan [+cognitive-load-analyser] | 12 | case、load_review、script | 显式调用 /cognitive-load-analyser → 加入 ['load_review'] |
| C | plan [+udl-lesson-auditor] | 12 | case、load_review、script | 显式调用 /udl-lesson-auditor → 加入 ['load_review'] |
| C | plan [+hinge-question-designer] | 11 | assessment、case、script | 显式调用 /hinge-question-designer → 加入 ['assessment'] |
| D | plan [builtin] | 11 | script | — |
| D | plan [+backwards-design-unit-planner] | 11 | learning_design、script | 显式调用 /backwards-design-unit-planner → 加入 ['learning_design'] |
| D | plan [+cognitive-load-analyser] | 12 | load_review、script | 显式调用 /cognitive-load-analyser → 加入 ['load_review'] |
| D | plan [+udl-lesson-auditor] | 12 | load_review、script | 显式调用 /udl-lesson-auditor → 加入 ['load_review'] |
| D | plan [+hinge-question-designer] | 11 | assessment、script | 显式调用 /hinge-question-designer → 加入 ['assessment'] |

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

## B / plan [+backwards-design-unit-planner]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | backwards-design-unit-planner | 3.45 | learning-designer(3.45) | 用户显式指定（Explicit User Choice）；为产出 learning_design；综合分 3.45 高于次优 learning-designer（3.45） |
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

## B / plan [+cognitive-load-analyser]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | learning-designer | 3.45 | backwards-design-unit-planner(3.45) | 为产出 learning_design；综合分 3.45 高于次优 backwards-design-unit-planner（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| load_review | cognitive-load-analyser | 3.25 | udl-barrier-anticipator(3.45)、udl-lesson-auditor(3.45)、load-reviewer(3.25) | 用户显式指定（Explicit User Choice）；为产出 load_review；综合分 3.25 高于次优 udl-barrier-anticipator（3.45） |
| media_plan | media-router | 3.25 | dual-coding-designer(3.25) | 为产出 media_plan；综合分 3.25 高于次优 dual-coding-designer（3.25） |
| diagrams | diagram-designer | 3.25 | — | 为产出 diagrams |
| evidence_assets | evidence-indexer | 3.5 | — | 为产出 evidence_assets |
| slide_plan | presentation-planner | 3.25 | — | 为产出 slide_plan |
| pptx_deck | presentation-composer | 3.3 | — | 为产出 pptx_deck |
| preview | preview-builder | 3.5 | — | 为产出 preview |
| export_manifest | docx-exporter | 3.5 | — | 为产出 export_manifest |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |

## B / plan [+udl-lesson-auditor]

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
| load_review | udl-lesson-auditor | 3.45 | udl-barrier-anticipator(3.45)、cognitive-load-analyser(3.25)、load-reviewer(3.25) | 用户显式指定（Explicit User Choice）；为产出 load_review；综合分 3.45 高于次优 udl-barrier-anticipator（3.45） |

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

## C / plan [builtin]

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

## C / plan [+backwards-design-unit-planner]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | backwards-design-unit-planner | 3.45 | learning-designer(3.45) | 用户显式指定（Explicit User Choice）；为产出 learning_design；综合分 3.45 高于次优 learning-designer（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45)、criterion-referenced-rubric-generator(3.45)、hinge-question-designer(3.45) | 为产出 assessment；综合分 3.45 高于次优 checking-for-understanding-protocol-designer（3.45） |
| case | case-designer | 3.45 | — | 为产出 case |
| script | script-writer | 3.45 | — | 为产出 script |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result |

## C / plan [+cognitive-load-analyser]

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
| load_review | cognitive-load-analyser | 3.25 | udl-barrier-anticipator(3.45)、udl-lesson-auditor(3.45)、load-reviewer(3.25) | 用户显式指定（Explicit User Choice）；为产出 load_review；综合分 3.25 高于次优 udl-barrier-anticipator（3.45） |
| script | script-writer | 3.45 | — | 为产出 script |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result |

## C / plan [+udl-lesson-auditor]

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
| load_review | udl-lesson-auditor | 3.45 | udl-barrier-anticipator(3.45)、cognitive-load-analyser(3.25)、load-reviewer(3.25) | 用户显式指定（Explicit User Choice）；为产出 load_review；综合分 3.45 高于次优 udl-barrier-anticipator（3.45） |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result |

## C / plan [+hinge-question-designer]

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

## D / plan [+backwards-design-unit-planner]

| 产物 | 选中 Skill | 分数 | 被拒候选（分数） | 理由 |
| --- | --- | ---: | --- | --- |
| template_spec | template-parser | 4.5 | — | 为产出 template_spec |
| requirements | requirements-builder | 3.5 | — | 为产出 requirements |
| learning_design | backwards-design-unit-planner | 3.45 | learning-designer(3.45) | 用户显式指定（Explicit User Choice）；为产出 learning_design；综合分 3.45 高于次优 learning-designer（3.45） |
| claims_set | claim-extractor | 3.45 | — | 为产出 claims_set |
| evidence_index | evidence-reviewer | 3.4 | — | 为产出 evidence_index |
| teaching_plan | pck-developer | 3.45 | explicit-instruction-sequence-builder(3.45)、learning-progression-builder(3.45)、udl-options-designer(3.45) | 为产出 teaching_plan；综合分 3.45 高于次优 explicit-instruction-sequence-builder（3.45） |
| lesson_plan | lesson-designer | 3.45 | discipline-specific-critical-thinking-task-designer(3.45)、experiential-learning-cycle-designer(3.45)、worked-example-fading-designer(3.45) | 为产出 lesson_plan；综合分 3.45 高于次优 discipline-specific-critical-thinking-task-designer（3.45） |
| assessment | assessment-designer | 3.45 | checking-for-understanding-protocol-designer(3.45)、criterion-referenced-rubric-generator(3.45)、hinge-question-designer(3.45) | 为产出 assessment；综合分 3.45 高于次优 checking-for-understanding-protocol-designer（3.45） |
| case | case-designer | 3.45 | — | 为产出 case |
| script | script-writer | 3.45 | — | 为产出 script |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result |

## D / plan [+cognitive-load-analyser]

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
| load_review | cognitive-load-analyser | 3.25 | udl-barrier-anticipator(3.45)、udl-lesson-auditor(3.45)、load-reviewer(3.25) | 用户显式指定（Explicit User Choice）；为产出 load_review；综合分 3.25 高于次优 udl-barrier-anticipator（3.45） |
| script | script-writer | 3.45 | — | 为产出 script |
| gate_result | gate-runner | 3.4 | — | 为产出 gate_result |

## D / plan [+udl-lesson-auditor]

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
| load_review | udl-lesson-auditor | 3.45 | udl-barrier-anticipator(3.45)、cognitive-load-analyser(3.25)、load-reviewer(3.25) | 用户显式指定（Explicit User Choice）；为产出 load_review；综合分 3.45 高于次优 udl-barrier-anticipator（3.45） |
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
