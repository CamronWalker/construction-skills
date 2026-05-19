# Phase: `draft` — Create Outlook Draft + Procore Publish

> Loaded by SKILL.md's router when the user invokes `/schedule-update draft`.
> Also requires `_attachments.md` and `procore.md`.

Turns the approved email content into a draft the user opens, reviews, and sends from Outlook. Also fans out to the Procore Documents upload as a single user-visible step.

## Step 1: Locate Source File

Prefer the edited HTML preview: `{dated_folder}/{YYYY-MM-DD}-email-preview.html`. Read it via `references/parse_email_html.py` to extract the reviewed values.

If the HTML preview is missing, fall back to `{dated_folder}/{YYYY-MM-DD}-update-email.md` (the archive markdown). If both are missing:
> "No update email file found for today's folder. Run `/schedule-update email` or `/schedule-update report` first."

## Step 2: Generate the draft (default: `.eml` on disk)

Default path — `references/generate_email_eml.py:generate_update_email_eml()`. The function:
- Builds the HTML body with the canonical `_build_html_body` from `generate_email_msg.py` so the rendered email is byte-identical to the COM path.
- Encodes the body as base64 (NOT quoted-printable — Outlook's compose-mode loader corrupts QP soft line breaks, post-mortem W1177 #15.1).
- Attaches inline screenshots as `multipart/related` parts with `Content-ID` only and no `filename=` (so Outlook shows them inline only, not in the attachment pane — post-mortem W1177 #15.2).
- Attaches the files listed in the preview's Attachments card (parser returns `attachment_paths` — checked & non-archived only). Skips Office temp lock files (`~$Foo.xlsm`).
- Includes the Westland email signature (inline logo, name, title, office phone, optional mobile).
- Sets `X-Unsent: 1` so opening the file lands the user in compose mode with editable To/Cc/Subject and a real Send button.

Output: `{dated_folder}/{YYYY-MM-DD}-update-email.eml`.

No external dependencies — everything is stdlib (`email.message.EmailMessage`).

### Step 2 (alternative): COM Outlook draft

If the user explicitly asks to skip the `.eml` ("save it straight to Outlook Drafts" / "use the Outlook draft path"), call `references/generate_email_msg.py:generate_update_email_msg()` instead. Same kwargs, same body — just writes via Outlook COM automation rather than to disk.

**Pre-conditions for COM path:**
- Classic Outlook must be open (not just installed — open it from Start menu so it syncs to Exchange and the draft shows up in new Outlook)
- `pywin32` must be installed (`pip install pywin32`)

If `pywin32` is missing, prompt: "Install pywin32 with `pip install pywin32`, then retry." If Outlook COM fails entirely, fall back to the `.eml` path automatically and tell the user.

## Step 3: Procore publish (fans out, fires unless skipped)

If `parsed['skip_procore'] == True`, log "Procore: skipped this week (per master toggle)." and proceed to Step 4.

Otherwise, follow `procore.md` to:
1. Import the XER to the Procore Schedule tool.
2. Create / reuse the dated `YYYY-MM-DD` subfolder under the configured documents folder.
3. Upload each attachment with `share_to_procore=True AND checked=True AND status != 'archived'`.
4. Verify each upload via folder listing; retry once on failure.

`procore.md` returns a per-operation result table. Include it in the summary.

## Step 4: Confirm

For the `.eml` path:

> "Draft written to `{eml_path}`. {procore_summary} Double-click the `.eml` to open in Outlook (classic or new), review, then Send."

Where `{procore_summary}` is one of:
- `"Procore: XER imported · folder {folder_id} · {N} uploaded · {M} skipped/failed. Retry with /schedule-update procore if needed."`
- `"Procore: skipped this week (per master toggle)."`
- `"Procore: not initialized — see \`phases/procore.md\` for first-time setup."`

For the COM path: same but mention Outlook Drafts instead of the `.eml`.
