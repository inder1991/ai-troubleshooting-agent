---
owner: '@inder'
---
# Harness extraction

Sprint H.3 extracts the harness substrate from DebugDuck into a
standalone `github.com/<owner>/ai-harness` repo so any new project can
adopt the harness without depending on DebugDuck's working tree.

## Files in this directory

- `build_manifest.py` — walks the repo, writes `manifest.txt` (one path
  per line) listing every file that goes into the standalone repo.
- `manifest.txt` — checked-in output of `build_manifest.py`. Re-generate
  whenever a new harness file lands.
- `extract.sh` — one-shot extraction script. Mirrors DebugDuck to
  `/tmp/ai-harness-mirror`, applies the manifest via `git filter-repo`
  (preserving authorship + history), moves the result to
  `/tmp/ai-harness`, and seeds a placeholder README.

## Procedure

The extraction is a one-time operation. Steps requiring external
authorization (GitHub repo creation, push, release publish) are NOT
scripted — invoke them manually so a misconfigured ref or wrong owner
doesn't accidentally publish.

### 1. Refresh the manifest (H.3.1)

```bash
python3 tools/extraction/build_manifest.py
```

### 2. Run the extraction (H.3.2)

```bash
brew install git-filter-repo   # one-time
bash tools/extraction/extract.sh
```

The script aborts if `git-filter-repo` is missing. Re-running wipes
`/tmp/ai-harness-mirror` and `/tmp/ai-harness` first; safe to invoke
repeatedly.

### 3. Smoke-test the extracted repo

```bash
cd /tmp/ai-harness
python3 -m pytest tests/harness/ -v 2>&1 | tail -10
```

Expected: every harness self-test still green (the extracted repo
passes its own validation).

### 4. Push to GitHub + tag (H.3.3 — manual)

```bash
cd /tmp/ai-harness
gh repo create <owner>/ai-harness --private \
    --description "AI development harness — rules + checks + generators"

git remote add origin git@github.com:<owner>/ai-harness.git
git push -u origin main

git tag -a v1.0.0 -m "ai-harness v1.0.0 — initial release

Seven-sprint substrate for AI-assisted development:
  H.0a: schema & substrate (loader, Makefile, root CLAUDE.md)
  H.0b: stack-foundation scaffolding (Q5/Q8/Q9/Q11–Q19 configs)
  H.1a: backend basic checks (Q7–Q12 + 4 self-learning invariants)
  H.1b: frontend checks (Q1–Q6, Q14, Q18 + meta-validator)
  H.1c: cross-stack policy checks (Q13, Q15, Q16, Q17)
  H.1d: typecheck + harness self-tests + baseline buffer
  H.2:  18 generators + run_harness_regen + Claude Code hook + init_harness bootstrap

24 deterministic checks, 18 deterministic generators, 25 H-rules,
19 Q-decisions."
git push origin v1.0.0

gh release create v1.0.0 \
    --title "v1.0.0 — ai-harness GA" \
    --notes-file <(git tag -l --format='%(contents)' v1.0.0)
```

## What's left out of the carve

- `/.harness/baselines/*.json` — repo-specific grandfathered debt; the
  consumer rebaselines against its own code.
- `/.harness/generated/*.json` — auto-derived; the consumer regenerates
  via `make harness`.
- `__pycache__`, `.venv`, `node_modules`, `.pytest_cache` — runtime
  artifacts.

These exclusions are encoded in `build_manifest.py::EXCLUDE_TOKENS`.
