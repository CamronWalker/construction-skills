# Read Meeting Transcript — Design

**Date:** 2026-07-16
**Skill:** `westland:read-meeting-transcript` (new, in `construction-skills`)
**Connector:** Microsoft 365 (claude.ai-managed) — `outlook_calendar_search`, `read_resource`, `get_me`
**Status:** Design — awaiting review

## Problem

A Westland user asks Claude to "read the meeting transcript" (or summarize the meeting, pull decisions, list follow-ups). There is no general skill for this, so Claude free-wheels: it searches OneDrive, then the project folder, then greps around, and — on Opus — sometimes burns ~100k tokens before stumbling onto the answer. When it *does* find the transcript, it reads the whole ~66 KB JSON straight into context, bloating the session for a question that only needed three lines.

The reliable path already exists but is buried inside the scheduling plugin's weekly-email pipeline (`scheduling/skills/schedule-update/phases/_m365_inputs.md`, "Recipe A"): **calendar event → read the event's `meetingTranscriptUrl` → `read_resource` that URL → JSON of speaker turns.** Only schedulers install the scheduling plugin, so that knowledge never reaches the rest of the company.

## Goals

1. **A general, always-available skill.** Lives in the `westland` base plugin — the required dependency every domain plugin installs — so schedulers and non-schedulers alike get it.
2. **Kill the spin.** A fixed, short procedure that names the exact tool chain and *forbids* the OneDrive / project-folder / SharePoint / web detours. Loaded in SKILL.md so it is always in context when the skill triggers.
3. **Never read the transcript into the main context.** Download → convert → grep. The 66 KB never lands in the main agent's window.
4. **Subagent owns the heavy read** (Sonnet). It downloads the JSON, converts to readable markdown, composes a summary, and tacks a **greppable YAML frontmatter block** on top (summary, decisions, follow-ups, keywords). It returns to the main agent only a file pointer + the summary — a few hundred tokens.
5. **Self-describing saved copies.** Every transcript markdown gets the frontmatter block, whether ephemeral (scratchpad) or a kept copy in a project folder, so it can be grepped months later.
6. **Progressive disclosure of connect steps.** How to connect the M365 connector lives in a reference file loaded *only* when the connector is missing — it never bloats the trigger path.

## Non-Goals

- **Refactoring scheduling's Recipe A.** Out of scope (user chose "standalone only"). Recipe A keeps working untouched. A later follow-up *could* point it at this skill — safe, because `westland` is a required dependency of `scheduling` — but not now.
- **Transcription itself.** We read transcripts Teams already generated. We do not transcribe audio.
- **Fetching transcripts from anywhere but the calendar event.** No OneDrive/SharePoint/file-system scavenging. If the event has no `meetingTranscriptUrl`, we say so and stop.
- **Meeting minutes / RFI / distribution.** This skill produces a readable transcript + summary. Turning that into minutes or an email is a separate skill's job (it can consume this skill's output).

## The load-bearing assumption (validate first)

**Approach A depends on a subagent being able to call the M365 connector's `read_resource`.** In Claude Code, Agent-tool subagents share the session's MCP servers, and `general-purpose` / `claude` agent types carry `*` tools, so a subagent should see the connector. **Implementation step 0 is to prove this on a live transcript.** If it turns out subagents cannot reach the connector, fall back to Approach B (below) and document it.

## Approach A — subagent owns the download (primary)

`read_resource` returns content **into whoever calls it**. The only way to keep the transcript out of the main context is to never call it there.

### Main agent (small context cost)

- **Step 0 — Connector check.** Confirm the M365 tools exist (`outlook_calendar_search`, `read_resource`). If missing, or `get_me` errors with not-connected / 401 → load `references/connect-m365.md`, show the connect steps, and **stop**. Never retry-loop.
- **Step 1 — Pin the meeting.** `outlook_calendar_search(query=<title token>, afterDateTime=<window start>, beforeDateTime=<window end>, order="newest")`. Drop `isCancelled == true` and `Canceled:` / `Declined:` title prefixes. Pick the occurrence closest to (on or just before) the target date. If two plausibly match, **ask the user** — do not guess. **Hard rule: the transcript comes from the calendar event and nowhere else. Do NOT search OneDrive, the project folder, SharePoint, Documents, or the web.**
- **Step 2 — Get the URL.** `read_resource(<event's calendar:///events/{id} uri>)`, read the `meetingTranscriptUrl` field. If absent/empty → tell the user the meeting has no transcript and stop. This is all the main agent pulls.
- **Step 3 — Dispatch the subagent.** Hand it: the transcript URL (verbatim), the output `.md` path, and the script path. **Smart default:** run **synchronous** when reading the transcript *is* the task (relay the summary immediately); run **background** when other work is in flight so the main agent keeps going and picks up the summary on the completion notification.

