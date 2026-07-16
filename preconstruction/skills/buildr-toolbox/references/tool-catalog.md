# Buildr MCP — tool catalog

The full surface of the `/buildr/mcp` connector: **72 read tools + 20 write tools = 92**, plus the
generic passthrough that reaches every readable endpoint. Grouped by domain so you can route
without round-tripping `buildr_list_endpoints`. Tool names below are the logical names you call.

Single-record `get_*` tools take an id (and often a `project_id` for project-scoped sub-resources).
`list_*` tools return a `{items, pagination}` envelope. When a resource isn't listed here, reach it
through the passthrough.

## Auth / sanity

| Tool | Use |
|---|---|
| `buildr_whoami` | Confirm the connector is wired. `email` = your Procore-federated identity; `buildrUser` = the OAuth-app creator (shared account), **not** you. |

## Generic passthrough (read)

Covers all ~89 GET endpoints, including the ones without a typed tool (go/no-go survey subsystem,
webhooks, small static lookups).

| Tool | Use |
|---|---|
| `buildr_list_endpoints` | The full read catalog; optionally filter by resource substring. Start here when unsure. |
| `buildr_describe_endpoint` | Verified path / params / envelope / docs URL for one endpoint (by tool name, path, or doc slug). Read this before a hand-built `buildr_get`. |
| `buildr_get` | Read-only GET against any `/api/beta` path. GET-only and Buildr-host-only by construction. |

## Insight tools (aggregate + inline widget)

| Tool | Args | Use |
|---|---|---|
| `get_win_loss_report` | `division_id?`, `market_sector?`, `since_date?` | Win rate + won/lost/no-decision rollups by division, market sector, loss reason. See `workflows.md`. |
| `get_workforce_availability` | `division_id?`, `horizon_months?` (default 6) | Per-employee deployed / bench / freeing-up classification. See `workflows.md`. |

Both pull full sets server-side and aggregate in JS (Buildr filters are unreliable — see
`gotchas.md`). They return a compact `structuredContent` plus a text summary, so they work in hosts
that don't render the widget.

## CRM / pipeline

| Resource | list | get |
|---|---|---|
| Companies | `list_companies` | `get_company` |
| Contacts | `list_contacts` | `get_contact` |
| Leads | `list_leads` | `get_lead` |
| Bidding packages (bid board) | `list_bidding_packages` | `get_bidding_package` |
| Calls | `list_calls` | `get_call` |
| Emails (logged records) | `list_emails` | `get_email` |
| Comments | `list_comments` | `get_comment` |
| Meetings | `list_meetings` | `get_meeting` |
| Company roles | `list_company_roles` | — |

## Projects & divisions

| Resource | list | get |
|---|---|---|
| Projects | `list_projects` | `get_project` |
| Divisions | `list_divisions` | — |
| Project changesets | `list_project_changesets` | — |
| Directory memberships | `list_project_directory_memberships` | `get_project_directory_membership` |
| Team memberships | `list_project_team_memberships` | `get_project_team_membership` |
| Documents | `list_project_documents`, `list_project_document_folders` | `get_project_document` |
| Photos | `list_project_photos` | `get_project_photo` |
| Events | `list_project_events`, `list_project_event_types` | `get_project_event`, `get_project_event_type` |

> Several project sub-resources (directory/team memberships, photos, task lists) require a top-level
> **`project_id` query param** — not a path param, not a filter. `buildr_describe_endpoint` tells you
> which.

## Financials

| Resource | list | get |
|---|---|---|
| Prime contracts | `list_prime_contracts` | `get_prime_contract` |
| Change orders | `list_change_orders` | `get_change_order` |
| Billing periods | `list_billing_periods` | — |
| Closed periods | `list_closed_periods` | `get_closed_period` |
| Forecast periods | `list_forecast_periods`, `list_account_forecast_periods` | `get_forecast_period` |

## Tasks

| Resource | list | get |
|---|---|---|
| Tasks | `list_tasks` (unpaginated — no query params) | `get_task` |
| Task lists | `list_task_lists` (needs `project_id`) | `get_task_list` |
| Assignments | `list_assignments` | `get_assignment` |

## Workforce (HR)

| Resource | list | get |
|---|---|---|
| Employees | `list_employees` | `get_employee` |
| Certifications | `list_employee_certifications`, `list_certification_types` | — |
| Experience | `list_employee_experiences`, `list_previous_employer_experiences` | `get_previous_employer_experience` |
| Utilization | `list_employee_utilization_periods` | — |
| Time off | `list_time_off` (requires `filters`) | `get_time_off` |
| Roles | `list_roles` | — |

## Custom fields & users

| Resource | list | get |
|---|---|---|
| Custom fields | `list_custom_fields` | `get_custom_field` |
| Custom field groups | `list_custom_field_groups` | `get_custom_field_group` |
| Users | `list_users` | — |

## Write tools (20)

All confirm-gated (`confirm: true`; omit → dry-run preview) and subject to the
`BUILDR_WRITES_DISABLED` kill switch. Attribution defaults to the shared app account — run
`connect_buildr_account` to attribute writes to yourself. See `gotchas.md`.

| Group | Tools |
|---|---|
| Calls | `create_call`, `update_call` |
| Comments | `create_comment`, `update_comment` |
| Companies | `create_company`, `update_company`, `update_company_role` |
| Contacts | `create_contact`, `update_contact` |
| Emails | `create_email` (logs an email *record*; does not send mail) |
| Meetings | `create_meeting`, `update_meeting` |
| Tasks | `create_task`, `update_task`, `delete_task` (the only delete tool) |
| Task lists | `create_task_list`, `update_task_list` |
| Custom-field values | `set_record_custom_fields` (model ∈ company/contact/project/lead; keyed by `api_name`) |
| Admin generics | `buildr_post`, `buildr_patch` (admin-gated escape hatches — troubleshooting only, not a team write path) |

**Not writable via MCP yet:** project **documents** and **photos** need a byte-upload route Buildr
doesn't expose to the Worker. Use the Buildr UI for those.

## Account access (per-user attribution)

| Tool | Use |
|---|---|
| `connect_buildr_account` | One-time. Returns a short-lived secure link to paste your own Buildr Client ID + Secret; afterwards your writes attribute to you. Credentials never reach Claude. |
| `disconnect_buildr_account` | Remove your stored credentials; writes revert to the shared app account. |
