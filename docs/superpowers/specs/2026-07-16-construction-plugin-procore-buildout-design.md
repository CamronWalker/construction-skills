# Construction plugin + Procore build-out — design

**Date:** 2026-07-16
**Branch:** `claude/procore-mcp-toolkit-4c5e74`
**Goal:** One feature PR to `main` that (1) consolidates the construction-phase plugins into a new `construction` plugin and (2) builds out a Procore-native skill set on the dedicated Procore MCP.

---

## 1. Summary

Take a look at the Procore MCP, build a Procore "toolkit" skill plus a set of Procore-data-native workflow skills, move the existing daily-log-review skill in with them, and fold the construction-phase plugins together under one roof.

Originally scoped as a standalone `procore` plugin. Reframed after review: these are **construction-phase** skills (field / PM / site), not a separate integration silo. So they land in a new **`construction`** plugin that absorbs `project-management` and `site-operations`, with every skill re-prefixed `construction-*`.

## 2. Scope & non-goals

**In scope**
- New `construction` plugin (`construction/`), version `0.1.0`.
- Merge all `project-management` + `site-operations` skills into it, re-prefixed `construction-*`.
- Add 8 new Procore-native skills (below).
- Retire the `project-management` and `site-operations` plugins (delete dirs, drop marketplace entries).
- Update the repo plumbing: `marketplace.json`, `CLAUDE.md`, root `README.md`, `.github/workflows/lint.yml`, `build.py`.

**Explicitly out of scope**
- **`estimating`** — untouched. A separate agent owns the `preconstruction` rename/PR. Do not edit `estimating/`, and keep its `marketplace.json` / `README` / `CLAUDE.md` / `lint.yml` / `build.py` entries as-is.
- **`scheduling`**, **`safety`**, **`westland`** — unchanged. (Scheduling stays its own mature plugin with its own MCP + versioning.)
- No changes to the Procore MCP server itself — this repo only authors skills that call it.

## 3. Coordination risk (parallel PR)

A second agent is preparing the `preconstruction` PR (renaming `estimating`). Both PRs touch shared files: `marketplace.json`, `CLAUDE.md`, `README.md`, `lint.yml`, `build.py`. Mitigation:
- Keep every edit to those shared files **surgical** — touch only the PM/Site → Construction lines; never touch the `estimating` entry/section.
- Whichever PR merges second rebases on `main` and resolves the (small, localized) conflicts.

## 4. Plugin taxonomy after this PR

| Plugin | State | Notes |
|--------|-------|-------|
| `westland` | unchanged | Org plugin, install-first dependency. |
| `scheduling` | unchanged | Own MCP, v9.6.0. |
| `estimating` | **untouched by this PR** | Being renamed to `preconstruction` by another agent. |
| `construction` | **new (0.1.0)** | PM + Site + 8 new Procore skills. |
| `safety` | unchanged | |
| ~~`project-management`~~ | **retired** | Skills moved into `construction`. |
| ~~`site-operations`~~ | **retired** | Skills moved into `construction`. |

Net plugin count in `marketplace.json` after this PR: westland, scheduling, estimating, construction, safety (5). CLAUDE.md's plugin-list parenthetical updates from `(westland, scheduling, estimating, project-management, site-operations, safety)` to `(westland, scheduling, estimating, construction, safety)`.

## 5. Skills in the `construction` plugin

11 skills total: 3 moved (re-prefixed), 8 new.

### Moved (re-prefixed, behavior preserved)

| New name | Was | Change |
|----------|-----|--------|
| `construction-change-event` | `pm-change-event` | Rename dir + frontmatter `name`. Refresh the "Procore Integration" section to point at the dedicated Procore MCP (`create_change_event`) + `construction-procore-toolbox`, replacing the stale Zapier-only guidance. |
| `construction-closeout-status-dashboard` | `pm-closeout-status-dashboard` | Rename dir + frontmatter `name`. Move `assets/` + `scripts/build_dashboard.py` intact. No Procore change. |
| `construction-rfi-writing` | `site-rfi-writing` | Rename dir + frontmatter `name`. Refresh the "Procore Integration" section to point at the dedicated Procore MCP (`create_rfi`) + `construction-procore-toolbox`, replacing the stale Zapier-only guidance. |

