# XER File Policy

## Rule

Every `.xer` file in a Westland project folder is an **immutable record**. No in-place edits, no overwrites, no deletes — ever. Every revision is a new versioned file.

## Why

`.xer` files are the P6/scheduling-software exports of the project's critical path at a specific point in time. They are the source of truth for:

- Claims and delay analysis (what the schedule looked like on the date a delay began)
- Contract disputes (milestone evidence, substantial completion projections)
- Forensic reconstruction of how the project evolved

If the historical sequence of `.xer` files is corrupted — even by a well-intentioned "cleanup" edit — we lose the ability to defend the company's position months or years later. The value of the record is in its **unaltered accumulation over time**.

## Mechanic

Every modification = a new versioned file alongside the previous one:

```
2026-04-17 NTVS ACME.xer            (original export)
2026-04-17 NTVS ACME-v2.xer         (first revision)
2026-04-17 NTVS ACME-v3.xer         (second revision)
...
```

- Increment `-vN` by one each revision. Don't skip numbers.
- Keep the base name (date + project) identical across the chain — only the `-vN` suffix changes.
- Never delete the older versions. The chain is the record.

## Enforcement

This plugin (`westland`) ships a PreToolUse hook at `hooks/westland_share_guard.py` that physically blocks:

- `Edit` / `MultiEdit` / `NotebookEdit` on any existing `.xer` file
- `Write` overwriting an existing `.xer` file
- Bash commands that delete `.xer` files (`rm`, `del`, `Remove-Item`, `find -delete`, `unlink`)

Writing a new `.xer` path (one that doesn't exist yet) is allowed — that's how `-v2.xer` gets created.

The hook fires on every session that has the `westland` plugin loaded. Since this plugin is set as a required organizational dependency, the rule applies to every Westland Claude Code session.

## If you think you need to edit or delete a `.xer`

You've misunderstood the workflow. Stop. Ask the colleague or project manager what they actually want — options are almost always:

- Create a new `-vN.xer` working copy (what the hook is steering you toward)
- Parse/read the existing file without modifying it
- Leave the file alone and work from a different artifact
