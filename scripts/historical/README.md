# Historical scripts

One-shot migration scripts that have already run. Kept as a reference for the next time a similar migration is needed; **do not run again** without reading the script and confirming intent.

## `codemods/`

Frontend Tailwind-color migrations (per the script headers): replaced raw color classes with the `wr-*` token namespace. Already applied to the codebase.

Move scripts here (rather than deleting) when:
- They were idempotent in spirit but **destructive in practice** (replaced a token namespace, mutated import paths, etc.)
- Their **logic is the precedent** for future migrations of the same kind.

If you're confident a script is past its useful life entirely, delete it.