### New (8)

| Name | Purpose | Key Procore MCP tools |
|------|---------|-----------------------|
| `construction-procore-toolbox` | **Anchor.** Reference + dispatcher + hands-on mini-workflows for the whole Procore MCP surface. | all (survey) |
| `construction-daily-log-review` | Review + grade a project's daily logs over a window; inline story + report card. *(the moved Cowork skill)* | `project_daily_log_quality`, `list_manpower_logs`, `list_call_logs` |
| `construction-project-pulse` | 30-second project-health snapshot from the executive widgets. | `project_rfi_snapshot`, `project_submittal_snapshot`, `project_response_times` |
| `construction-rfi-followup` | Drill overdue RFIs/submittals by ball-in-court; draft chase nudges. | `list_rfis`, `list_submittals`, `list_rfi_ball_in_court_options`, mail MCP (draft only) |
| `construction-daily-log-entry` | Draft & post manpower / call / photo entries; scheduled-vs-actual read. | `create_manpower_log`, `create_call_log`, `create_photo`, `find_company_vendor`, `list_schedule_activities` |
| `construction-email-to-log` | Turn important recent emails into Procore **call-log** entries on the right day. | `create_call_log`, mail MCP |
| `construction-observations-import` | Batch-create observations from an architect/engineer field/observation report — one per item. | `create_observation`, `list_project_users`, `list_locations` |
| `construction-submittal-review` | Pull submittals, check against spec requirements, flag deviations. | `list_submittals`, `get_submittal`, `find_specification`, `get_specification` |

> **Note on `construction-daily-log-review`:** the source lives in a Cowork-managed folder
> (`%APPDATA%\Claude\local-agent-mode-sessions\…\skills\project-daily-log-review\SKILL.md`).
> Copy it into the plugin (re-prefixed). The Cowork copy is left in place — it's a
> desktop-app-managed location, not something this PR should delete.

## 6. Cross-cutting discipline (documented once in the toolbox, referenced by the rest)

- **Project resolution.** Always `find_project` → confirm the match with the user → carry `projectId`. On zero/multiple matches, show candidates and ask. Never guess a `projectId`.
- **Read-before-write / confirm-before-post.** Every write is two-stage: call with `confirm` omitted → show the returned dry-run preview to the user → get an explicit yes → re-call with `confirm:true`. This satisfies *both* the Procore MCP's own write gate (and the `PROCORE_WRITES_DISABLED` kill switch) *and* the standing rule that posting to an external system requires per-action approval.
- **Pagination.** List endpoints paginate; loop on `pagination.has_more` / `page` until exhausted before drawing conclusions.
- **Escape hatch.** For anything without a typed helper: `procore_describe_endpoint` → `procore_get` / `procore_post` / `procore_patch`.
- **Voice.** All skills defer to `westland-house-style` — direct, concrete, active voice; state numbers/dates/dollars plainly.

## 7. Procore MCP capability notes (verified 2026-07-16)

- **Daily-log types creatable via MCP:** manpower (`create_manpower_log`), call (`create_call_log`), photos (`create_photo`). Westland uses manpower + call + photos only; notes live in the manpower `comments` field.
- **Email into daily logs / forward-to-Procore-inbox: NOT AVAILABLE via this MCP — and dropped from the design.** Verified with `procore_describe_endpoint`: neither `GET /rest/v1.0/projects/{project_id}/daily_logs` nor `…/emails` is in the MCP's OAS index, and `manpower_logs` exposes no email-dropbox field. The per-record `procore-…@procoretech.com` dropbox seen in the Procore UI is a UI-only email-thread feature; it is not surfaced by the MCP. **Consequence:** `construction-email-to-log` does email → **call-log capture only** (a communication logged on a date). There is no inbox-forwarding path in the skill — it is not designed, mentioned, or attempted. (Per review decision: if it isn't available, don't ship it.)
- **Observations:** `create_observation` supports `name`, `type` (`commissioning` | `quality` | `safety` | `warranty` | `work_to_complete`), `description`, `assigneeId`, `dueDate`, `priority` (`low`|`medium`|`high`|`urgent`), `status`, `tradeId`, `locationId` — enough for a faithful batch import of a field/observation report.
- **Executive widgets** (`project_rfi_snapshot`, `project_submittal_snapshot`, `project_response_times`, `project_daily_log_quality`) render inline and also return a text summary; results cache ~1h. `project-pulse` and `daily-log-review` lean on these.

