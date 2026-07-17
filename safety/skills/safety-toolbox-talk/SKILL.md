---
name: safety-toolbox-talk
description: >
  Generate a jobsite toolbox talk (a.k.a. tailgate / safety meeting / safety
  moment) on a given hazard topic, ready to print with a crew sign-in sheet.
  Use this skill whenever the user asks to "write a toolbox talk", "create a
  toolbox talk", "toolbox talk on fall protection", "safety talk", "tailgate
  meeting", "weekly safety meeting", "safety moment", "TBT", "pre-task safety
  briefing", "give me a 5-minute safety talk", or "we need a talk about" a
  hazard (heat, silica, ladders, excavation, electrical, PPE, housekeeping,
  hand tools, struck-by, caught-between, etc.). Also trigger when the user
  points at a recent incident, near-miss, or observation and wants a talk that
  addresses it. The skill asks only for what it needs (topic, trade/crew, and
  any site specifics), then produces a focused talk covering the hazard, why
  it matters, the controls and safe work practices, required PPE, a few
  discussion questions, and a dated sign-in block — as printable markdown by
  default, or a Word document on request.
---

# Toolbox Talk Generator

Produce a short, focused safety talk a foreman can read to the crew in five
minutes before work starts. A good toolbox talk names one hazard, explains why
it matters *on this job today*, lists the controls in plain language, and ends
with the crew signing that they heard it.

## When to use

- The crew needs this week's (or today's) safety meeting document.
- A near-miss, incident, or observation just happened and the topic should
  respond to it directly.
- A new task is starting (excavation opening, crane pick, roof work) and the
  foreman wants a pre-task briefing on the specific hazard.

## What to gather first

Ask only for what you can't infer. Usually you need:

1. **Topic / hazard.** If the user gives an incident or observation instead of
   a topic, derive the topic from it (e.g. "guy rolled his ankle on debris" →
   housekeeping / slips-trips-falls).
2. **Trade or crew** (framers, concrete, electrical, general labor) — tunes the
   examples and PPE.
3. **Site specifics**, if any — weather (heat/cold), current activities, known
   conditions. Skip if the user has nothing to add; use sensible defaults.

Don't interrogate. One round of questions at most; if the user just says
"toolbox talk on ladders," write it.

## Structure of the talk

Keep it to one page. Use this order:

1. **Header** — Topic, project/date line, presented-by line.
2. **Why it matters** — 2–3 sentences. Real consequence, not a lecture. Tie to
   the crew's actual work.
3. **The hazards** — a short bulleted list of how someone gets hurt.
4. **Safe work practices / controls** — the meat. Bulleted, imperative, doable
   ("Inspect the ladder before each use; tag and remove any with cracked
   rails"). Prefer the hierarchy of controls — eliminate/substitute/engineer
   before relying on PPE and training.
5. **Required PPE** — specific to the task.
6. **Discussion questions** — 2–3 open questions to get the crew talking, not
   yes/no.
7. **Sign-in** — a dated table: printed name, signature, company/trade.

## Regulatory grounding

Reference the relevant OSHA 1926 (construction) standard by number where it
adds authority (e.g. fall protection → 1926 Subpart M; excavations → Subpart P;
silica → 1926.1153). Keep it a one-line "Reference:" note — this is a crew
briefing, not a compliance memo. Never invent a citation; if unsure of the
exact number, describe the standard by name instead.

## Output

- **Default:** printable markdown, one page, with the sign-in table at the
  bottom.
- **On request** ("as a Word doc", "printable", "for the binder"): produce a
  `.docx` via the `docx` skill. Follow Westland house style for the header and
  document naming; load the `westland-house-style` skill if you're unsure of
  the format.

## Notes

- Write for the field. Short sentences, plain words, no HR-speak.
- One topic per talk. If the user lists several, ask which one, or offer to
  produce a short series.
- This skill is standalone — it doesn't require any MCP connector. If a Procore
  connection is available and the user wants the source incident pulled in,
  the construction plugin's observation/incident tools can supply the details;
  otherwise work from what the user tells you.
