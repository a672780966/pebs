# 教师人工评价材料包（M6 §30–§32 / Acceptance 5）

本目录由 `python -m pebs.cli benchmark --export-eval-kit` 生成，用于让**真实教师**在不运行
PEBS 的情况下完成 M6 的人工评价（Honest Evaluation 不允许由另一个 LLM 自动评分）。

## 目录结构

```
evaluation_kit/
└── <case>-<variant>/
    ├── course.md          # 该次运行的关键产物（教案/脚本/幻灯片计划等，JSON 形式）
    ├── run.json           # 运行摘要（状态、模型调用数、证据政策、可复现信息）
    ├── <case>-<variant>-human_eval.yaml   # 待填写的评分表
    └── README.md          # 填写说明
```

## 评分步骤（每位教师约 3–5 分钟/课）

1. 打开 `course.md` 通读该课产物。
2. 打开 `human_eval.yaml`，在 `scores` 里给 1–5 分（14 个维度：学科准确性、教学逻辑、
   学习目标清晰度、内容与目标对齐、概念解释清晰度、案例质量、可执行性、学生参与度、
   认知挑战、评价设计、语言自然度、视觉必要性、连贯性、教师可用性；脚本类另填
   `spoken_naturalness`）。
3. `comment` 必填；`must_fix` / `nice_to_have` 建议填写。
4. 若你在阅读时做了修改，把改前/改后文本粘进 `edits.generated_text` / `edits.edited_text`，
   并在 `edits.items` 里按类别（fact correction 等）与严重度（S0–S5）登记。
5. 提交：

```
python -m pebs.cli benchmark --submit-eval <worksheet.yaml> --project <project_id>
```

评分以 Artifact 形式落库（`human_eval`），并绑定到当次运行的 skill 版本；Teacher Edit Ratio
会由 `edits.generated_text/edited_text` 自动计算。

## 重要说明

- 这些课程材料由**合成 fixture**（模板、材料、讲稿）生成，不含真实学生数据。
- 请勿勾选式打分：分数差异需要 `comment` 佐证；M6 的核心指标是
  **Evidence Error Rate** 与 **Major Teacher Edit Rate**，其次是 Human Teaching Score。
- 目标是"减少无意义修改、把人工修改集中到高价值教学判断"，不是追求零修改（§74）。
- 至少需要覆盖 3 个真实课程项目（§71-5）。当前建议优先评：
  `C-dynamic`（托育四节）、`A-dynamic`（融合教育三节）、`B-dynamic`（心理健康第一课）。