## 8. Repo mechanics — files to change

1. **Create** `construction/.claude-plugin/plugin.json` — name `construction`, version `0.1.0`, description < 500 chars (build.py enforces), author/repo/license/keywords matching the house pattern.
2. **Create** `construction/skills/<skill>/SKILL.md` for all 11 skills (3 moved + 8 new); move the closeout dashboard's `assets/` + `scripts/`.
3. **Delete** `project-management/` and `site-operations/` directories.
4. **`.claude-plugin/marketplace.json`** — remove the `project-management` and `site-operations` entries; add a `construction` entry (`0.1.0`, description in lockstep with plugin.json). Leave `estimating` alone.
5. **`CLAUDE.md`** — update the plugin-list parenthetical to `(westland, scheduling, estimating, construction, safety)`.
6. **`README.md`** — replace the `### Project Management` and `### Site Operations` sections with a single `### Construction` section cataloguing the 11 skills. Leave `### Estimating` untouched (other agent owns it).
7. **`.github/workflows/lint.yml`** — change the loop `for plugin in westland scheduling estimating project-management site-operations safety` → `for plugin in westland scheduling estimating construction safety`. (A brand-new plugin passes the gate cleanly: base version empty → monotonicity checks skip; the `+"version":` lines exist because the files are new; lockstep 0.1.0 == 0.1.0.)
8. **`build.py`** — update `PLUGINS = [...]` to `["westland", "scheduling", "estimating", "construction", "safety"]`.

No `.githooks/pre-commit` exists (retired) — nothing to update there. Skills are auto-discovered from `skills/*/SKILL.md`; there is no skills array in `plugin.json` to maintain.

## 9. New-skill authoring detail

Each new skill is a single `SKILL.md` (add `scripts/`/`assets/` only if a skill genuinely needs them; prefer inline `mcp__visualize__show_widget` for visuals, matching the daily-log-review pattern). Frontmatter `name` matches the directory; `description` is trigger-rich (third-person, lists the phrases that should fire it).

### 9.1 `construction-procore-toolbox` (anchor)
- **Triggers:** "procore", "in procore", "pull from procore", "post to procore", "procore tools/api", "look up an RFI/submittal/commitment/observation", plus a catch-all for Procore data tasks not owned by a more specific skill.
- **Body:** auth (`whoami`); project resolution (`find_project` → confirm → `projectId`, `show_project`); the 4 executive widgets; typed helpers grouped by domain (RFIs, submittals, daily logs, observations, punch, drawings, specs, commitments, change events/orders, prime contracts, budget, schedules, meetings, correspondence, documents, users, vendors); pagination; the two-stage write-safety contract + `PROCORE_WRITES_DISABLED`; the raw escape hatch; a **dispatch table** routing common intents to the sibling `construction-*` skills; and a handful of **hands-on mini-workflows** (create an RFI, log manpower/a call, find a vendor, look up a spec/drawing) — the "Also hands-on workflows" depth chosen in review.

### 9.2 `construction-daily-log-review` (moved)
- Port the existing SKILL.md verbatim in behavior; update frontmatter `name`; add a one-line cross-link to `construction-procore-toolbox` and confirm the `westland-house-style` reference. No logic changes.

