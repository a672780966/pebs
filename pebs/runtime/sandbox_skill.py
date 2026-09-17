from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .. import sandbox
from . import skill_loader
from .result import validate_result
from .skill_loader import SkillRuntimeBlocked


class SandboxSkillExecutor:
    """Runs an external skill's declared entrypoint only through a verified sandbox adapter."""

    def execute(self, ctx: Any, node: dict[str, Any], *, skill_record: dict[str, Any]) -> list[dict[str, Any]]:
        name = skill_record.get("name")
        if skill_record.get("execution_policy") != "SANDBOX_ONLY":
            raise SkillRuntimeBlocked(f"{name} 未声明 SANDBOX_ONLY，拒绝执行脚本")
        if not sandbox.available():
            raise SkillRuntimeBlocked(f"没有通过验证的沙箱适配器，拒绝执行 {name} 的脚本")
        loaded = skill_loader.load(name)
        entrypoint = (skill_record.get("handler") or {}).get("entrypoint") or loaded.manifest.get("entrypoint")
        if not entrypoint:
            raise SkillRuntimeBlocked(f"{name} 没有声明 entrypoint")
        workdir = Path(tempfile.mkdtemp(prefix=f"pebs_{name}_"))
        declared = skill_loader.declared_artifact_types(skill_record)
        inputs_payload = {
            artifact_type: ctx.content(artifact_type)
            for artifact_type in declared
            if ctx.content(artifact_type) is not None
        }
        (workdir / "inputs.json").write_text(json.dumps(inputs_payload, ensure_ascii=False), encoding="utf-8")
        command = [str(part) for part in entrypoint] if isinstance(entrypoint, list) else ["sh", "-c", str(entrypoint)]
        result = sandbox.run_sandboxed(command, workdir=workdir, timeout=int(loaded.manifest.get("timeout_seconds", 120) or 120))
        if result.get("returncode") != 0:
            raise SkillRuntimeBlocked(f"{name} 沙箱执行失败：{str(result.get('stderr'))[-200:]}")
        outputs: list[dict[str, Any]] = []
        for declaration in (skill_record.get("handler") or {}).get("outputs", []) or []:
            artifact_type = str(declaration.get("artifact_type", ""))
            filename = str(declaration.get("file", "output.json"))
            path = workdir / filename
            if not artifact_type or not path.is_file():
                raise SkillRuntimeBlocked(f"{name} 未产出声明的文件：{filename}")
            content = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_result(content, artifact_type=artifact_type, inline_schema=loaded.output_schema)
            if errors:
                raise SkillRuntimeBlocked(f"{name} 输出未通过校验：{'；'.join(errors[:3])}")
            outputs.append({"artifact_type": artifact_type, "content": content})
        shutil.rmtree(workdir, ignore_errors=True)
        if not outputs:
            raise SkillRuntimeBlocked(f"{name} 没有声明任何 outputs，无法登记产物")
        return outputs
