# AI Harness — Design & Implementation Plan

**Status:** Finalized 2026-04-26
**Scope:** Repo-level harness for AI-assisted development. Serves both Consumer 1 (human contributors using Claude Code / Cursor / Copilot in their IDE) and Consumer 2 (autonomous CI agents that propose PRs without a human in the loop).
**Approach:** Test-Driven Development (red → green → refactor) on every story. Harness self-tests its own checks (Rule H-24).
**Cadence:** 2-week sprints. 3 sprints. ~6 weeks elapsed.

---

## 0. Assumptions baked into this plan

| # | Assumption | Default applied |
|---|---|---|
| 1 | Team capacity | 2 engineers (1 backend lead, 1 full-stack) at ~32 pts/sprint, 80% load. |
| 2 | Language | All harness scripts in Python (matches backend). Calls into TS tooling via subprocess where needed. |
| 3 | Existing tooling | `ruff`, `mypy`, `pytest` for backend; `eslint`, `prettier`, `tsc`, `vitest` for frontend. Harness wraps these, doesn't replace. |
| 4 | CI | None today. Local-first composite enforcement (H-14, H-18). CI becomes an upgrade path running the same `make validate` (H-20). |
| 5 | Pre-commit framework | Plain git hook (no `pre-commit` framework dependency) for v1 to keep onboarding zero-step. |

---

## 1. Locked architectural baseline

### 1.1 Decisions Q1–Q4

| Q | Decision |
|---|---|
| **Q1 — Primary "AI" consumer** | A + B both. Human contributors using AI in IDE *and* background CI agents that propose PRs autonomously. Same harness, two consumers. |
| **Q2 — Failure modes prioritized** | A (convention violations) + B (architecturally wrong choices) + G (subtle invariant breaks). Deferred: C (verify-before-claim), D (test discovery), E (entropy), F (cross-session memory). |
| **Q3 — Rule architecture** | Hybrid E++. Root `CLAUDE.md` (≤70 lines) + per-directory `CLAUDE.md` + scoped `.harness/*.md` cross-cutting + `.harness/generated/` machine-readable truth. Front-matter on every file. Deterministic loader. Explicit precedence. |
| **Q4 — Enforcement** | Local-first composite. `make validate` is the single contract. AI self-validation (primary), pre-commit hook (safety net), CI as upgrade path. |

### 1.2 Inviolable harness rules (H-1 through H-25)

#### Rule architecture (Q3)

| # | Rule |
|---|---|
| **H-1** | Root `CLAUDE.md` ≤ 70 lines. Behavioral guardrails only. CI-enforced size cap. |
| **H-2** | Per-directory `CLAUDE.md` captures local intelligence. Lives next to code it governs. Owned by area lead. Loaded only when AI works in that subtree. |
| **H-3** | `.harness/*.md` holds cross-cutting rules. Each declares scope via `applies_to` glob front-matter. Loaded when matching files are touched. |
| **H-4** | `.harness/generated/` is auto-derived from code. Owned by generators, never hand-edited. Regenerated via `make harness`. |
| **H-5** | Precedence: **Root rules < Cross-cutting harness < Generated facts < Directory rules**. Local-most wins. |
| **H-6** | Ownership is explicit. Every rule file declares `owner:` in front-matter. Unclear ownership = invalid rule. |
| **H-7** | Progressive rollout — week 1 root + 2-3 directory files; week 2 cross-cutting; week 3 generated. No big-bang drop. |
| **H-8** | Rules reduce prompting overhead, not just enforce quality. The test: if removing a rule changes how engineers prompt, it's working. |

#### Rule contract — E++ refinements

| # | Rule |
|---|---|
| **H-9** | Every rule file carries YAML front-matter: `scope`, `owner`, `priority`, `applies_to` (glob list for `.harness/*.md`), `type`. |
| **H-10** | Generated rules are structured data (JSON / YAML), not markdown. Parseable by any consumer; readable by Claude. |
| **H-11** | Reference loading algorithm is documented in root `CLAUDE.md` under a "Rule Loading Contract" section. |
| **H-12** | Conflicts surface as lint errors, not silent overrides. The loader detects and reports rule contradictions. |
| **H-13** | Loader is a real script (`tools/load_harness.py`), not "just walk the tree." Same loader is used by Consumer 1's IDE setup, Consumer 2's autonomous agents, and the validator. |

#### Enforcement spine — Local-first composite (Q4)

