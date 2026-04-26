---
owner: '@inder'
---
# Policy schemas

Each `.harness/<topic>(_policy)?.yaml` validates against
`.harness/schemas/<topic>(_policy)?.schema.json`.

Schemas use JSON Schema draft 2020-12. Adding a key to a policy file is
fine; removing one or changing its type requires a schema update + ADR.

The initial schemas (Sprint H.1d.4) are deliberately permissive
(`additionalProperties: true`, no `required` array). They validate the
top-level type and primitive constraints only — enough to catch obvious
shape regressions while leaving room for the policy YAML to grow without
bouncing off the schema. Tighten in follow-up work as patterns stabilize.
