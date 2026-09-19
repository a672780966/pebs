from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import providers
from .engine import Engine, PlanEditRejected
from .store import StoreError


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("pebs.server:app", host="127.0.0.1", port=args.port, log_level="info")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    status = providers.provider_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from .engine import ExplicitSkillDenied, PiiBlocked

    engine = Engine(args.project)
    template = Path(args.template) if args.template else None
    materials = [Path(p) for p in (args.material or [])]
    try:
        start = engine.start_build(
            args.request,
            template_path=template,
            material_paths=materials,
            budgets={
                key: value
                for key, value in {
                    "model_calls": args.max_model_calls,
                    "research_requests": args.max_research,
                    "run_seconds": args.max_seconds,
                }.items()
                if value
            }
            or None,
            planner_mode=args.planner,
        )
    except (PiiBlocked, ExplicitSkillDenied) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    run_id = start["run_id"]
    print(f"run {run_id} started; changeset {start['changeset_id']}")
    while True:
        status = engine.run_status(run_id)
        if status["run"]["status"] != "running":
            break
        time.sleep(1.0)
    for step in status["steps"]:
        line = f"{step['status']:<9} {step['step_id']:<16} {step.get('note') or step.get('error') or ''}"
        print(line)
    print(f"run status: {status['run']['status']}")
    print(f"changeset: {start['changeset_id']} (candidate; 用 serve 模式查看 Diff 并接受/拒绝)")
    return 0 if status["run"]["status"] == "succeeded" else 2


def cmd_accept(args: argparse.Namespace) -> int:
    engine = Engine(args.project)
    if args.reject:
        result = engine.reject(args.changeset)
    else:
        result = engine.accept(args.changeset)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "accepted" or result.get("status") == "rejected" else 1


def cmd_export(args: argparse.Namespace) -> int:
    engine = Engine(args.project)
    result = engine.export_now(args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


def cmd_rerun(args: argparse.Namespace) -> int:
    from .engine import PlanEditRejected

    engine = Engine(args.project)
    try:
        result = engine.rerun_from(args.step)
    except PlanEditRejected as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    status = engine.run_status(result["run_id"])
    for step in status["steps"]:
        print(f"{step['status']:<9} {step['step_id']:<16} {step.get('note') or step.get('error') or ''}")
    print(f"changeset: {result['changeset_id']}")
    return 0 if status["run"]["status"] == "succeeded" else 2


def cmd_resume(args: argparse.Namespace) -> int:
    engine = Engine(args.project)
    try:
        result = engine.resume(
            args.run,
            budgets={
                "model_calls": args.max_model_calls,
                "research_requests": args.max_research_requests,
                "run_seconds": args.run_seconds,
            },
        )
    except PlanEditRejected as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    status = engine.run_status(result["run_id"])
    for step in status["steps"]:
        print(f"{step['status']:<9} {step['step_id']:<16} {step.get('note') or step.get('error') or ''}")
    print(f"resumed: {', '.join(result['resumed']) or '-'}")
    return 0 if status["run"]["status"] == "succeeded" else 2


def cmd_delete(args: argparse.Namespace) -> int:
    import shutil

    from . import config

    target = config.project_dir(args.project)
    if not target.exists():
        print(f"project not found: {args.project}", file=sys.stderr)
        return 1
    if not args.yes:
        answer = input(f"确认删除项目 {args.project}（托管输入/产物/日志，不含上传前原件）? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("已取消")
            return 1
    shutil.rmtree(target)
    print(f"deleted: {args.project}")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    from . import skills_mgr

    command = args.skills_command
    try:
        if command == "import":
            record = skills_mgr.import_candidate(
                args.url, ref=args.ref, commit_sha=args.sha, name=args.name
            )
            print(json.dumps(record["source"], ensure_ascii=False, indent=2))
        elif command == "list":
            print(json.dumps(skills_mgr.list_skills(), ensure_ascii=False, indent=2))
        elif command == "review":
            decision = {"in_review": "IN_REVIEW", "approve": "APPROVED", "reject": "REJECTED"}[args.decision]
            record = skills_mgr.review(
                args.name,
                decision,
                reviewer=args.reviewer,
                evidence=args.evidence,
                adoption_decision=args.adoption,
            )
            print(json.dumps({"name": record["name"], "review_status": record["review_status"]}, ensure_ascii=False))
        elif command == "publish":
            record = skills_mgr.publish(args.name, version=args.version)
            print(json.dumps({"name": record["name"], "pinned_version": record["pinned_version"]}, ensure_ascii=False))
        elif command == "pin":
            record = skills_mgr.pin(args.name, args.version)
            print(json.dumps({"name": record["name"], "pinned_version": record["pinned_version"]}, ensure_ascii=False))
        elif command == "patch":
            record = skills_mgr.apply_patch(
                args.name,
                Path(args.dir),
                patch_version=args.patch_version,
                patch_reason=args.reason,
                reviewer=args.reviewer,
                tests=args.tests,
            )
            print(json.dumps({"name": record["name"], "patches": [p["patch_version"] for p in record["patches"]]}, ensure_ascii=False))
        elif command == "enable":
            record = skills_mgr.enable(args.name, enabled=not args.disable)
            print(json.dumps({"name": record["name"], "enabled_by_default": record["enabled_by_default"]}, ensure_ascii=False))
        elif command == "verify":
            result = skills_mgr.verify_skill(args.name)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["passed"] else 2
        else:
            print(f"unknown skills command: {command}", file=sys.stderr)
            return 1
    except skills_mgr.SkillError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_sandbox(args: argparse.Namespace) -> int:
    import tempfile
    from dataclasses import asdict
    from pathlib import Path

    from . import sandbox

    if getattr(args, "exec_command", None):
        workdir = Path(tempfile.mkdtemp(prefix="pebs_sandbox_"))
        try:
            result = sandbox.run_sandboxed(["sh", "-c", args.exec_command], workdir=workdir)
        except sandbox.SandboxUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({**result, "workdir": str(workdir)}, ensure_ascii=False, indent=2))
        return 0 if result["returncode"] == 0 else 2
    reports = sandbox.probe_all() if args.probe else [sandbox.load_report()]
    print(json.dumps([asdict(report) for report in reports], ensure_ascii=False, indent=2))
    return 0


def cmd_signoff(args: argparse.Namespace) -> int:
    engine = Engine(args.project)
    try:
        content = engine.record_signoff(
            args.changeset, reviewer=args.reviewer, basis=args.basis, changes=args.changes or ""
        )
    except Exception as exc:  # noqa: BLE001 - CLI surfaces the reason
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(content, ensure_ascii=False, indent=2))
    return 0


