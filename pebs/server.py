from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, gates, providers, sandbox, skills_mgr
from .engine import Engine, ExplicitSkillDenied, PiiBlocked, PlanEditRejected
from .hooks import HookFailure
from .store import ConflictError, StoreError, canonical_json
from .template_parse import MAX_FILE_BYTES, ImportLimitExceeded, ParseError, check_import_limits

STATIC_DIR = Path(__file__).resolve().parent / "static"
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]{1,40}$")

UPLOAD_CHUNK = 1024 * 1024

app = FastAPI(title="Psychology Education Build System", version="0.1.0")
_engines: dict[str, Engine] = {}


def get_engine(project_id: str) -> Engine:
    if not PROJECT_ID_RE.match(project_id):
        raise HTTPException(status_code=400, detail="非法项目 ID")
    if project_id not in _engines:
        _engines[project_id] = Engine(project_id)
    return _engines[project_id]


class ProjectIn(BaseModel):
    project_id: str


class BuildIn(BaseModel):
    request: str = Field(min_length=1)
    template_path: str | None = None
    material_paths: list[str] = Field(default_factory=list)
    environment: str = "production"
    planner: str | None = None


class PlanEditIn(BaseModel):
    op: str
    step_id: str
    index: int | None = None


class CaseReplaceIn(BaseModel):
    case_artifact_id: str
    instruction: str = Field(min_length=1)


class ExportIn(BaseModel):
    mode: str = "draft"


class RerunIn(BaseModel):
    step_id: str


class SkillImportIn(BaseModel):
    url: str
    ref: str | None = None
    sha: str | None = None


class SkillReviewIn(BaseModel):
    name: str
    decision: str
    reviewer: str | None = None
    evidence: str | None = None
    adoption: str | None = None


class SkillPublishIn(BaseModel):
    name: str
    version: str | None = None


class SlideEditIn(BaseModel):
    slide: int = Field(ge=1)
    title: str | None = None
    points: list[str] | None = None
    core_message: str | None = None
    notes: str | None = None
    density: str | None = None


class SignoffIn(BaseModel):
    changeset_id: str
    reviewer: str
    basis: str
    changes: str = ""


class ClaimReviewIn(BaseModel):
    claim_id: str
    version: int = Field(ge=1)
    decision: str
    reviewer: str
    basis: str
    source_id: str | None = None
    source_version: int | None = None
    quote: str = ""
    quote_location: str = ""


class ConversationIn(BaseModel):
    message: str
    execute: bool = True


class HumanEvalIn(BaseModel):
    reviewer: str
    role: str = "teacher"
    run_id: str = ""
    mode: str = ""
    scores: dict[str, float] = Field(default_factory=dict)
    comment: str = ""
    must_fix: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    evidence_errors: int = 0
    routing_errors: int = 0
    plan_errors: int = 0
    edits: dict[str, Any] = Field(default_factory=dict)


@app.get("/api/registry")
def registry_report() -> dict[str, Any]:
    return {"skills": skills_mgr.list_skills()}


@app.get("/api/sandbox")
def sandbox_status() -> dict[str, Any]:
    return asdict(sandbox.load_report())


@app.post("/api/sandbox/probe")
def sandbox_probe() -> dict[str, Any]:
    return {"reports": [asdict(report) for report in sandbox.probe_all()]}


@app.post("/api/skills/import")
def skills_import(payload: SkillImportIn) -> dict[str, Any]:
    try:
        record = skills_mgr.import_candidate(payload.url, ref=payload.ref, commit_sha=payload.sha)
    except skills_mgr.SkillError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"name": record["name"], "source": record["source"], "review_status": record["review_status"]}


@app.post("/api/skills/review")
def skills_review(payload: SkillReviewIn) -> dict[str, Any]:
    mapping = {"in_review": "IN_REVIEW", "approve": "APPROVED", "reject": "REJECTED"}
    decision = mapping.get(payload.decision.lower())
    if decision is None:
        raise HTTPException(status_code=400, detail="decision 只能是 in_review/approve/reject")
    try:
        record = skills_mgr.review(
            payload.name,
            decision,
            reviewer=payload.reviewer,
            evidence=payload.evidence,
            adoption_decision=payload.adoption,
        )
    except skills_mgr.SkillError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"name": record["name"], "review_status": record["review_status"]}