| # | Rule |
|---|---|
| **H-14** | `make validate` is the harness contract. Single entry point. Same command runs in five contexts (AI loop, terminal, pre-commit, CI, autonomous agent). |
| **H-15** | Root `CLAUDE.md` mandates AI self-validation. Every AI session must run `make validate` before declaring task complete. Failure → analyze → fix → re-run. Loop until pass or explicit blocker. |
| **H-16** | Validation output is structured: `[SEVERITY] file=<path>:<line> rule=<rule-id> message="<what's wrong>" suggestion="<concrete fix>"`. Parseable by AI for self-correction. |
| **H-17** | Two validation tiers. `make validate-fast` = lint + typecheck + custom rule checks (under 30 seconds). `make validate-full` = + tests + heavy checks (minutes). AI uses fast loop; full runs before commit. |
| **H-18** | Pre-commit hook (recommended, opt-in via `make harness-install`) wraps `make validate-fast`. Bypassable but adds safety net. |
| **H-19** | Discipline is the temporary CI. Until CI lands, contributor checklist documented in `CONTRIBUTING.md`. |
| **H-20** | CI is the upgrade path, not the blocker. When CI is added, it runs the existing `make validate` verbatim. No rewrites. |
| **H-21** | Every rule has a programmatic check. A rule with no validator is documentation, not a rule. Either build the check or move the rule to docs. |

#### Quality discipline (from 15 best-practice principles)

| # | Rule |
|---|---|
| **H-22** | Rules must be specific and measurable. No vague rules ("write clean code," "optimize performance"). Every rule expressible as a yes/no check with a concrete violation criterion. |
| **H-23** | Validator output includes a `suggestion` field, not just a message. The AI uses the suggestion to self-correct without re-thinking the fix. |
| **H-24** | The harness has its own test suite under `tests/harness/`. Every check has a "violation fixture" + "compliant fixture" pair. The harness can never silently rot. |
| **H-25** | Design for failure first. Every check, generator, and loader function answers in its docstring: *what if input is missing? what if input is malformed? what if upstream check failed?* |

---

## 2. Architecture

### 2.1 File layout

```
debugduck/                                ← repo root
├── CLAUDE.md                             ← root behavioral rules (≤70 lines)
├── AGENTS.md                             ← symlink → CLAUDE.md (cross-vendor alias)
├── .cursorrules                          ← pointer: "see CLAUDE.md and CLAUDE.md in subdirectories"
├── Makefile                              ← single contract entry point
├── CONTRIBUTING.md                       ← human discipline checklist (H-19)
│
├── tools/
│   ├── load_harness.py                   ← THE rule loader (H-13)
│   ├── run_validate.py                   ← orchestrator for `make validate*`
│   ├── run_harness_regen.py              ← orchestrator for `make harness`
│   └── install_pre_commit.sh             ← `make harness-install` target
│
├── .harness/
│   ├── README.md                         ← how the harness works (for humans)
│   ├── checks/                           ← custom rule validators (one file per rule)
│   │   ├── _common.py                    ← shared output formatting + file walking
│   │   ├── safe_bounds.py
│   │   ├── storage_isolation.py
│   │   ├── no_duck_tokens.py
│   │   ├── audit_emission.py
│   │   ├── append_only_spine.py
│   │   ├── contract_typed.py
│   │   ├── todo_in_prod.py
│   │   ├── owners_present.py             ← harness self-check
│   │   ├── precedence_no_conflicts.py    ← harness self-check
│   │   └── claude_md_size_cap.py         ← enforces root ≤ 70 lines (H-1)
│   ├── generators/                       ← scripts producing generated/
│   │   ├── _common.py
│   │   ├── extract_contract_names.py
│   │   ├── extract_valid_tokens.py
│   │   ├── extract_lint_rules.py
│   │   └── extract_agent_manifests.py
│   ├── generated/                        ← machine-readable truth (NEVER hand-edited)
│   │   ├── README.md                     ← warns "DO NOT EDIT"
│   │   ├── valid_contract_names.json
│   │   ├── valid_wr_tokens.json
│   │   ├── registered_lint_rules.json
│   │   └── registered_agent_manifests.json
│   ├── python-style.md                   ← cross-cutting (applies_to: backend/**/*.py)
│   ├── frontend-tokens.md                ← cross-cutting (applies_to: frontend/src/**/*.{tsx,ts,css})
│   ├── security.md                       ← cross-cutting (applies_to: backend/src/api/**/*.py)
│   ├── accessibility.md                  ← cross-cutting (applies_to: frontend/src/**/*.{tsx,jsx})
│   └── api-contracts.md                  ← cross-cutting
│
├── backend/
│   ├── CLAUDE.md                         ← backend-wide rules
│   └── src/
│       ├── CLAUDE.md
│       ├── api/CLAUDE.md
│       ├── agents/CLAUDE.md
│       └── learning/CLAUDE.md
│
├── frontend/
│   ├── CLAUDE.md                         ← frontend-wide rules
│   └── src/
│       └── components/Investigation/CLAUDE.md
│
└── tests/
    └── harness/                          ← harness's own test suite (H-24)
        ├── checks/
        │   ├── test_safe_bounds.py
        │   ├── test_storage_isolation.py
        │   └── ...
        ├── generators/
        │   └── ...
        ├── fixtures/
        │   ├── violation/                ← "this file violates rule X"
        │   └── compliant/                ← "this file complies with rule X"
        └── test_loader.py                ← tests for tools/load_harness.py
```

