# Buildr Toolbox — demo workflows

Four guided recipes. Each is *when to use → tools & params → how to present*. Output goes to
Westland people, so load the **`westland-house-style`** skill and follow it: direct, active voice,
lead with what the reader cares about, state numbers plainly. Confirm any ambiguous slice with the
requester before you pull (which division? what date window?).

Rate-limit reminder: these pull broad and reuse. Don't re-pull the same list for two sections of
one report.

---

## 1. Win/Loss report

**When:** "How are we doing this year?" · quarterly BD review · go/no-go input ("what's our win
rate in \<market\>?") · board/ownership reporting.

**Tools:**
- `get_win_loss_report` — the whole report in one call. Args: `division_id?`, `market_sector?`,
  `since_date?` (all optional; omit for company-wide, all-time).
- It returns rollups by division, market sector, and loss reason, plus top won/lost rows, plus an
  inline widget in hosts that render it.

**Present:**
- Lead with the **single win rate** = wins / (wins + `closed_lost`), and the window it covers.
- Then the cut the requester asked for (by division, or by market sector).
- Then **why we lost** — the loss-reason rollup. This is the actionable part for BD.
- **Always state the classification** so the number isn't misread: *"Win rate excludes projects we
  cancelled or chose not to pursue (no-decision); it's wins over competitive decisions only."* If
  someone quotes a lower number, it's almost always because did-not-pursue got folded into losses
  (~52% vs. the true ~74% — see `gotchas.md`).
- Slice, don't re-pull: for "by division AND by sector," call once and read both rollups from the
  same result.

---

## 2. Workforce availability

**When:** staffing a pursuit or proposal team ("who could we put on this?") · "who's rolling off in
Q3?" · bench check.

**Tools:**
- `get_workforce_availability` — args `division_id?`, `horizon_months?` (default 6). Joins employees
  × assignments × divisions and classifies each person:
  - **Deployed** — has a current/future assignment; roll-off = latest assignment end date.
  - **Bench** — only past assignments.
  - **No assignment** — no assignment records.
  - **Freeing up in horizon** — roll-off ≤ today + horizon.

**Present:**
- Lead with the counts: deployed / freeing-up-in-N-months / bench.
- Then the **freeing-up roster** (name + roll-off date) — that's the actionable list for staffing.
- **Flag the caveat honestly:** bench and no-assignment rows are *needs-confirmation* — they're
  often overhead roles or unmaintained records, not idle field staff. Say so; don't present bench
  headcount as "available people."
- `exclude_from_headcount` employees are tallied separately — keep them out of availability totals.
- The roster caps at 150 rows for transport; if truncated, the tool says so — surface that rather
  than implying full coverage.

---

## 3. Pipeline / pursuit snapshot

**When:** "where's the pipeline right now?" · Monday BD stand-up · proposals capacity planning.

**Tools (pull each once, then roll up in your head / a table):**
- `list_leads` — early pipeline. Group by stage/status.
- `list_projects` — filter to open/pursuit stages (skip `closed_*`). These are live pursuits.
- `list_bidding_packages` — the bid board; surface **upcoming due dates**.
- Optional: `get_win_loss_report` for the trailing win rate as context on the pursuit set.

**Present:**
- A stage-ordered rollup: count (and value if available) per stage, early → late
  (lead → pursuit → bidding → awarded).
- A short **"due this week / next two weeks"** list from the bidding packages — the time-sensitive
  part.
- Keep it a snapshot: counts and the few dated items that need action, not a dump of every record.
- Because Buildr filters are unreliable, filter stages in your own read of the list results and
  sanity-check counts against the unfiltered totals (see `gotchas.md`).

---

## 4. Account 360

**When:** "what do we know about \<owner / partner / GC\>?" before a meeting, a teaming decision, or
a proposal.

**Tools:**
- `get_company` (or `get_contact`) — the anchor record. Get its id from `list_companies` /
  `list_contacts` first if you only have a name.
- Touch history: `list_calls`, `list_emails`, `list_meetings`, `list_comments` — filtered to that
  company/contact, most-recent first.
- Relationship: `list_projects` and `list_bidding_packages` linked to the company; `list_contacts`
  at the company.
- Open items: `list_tasks` / `list_assignments` tied to the account.

**Present:**
- Header: who they are (company/contact, role, division, key fields).
- **Recent touches** — last handful of calls/emails/meetings with dates and who at Westland.
  This is what someone walking into a meeting actually wants.
- **Relationship** — projects we've done or are pursuing with them, bidding packages, key contacts.
- **Open items** — anything assigned or outstanding.
- If the account has almost no history, say so plainly — a thin record is itself the finding.

---

## Output & filing

- Short answers can go straight into chat. For anything a colleague will forward or file, format per
  `westland-house-style` and offer to save it (e.g. under the relevant `W{job} - {Project}` folder,
  dated `YYYY-MM-DD`).
- Never paste raw tool JSON into a report. Summarize; keep the numbers, drop the plumbing.