### Subagent (Sonnet; holds the 66 KB in its own context)

1. `read_resource(<transcriptUrl>)` → JSON `{ meeting: {...}, transcripts: [...] }`. May carry more than one transcript for a recurring series; pick the one whose timing matches this occurrence (the URI carries start/end scoping).
2. Write the raw JSON to a temp file (provenance) and run `scripts/transcript_json_to_md.py <json> <out.md>` to produce the readable speaker-turn markdown.
3. Read its own markdown output, compose the summary, and **prepend the YAML frontmatter block** (schema below).
4. Return to the main agent **only**: the markdown file path + the summary / decisions / follow-ups. **Not** the transcript body.

### Frontmatter schema (what the subagent writes; greppable)

```yaml
---
type: meeting-transcript
meeting: "Neiafu Tonga Temple — Weekly Schedule Update"
date: 2026-07-08
participants: [Marty Jacks, B. Jensen]
summary: >
  Two-to-four sentence plain-language summary of the meeting.
decisions:
  - "Owner approved the revised slab sequence."
follow_ups:
  - "Marty to send updated rebar submittal by 2026-07-15"
keywords: [slab, rebar, submittal, elevator, EOT]
source_url: "<meetingTranscriptUrl>"
generated_by: "read-meeting-transcript (sonnet subagent)"
---
```

The main agent then does `grep '^summary:'`, `grep -A20 '^decisions:'`, or greps `keywords:` and then greps the body for a keyword — never loading the whole file.

## Approach B — fallback (only if subagents cannot reach the connector)

Main agent calls `read_resource(transcriptUrl)` once (unavoidable single hit), writes the JSON straight to a file, runs the script, then dispatches the subagent to read the *file*, summarize, and write frontmatter. This does not fully avoid the main-context hit but still isolates the summary work and produces the same self-describing artifact. Document the limitation in SKILL.md so the user understands why the token cost is higher in this mode.

## Save location & naming

- **Default (no "save" ask):** write to the session scratchpad — ephemeral, grep-and-discard.
- **User wants a kept copy:** write to the location / project folder they name, using the house-style filename `{Project} meeting transcript {YYYY-MM-DD}.md` (sanitize `/ \ : * ? " < > |` out of the project name). Match `westland-house-style` naming.
- **Reading back later:** glob `*transcript*.md` (newest wins) — the same convention Recipe A's consumers use, so the two skills' outputs are interchangeable.

## File layout

```
westland/skills/read-meeting-transcript/
  SKILL.md                      # triggers + when-to-use + the fixed 3-step procedure + subagent dispatch + the "never read it directly / never scavenge the filesystem" rules + frontmatter schema
  references/
    connect-m365.md             # M365 connector connect steps — loaded ONLY when the connector is missing
  scripts/
    transcript_json_to_md.py    # transcript JSON file → readable speaker-turn markdown (stdlib only; no frontmatter — the subagent adds that)
```

- **SKILL.md** carries the procedure (this *is* the anti-spin fix, so it must always load). Keep it tight; push the connect steps to the reference.
- **`transcript_json_to_md.py`** is a plain stdlib Python CLI: `python transcript_json_to_md.py <in.json> <out.md> [--occurrence <iso>]`. It parses `transcripts[]`, selects the matching occurrence, and emits speaker turns as markdown. It writes the *body only*; the subagent prepends frontmatter after reading it. The exact JSON shape is validated against a live transcript at implementation (step 0).

## Triggers (SKILL.md description)

"read the meeting transcript", "pull the transcript", "get the Teams transcript", "what did we decide in the meeting", "summarize yesterday's meeting", "meeting follow-ups / action items", "transcript for <meeting>". Explicitly a **general** skill, not scheduling-specific.

## Release

Standard convention (repo `CLAUDE.md`): bump `westland/.claude-plugin/plugin.json` (minor — new skill), match `.claude-plugin/marketplace.json`, register the skill, one commit, PR to `main`, then build/distribute from the main checkout.

## Open validation items (implementation step 0)

1. Confirm subagents can call the M365 connector's `read_resource` (decides A vs. B).
2. Confirm the exact `read_resource` transcript JSON shape (`meeting` / `transcripts[]` nesting, where speaker turns live, VTT vs. structured) against a real recent meeting — drives the parser.
3. Confirm the M365 connector's display name and connect path for `references/connect-m365.md`.