### 2.2 Validation tiers

| Tier | Command | Time budget | Contains |
|---|---|---|---|
| **Fast** | `make validate-fast` | < 30s | Syntax check, lint, typecheck, custom rule checks, harness self-checks |
| **Full** | `make validate-full` (alias `make validate`) | minutes | All of fast + unit tests + integration tests + heavy audits |

AI inner loop uses `validate-fast`. Pre-commit hook uses `validate-fast`. Manual pre-commit + CI use `validate-full`.

### 2.3 Discovery flow

When AI opens to work on `<file>`:

```
tools/load_harness.py --target <file>
   ├── 1. Load root CLAUDE.md
   ├── 2. Walk up directory: collect every CLAUDE.md from <file>'s dir up to root
   ├── 3. Load all .harness/generated/*.json
   ├── 4. Match .harness/*.md using `applies_to` patterns against <file>
   └── 5. Resolve conflicts using precedence (Local > Generated > Cross-cutting > Root)
   → outputs single concatenated context block, precedence-ordered
```

### 2.4 Output format (binding for all checks)

Every check emits one line per violation:

```
[SEVERITY] file=<path>:<line> rule=<rule-id> message="<what's wrong>" suggestion="<concrete fix>"
```

`SEVERITY` ∈ `{ERROR, WARN, INFO}`. ERROR fails `make validate*`. WARN/INFO are reported but non-blocking.

### 2.5 Five execution contexts

| Context | What runs | Trigger | On failure |
|---|---|---|---|
| **AI session loop (Consumer 1)** | `make validate-fast` | Claude Code itself, before declaring done | AI parses output, fixes, re-runs |
| **Your terminal** | `make validate-full` | Manual, before commit | You see output, fix, re-run |
| **Pre-commit hook** | `make validate-fast` | Git, on `git commit` | Commit blocked (bypassable with `--no-verify`) |
| **CI (future)** | `make validate-full` | GitHub Actions on PR push | PR cannot merge (NOT bypassable) |
| **Autonomous agent (Consumer 2)** | `make validate-full` | Agent's own loop | Agent parses output, fixes, retries (bounded) |

---

## 3. Foundations

### 3.1 Definition of Ready (DoR)

Story is "Ready" when:
- [ ] Acceptance criteria written as Given/When/Then.
- [ ] Test plan lists at least one failing-first test per acceptance criterion.
- [ ] Dependencies on other stories explicitly named.
- [ ] Estimate (1, 2, 3, 5, 8) agreed.
- [ ] If story adds a new check: violation fixture + compliant fixture identified (H-24).

### 3.2 Definition of Done (DoD)

Story is "Done" when:
- [ ] Every AC has a passing test.
- [ ] Test pyramid respected: unit > integration > e2e.
- [ ] Cyclomatic complexity ≤ 10 per function.
- [ ] Inviolable Rules H-1 through H-25 not violated (PR checklist).
- [ ] If story added a check: harness self-test (violation fixture fires, compliant fixture is silent) passes.
- [ ] Output of any new check conforms to H-16 / H-23 format.
- [ ] No `# TODO` comments in production paths.

### 3.3 TDD discipline (binding)

1. **Red** — failing test first. Commit: `test(red): <story-id> — <test name>`.
2. **Green** — minimum production code to pass. Commit: `feat(green): <story-id> — <change>`.
3. **Refactor** — improve structure without changing behavior. Commit: `refactor: <story-id> — <description>`.

PRs without a preceding red commit are rejected at code review.

### 3.4 Story-point legend

