// Q18 — Conventional Commits enforcement.
module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "header-max-length": [2, "always", 72],
    "type-enum": [2, "always", [
      "feat", "fix", "docs", "refactor", "test",
      "chore", "perf", "style", "build", "ci",
    ]],
    "subject-case": [0],   // disable; we want flexibility for proper nouns
  },
};
