# AGENTS.md — Psychology Education Build System (PEBS)

Spec: `psychology-education-skills-grok-build-requirements-v1.1.md` (V1.1). Current scope: M0–M4 (renderer available: LibreOffice at `C:\Program Files\LibreOffice`; ppt-foundry delivery check wired).

## Commands

- Install: `pip install -r requirements.txt`
- Test: `python -m pytest tests -q`
- Compile check: `python -m compileall -q pebs`
- Run server: `python -m pebs.cli serve --port 8710` (or `uvicorn pebs.server:app --port 8710`)
- Run one build from CLI: `python -m pebs.cli build --request "..." --project demo`
- Accept/reject: `python -m pebs.cli decide --project demo --changeset cs_xxx [--reject]`
- Rerun from a step: `python -m pebs.cli rerun --project demo --step gates`
- Delete project: `python -m pebs.cli delete --project demo --yes`
- Sandbox probe: `python -m pebs.cli sandbox --probe`
- Skill lifecycle: `python -m pebs.cli skills import <tar.gz-url> [--ref/--sha]` → `skills review` → `skills publish` → `skills pin` → `skills patch` → `skills enable`
- Skill regression: `python -m pebs.cli skills verify <name>` (records to `registry/regression.json`)
- Teacher sign-off: `python -m pebs.cli signoff --project demo --changeset cs_xxx --reviewer X --basis "..."`
- Human claim review: `python -m pebs.cli claim-review --project demo --claim clm_x --version 1 --decision supported|qualify|unsupported|disputed|human_review --reviewer X --basis "..."`
- Budget-capped run: `python -m pebs.cli build --project demo --max-model-calls N --request "..."`

## Hard rules (do not violate)

- Models/research providers unconfigured: steps report unavailable and stay BLOCKED/PENDING. Never fabricate research or model output.
- Research layer: Crossref/OpenAlex/Semantic Scholar/PubMed composite search with per-source logs in `search_logs`; optional bounded OA full-text fetch (`CompositeResearch.fetch_fulltext` → `fetch_pdf_text`, PDF magic/MIME/size checks) and Unpaywall lookup. Quote-grounded assessments only: a claim is SUPPORTED only when the model's quote is locatable in the stored snapshot; abstract-level sources always carry the "仅摘要" limitation note.
- External skill import NEVER executes any file (no install hooks/scripts). Only allowlisted source prefixes; path traversal/symlink/size/count checks enforced; unapproved or unpinned skills never enter runtime routing. Patch composition stops on upstream SHA mismatch instead of guessing.
- Candidate scripts run only through a verified sandbox adapter (`python -m pebs.cli sandbox --probe` must pass filesystem/network/memory controls); on hosts without a passing adapter, sandbox-only skills are denied and there is NO host fallback.
- Media: diagrams must pass SVG validation (no `<script>`, no `on*` attributes, no external refs; `viewBox` and `<text>` required). Animations require Animation Gate approval (`temporal_necessity`, static-alternative rejection, narration synchrony); storyboards always carry `rendered=false` — the system stops before video rendering and never calls video/TTS/ASR.
- PPTX: decks are composed only after Evidence Index + Production Planning Table; slides use native shapes/tables/notes (no flattened pages). Formal export requires a working renderer (LibreOffice/PowerPoint detected via `pebs.render.find_renderer`) plus generated thumbnails; without them G8 is NEEDS_REVIEW and export stays draft (83.4). Slide families live in `config/slide_families.yaml`; a user PPTX template (when uploaded) supplies masters/layouts. The upstream `ppt-foundry` skill (MIT, pinned `e6d47bebba83`) runs its `pptx_delivery_check.py` on every deck; its routes run only through the skill lifecycle.
- Student/PII (57.1/A20): uploaded materials are scanned before any external send; materials with identifiable student data are excluded from prompts and surfaced as "待脱敏"（never sent）. A build request that itself contains identifiable student data is rejected before the run starts. Explicit `/skill-name` invocations are validated against the allowlist and recorded in `skill_invocations`.
- Human review/sign-off (62.1): a claim can only become SUPPORTED by a human if the reviewer supplies a locatable quote from a stored source snapshot (no button-forcing); sign-off records require reviewer + basis and bind to the exact artifact revisions of an accepted changeset; accepted formal manifests carry current sign-offs. Budget exhaustion pauses the run (BLOCKED) and never fabricates output.
- Test fixtures must not enter formal outputs; runs carry `environment=test_fixture`, revisions/gate results record it, and formal export is blocked while fixture revisions are current. Draft exports must be labeled `草稿—未通过 QA`.
- Formal export requires all applicable G1–G8 gate results PASS and current (same target revisions + rules version). Draft exports must be labeled `草稿—未通过 QA`.
- Artifact revisions are immutable. Staleness propagates along dependency edges. Locked artifacts cannot be modified by a changeset.
- Credentials never enter prompts, project files, logs, Memory, or subagents. Provider keys are read from environment variables only. The `codex_exec` provider kind shells out to the locally logged-in Codex CLI (`codex exec --ephemeral --ignore-user-config`, read-only sandbox) and never reads or stores API keys; each call consumes the Codex account quota.
- External write actions (CNKI download, Zotero, publish) are out of scope for M1 and must be denied by the permission layer.