| Points | Meaning |
|---|---|
| 1 | Trivial, < 0.5 day |
| 2 | Single function or schema change, ~0.5–1 day |
| 3 | Multi-file change, no architectural decisions, ~1–2 days |
| 5 | Cross-component change, some design needed, ~2–4 days |
| 8 | Significant feature, ~4–8 days; if higher, split |

Sprint capacity per engineer: ~13 pts. Team of 2 = ~26 pts/sprint at 80% load.

### 3.5 Cross-cutting non-negotiables

- **Every check has a violation+compliant fixture pair** (H-24). No check ships without both.
- **Output format is binding** (H-16, H-23). Linter `tools/check_output_format.py` runs in `make validate-fast` and fails any check whose output doesn't conform.
- **Performance budget:** `make validate-fast` total wall time < 30 seconds on a 2024-era laptop. Budget violation = sprint blocker.

---

## 4. Sprint H.0 — Scaffold (2 weeks · 26 pts)

**Sprint goal:** The skeleton ships. `make validate-fast` runs, finds zero violations because no custom checks exist yet, but the contract is in place. Root `CLAUDE.md` + 2-3 directory rules. Pre-commit hook installable. Harness self-tests bootstrapped.

**Sprint exit criteria:**
- `make validate-fast` runs in < 5 seconds (no custom checks yet, so just lint + typecheck).
- Root `CLAUDE.md` + `backend/CLAUDE.md` + `backend/src/learning/CLAUDE.md` + `frontend/CLAUDE.md` exist and pass front-matter validation.
- `tools/load_harness.py` correctly walks the tree and outputs a context block for any target file.
- `make harness-install` installs the pre-commit hook idempotently.
- Harness self-test infrastructure exists (`tests/harness/` directory, fixture loader, assertion helpers).
- AGENTS.md alias and `.cursorrules` pointer in place.

| ID | Title | Pts |
|---|---|---|
| H.0.1 | Repo scaffolding — `Makefile` + directory skeleton | 3 |
| H.0.2 | Root `CLAUDE.md` (≤70 lines) with Rule Loading Contract section | 3 |
| H.0.3 | `tools/load_harness.py` — deterministic loader | 5 |
| H.0.4 | `tools/run_validate.py` — orchestrator wrapping ruff/mypy/eslint/tsc | 5 |
| H.0.5 | First per-directory CLAUDE.md files (backend/, backend/src/learning/, frontend/) | 3 |
| H.0.6 | YAML front-matter validator + harness self-check `claude_md_size_cap.py` | 3 |
| H.0.7 | `make harness-install` — pre-commit hook installer | 2 |
| H.0.8 | Harness test infrastructure (`tests/harness/` skeleton + fixture pattern) | 5 |
| H.0.9 | AGENTS.md alias + `.cursorrules` pointer | 1 |
| H.0.10 | `CONTRIBUTING.md` — human discipline checklist | 1 |

**Total: 31 pts** (slight overshoot — pull H.0.10 to next sprint if capacity tight)

### Story H.0.1 — Repo scaffolding

**As a** harness builder, **I want** the directory skeleton + `Makefile` in place **so that** every subsequent story has a known home.

**AC:**
- AC-1: `Makefile` exists with targets: `validate-fast`, `validate-full`, `validate` (alias for full), `harness`, `harness-install`. Each target prints "TODO" and exits 0 for now.
- AC-2: Directories created: `tools/`, `.harness/`, `.harness/checks/`, `.harness/generators/`, `.harness/generated/`, `tests/harness/`.
- AC-3: `.harness/README.md` written explaining the layout for human readers.
- AC-4: `.harness/generated/README.md` warns "DO NOT EDIT — regenerated by `make harness`."

**Test plan:**
1. Red: `tests/harness/test_skeleton.py::test_makefile_targets_exist` — assert `make -n validate-fast` exits 0.
2. Green: write Makefile.
3. Red: `test_required_directories_exist`.
4. Green: `mkdir -p` in scaffolding.

**Deps:** none.

### Story H.0.2 — Root `CLAUDE.md`

**As an** AI session, **when** I open in this repo, **I want** to read a tiny root file with the always-relevant rules **so that** I behave correctly without re-asking conventions.

**AC:**
- AC-1: Root `CLAUDE.md` exists and is ≤ 70 lines (excluding YAML front-matter).
- AC-2: Contains a "Rule Loading Contract" section that documents the 5-step loader algorithm.
- AC-3: Contains the AI self-validation mandate (H-15).
- AC-4: Contains the precedence rule (H-5).
- AC-5: YAML front-matter declares `scope: repo`, `owner: @platform-team`, `priority: highest`.

