# 教师评分工作表（M6 §30–§32）

1. 打开对应的 `<case>-<mode>-human_eval.yaml`，在 `scores` 中给 1–5 分（14 个维度；脚本类任务另填 `spoken_naturalness`）。
2. `comment` 必填（文字备注），`must_fix` / `nice_to_have` 选填。
3. 若做过人工修改，把修改前后的文本填入 `edits.generated_text` / `edits.edited_text`，并按类别与严重度登记 `edits.items`。
4. 提交：`python -m pebs.cli benchmark --submit-eval <worksheet.yaml> --project <project_id>`
   （等价于 POST /api/projects/<project_id>/evaluation；评分以 Artifact 形式落库并绑定 Skill 版本）