@app.post("/api/skills/publish")
def skills_publish(payload: SkillPublishIn) -> dict[str, Any]:
    try:
        record = skills_mgr.publish(payload.name, version=payload.version)
    except skills_mgr.SkillError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"name": record["name"], "pinned_version": record["pinned_version"], "versions": [v["version"] for v in record["versions"]]}


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "providers": providers.provider_status(),
        "rules_version": config.RULES_VERSION,
        "budgets": config.RULES.get("budgets", {}),
        "projects_dir": str(config.PROJECTS_DIR),
    }


@app.get("/api/projects")
def list_projects() -> dict[str, Any]:
    config.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    items = [p.name for p in sorted(config.PROJECTS_DIR.iterdir()) if p.is_dir()]
    return {"projects": items}


@app.post("/api/projects")
def create_project(payload: ProjectIn) -> dict[str, Any]:
    get_engine(payload.project_id)
    return {"project_id": payload.project_id, "path": str(config.ensure_project_dirs(payload.project_id))}


@app.get("/api/projects/{project_id}/files")
def list_files(project_id: str) -> dict[str, Any]:
    base = config.project_dir(project_id) / "inputs"
    if not base.exists():
        return {"files": []}
    return {"files": [str(p) for p in sorted(base.iterdir()) if p.is_file()]}


