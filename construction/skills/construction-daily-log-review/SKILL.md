---
name: construction-daily-log-review
description: >
  Review a Procore project's daily logs over the past month and tell the story of
  what the field actually did — then grade how well they documented it. Produces
  three stacked inline visuals: (1) the Procore daily-log-quality chart on top,
  (2) a thoroughness rating scorecard, (3) an "Executive Insights" narrative of the
  month plus growth areas for next month. Use this whenever someone asks to "review
  the daily logs", "how's the field doing on logging", "are we keeping up on daily
  logs", "manpower summary for the last month", "what happened on [project] this
  month", "daily log report card", "grade the site documentation", or wants a
  month-in-review of manpower / call logs / site activity for a project. Trigger
  even if they don't say "daily log" explicitly but clearly want a look-back at
  field documentation or site activity for a project over a period of time.
---

# Construction Daily Log Review

Read a project's daily logs for the past month, reconstruct the story of what happened on site, and grade how thoroughly the field team documented it. Everything renders **inline** — the Procore quality visual on top, then a rating scorecard and an Executive Insights narrative below it. No file is written unless the user asks.

> **Procore access:** this skill reads through the dedicated Procore MCP. For project resolution, pagination, and the full tool surface, see `construction-procore-toolbox`.

## Why this exists

Daily logs are the field's record of the job — who was on site, how many bodies, what got built, who called about what. When they're kept well, they protect the company in disputes and give the office a real read on progress. When they slip, everyone finds out too late. This skill does two jobs at once: it **tells the story** of the month from the logs (so a busy PM or director gets the month in 30 seconds), and it **holds up a mirror** on documentation quality with a fair, transparent grade and concrete ways to do better next month.

Keep the tone honest and useful, not scolding. The point is to help the field improve, not to dunk on them.

## What Westland logs in Procore (important scoping)

Westland uses only three daily-log types in Procore: **manpower logs**, **call logs**, and **photos**. Weather, delay, and work logs are not used. So "breadth of logging" means those three — never penalize the team for not using log types the company doesn't use. This keeps the grade fair.

Notes live in the `comments` field of each **manpower** log — there is no separate notes log.

## Data sources (Procore MCP)

| Tool | What it gives you |
|------|-------------------|
| `find_project` | Resolve a project by name/number substring → `projectId`. |
| `project_daily_log_quality` | The **top visual** — inline grouped-bar chart of manpower/photos/calls per day + "days with a manpower entry" completeness read, over a rolling 30 days. Also returns a text summary you can mine. |
| `list_manpower_logs` | Per-entry detail for the window: `date`, `contact_company`, `num_workers`, `hours`, `total_hours`, `comments`. This is the backbone of both the story and the rating. Paginate on `pagination.has_more`. |
| `list_call_logs` | Call/phone entries for the window: `datetime`, `subject_to`, `subject_from`, `description`. Paginate. |

Photos are already summarized inside `project_daily_log_quality` (photos-per-day). Lean on that rather than paging every photo, unless the user wants photo detail specifically.

## Workflow

### 1. Resolve the project and the window

If the user named a project, call `find_project` to get the `projectId`. If the search returns nothing or several matches, show what you found and ask which one — don't guess.

The window is **configurable**; default to the **last 30 days** if the user didn't specify. Get today's date (it's in your environment, or run `date +%F`) and compute `dateFrom`/`dateTo`. Honor phrases like "June", "last two weeks", "since May 1". State the window you used so there's no ambiguity.

One wrinkle to surface honestly: `project_daily_log_quality` always renders a **rolling 30-day** view — that's what the tool produces. The rating and story below it honor whatever window was requested. If those differ (e.g., the user asked for "June" but it's mid-July), say so in a sentence so the top chart and the numbers below don't look contradictory.

### 2. Render the top visual

Call `project_daily_log_quality(projectId)`. It renders its own inline widget — that's the "visual on top." Read its text summary too; it feeds the rating and narrative.

### 3. Pull the detail

Call `list_manpower_logs` and `list_call_logs` across the window, paginating until `has_more` is false. This is the raw material for everything below.

### 4. Reconstruct the story

Before grading, understand what actually happened. Walk the manpower logs in date order and look for the shape of the month:

- **Who was on site, when.** `contact_company` over time shows the trade sequence — sitework early, then concrete, then framing, etc. Note when new companies appear and when they drop off.
- **Intensity and trend.** `num_workers` and `total_hours` per day — is manpower ramping up, steady, or falling off? Call out the peak day and any stretches of low or zero staffing.
- **What got built.** Mine the `comments` for the actual work described. This is where the narrative lives.
- **Calls.** Skim call-log `description`/`subject` for anything that signals coordination, problems, or owner/architect involvement.

The goal is a short, concrete story a director could read in 30 seconds: what phase the job is in, what moved, what stalled, and anything notable.

### 5. Grade thoroughness

Score how well the field documented the month. This is a **guideline, not a rigid formula** — use judgment and explain your reasoning. Give an overall grade (a letter A–F and a 0–100 read the same way a report card does) built from these factors:

