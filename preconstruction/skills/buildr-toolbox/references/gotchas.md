# Buildr MCP — gotchas & identity model

Distilled from the connector's own service notes (`westland-mcps/src/services/buildr/CLAUDE.md`).
Read this when a result surprises you or before doing anything at volume or writing data.

## Identity: Procore is the login, the token is shared

- **Sign-in** federates from your Westland **Procore** identity (same pattern as SmartPM). The
  connector never touches Procore data — it's identity verification only.
- **Membership gate.** Access mirrors Buildr's own user directory, checked live at sign-in: if
  you're a current Buildr user you're in, otherwise you're not. To grant/revoke MCP access, add or
  remove the person **in Buildr** — there's no separate allowlist. This is safe because every
  Buildr user already has native access to the same data.
- **API access uses a shared org-level token** (client-credentials), because Buildr's Custom App
  only supports that grant. Consequences below.

## Rate limits are per ACCOUNT and shared

One token means Buildr's per-account limits are shared across **all** Westland users on the
connector at once:

| Window | Limit |
|---|---|
| Burst | **20 requests / 10 seconds** |
| Hourly | 2,000 / hour |
| Daily | 48,000 / day |

On a 429 the client auto-retries up to 3× honoring `Retry-After`, but the burst ceiling is easy to
hit when two or three people report simultaneously. **Pull broad and reuse.** Prefer one `list_*`
over N `get_*`; don't fan out per-record calls when a list already carries what you need.

## Write attribution — the shared-token problem, and the fix

- With the shared token, Buildr stamps `created_by` as the **OAuth-app creator (Camron Walker,
  user 110547)** on every mutation, regardless of who ran the tool. No write body exposes a
  settable author field.
- **The fix is `connect_buildr_account`** (run once per person): you paste your own Buildr Custom
  App Client ID + Secret on a short-lived secure Westland page; afterwards your writes run on your
  own token and attribute to you. `disconnect_buildr_account` reverts.
- **Until you connect,** free-text writes (`create_call`/`update_call` notes, `create_comment`
  html, `create_meeting` notes, `create_task` notes, `create_email` body) auto-append a
  "logged via Claude by \<acting user\>" line so the real human is still traceable. Pass
  `omitAttribution: true` to suppress it.

## Buildr silently ignores unsupported `filters`

The API accepts a `filters` object but **quietly returns the unfiltered set** for any filter key it
doesn't recognize — no error. That means:

- A hand-built filtered `buildr_get` can look like it worked while returning everything.
- The insight tools (`get_win_loss_report`, `get_workforce_availability`) deliberately pull full
  sets and filter in JS for this reason — trust their numbers over an ad-hoc filter.
- When you must filter yourself, verify the returned count is plausibly smaller than the unfiltered
  count before you report it. Verify a filter key against `buildr_describe_endpoint` (or the Buildr
  docs) rather than guessing its name.

Other request-shape facts worth knowing: `filters` serializes as `filters[key]=value` (a flat
`filters` returns 400); `list_tasks` is unpaginated and takes no query params; a few sub-resources
need a top-level `project_id` query param (see `tool-catalog.md`). Pagination is via the RFC-5988
`Link` header — the body has no page metadata, and the tools handle it for you.

## Writes are confirm-gated + kill-switched

- Every write tool has `confirm: {const: true}`. **Omit `confirm`** → you get a dry-run preview of
  the exact request (method, path, body). **`confirm: true`** → it writes. Always preview first.
- `BUILDR_WRITES_DISABLED=true` on the Worker turns every mutation into a no-op preview regardless
  of `confirm` — if a write "previews" when you passed `confirm: true`, writes are globally
  disabled.

## Win/loss classification (so the numbers are honest)

Verified against a full live project sweep (2026-07-09):

- **Won** = project status complete/active, or stage category `"won"`.
- **Lost** = status **`closed_lost` ONLY** — a competitive loss. Buildr logs a `loss_reason` on
  100% of these and on no other status.
- **No-decision** = `closed_cancelled` + `closed_did_not_pursue`. We passed, or the owner
  cancelled/deferred — revivable, not a loss to a competitor. **Excluded from the win rate.**
- **Win rate = wins / (wins + closed_lost).** Folding no-decision into losses understates the rate
  badly — measured **~52% vs. the true ~74%**, because did-not-pursue alone (143) outnumbered real
  competitive losses (140).
- `since_date` filters on `award_date` → `bid_due_date` → `created_at` (award_date is populated on
  100% of closed projects).