### 9.3 `construction-project-pulse`
- **Triggers:** "how's the project doing", "project pulse/health", "are RFIs/submittals piling up", "who's sitting on responses", "turnaround", "status snapshot".
- **Workflow:** resolve project → call `project_rfi_snapshot`, `project_submittal_snapshot`, `project_response_times` (offer `project_daily_log_quality` too) → synthesize a short executive narrative from the text summaries → if overdue items exist, offer to hand off to `construction-rfi-followup`.
- **Output:** the inline widgets + a tight narrative. Read-only.

### 9.4 `construction-rfi-followup`
- **Triggers:** "chase overdue RFIs", "who owes us RFI responses", "follow up on submittals", "RFI aging", "ball in court".
- **Workflow:** resolve project → `list_rfis` (open/overdue) + `list_rfi_ball_in_court_options` (+ `list_submittals`), paginate → group by ball-in-court, sort by days overdue → present a prioritized table → optionally **draft** follow-up nudges (mail MCP). Drafts only — never send without explicit approval (external-message rule).

### 9.5 `construction-daily-log-entry`
- **Triggers:** "log manpower", "add a daily log", "log a call", "post today's log", "who was on site today".
- **Workflow:** resolve project → gather entry data (date, vendor via `find_company_vendor`, headcount/hours, comments; or call details) → optional scheduled-vs-actual read via `list_schedule_activities` → **dry-run** `create_manpower_log`/`create_call_log` → preview → `confirm:true`. Photos via `create_photo` when provided.

### 9.6 `construction-email-to-log`
- **Triggers:** "log these emails to Procore", "put this correspondence in the daily log", "record this email on the job", "log the call/email with [party]".
- **Workflow:** pull recent/important emails (mail MCP) or take a pasted thread → user picks which → map each to a call-log (date = email date, `subjectFrom`/`subjectTo` = parties, `description` = summary + follow-ups) → dry-run preview of the batch → `confirm:true` each.
- **No forwarding.** The skill does not forward mail to a Procore inbox — no MCP path exists (§7). Call-log capture is the whole skill.

### 9.7 `construction-observations-import`
- **Triggers:** "add these observations", "import the architect's/engineer's observation report", "batch add to the observations tracker", "turn this field report into observations", "log the punch/design report items".
- **Workflow:** read the report (PDF via the pdf skill / pasted text) → extract each discrete item → map each to `type` (default `work_to_complete` or `quality`), `description`, optional `assigneeId` (`list_project_users`), `dueDate`, `priority`, `locationId` (`list_locations`) → present the full batch as a review table → dry-run each `create_observation` → on approval, `confirm:true` all → report created items with IDs/links and flag any that failed.

### 9.8 `construction-submittal-review`
- **Triggers:** "review submittals against the specs", "check this submittal for deviations", "does this submittal comply", "submittal review".
- **Workflow:** resolve project → `list_submittals`/`get_submittal` (or take an uploaded submittal PDF) → obtain the governing spec (`find_specification` → `get_specification`, or a local spec PDF) → compare product data to spec requirements → produce a compliance table (requirement → submitted value → comply/deviate/insufficient) + draft review comments. Read-only unless the user asks to post comments (then two-stage write).

## 10. Versioning & release

- `construction` starts at `0.1.0`; `marketplace.json` entry in lockstep at `0.1.0`.
- Follow the CLAUDE.md release convention: version bump in both files (new plugin), commit on the feature branch, PR to `main`. The zip build/distribute step happens in the main checkout post-merge (out of this PR's diff — `src/` is gitignored).

## 11. Acceptance criteria

- `construction/` exists with 11 `SKILL.md` files (3 moved + 8 new) and the closeout dashboard's assets/scripts.
- `project-management/` and `site-operations/` are gone.
- `marketplace.json`, `CLAUDE.md`, `README.md`, `lint.yml`, `build.py` reflect the new plugin set; `estimating` is untouched in all of them.
- `python build.py construction` builds a zip with no description-length error.
- `whoami` against the Procore MCP succeeds (auth sanity) and the toolbox's documented tool names all resolve to real MCP tools.
- Feature PR opened to `main` from `claude/procore-mcp-toolkit-4c5e74`.