@app.post("/api/projects/{project_id}/upload")
async def upload(project_id: str, file: UploadFile) -> dict[str, Any]:
    base = config.ensure_project_dirs(project_id) / "inputs"
    safe_name = Path(file.filename or "upload.bin").name
    target = base / safe_name
    written = 0
    try:
        with target.open("wb") as fh:
            while True:
                chunk = await file.read(UPLOAD_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_FILE_BYTES:
                    raise ImportLimitExceeded(
                        f"文件超过 {MAX_FILE_BYTES // (1024 * 1024)} MiB: {safe_name}",
                        http_status=413,
                    )
                fh.write(chunk)
    except ImportLimitExceeded as exc:
        # An over-limit upload is refused, never stored truncated.
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    return {"path": str(target), "size": written}


@app.post("/api/projects/{project_id}/build")
def build(project_id: str, payload: BuildIn) -> dict[str, Any]:
    engine = get_engine(project_id)
    template = Path(payload.template_path) if payload.template_path else None
    materials = [Path(p) for p in payload.material_paths]
    for path in [*materials, *([template] if template else [])]:
        if not path.exists():
            raise HTTPException(status_code=400, detail=f"文件不存在: {path}")
    try:
        check_import_limits(materials)
    except ImportLimitExceeded as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.environment not in ("production", "test_fixture"):
        raise HTTPException(status_code=400, detail="非法 environment")
    try:
        return engine.start_build(
            payload.request,
            template_path=template,
            material_paths=materials,
            environment=payload.environment,
            planner_mode=payload.planner,
        )
    except (PiiBlocked, ExplicitSkillDenied) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/runs/{run_id}")
def run_status(project_id: str, run_id: str) -> dict[str, Any]:
    engine = get_engine(project_id)
    try:
        return engine.run_status(run_id)
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/runs/{run_id}/cancel")
def cancel_run(project_id: str, run_id: str) -> dict[str, Any]:
    return get_engine(project_id).cancel(run_id)


@app.get("/api/projects/{project_id}/plan")
def get_plan(project_id: str) -> dict[str, Any]:
    return get_engine(project_id).current_plan()


@app.post("/api/projects/{project_id}/plan/edit")
def edit_plan(project_id: str, payload: PlanEditIn) -> dict[str, Any]:
    try:
        return get_engine(project_id).edit_plan(payload.op, payload.step_id, payload.index)
    except PlanEditRejected as exc:
        return JSONResponse(status_code=409, content={"ok": False, "reason": str(exc)})


@app.post("/api/projects/{project_id}/conversation")
def conversation(project_id: str, payload: ConversationIn) -> dict[str, Any]:
    engine = get_engine(project_id)
    try:
        return engine.conversation_edit(payload.message, execute=payload.execute)
    except PlanEditRejected as exc:
        return JSONResponse(status_code=409, content={"ok": False, "reason": str(exc)})


@app.get("/api/projects/{project_id}/patch-plan")
def get_patch_plan(project_id: str) -> dict[str, Any]:
    store = get_engine(project_id).store
    content = store.accepted_content("patch_plan")
    if not content:
        raise HTTPException(status_code=404, detail="no patch plan")
    return content


@app.get("/api/projects/{project_id}/dynamic-plan")
def get_dynamic_plan(project_id: str) -> dict[str, Any]:
    store = get_engine(project_id).store
    plan = store.accepted_content("build_plan_dynamic")
    if not plan:
        return {"mode": "static", "nodes": [], "human_steps": []}
    return {
        "mode": plan.get("mode", "dynamic"),
        "plan_id": plan.get("plan_id"),
        "goal": plan.get("goal"),
        "nodes": plan.get("nodes", []),
        "terminal_outputs": plan.get("terminal_outputs", []),
        "reused_artifacts": plan.get("reused_artifacts", []),
        "human_steps": human_steps(plan),
    }


def human_steps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """把内部节点翻译成人话（§40），内部 node_id / skill 只在高级模式显示。"""
    from . import registry

    human_titles = {
        "template-parser": "解析课程要求与模板",
        "requirements-builder": "整理课程要求",
        "learning-designer": "设计学习目标与难点",
        "claim-extractor": "提取待核验的心理学事实",
        "evidence-reviewer": "核验心理学事实",
        "pck-developer": "设计教学策略",
        "lesson-designer": "设计教学活动",
        "assessment-designer": "设计评价方式",
        "case-designer": "编写教学案例",
        "worksheet-designer": "设计学习单",
        "script-writer": "编写课程脚本",
        "media-router": "选择媒体形式",
        "load-reviewer": "检查认知负荷",
        "diagram-designer": "生成图示",
        "animation-gate": "审查动画必要性",
        "storyboard-designer": "生成动画分镜",
        "evidence-indexer": "整理证据索引",
        "presentation-planner": "规划幻灯片",
        "presentation-composer": "生成 PPT",
        "gate-runner": "质量检查",
        "preview-builder": "生成预览",
        "docx-exporter": "导出正式文档",
    }
    steps = []
    for node in plan.get("nodes", []):
        skill = node.get("skill")
        steps.append(
            {
                "title": human_titles.get(skill, node.get("title") or skill),
                "status": "reuse" if node.get("reused") else "planned",
                "advanced": {
                    "node_id": node.get("node_id"),
                    "skill": skill,
                    "agent": (registry.get(skill) or {}).get("agent"),
                    "depends_on": node.get("depends_on", []),
                    "parallel_group": node.get("parallel_group"),
                },
            }
        )
    return steps


@app.get("/api/projects/{project_id}/trace")
def get_trace(project_id: str, run_id: str | None = None) -> dict[str, Any]:
    """§39/§63：Skill Trace（绑定版本/provider/patch）+ 选择解释。"""
    from .benchmark import trace as trace_mod

    engine = get_engine(project_id)
    run = engine.store.get_run(run_id) if run_id else engine.store.latest_run()
    if not run:
        raise HTTPException(status_code=404, detail="no run")
    plan = engine.store.accepted_content("build_plan_dynamic") or {}
    return {
        "trace": trace_mod.build_trace(engine, run["run_id"]),
        "selection_trace": plan.get("selection_trace", []),
        "plan_mode": plan.get("mode", "static"),
    }


@app.get("/api/projects/{project_id}/evaluation")
def get_evaluation(project_id: str) -> dict[str, Any]:
    """§62：Evaluation Tab 数据（Run/Skills/Human Scores/Edit Ratio/Issues/Comparison）。"""
    from .benchmark import evaluation as evaluation_mod
    from .benchmark import report as report_mod

    engine = get_engine(project_id)
    run = engine.store.latest_run()
    trace = {}
    if run:
        from .benchmark import trace as trace_mod

        trace = trace_mod.build_trace(engine, run["run_id"])
    summary_path = Path(benchmark_reports_dir()) / "benchmark_summary.json"
    comparison = None
    if summary_path.exists():
        try:
            comparison = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            comparison = None
    return {
        "run": {"run_id": run["run_id"], "status": run["status"]} if run else None,
        "trace": trace,
        "human_eval": evaluation_mod.latest(engine),
        "performance": benchmark_performance(),
        "comparison": comparison,
    }


@app.post("/api/projects/{project_id}/evaluation")
def record_evaluation(project_id: str, payload: HumanEvalIn) -> dict[str, Any]:
    from .benchmark import evaluation as evaluation_mod

    engine = get_engine(project_id)
    try:
        content = evaluation_mod.record(engine, payload.model_dump())
    except ValueError as exc:
        return JSONResponse(status_code=409, content={"ok": False, "reason": str(exc)})
    return content


def benchmark_reports_dir() -> str:
    from . import config

    return str(Path(config.BENCHMARKS_DIR) / "reports")


def benchmark_performance() -> dict[str, Any]:
    from .benchmark import performance as performance_mod

    return performance_mod.load_performance().get("skills", {})


@app.get("/api/projects/{project_id}/artifacts")
def list_artifacts(project_id: str) -> dict[str, Any]:
    items = get_engine(project_id).store.list_artifacts()
    for item in items:
        if item["accepted_rev"]:
            rev = get_engine(project_id).store.get_revision(item["accepted_rev"])
            item["content_hash"] = rev["content_hash"]
    return {"artifacts": items}


@app.get("/api/projects/{project_id}/artifacts/{artifact_id:path}")
def get_artifact(project_id: str, artifact_id: str, rev: str | None = None) -> dict[str, Any]:
    store = get_engine(project_id).store
    revision_id = rev or store.accepted_rev_id(artifact_id)
    if not revision_id:
        raise HTTPException(status_code=404, detail=f"no revision for {artifact_id}")
    try:
        revision = store.get_revision(revision_id)
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"revision_id": revision_id, "artifact_id": artifact_id, "content": revision["content"], "content_hash": revision["content_hash"]}


