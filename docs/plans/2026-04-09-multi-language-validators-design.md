# Multi-Language Validators — Design

**Goal:** Extend the Python-only static validator to support Go, JavaScript, TypeScript, Kotlin, and Java — using a config-driven approach with best-effort tool availability.

**Context:** The current `StaticValidator` uses `ast.parse()`, `ruff`, and import checking — all Python-specific. For non-Python repos, validation silently passes (does nothing). This means LLM-generated Go/Node/Kotlin/Java fixes ship without any syntax or lint checking.

---

## 1. Language Detection

Detect language from file extension in `validate_all()`:

| Extension | Language | Syntax Check | Linter |
|-----------|----------|-------------|--------|
| `.py` | Python | `ast.parse()` (in-process) | `ruff check` |
| `.go` | Go | `go vet` | `golangci-lint run` (fallback: `go vet` only) |
| `.js`, `.jsx`, `.mjs` | JavaScript | `node --check` | `eslint` |
| `.ts`, `.tsx` | TypeScript | `npx tsc --noEmit` | `eslint` |
| `.kt`, `.kts` | Kotlin | `kotlinc -script` | `ktlint` |
| `.java` | Java | `javac` (syntax only) | `checkstyle` (fallback: skip) |

**Import checking** stays Python-only — `ast.parse` makes it trivial. For other languages, import/dependency errors surface through the syntax check naturally (`go vet` catches unused imports, `tsc` catches missing imports, etc.).

**Fallback:** If no tool is installed for a language, validation passes with a warning (best-effort).

---

## 2. Validator Refactoring

### Language Config Registry

```python
LANGUAGE_CONFIG = {
    "python": {
        "extensions": [".py"],
        "syntax_cmd": None,  # uses in-process ast.parse()
        "lint_cmd": ["ruff", "check", "--output-format=json"],
        "lint_parse_json": True,
    },
    "go": {
        "extensions": [".go"],
        "syntax_cmd": ["go", "vet"],
        "lint_cmd": ["golangci-lint", "run", "--out-format=json"],
        "lint_parse_json": True,
        "lint_fallback_cmd": ["go", "vet"],
    },
    "javascript": {
        "extensions": [".js", ".jsx", ".mjs"],
        "syntax_cmd": ["node", "--check"],
        "lint_cmd": ["eslint", "--format=json"],
        "lint_parse_json": True,
    },
    "typescript": {
        "extensions": [".ts", ".tsx"],
        "syntax_cmd": ["npx", "tsc", "--noEmit", "--allowJs"],
        "lint_cmd": ["eslint", "--format=json"],
        "lint_parse_json": True,
    },
    "kotlin": {
        "extensions": [".kt", ".kts"],
        "syntax_cmd": ["kotlinc", "-script"],
        "lint_cmd": ["ktlint"],
        "lint_parse_json": False,
    },
    "java": {
        "extensions": [".java"],
        "syntax_cmd": ["javac", "-d", "/tmp"],
        "lint_cmd": ["checkstyle", "-c", "/google_checks.xml"],
        "lint_parse_json": False,
    },
}
```

### Key Changes to `StaticValidator`

- `detect_language(file_path)` → looks up extension in config
- `validate_syntax()` → Python uses `ast.parse()`, all others write to temp file and run `syntax_cmd`
- `run_linting()` → dispatches to language-specific `lint_cmd`
- `check_imports()` → Python only (skipped for other languages)
- `validate_all()` → detects language first, then runs the chain

### Self-Correction

`_self_correct()` in `fix_generator.py` already uses LLM to fix code — update the prompt from hardcoded "python" to the detected language name.

---

## 3. Files Changed

| File | Action | Description |
|------|--------|-------------|
| `backend/src/agents/agent3/validators.py` | **MODIFY** | Add `LANGUAGE_CONFIG`, `detect_language()`, refactor all validation methods to be language-aware |
| `backend/src/agents/agent3/fix_generator.py` | **MODIFY** | Update `_self_correct()` prompt to include detected language |
| `backend/tests/test_validators.py` | **CREATE** | Tests for language detection, syntax validation per language (mocked subprocess), best-effort skip |

## What Does NOT Change

- `fix_job_queue.py` — validation is called the same way
- `supervisor.py` — no changes needed
- `routes_v4.py` — no API changes
- Frontend — validation results already rendered generically
