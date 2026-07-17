---
name: read-meeting-transcript
description: >
  Read, summarize, or pull decisions/action-items from a Teams meeting
  transcript via the Microsoft 365 connector. Use whenever the user asks to
  "read the meeting transcript", "pull the transcript", "get the Teams
  transcript", "summarize the meeting / yesterday's call", "what did we decide
  in the meeting", "action items / follow-ups from the meeting", "meeting
  notes from <date/meeting>", or points at a Teams/Outlook meeting and wants
  what was said. General-purpose (any meeting the user has transcript access
  to), not scheduling-specific. Enforces the reliable path — calendar event →
  meetingTranscriptUrl → transcript — and hands the heavy read to a subagent so
  the ~30–70 KB transcript never lands in the main context.
---

# Read Meeting Transcript

Turn a Teams meeting into a readable transcript plus a greppable summary,
**without burning the main context**. The transcript resource is 30–70 KB of
WebVTT; reading it directly is what makes Claude spin for 100k tokens. This
skill forbids that: a subagent downloads and converts it, tacks a summary on
top, and returns only a pointer + a few-hundred-token summary.

## The one hard rule

**A Teams transcript comes from the calendar event and nowhere else.** Do NOT
search OneDrive, the project folder, SharePoint, Outlook mail, Documents, the
web, or `grep` the filesystem looking for it. The only path is:

```
calendar event  →  event.meetingTranscriptUrl  →  read_resource(that URL)  →  WebVTT JSON
```

If that path yields nothing, the transcript does not exist for you (see
**Access requirement**) — say so and stop. Never fall back to scavenging.

## Access requirement — state this up front if it might bite

Microsoft only returns a meeting's transcript to:

- the **meeting organizer**, or
- a **co-organizer**, or
- someone the transcript was **explicitly shared with**.

A plain attendee usually gets **no `meetingTranscriptUrl`** on the event (or a
permission error when reading it). Also, the meeting must have actually been
**recorded/transcribed** — no transcription, no transcript. When the path comes
up empty, do not retry or scavenge; tell the user plainly:

> I can't pull that transcript — Teams only exposes it to the organizer, a
> co-organizer, or someone it was explicitly shared with. If you're an attendee,
> ask the organizer to share the transcript (or add you as co-organizer), then
> try again. (Also possible: the meeting wasn't recorded/transcribed.)

## Prerequisite — the Microsoft 365 connector

The chain uses the Microsoft 365 connector's tools: `outlook_calendar_search`
and `read_resource` (and `get_me`). In Claude Code these may be **deferred** —
load them with `ToolSearch` (keyword search `microsoft 365 read_resource
outlook calendar`) and use whatever `mcp__…__<tool>` names match.

If the connector isn't connected at all (no such tools, or `get_me` errors with
not-connected / 401), **read [`references/connect-m365.md`](references/connect-m365.md)**,
show the user the connect steps, and stop. Do not loop-retry a missing connector.

## Procedure

### Step 1 — Pin the meeting (main agent; cheap)

`outlook_calendar_search` with a **tight date window** and a title token:

```
outlook_calendar_search(
  query      = "<distinctive word from the meeting/project name>",
  afterDateTime  = "<day before the meeting>",
  beforeDateTime = "<day after the meeting>",
  order      = "newest"
)
```

From the results:
- Drop `isCancelled == true` and any `Canceled:` / `Declined:` title prefix.
- Pick the occurrence whose `start` is on (or just before) the target date.
- Recurring meetings: instances have `recurrence: null` and share a title —
  match by **title + date**, not by series. Each occurrence's event carries its
  own occurrence-scoped `meetingTranscriptUrl`.
- If two events plausibly match, **ask the user which one** — do not guess.

You now have the chosen event's `calendar:///events/{id}` URI. That is all the
main agent needs; it does **not** read the event body or the transcript itself.

### Step 2 — Dispatch the subagent (Sonnet)

Hand the heavy read to a subagent so the transcript stays out of your context.
**Smart default for dispatch:**

- **Synchronous** (`run_in_background: false`) when reading/summarizing the
  transcript *is* the task — you relay the summary as soon as it returns.
- **Background** (`run_in_background: true`) when other work is in flight — keep
  going and pick up the summary from the completion notification.