def cmd_claim_review(args: argparse.Namespace) -> int:
    engine = Engine(args.project)
    try:
        result = engine.review_claim(
            args.claim,
            args.version,
            decision=args.decision,
            reviewer=args.reviewer,
            basis=args.basis,
            source_id=args.source,
            source_version=args.source_version,
            quote=args.quote or "",
            quote_location=args.quote_location or "",
        )
    except Exception as exc:  # noqa: BLE001 - CLI surfaces the reason
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_conversation(args: argparse.Namespace) -> int:
    engine = Engine(args.project)
    try:
        result = engine.conversation_edit(args.message, execute=not args.plan_only)
    except PlanEditRejected as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    patch = {
        "plan_id": result.get("plan_id"),
        "intent": result.get("intent", {}).get("intent"),
        "affected_artifacts": result.get("affected_artifacts", []),
        "locked_artifacts": result.get("locked_artifacts", []),
        "step_order": result.get("step_order", []),
    }
    print(json.dumps(patch, ensure_ascii=False, indent=2))
    if args.plan_only:
        print("仅生成 Patch Plan（未执行）；去掉 --plan-only 可执行局部重建")
        return 0
    print(f"run {result.get('run_id')} · {result.get('run_status')}")
    print(f"changeset {result.get('changeset_id')}（用 decide 接受或拒绝）")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import report as report_mod
    from .benchmark import runner

    if args.submit_eval:
        from .benchmark import evaluation as evaluation_mod

        if not args.project:
            print("error: --submit-eval 需要 --project", file=sys.stderr)
            return 1
        engine = Engine(args.project)
        payload = report_mod.load_worksheet(Path(args.submit_eval))
        try:
            content = evaluation_mod.record(engine, payload, run_id=payload.get("run_id", ""), mode=payload.get("mode", ""))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(
            json.dumps(
                {
                    "reviewer": content["reviewer"],
                    "overall": content["overall"],
                    "edit_ratio": content["edit_ratio"],
                    "evidence_errors": content["evidence_errors"],
                    "routing_errors": content["routing_errors"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.report:
        path = report_mod.write_report()
        worksheets = report_mod.write_worksheets()
        print(path)
        print(f"worksheets: {len(worksheets)} 份（benchmarks/reports/worksheets/）")
        return 0
    case_ids = [item.strip() for item in (args.cases or "A,B,C,D,E,F,G,H").split(",") if item.strip()]
    modes = [item.strip() for item in (args.modes or "dynamic").split(",") if item.strip()]
    budgets = {
        key: value
        for key, value in {
            "model_calls": args.max_model_calls,
            "research_requests": args.max_research,
            "run_seconds": args.max_seconds,
        }.items()
        if value
    }
    failures = 0
    for case_id in case_ids:
        for mode in modes:
            try:
                record = runner.run_case(
                    case_id,
                    mode=mode,
                    accept=not args.no_accept,
                    budgets=budgets or None,
                    extra_skills=[item.strip() for item in args.skills.split(",") if item.strip()],
                    experiment=args.experiment,
                )
            except Exception as exc:  # noqa: BLE001 - benchmark harness reports and continues
                failures += 1
                print(f"{case_id}/{mode}: ERROR {exc}", file=sys.stderr)
                continue
            issues = (record.get("automatic_issues") or {}).get("issues", [])
            status = record.get("run_status")
            if status != "succeeded" or issues:
                failures += 1
            print(f"{case_id}/{mode}: {status} · issues={len(issues)} · {record.get('run_dir', '')}")
    path = report_mod.write_report()
    print(f"report: {path}（{len(case_ids)} cases × {len(modes)} modes，异常 {failures}）")
    return 1 if failures and args.strict else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pebs", description="Psychology Education Build System (M0+M1)")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="启动本机 Web 工作台")
    serve.add_argument("--port", type=int, default=8710)
    serve.set_defaults(func=cmd_serve)

    status = sub.add_parser("status", help="查看 Provider 配置状态")
    status.set_defaults(func=cmd_status)

    build = sub.add_parser("build", help="按请求运行一次构建")
    build.add_argument("--request", required=True)
    build.add_argument("--project", required=True)
    build.add_argument("--template")
    build.add_argument("--material", action="append")
    build.add_argument("--max-model-calls", type=int)
    build.add_argument("--max-research", type=int)
    build.add_argument("--max-seconds", type=int)
    build.add_argument("--planner", choices=["static", "dynamic"])
    build.set_defaults(func=cmd_build)

    signoff = sub.add_parser("signoff", help="教师复核签署（记录依据与被复核版本）")
    signoff.add_argument("--project", required=True)
    signoff.add_argument("--changeset", required=True)
    signoff.add_argument("--reviewer", required=True)
    signoff.add_argument("--basis", required=True)
    signoff.add_argument("--changes", default="")
    signoff.set_defaults(func=cmd_signoff)

    claim_review = sub.add_parser("claim-review", help="人工复核 Claim（不能无证据强制批准）")
    claim_review.add_argument("--project", required=True)
    claim_review.add_argument("--claim", required=True)
    claim_review.add_argument("--version", type=int, required=True)
    claim_review.add_argument(
        "--decision", required=True, choices=["supported", "qualify", "unsupported", "disputed", "human_review"]
    )
    claim_review.add_argument("--reviewer", required=True)
    claim_review.add_argument("--basis", required=True)
    claim_review.add_argument("--source")
    claim_review.add_argument("--source-version", type=int)
    claim_review.add_argument("--quote", default="")
    claim_review.add_argument("--quote-location", default="")
    claim_review.set_defaults(func=cmd_claim_review)

    dec = sub.add_parser("decide", help="接受或拒绝候选变更集")
    dec.add_argument("--project", required=True)
    dec.add_argument("--changeset", required=True)
    dec.add_argument("--reject", action="store_true")
    dec.set_defaults(func=cmd_accept)

    exp = sub.add_parser("export", help="导出草稿或正式文件")
    exp.add_argument("--project", required=True)
    exp.add_argument("--mode", choices=["draft", "formal"], default="draft")
    exp.set_defaults(func=cmd_export)

    rerun = sub.add_parser("rerun", help="从指定步骤起重跑（使用已接受的上游产物）")
    rerun.add_argument("--project", required=True)
    rerun.add_argument("--step", required=True)
    rerun.set_defaults(func=cmd_rerun)

    resume = sub.add_parser("resume", help="调整预算并续跑被预算阻塞的步骤（规格 84 节）")
    resume.add_argument("--project", required=True)
    resume.add_argument("--run", required=True)
    resume.add_argument("--max-model-calls", type=int, default=None)
    resume.add_argument("--max-research-requests", type=int, default=None)
    resume.add_argument("--run-seconds", type=int, default=None)
    resume.set_defaults(func=cmd_resume)

    conversation = sub.add_parser("conversation", help="用自然语言做局部修改（生成 Patch Plan 并只重建受影响产物）")
    conversation.add_argument("--project", required=True)
    conversation.add_argument("--message", required=True)
    conversation.add_argument("--plan-only", action="store_true")
    conversation.set_defaults(func=cmd_conversation)

    bench = sub.add_parser("benchmark", help="M6 Golden Benchmark：A–G/H × direct/builtin/dynamic 并生成对比报告")
    bench.add_argument("--cases", default="A,B,C,D,E,F,G,H")
    bench.add_argument("--modes", default="dynamic")
    bench.add_argument("--no-accept", action="store_true")
    bench.add_argument("--report", action="store_true", help="只根据已有 runs 生成对比报告与教师评分工作表")
    bench.add_argument("--submit-eval", default="", help="回收教师填写的工作表 YAML（需配合 --project）")
    bench.add_argument("--project", default="", help="--submit-eval 的目标项目")
    bench.add_argument("--strict", action="store_true", help="存在失败/自动问题时以非零退出")
    bench.add_argument("--max-model-calls", type=int, default=0)
    bench.add_argument("--max-research", type=int, default=0)
    bench.add_argument("--max-seconds", type=int, default=0)
    bench.add_argument("--skills", default="", help="§46 实验：追加显式 /skill-name（逗号分隔），用于 External only / Hybrid 对照")
    bench.add_argument("--experiment", default="", help="实验标签（写入 run.json）")
    bench.set_defaults(func=cmd_benchmark)

    delete = sub.add_parser("delete", help="删除本机项目（托管数据）")
    delete.add_argument("--project", required=True)
    delete.add_argument("--yes", action="store_true")
    delete.set_defaults(func=cmd_delete)

    skills = sub.add_parser("skills", help="外部 Skill 管理（隔离下载/审查/发布/补丁/回归）")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)
    skill_import = skills_sub.add_parser("import")
    skill_import.add_argument("url")
    skill_import.add_argument("--ref")
    skill_import.add_argument("--sha")
    skill_import.add_argument("--name")
    skills_sub.add_parser("list")
    skill_review = skills_sub.add_parser("review")
    skill_review.add_argument("name")
    skill_review.add_argument("--decision", required=True, choices=["in_review", "approve", "reject"])
    skill_review.add_argument("--reviewer")
    skill_review.add_argument("--evidence")
    skill_review.add_argument("--adoption", choices=["ADOPT", "PATCH", "REFERENCE_ONLY", "DISABLED"])
    skill_publish = skills_sub.add_parser("publish")
    skill_publish.add_argument("name")
    skill_publish.add_argument("--version")
    skill_pin = skills_sub.add_parser("pin")
    skill_pin.add_argument("name")
    skill_pin.add_argument("--version", required=True)
    skill_patch = skills_sub.add_parser("patch")
    skill_patch.add_argument("name")
    skill_patch.add_argument("--dir", required=True)
    skill_patch.add_argument("--patch-version", required=True)
    skill_patch.add_argument("--reason", required=True)
    skill_patch.add_argument("--reviewer", required=True)
    skill_patch.add_argument("--tests")
    skill_enable = skills_sub.add_parser("enable")
    skill_enable.add_argument("name")
    skill_enable.add_argument("--disable", action="store_true")
    skill_verify = skills_sub.add_parser("verify")
    skill_verify.add_argument("name")
    skills.set_defaults(func=cmd_skills)

    sandbox_parser = sub.add_parser("sandbox", help="沙箱适配器探测（通过验证才允许执行候选脚本）")
    sandbox_parser.add_argument("--probe", action="store_true", help="重新探测并写回报告")
    sandbox_parser.add_argument("--exec", dest="exec_command", help="在验证通过的沙箱中执行 shell 命令（候选脚本唯一允许路径）")
    sandbox_parser.set_defaults(func=cmd_sandbox)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (StoreError, PlanEditRejected) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