**Day coverage (~40%)** — the single strongest signal. Of the working days in the window, how many have a manpower entry? Count distinct dates with a manpower log against weekdays (Mon–Fri) in the window; Saturday/holiday entries are a bonus, not a requirement, and don't hold missing weekends against a job that doesn't work them. `project_daily_log_quality` already computes a completeness read — use it. A job logging most working days is doing the core job right.

**Documentation richness (~35%)** — how much a reader actually learns from a given day. This is where the manpower-vs-notes tradeoff lives: **rich manpower detail can stand in for written notes.** A day with several companies broken out, worker counts, and hours filled in tells the story even with a blank comment. Conversely, a bare entry ("12 men") with no company breakdown and no comment is thin. So reward *either* a good per-company/hours breakdown *or* meaningful comments — you don't need both, and don't double-penalize a team that logs detailed manpower but writes few notes. Penalize only when a day is genuinely uninformative.

**Breadth (~15%)** — are they using more than one log type? Photos and call logs on top of manpower show a team that's documenting fully. **Call logs specifically:** check whether any calls were logged at all — many field teams never touch this, so if calls are absent, that's a natural growth area to name (not a heavy penalty). Presence of photos (from the quality summary) counts here too.

**Consistency (~10%)** — is documentation holding up or slipping? A month that starts strong and fades tells a different story than steady effort. Reward consistency; flag a downward trend.

Translate to a grade with common sense: near-full coverage with informative entries and some breadth is an A; solid coverage but thin/uninformative entries lands in the B/C range; big gaps in coverage pull toward D/F regardless of how nice the logged days look, because a log nobody keeps isn't protecting anyone.

### 6. Name growth areas

Close with 2–4 **specific, actionable** things to do better next month, targeted at the weakest factors. Concrete beats generic: "Log calls with the architect — there were zero call entries in June despite the RFI back-and-forth" is useful; "improve documentation" is not. If they're strong everywhere, say so and name the one thing that would take them from good to airtight.

### 7. Render the widgets below the top visual

Before building, call `mcp__visualize__read_me` once with modules `["data_viz","chart"]` to load the theming variables, then produce **one** `mcp__visualize__show_widget` call containing two stacked sections: the **rating scorecard** on top and the **Executive Insights** narrative below it. One widget keeps it a single coherent "report card" under the Procore chart.

**Rating scorecard section:**

- A prominent overall grade — letter + score (e.g., **B+ · 84/100**) — with a one-line verdict.
- The four factors below it, each with a small proportional bar (or 5-dot rating) and a one-line, specific explanation ("Coverage: 22 of 23 working days logged", "Richness: strong company breakdowns, comments sparse").
- Use the CSS variables from `read_me` so colors match the app; green/teal for strong, amber for soft, red for weak.

**Executive Insights section** — match the reference house style exactly:

- A header in uppercase, letter-spaced, muted color, e.g. `EXECUTIVE INSIGHTS — [PROJECT] · [WINDOW]`.
- A stack of rows. Each row is a light rounded rectangle with a **thick colored left border**: green/teal for wins and progress, amber/red for concerns and gaps. One to two sentences each, always concrete with numbers, dates, and company names pulled from the logs.
- The first few rows tell the **story of the month** (trade sequence, manpower trend, what got built, notable calls). The last rows are the **growth areas** for next month, visually distinct (amber/red border) so they read as the to-do list.

Aim for 5–8 insight rows total. Every row earns its place by saying something specific — no filler like "documentation is important."

**Voice** (see `westland-house-style`): direct, concrete, active voice, short. Lead with what matters. State numbers, dates, and dollar figures plainly — never hedge on hard facts.

## Executive Insight examples

Match this specificity and rhythm — pull the real numbers from the data:

**Story rows (green/teal border):**
- "Concrete dominated the first half of June — Anderson Concrete ran 8–14 workers daily through the 14th, then tapered as framing picked up. The job is transitioning from foundations to vertical."
- "Manpower peaked June 18 at 47 workers across 6 companies — the busiest day of the month and a clean handoff between trades."

**Concern rows (amber/red border):**
- "Coverage dipped hard in the last week — only 2 of 5 working days logged June 24–28, so the tail of the month is a blind spot in the record."
- "Zero calls were logged all month despite active RFI traffic. If the field is coordinating by phone, none of it is on record — a gap if this job ever gets contentious."

**Growth-area rows (amber/red border, phrased as next-month actions):**
- "Next month: log the daily company breakdown even on light days — six 'crew on site' entries in June had no company or hours, which won't hold up as a record."
- "Next month: start logging calls. Even a one-line entry per owner/architect call builds the paper trail this job currently lacks."

## Edge cases

- **No logs in the window** — say so plainly, grade it honestly (an unkept log is an F on coverage), and make the growth areas about simply starting the habit. Don't fabricate a story from nothing.
- **Project not found / multiple matches** — show candidates and ask; never guess the projectId.
- **Sparse data** — a handful of entries is still a story; just keep the narrative proportional and don't over-interpret.
- **User wants it saved** — the default is inline. If they ask for a file, offer an HTML report (self-contained, opens in a browser / prints to PDF) built from the same widget markup.