@app.get("/api/projects/{project_id}/changesets")
def list_changesets(project_id: str) -> dict[str, Any]:
    return {"changesets": get_engine(project_id).store.list_changesets()}


@app.get("/api/projects/{project_id}/changesets/{changeset_id}/diff")
def changeset_diff(project_id: str, changeset_id: str) -> dict[str, Any]:
    try:
        return {"diff": get_engine(project_id).diff(changeset_id)}
    except StoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/changesets/{changeset_id}/accept")
def accept(project_id: str, changeset_id: str) -> dict[str, Any]:
    return get_engine(project_id).accept(changeset_id)


@app.post("/api/projects/{project_id}/changesets/{changeset_id}/reject")
def reject(project_id: str, changeset_id: str) -> dict[str, Any]:
    return get_engine(project_id).reject(changeset_id)


@app.get("/api/projects/{project_id}/gates")
def gate_report(project_id: str) -> dict[str, Any]:
    engine = get_engine(project_id)
    ctx = gates.GateContext(store=engine.store, evidence=engine.evidence)
    results = gates.latest_gate_results(engine.store)
    readiness = gates.export_readiness_with_overrides(ctx)
    return {"results": results, "readiness": readiness}


@app.get("/api/projects/{project_id}/evidence")
def evidence_report(project_id: str) -> dict[str, Any]:
    engine = get_engine(project_id)
    return {
        "claims": engine.evidence.claims(),
        "sources": engine.evidence.sources(),
        "assessments": engine.evidence.assessments(),
        "search_logs": engine.store.list_search_logs(),
    }


@app.get("/api/projects/{project_id}/memory")
def memory_report(project_id: str) -> dict[str, Any]:
    from . import memory as memory_mod

    engine = get_engine(project_id)
    return {"memory": memory_mod.read_memory(engine.store)}


@app.get("/api/projects/{project_id}/rules")
def rules_report(project_id: str) -> dict[str, Any]:
    from . import project_rules

    engine = get_engine(project_id)
    path = project_rules.ensure_project_rules(config.project_dir(project_id))
    return {"path": str(path), "text": path.read_text(encoding="utf-8"), "parsed": project_rules.load_rules(config.project_dir(project_id))}


@app.get("/api/projects/{project_id}/preview")
def preview(project_id: str) -> dict[str, Any]:
    store = get_engine(project_id).store
    for artifact_id in ["preview"]:
        revision_id = store.accepted_rev_id(artifact_id)
        if revision_id:
            return {"revision_id": revision_id, "content": store.get_revision(revision_id)["content"]}
    raise HTTPException(status_code=404, detail="preview 尚未生成")


@app.get("/api/projects/{project_id}/outputs")
def outputs(project_id: str) -> dict[str, Any]:
    store = get_engine(project_id).store
    revision_id = store.accepted_rev_id("export_manifest")
    manifest = store.get_revision(revision_id)["content"] if revision_id else None
    formal_dir = Path(store.base_dir) / "outputs" / "formal"
    formal_files = sorted(p.name for p in formal_dir.iterdir() if p.is_file()) if formal_dir.exists() else []
    return {"manifest": manifest, "formal_files": formal_files}


