---
name: buildr-toolbox
description: >
  Buildr CRM / preconstruction reporting via the remote Buildr MCP connector. Win/loss reporting,
  workforce availability, pipeline & pursuit snapshots, and account-360 lookups for business
  development, estimating, and proposals. Trigger on: Buildr, win rate, win/loss, pipeline,
  pursuit, bid board, workforce availability, bench / who's free, bidding package, lead, contact,
  company, CRM, prime contract, change order, forecast period, account history, precon reporting,
  go/no-go.
---

# Buildr Toolbox

> **Companion skill for the remote Buildr MCP connector (`/buildr/mcp`).** The connector lives in
> the `westland-mcps` repo; this skill does not ship code — it routes the connector's tools and
> gives guided report recipes. Call tools by name (e.g. `get_win_loss_report`, `list_leads`,
> `get_company`). If those tools aren't available, the Buildr connector isn't connected: add it in
> Settings → Connectors (it signs in through your Westland **Procore** identity, and you must be a
> current **Buildr** user). Confirm wiring with `buildr_whoami`.

Buildr is Westland's cross-role platform — **business development** (leads, pipeline, win/loss),
**estimating** (bid boards, go/no-go), and **proposals** (staffing, references, teaming) all live
here. This skill is read-and-report first; writes are real but fenced (see the last section).

==============================================================================
## Read before you pull — the four things that bite

1. **Shared org token → shared, per-ACCOUNT rate limits.** Every Westland user's calls run on one
   Buildr token. Limits are per account: **burst 20 req / 10 s**, 2,000/hr, 48,000/day. Two or
   three people reporting at once can trip the burst limit. Pull broad, then reuse — don't loop
   one-record-at-a-time when a list call will do.
2. **Writes are attributed to the app creator (Camron), not you** — unless you've run
   `connect_buildr_account` (see the Writes section). Free-text writes auto-append a
   "logged via Claude by \<you\>" line so the human is still traceable.
3. **Buildr silently ignores unsupported `filters`.** A filter Buildr doesn't recognize returns the
   *unfiltered* set, not an error. The insight tools already pull full sets and filter in JS; when
   you filter by hand, verify the count makes sense before trusting it. See `references/gotchas.md`.
4. **Reports represent Westland.** Load the **`westland-house-style`** skill before writing any
   report or email the numbers feed into.
==============================================================================

## Quick routing

| I need to… | Call |
|---|---|
| Win rate / why we're losing, by division & market sector | `get_win_loss_report` (insight + widget) — see `references/workflows.md` |
| Who's deployed / on the bench / freeing up soon | `get_workforce_availability` (insight + widget) |
| Confirm the connector is wired / who am I | `buildr_whoami` |
| List / open a **lead** | `list_leads`, `get_lead` |
| List / open a **company** or **contact** | `list_companies`, `get_company`, `list_contacts`, `get_contact` |
| List / open a **bidding package** (bid board) | `list_bidding_packages`, `get_bidding_package` |
| Recent **calls / emails / meetings / comments** on an account | `list_calls`, `list_emails`, `list_meetings`, `list_comments` (+ `get_*`) |
| List / open a **project**; divisions | `list_projects`, `get_project`, `list_divisions` |
| Project **documents / photos / events / team** | `list_project_documents`, `list_project_photos`, `list_project_events`, `list_project_team_memberships` |
| **Financials** — prime contracts, change orders, billing/forecast/closed periods | `list_prime_contracts`, `list_change_orders`, `list_billing_periods`, `list_forecast_periods`, `list_closed_periods` (+ `get_*`) |
| **Tasks / assignments** | `list_tasks`, `list_task_lists`, `list_assignments` (+ `get_*`) |
| **Workforce** — employees, certs, experience, utilization, time-off | `list_employees`, `list_employee_certifications`, `list_employee_experiences`, `list_employee_utilization_periods`, `list_time_off` |
| **Custom fields** (discover api_names) | `list_custom_fields`, `list_custom_field_groups` |
| Users / roles | `list_users`, `list_roles`, `list_company_roles` |
| Anything not listed — any of ~89 read endpoints | `buildr_list_endpoints` → `buildr_describe_endpoint` → `buildr_get` |

Full domain-grouped catalog (72 reads + 20 writes + passthrough): `references/tool-catalog.md`.

## Who reaches for what

- **Business development** — pipeline health and relationships. `get_win_loss_report`, `list_leads`,
  the Account 360 recipe, `list_calls` / `list_meetings` for touch history. Logs touches with the
  write tools (`create_call`, `create_meeting`).
- **Estimating** — the bid board and go/no-go. `list_bidding_packages`, `list_projects` filtered to
  precon stages, and `get_win_loss_report` sliced by market sector to inform a bid decision.
- **Proposals** — staffing and references. `get_workforce_availability` to see who can be put on a
  pursuit team, won-project history (from the win/loss data) for past-performance references, and
  `get_company` / `get_contact` for teaming partners.

## Demo workflows (recipes)

Each recipe is *when to use → exact tools → house-style output*. Full detail in
`references/workflows.md`.

1. **Win/Loss report** — `get_win_loss_report`. Win rate by division + market sector + loss reason,
   with an inline widget. Note the classification: **lost = `closed_lost` only**; cancelled /
   did-not-pursue are a separate *no-decision* bucket excluded from the rate (true rate ≈ 74%, not
   the ~52% you get if you fold them into losses).
2. **Workforce availability** — `get_workforce_availability`. Deployed / bench / freeing-up over a
   horizon (default 6 months). Bench & no-assignment rows are flagged *needs-confirmation* (often
   overhead roles, not idle staff).
3. **Pipeline / pursuit snapshot** — `list_leads` + `list_projects` (open stages) +
   `list_bidding_packages` (upcoming due dates), rolled up by stage. The "where's the pipeline"
   view for BD + proposals.
4. **Account 360** — one company/contact: linked projects, recent calls/emails/meetings, bidding
   packages, open tasks. The "what do we know about this owner/partner" lookup.

## Writes — fenced, and how to make them yours

Buildr has **20 write tools** (create/update calls, comments, companies, contacts, emails,
meetings, tasks, task lists; `set_record_custom_fields`; admin-only `buildr_post`/`buildr_patch`).
They are secondary to reporting. Before using them, know:

- **Confirm gate.** Every write needs `confirm: true`. Omit it → you get a dry-run preview of the
  request, not a mutation. Always preview first, then confirm.
- **Attribution.** By default `created_by` is the shared app creator (Camron), **not the signed-in
  user**. Two mitigations, in order of preference:
  1. **Run `connect_buildr_account` once.** It returns a short-lived link to a secure Westland page
     where you paste your *own* Buildr Custom App Client ID + Secret (credentials go straight to
     secure storage — Claude never sees them). After that, your writes attribute to **you**.
     `disconnect_buildr_account` reverts to the shared account.
  2. If you haven't connected, free-text writes still auto-append a "logged via Claude by \<you\>"
     line to the body, so the human is traceable even though `created_by` shows the app creator.
- **Custom-field values** are set through the record's own update with `set_record_custom_fields`
  (model ∈ company/contact/project/lead), keyed by the field's `api_name` — discover those via
  `list_custom_fields`.
- **Kill switch.** If writes are globally disabled (`BUILDR_WRITES_DISABLED`), every mutation is a
  no-op preview regardless of `confirm`.

See `references/gotchas.md` for the identity model and `references/tool-catalog.md` for the full
write inventory.