**Test plan:**
1. Red: `tests/harness/test_root_claude_md.py::test_root_exists`.
2. Green: write root file.
3. Red: `test_size_under_70_lines` (excluding front-matter).
4. Green: trim if needed.
5. Red: `test_has_rule_loading_contract_section`.
6. Green: add section.
7. Red: `test_front_matter_required_fields`.
8. Green: write front-matter.

**Deps:** H.0.1.

### Story H.0.3 — `tools/load_harness.py`

**As** Consumer 2 (autonomous agent), **I want** a deterministic Python loader that returns the rules for a given file path **so that** I have the same context as Consumer 1's IDE-AI.

**AC:**
- AC-1: `python tools/load_harness.py --target <path>` returns a structured dict: `{root, directory_rules, cross_cutting, generated, precedence_order}`.
- AC-2: Root rules always included.
- AC-3: Directory rules collected by walking up from `<target>` to repo root.
- AC-4: Cross-cutting rules included only if their `applies_to` glob matches `<target>`.
- AC-5: All `.harness/generated/*.json` always loaded.
- AC-6: Conflicting rules (same key, different value, overlapping scope) raise `LoaderConflictError` with both source files cited.
- AC-7: Loader is pure (no I/O beyond reading input files; no logging side effects to stdout in `--quiet` mode).

**Test plan:**
1. Red: `test_loader_returns_root_for_any_target`.
2. Green: minimal loader returning root only.
3. Red: `test_loader_walks_directory_tree`.
4. Green: walk-up logic.
5. Red: `test_loader_glob_matches_cross_cutting`.
6. Green: glob matching using `pathlib.PurePath.match`.
7. Red: `test_loader_loads_generated`.
8. Green: read all JSON in `generated/`.
9. Red: `test_loader_raises_on_conflict`.
10. Green: conflict detector with explicit error.
11. Refactor: extract path-walking and glob-matching into separate testable functions.

**Deps:** H.0.1, H.0.2.

### Story H.0.4 — `tools/run_validate.py`

**As a** contributor (or AI session), **I want** `make validate-fast` to run lint + typecheck across both stacks and emit structured output **so that** errors are uniform and parseable.

**AC:**
- AC-1: `python tools/run_validate.py --fast` runs ruff, mypy, eslint, tsc in order.
- AC-2: Each tool's output is normalized into the H-16 format: `[SEVERITY] file=... rule=... message=... suggestion=...`.
- AC-3: Suggestion field is auto-populated from tool docs where available; "see <rule-id> docs" fallback otherwise.
- AC-4: Aggregate exit code is 0 only if all tools pass; 1 if any failed.
- AC-5: `--fast` mode skips tests; `--full` includes pytest + vitest.
- AC-6: Performance budget: `--fast` mode wall time < 30 seconds on the harness's own test suite. Asserted by a meta-test.

**Test plan:**
1. Red: `test_run_validate_fast_exits_zero_on_clean_repo`.
2. Green: minimal orchestrator.
3. Red: `test_run_validate_emits_structured_output_on_lint_violation` — fixture file with deliberate ruff violation.
4. Green: ruff invocation + output normalizer.
5. Red: `test_run_validate_includes_suggestion_field`.
6. Green: extend normalizer.
7. Red: `test_run_validate_fast_under_30_seconds` (perf assertion).
8. Green: parallelize tool invocations if needed.

**Deps:** H.0.1.

### Story H.0.5 — First per-directory CLAUDE.md files

**As an** area lead, **I want** scoped rules for my code area **so that** AI working there knows local conventions without loading unrelated rules.

**AC:**
- AC-1: `backend/CLAUDE.md` exists with Pydantic 2 + pytest + StorageGateway conventions.
- AC-2: `backend/src/learning/CLAUDE.md` exists with the 25 inviolable design rules from the self-learning plan summarized.
- AC-3: `frontend/CLAUDE.md` exists with wr-* token + war-room invariants.
- AC-4: Each file has YAML front-matter (`scope`, `owner`, `priority`).
- AC-5: Each file ≤ 150 lines (directory rules can be larger than root but still bounded).

**Test plan:**
1. Red: per-file existence tests.
2. Green: write each file.
3. Red: `test_all_directory_claude_md_have_front_matter`.
4. Green: validator + add front-matter.

**Deps:** H.0.2, H.0.3.

### Story H.0.6 — Front-matter validator + size-cap self-check

**As the** harness, **I want** to enforce its own structural rules **so that** drift is impossible.