Spawn a `general-purpose` agent with `model: sonnet` and this prompt, filling in
the four `<...>` values:

````
You are reading one Teams meeting transcript and producing a readable markdown
file with a greppable summary on top. Report STRUCTURE + SUMMARY to your caller;
never paste the full transcript back — your caller must not see the raw body.

INPUTS
- Event URI:   <calendar:///events/{id}>
- Output .md:  <absolute path for the transcript markdown>
- Raw JSON:    <absolute path for a temp .json, same folder as the .md>
- Converter:   <absolute path to scripts/transcript_json_to_md.py>
- Occurrence:  <YYYY-MM-DD of the meeting> ; Meeting label: <title>

STEPS
1. Load the connector tool: ToolSearch query "microsoft 365 read_resource" and
   use the matching mcp__…__read_resource. (Also load outlook if you need it.)
2. read_resource(<Event URI>). Read the `meetingTranscriptUrl` field.
   - If it is missing or empty: STOP and return exactly:
     NO_TRANSCRIPT: the event has no meetingTranscriptUrl (organizer/co-organizer/
     shared access required, or the meeting was not transcribed).
3. read_resource(<meetingTranscriptUrl VERBATIM — do not alter the token or the
   ?start/&end params>). If it errors with a permission/403/404: STOP and return:
     NO_ACCESS: <the exact error text>.
4. Write the FULL JSON object you got in step 3 to <Raw JSON> (UTF-8).
5. Run: python "<Converter>" "<Raw JSON>" "<Output .md>"
   Report any non-zero exit / traceback verbatim and stop.
6. Read <Output .md>. From its content compose:
   - summary: 2–4 plain sentences of what the meeting covered.
   - decisions: bullet list of decisions/outcomes (empty list if none).
   - follow_ups: bullet list of action items with owner + due if stated.
   - participants: distinct speaker names seen in the transcript.
   - keywords: 5–12 lowercase topic keywords for grep.
7. Prepend this YAML frontmatter block to the TOP of <Output .md> (write it,
   then the existing body):
   ---
   type: meeting-transcript
   meeting: "<title>"
   date: <occurrence YYYY-MM-DD>
   participants: [<names>]
   summary: >
     <the summary>
   decisions:
     - "<decision>"
   follow_ups:
     - "<owner: task (due)>"
   keywords: [<keywords>]
   source_url: "<the meetingTranscriptUrl>"
   generated_by: "read-meeting-transcript (sonnet subagent)"
   ---
8. Return ONLY (a few hundred tokens): the Output .md path, the summary, the
   decisions, the follow_ups, and the participants. NOT the transcript body.
````

### Step 3 — Relay and grep (main agent)

Relay the subagent's summary to the user. If they then ask for specifics, **grep
the file** — never read it whole:

```bash
# The summary block:
grep -A30 '^---' "<Output .md>" | head -40
# A topic:
grep -n -i "rebar" "<Output .md>"
```

## Save location & naming

- **Default (no "save" ask):** write to the session **scratchpad** directory
  (the temp path named in your environment) — ephemeral, grep-and-discard.
- **User wants a kept copy:** write to the folder they name, using the
  house-style filename `{Project} meeting transcript {YYYY-MM-DD}.md` (strip
  `/ \ : * ? " < > |` from the name). See `westland:westland-house-style`.
- **Reading one back later:** glob `*transcript*.md` (newest wins) — the same
  convention the scheduling weekly-update flow uses, so the artifacts are
  interchangeable.

## What NOT to do

- Don't `read_resource` the transcript URL from the **main** agent — that dumps
  30–70 KB into your context. That's the whole bug this skill fixes.
- Don't scavenge OneDrive / project folders / SharePoint / mail / the web.
- Don't retry-loop a missing connector or a no-access transcript — surface the
  reason and stop.
- Don't sort transcript cues by timestamp (cross-talk overlaps; the converter
  preserves speech order) and don't hand-parse the WebVTT — drive the script.
- Don't paste the raw transcript body back from the subagent to the main agent.

## Reference files

| File | Load when |
|---|---|
| [`references/connect-m365.md`](references/connect-m365.md) | The connector isn't connected — show the user how to add it. |
| [`scripts/transcript_json_to_md.py`](scripts/transcript_json_to_md.py) | Always — the subagent runs it to convert the transcript JSON to markdown. |