@app.post("/api/projects/{project_id}/case-replace")
def case_replace(project_id: str, payload: CaseReplaceIn) -> dict[str, Any]:
    engine = get_engine(project_id)
    try:
        return engine.case_replace(payload.case_artifact_id, payload.instruction)
    except (StoreError, ConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/export")
def export(project_id: str, payload: ExportIn) -> dict[str, Any]:
    engine = get_engine(project_id)
    if payload.mode not in ("draft", "formal"):
        raise HTTPException(status_code=400, detail="mode 只能是 draft 或 formal")
    try:
        return engine.export_now(payload.mode)
    except HookFailure as exc:
        return JSONResponse(status_code=409, content={"ok": False, "reason": str(exc)})


@app.get("/api/projects/{project_id}/artifact-json/{artifact_id:path}")
def artifact_json(project_id: str, artifact_id: str) -> dict[str, Any]:
    store = get_engine(project_id).store
    revision_id = store.accepted_rev_id(artifact_id)
    if not revision_id:
        raise HTTPException(status_code=404, detail="not found")
    return store.get_revision(revision_id)["content"]


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    if not PROJECT_ID_RE.match(project_id):
        raise HTTPException(status_code=400, detail="非法项目 ID")
    engine = _engines.pop(project_id, None)
    if engine is not None:
        engine.close()
    target = config.project_dir(project_id)
    if target.exists():
        shutil.rmtree(target)
    return {
        "deleted": project_id,
        "note": "已删除托管输入、快照、产物、运行记录与缓存；用户上传前的原文件不受影响",
    }


@app.post("/api/projects/{project_id}/plan/rerun")
def rerun(project_id: str, payload: RerunIn) -> dict[str, Any]:
    engine = get_engine(project_id)
    try:
        return engine.rerun_from(payload.step_id)
    except PlanEditRejected as exc:
        return JSONResponse(status_code=409, content={"ok": False, "reason": str(exc)})


@app.get("/api/projects/{project_id}/file")
def project_file(project_id: str, path: str) -> FileResponse:
    if not PROJECT_ID_RE.match(project_id):
        raise HTTPException(status_code=400, detail="非法项目 ID")
    base = config.project_dir(project_id).resolve()
    target = Path(path).resolve()
    if target != base and base not in target.parents:
        raise HTTPException(status_code=403, detail="文件不在项目目录内")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(str(target))


@app.get("/api/projects/{project_id}/media")
def media_report(project_id: str) -> dict[str, Any]:
    store = get_engine(project_id).store

    def latest(artifact_id: str) -> Any:
        revisions = store.revisions_of(artifact_id)
        if not revisions:
            return None
        return store.get_revision(revisions[-1])["content"]

    requirements = latest("requirements") or {}
    sections = []
    for section in requirements.get("sections", []):
        section_id = section["section_id"]
        sections.append(
            {
                "section_id": section_id,
                "title": section.get("title"),
                "media_plan": latest(f"media_plan:{section_id}"),
                "animation_decisions": latest(f"animation_decisions:{section_id}"),
                "diagrams": (latest(f"diagrams:{section_id}") or {}).get("diagrams", []),
                "storyboard": latest(f"storyboard:{section_id}"),
            }
        )
    return {"sections": sections}


@app.post("/api/projects/{project_id}/slide-edit")
def slide_edit(project_id: str, payload: SlideEditIn) -> dict[str, Any]:
    engine = get_engine(project_id)
    patch = {key: value for key, value in payload.model_dump().items() if key != "slide" and value is not None}
    try:
        return engine.edit_slide(payload.slide, patch)
    except (PlanEditRejected, StoreError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/signoff")
def signoff(project_id: str, payload: SignoffIn) -> dict[str, Any]:
    engine = get_engine(project_id)
    try:
        return engine.record_signoff(
            payload.changeset_id, reviewer=payload.reviewer, basis=payload.basis, changes=payload.changes
        )
    except (PlanEditRejected, StoreError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/claim-review")
def claim_review(project_id: str, payload: ClaimReviewIn) -> dict[str, Any]:
    engine = get_engine(project_id)
    try:
        return engine.review_claim(
            payload.claim_id,
            payload.version,
            decision=payload.decision,
            reviewer=payload.reviewer,
            basis=payload.basis,
            source_id=payload.source_id,
            source_version=payload.source_version,
            quote=payload.quote,
            quote_location=payload.quote_location,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))