**AC:**
- AC-1: `.harness/checks/claude_md_size_cap.py` enforces root ≤ 70 lines.
- AC-2: `.harness/checks/owners_present.py` enforces `owner:` field on every CLAUDE.md and `.harness/*.md`.
- AC-3: Both checks emit H-16 conformant output.
- AC-4: Both checks have violation + compliant fixtures under `tests/harness/fixtures/`.
- AC-5: Both checks are wired into `make validate-fast`.

**Test plan:**
1. Red: `test_size_cap_check_fires_on_oversized_file` — fixture: 100-line CLAUDE.md.
2. Green: implement size-cap check.
3. Red: `test_size_cap_check_silent_on_compliant_file` — fixture: 50-line CLAUDE.md.
4. Green: confirms.
5. Red+Green: same pattern for `owners_present.py`.

**Deps:** H.0.4, H.0.5.

### Story H.0.7 — `make harness-install` pre-commit hook installer

**As a** new contributor, **when** I clone the repo and run `make harness-install`, **then** the pre-commit hook runs `make validate-fast` automatically on commit.

**AC:**
- AC-1: `tools/install_pre_commit.sh` writes `.git/hooks/pre-commit` with one line: `make validate-fast`.
- AC-2: Idempotent — running twice doesn't break.
- AC-3: Detects existing pre-commit hook and refuses to overwrite without `--force`.

**Test plan:** Standard idempotence + interaction tests with shell fixtures.

**Deps:** H.0.4.

### Story H.0.8 — Harness test infrastructure

**As a** harness developer, **I want** a fixture-driven testing pattern for checks **so that** every check has paired violation + compliant fixtures (H-24).

**AC:**
- AC-1: `tests/harness/fixtures/violation/<rule_id>/` and `tests/harness/fixtures/compliant/<rule_id>/` directory pattern documented.
- AC-2: Helper `tests/harness/_helpers.py::assert_check_fires(rule_id, fixture_dir)` and `assert_check_silent(rule_id, fixture_dir)`.
- AC-3: Convention test that walks `.harness/checks/*.py` and asserts every check has both a violation and compliant fixture.
- AC-4: Convention test runs in `make validate-fast`.

**Test plan:**
1. Red: `test_every_check_has_violation_fixture`.
2. Green: convention test that scans both directories.
3. Red: `assert_check_fires` helper exists and works on a known check.
4. Green: implement helper.

**Deps:** H.0.6.

### Story H.0.9 — AGENTS.md + .cursorrules aliases

**AC:**
- AC-1: `AGENTS.md` is a symlink to `CLAUDE.md` (Mac/Linux); on Windows-hostile environments, a stub file that says "see CLAUDE.md."
- AC-2: `.cursorrules` is a 3-line text file: "see CLAUDE.md and CLAUDE.md files in subdirectories. Run `tools/load_harness.py --target <file>` for full context."

**Deps:** H.0.2.

### Story H.0.10 — CONTRIBUTING.md

Tactical. Document the human discipline checklist (H-19): "Before commit, did make validate pass? Did your AI run the loop? Did you review the diff?"

**Deps:** H.0.7.

---

## 5. Sprint H.1 — Cross-cutting rules + custom checks (2 weeks · 26 pts)

**Sprint goal:** The first real custom checks ship. Cross-cutting rule files exist with `applies_to` globs. Every check has its violation + compliant fixture pair.

**Sprint exit criteria:**
- 5 cross-cutting rule markdown files in `.harness/`.
- 8 custom checks in `.harness/checks/`, all with H-16/H-23 conformant output.
- Every check has violation + compliant fixtures.
- `make validate-fast` runs all 8 checks + lint + typecheck in < 30 seconds.

| ID | Title | Pts |
|---|---|---|
| H.1.1 | `.harness/python-style.md` (cross-cutting, applies_to: backend/**/*.py) | 2 |
| H.1.2 | `.harness/frontend-tokens.md` (cross-cutting, applies_to: frontend/src/**) | 2 |
| H.1.3 | `.harness/security.md` (cross-cutting, applies_to: backend/src/api/**/*.py) | 2 |
| H.1.4 | `.harness/accessibility.md` (cross-cutting, applies_to: frontend/src/**/*.{tsx,jsx}) | 2 |
| H.1.5 | `.harness/api-contracts.md` (cross-cutting) | 2 |
| H.1.6 | Check: `safe_bounds.py` — every Pydantic Field has ge/le | 3 |
| H.1.7 | Check: `storage_isolation.py` — no cursor.execute() outside storage/ | 3 |
| H.1.8 | Check: `no_duck_tokens.py` — no duck-* tokens (must be wr-*) | 3 |
| H.1.9 | Check: `audit_emission.py` — gateway writes call _audit() | 3 |
| H.1.10 | Check: `contract_typed.py` — no Optional[Any] / bare dict in sidecar models | 3 |
| H.1.11 | Check: `todo_in_prod.py` — no `# TODO` outside `tests/` | 1 |
| H.1.12 | Output-format conformance check (`tools/check_output_format.py`) | 2 |

