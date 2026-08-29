# Domain Docs

How the engineering skills should consume this repo's domain documentation when
exploring the codebase.

**Layout: single-context.** One `CONTEXT.md` and one `docs/adr/` at the repo
root. Neither exists yet, and that is fine.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root
- **`docs/adr/`**: read ADRs that touch the area you are about to work in

If either is absent, **proceed silently**. Do not flag it; do not suggest
creating it upfront. `/domain-modeling` creates them lazily, when a term or a
decision actually gets resolved.

## File structure

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-....md
│   └── 0002-....md
└── src/agent_yield/
```

Should this repo ever split into multiple packages, add a root `CONTEXT-MAP.md`
pointing at one `CONTEXT.md` per context, with context-scoped ADRs under
`src/<context>/docs/adr/`. Nothing here needs that today.

## Use the glossary's vocabulary

When your output names a domain concept (an issue title, a refactor proposal, a
hypothesis, a test name), use the term as defined in `CONTEXT.md`. Do not drift
to synonyms the glossary avoids.

If the concept is not in the glossary yet, that is a signal: either you are
inventing language the project does not use, or there is a real gap worth
noting for `/domain-modeling`.

## Flag ADR conflicts

If your output contradicts an existing ADR, say so rather than silently
overriding it:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
