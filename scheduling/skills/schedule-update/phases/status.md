# Phase: `status` — Pipeline Status

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `status` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update status` or no arg.

Shows where the project is in the weekly update pipeline based on what files exist.

## Detection Logic

| Check | Indicates |
|-------|-----------|
| Today's dated folder exists | Step 1 (copy) done |
| `{dated_folder}/*.xer` exists | Export done (step 5) |
| `{dated_folder}/*transcript*.md` exists | Transcript present (step 9 — auto-pulled or manual) |
| `{dated_folder}/screenshots/{job_number}-{YYYY-MM-DD}-all-graphs-stacked.png` exists | Stacked PNG built (post-finalize) |
| `{dated_folder}/YYYY-MM-DD-email.json` exists | Cloud-editor draft finalized (step 11) |
| `{dated_folder}/YYYY-MM-DD-update-email.md` exists | Email archived after review |
| `{dated_folder}/YYYY-MM-DD-update-email.eml` exists | `.eml` draft created (step 13) |
| **Procore publish ran today** | check via `procore_get` on the dated folder under `procore_documents_folder_id`; presence of today's `YYYY-MM-DD` subfolder = ran |

Report each phase as DONE / PENDING / NOT STARTED, and name the recommended next step.

### No-arg routing

When invoked without a command, run detection above, then:

- If no dated folder for today → "Run `/schedule-update copy` to set up today's folder."
- If folder exists but no XER → "Export the schedule and drop the XER in `{path}`."
- If XER exists but no `{YYYY-MM-DD}-email.json` → "Run `/schedule-update report`."
- If draft JSON exists but no `.eml` → "Run `/schedule-update draft`."
- If `.eml` exists but Procore folder NOT detected → "Run `/schedule-update procore` to publish."
- If everything detected → "All steps done. `.eml` at `{path}`."