**Total: 28 pts** (slight overshoot — pull H.1.5 to H.2 if capacity tight)

Each story follows the same shape:

#### Story H.1.X (template) — Custom check

**AC:**
- AC-1: Check exists at `.harness/checks/<rule_id>.py`.
- AC-2: Output conforms to H-16 + H-23 (suggestion field present).
- AC-3: Violation fixture at `tests/harness/fixtures/violation/<rule_id>/` causes check to emit ERROR.
- AC-4: Compliant fixture at `tests/harness/fixtures/compliant/<rule_id>/` produces no output.
- AC-5: Check is registered in `make validate-fast`.
- AC-6: Check completes on the entire repo in < 2 seconds.
- AC-7: Check function answers H-25 questions in its docstring (missing input? malformed input? upstream failed?).

**Test plan:**
1. Red: `test_<rule_id>_fires_on_violation_fixture`.
2. Green: minimum check.
3. Red: `test_<rule_id>_silent_on_compliant_fixture`.
4. Green: refine check.
5. Red: `test_<rule_id>_output_conforms_to_format`.
6. Green: ensure suggestion field present.
7. Red: `test_<rule_id>_under_2_seconds_on_full_repo`.
8. Green: optimize if needed.
9. Refactor: extract reusable parsers to `_common.py`.

---

## 6. Sprint H.2 — Generated layer + AI integration (2 weeks · 26 pts)

**Sprint goal:** The harness becomes self-maintaining. Generated truth files exist and regenerate via `make harness`. Claude Code is wired to load harness context at session start. Documentation is complete.

**Sprint exit criteria:**
- 4 generators ship; `make harness` regenerates all `.harness/generated/*.json`.
- Generated files are git-tracked but enforce "regenerated, not hand-edited" via a check.
- Claude Code session-start hook configured (`.claude/settings.local.json`) to invoke `tools/load_harness.py`.
- `harness-init` template repo (or one-line bootstrap) exists for new repos.
- `.harness/README.md` documents the full system.
- All 25 harness rules verifiably enforced by some check or convention test.

