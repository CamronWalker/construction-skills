# Evals

Dev-only scratch for qualifying skill reruns and catching regressions. Not part of any plugin and not shipped in the zips (build.py skips paths outside the specific plugin directories).

## Layout

```
.evals/
  <skill-name>/
    <project-slug>/
      dry-run-<date>.md     # qualitative walk-through of the skill vs a real project
      trigger-eval.json     # skill-creator trigger prompts (should / should-not)
      ...
```

## What belongs here

- Dry-run analyses (markdown): "if I pointed the updated skill at project X's docs, what would Phase 2 / 3 / 7 produce?"
- Trigger eval sets for the skill-creator description optimizer (prompt text only)
- Extracted summaries, scoring JSON, WBS-tree snapshots — anything derived from a real project that helps test the skill

## What does NOT belong here

- **`.xer` files** — company property, proprietary schedule logic. `*.xer` is gitignored repo-wide. Keep them on OneDrive or the project's G:\ path.
- **Full RFPs or bid documents** — unless verified as public / non-confidential.
- **Client-identifying information** beyond what appears in public project names.

If in doubt, paraphrase or summarize rather than copying source material.

## Why this exists

The continuous improvement loop documented in the repo-root `CLAUDE.md` depends on concrete comparisons between what Claude produced and what the human scheduler produced. Keeping those comparisons in git (as summaries, not raw XERs) means a new machine or a new collaborator can clone the repo and have the full regression-test context ready to go.