| ID | Title | Pts |
|---|---|---|
| H.2.1 | Generator: `extract_contract_names.py` (reads contracts.py → JSON) | 3 |
| H.2.2 | Generator: `extract_valid_tokens.py` (reads frontend index.css → JSON) | 3 |
| H.2.3 | Generator: `extract_lint_rules.py` (registry of `.harness/checks/*.py`) | 3 |
| H.2.4 | Generator: `extract_agent_manifests.py` (reads agents/manifests/*.yaml → JSON) | 3 |
| H.2.5 | `tools/run_harness_regen.py` orchestrator | 3 |
| H.2.6 | Check: `generated_not_handedited.py` (asserts generated files match output of regen) | 3 |
| H.2.7 | Claude Code session-start hook (`.claude/settings.local.json`) | 3 |
| H.2.8 | `harness-init` bootstrap template (separate repo or `tools/init_harness.py`) | 5 |
| H.2.9 | `.harness/README.md` end-user documentation | 2 |
| H.2.10 | Harness self-test: convention test that every H-rule has either a check or a doc reference | 3 |

**Total: 31 pts** (overshoot — defer H.2.8 to a follow-up sprint if capacity tight)

### Story H.2.X (representative) — Generator

**AC:**
- AC-1: Generator at `.harness/generators/<name>.py`.
- AC-2: Reads source file(s) and writes JSON to `.harness/generated/<name>.json`.
- AC-3: JSON has versioned schema (`{"$schema_version": 1, "data": [...]}`).
- AC-4: Idempotent — running twice produces byte-identical output.
- AC-5: Triggered by `make harness`.
- AC-6: Output validated by `generated_not_handedited.py` check (which re-runs the generator and diffs against checked-in file).

**Test plan:** TDD with synthetic input fixtures.

### Story H.2.7 — Claude Code session-start hook

**AC:**
- AC-1: `.claude/settings.local.json` declares a session-start command that runs `tools/load_harness.py --target <current-file>` and stashes the output where Claude reads it.
- AC-2: Documented in `CLAUDE.md` so contributors using other AI tools know how to wire equivalents.

**Deps:** H.0.3.

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `validate-fast` exceeds 30s budget as checks accumulate | Medium | High | Performance assertion in CI; profile per check; parallelize where safe; move slow checks to `validate-full`. |
| Custom check has false positives, AI gets stuck in fix-loop | Medium | High | Violation + compliant fixtures (H-24) catch this before merge. AI escape hatch: if same check fires after 3 fix attempts, raise blocker. |
| Generated file drift between commits | Low | Medium | `generated_not_handedited.py` check runs in `validate-fast`; PR fails if generated files don't match regen output. |
| Rule file owner unreachable, rules go stale | Medium | Medium | Owners declared in front-matter; quarterly review surfaces orphans; fallback owner = @platform-team. |
| AI bypasses `make validate` despite mandate | Low | Critical | Pre-commit hook (H-18); `tests/harness/test_ai_loop_enforcement.py` analyzes git log for "feat" commits without preceding "test" commits. |
| Check writes silent failure (exit 0 despite violation) | Low | Critical | H-24 violation fixtures catch this; convention test asserts every check emits ≥1 ERROR line on its violation fixture. |
| Loader produces non-deterministic output (e.g., dict ordering) | Low | High | Loader output sorted by precedence then by file path; test asserts byte-identical output across runs. |
| Front-matter typo silently disables a rule | Low | High | Strict YAML schema validation in `claude_md_size_cap.py`'s sibling; unknown front-matter keys raise warning. |
| Generated files in PR diff are noisy | Medium | Low | Configure git to render `.harness/generated/*.json` as collapsed in PR review (CODEOWNERS / repo settings). |

---

## 8. Sprint Roadmap Summary

| Sprint | Focus | Cumulative outcome |
|---|---|---|
| H.0 | Scaffold + first directory rules | Skeleton in place, root + 3 directory CLAUDE.md, loader works, harness self-test infra ready, pre-commit installable |
| H.1 | Cross-cutting rules + 8 custom checks | First real enforcement: storage isolation, safe bounds, no duck tokens, audit emission, etc. — all with violation + compliant fixtures |
| H.2 | Generated layer + AI integration | Self-maintaining harness: generators regenerate truth, Claude Code wired to load context automatically, full documentation, bootstrap template |

**Total elapsed: ~6 weeks at 2-week sprints, 80% capacity load.**

---

## 9. Glossary

- **Harness** — the repo-level scaffolding (rules + checks + generators + loader + Makefile) that makes AI-assisted development productive in *this* codebase.
- **Consumer 1** — human contributor using AI in their IDE (Claude Code, Cursor, Copilot).
- **Consumer 2** — autonomous CI agent that proposes PRs without a human in the loop.
- **Root rules** — the contents of root `CLAUDE.md` (≤ 70 lines, always loaded).
- **Directory rules** — per-directory `CLAUDE.md`, scoped to a subtree, loaded when AI works there.
- **Cross-cutting rules** — `.harness/*.md` files with `applies_to` glob patterns.
- **Generated rules** — `.harness/generated/*.json`, code-derived structured truth, regenerated by `make harness`.
- **Loader** — `tools/load_harness.py`, the deterministic discovery + precedence resolver.
- **Validate-fast** — `make validate-fast`, the < 30s inner-loop gate (lint + typecheck + custom checks + harness self-checks).
- **Validate-full** — `make validate-full`, the pre-commit / CI gate (validate-fast + tests + heavy audits).
- **Check** — a script in `.harness/checks/*.py` that detects violations of one rule and emits structured output.
- **Generator** — a script in `.harness/generators/*.py` that produces a `.harness/generated/*.json` truth file from code.
- **Violation fixture / compliant fixture** — paired example files under `tests/harness/fixtures/` proving each check fires correctly.
- **Front-matter** — YAML block at the top of every rule file declaring `scope`, `owner`, `priority`, `applies_to`, `type`.
- **Precedence** — Local > Generated > Cross-cutting > Root. Conflicts surface as lint errors.
- **Five execution contexts** — AI session loop, terminal, pre-commit hook, CI (future), autonomous agent. Same `make validate` runs in all five.

---

**Plan finalized 2026-04-26. Per the brainstorming skill terminal flow, the next step is to invoke `superpowers:writing-plans` if a deeper-than-story-level work-breakdown is needed before execution begins.**
