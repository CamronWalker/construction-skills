---
name: westland-slide-deck
description: >
  Build a Westland-branded slide deck and publish it as a shareable artifact —
  a private link colleagues open in a browser or on their phone. Ships a
  ready-to-use HTML deck template (Westland cover page, logo header, fixed
  canvas that scales instead of reflowing, rotate-to-landscape gate for phones,
  swipe navigation) plus a build script with a fast local-preview loop. Use
  whenever the user wants a deck, slides, a presentation, a pitch, a capability
  demo, a project review, or an owner or board briefing — including "make me a
  deck", "build some slides", "put a presentation together", "turn this into
  slides", "share this as a link", or "publish the deck" — even if they never
  say the word artifact. If the deliverable has to be a PowerPoint file the
  recipient can edit, use the pptx skill instead; this skill produces a hosted
  link, not a file.
---

# Westland Slide Deck (shareable artifact)

Produces a self-contained HTML deck published to a default-private claude.ai
page. The reader gets a link — no attachment, no PowerPoint, no download — and
it works on a phone, which is where most of these actually get read.

The whole point of the tooling here is a **tight loop**: build to a local file,
serve it, look at it, change one slide, rebuild. Two seconds per cycle. Publish
only when it's right.

## First, confirm the deliverable

A link and a file are different products. Ask if it isn't already obvious:

- **Shareable link** (this skill) — read on a phone, always current, you control
  who has the URL, and it can hold live charts and screenshots at full fidelity.
- **PowerPoint file** — the recipient needs to edit it, drop slides into their
  own deck, or present from their laptop offline. Use the pptx skill.

If they want both, build the deck here first; the content transfers.

## Set up

Copy the template into the project folder the deck belongs to:

```bash
cp -r "<skill-dir>/assets/deck-template" "<project folder>/deck-src"
```

`<skill-dir>` is the base directory reported when this skill loads. That gives you:

```
<project folder>/
  deck-src/
    _00_head.html      design system + <title>   (edit the title once)
    slides/*.html      one file per slide, built in filename order
    _99_tail.html      navigation + per-deck chart scripts
    _mobile.html       fixed-canvas scaling + touch layer  (rarely edited)
    build_deck.py      the build
    assets/            cover, logos, manifest.json
```

Six starter slides ship with it — title, bullets, three-up, screenshot, chart,
close. They are a working deck, not a stub: build immediately and you get
something real on screen. Delete the patterns you don't need.

Fill the `{{TOKENS}}`. Two kinds, and the difference matters:

- **Global** — `{{DECK_TITLE}}`, `{{PRESENTER}}`, `{{FOOTER_LEFT}}`,
  `{{DATE_LINE}}`, `{{KICKER}}`, `{{SUBTITLE}}`. Same value everywhere; safe to
  replace across all files at once.
- **Per-slide** — `{{EYEBROW}}`, `{{SLIDE_HEADLINE}}`, `{{CLOSING_HEADLINE}}`.
  Each slide needs its own. Don't bulk-replace these or every slide ends up with
  the same headline.
- **Asset** — `{{COVER}}`, `{{LOGO_DARK}}`, `{{LOGO_LIGHT}}`. Never edited by
  hand; the build resolves them from `assets/manifest.json`.

`{{DECK_TITLE}}` appears in the `<title>` tag too. If the title slide version
uses a `<br>`, set the `<title>` to the plain-text version — it becomes the
browser tab and the artifact gallery name.

## The iteration loop

This is the part worth doing properly. Build, serve once, then keep rebuilding
behind the running server.

```bash
python deck-src/build_deck.py local
```

Writes `_local-preview.html` next to `deck-src/`, and on first run drops a
`.claude/launch.json` so the preview server knows how to serve the folder. Then:

1. `preview_start` with `{"name": "deck-preview"}` — serves the folder on :8080.
2. Open `http://localhost:8080/_local-preview.html`.
3. Edit a slide file → rerun `build_deck.py local` → reload the tab. The server
   keeps running; you never restart it.

Check the work with `read_console_messages` (a chart that throws leaves the deck
navigable but blank on that slide — easy to miss visually) and by stepping
through every slide. Content that overruns the canvas is the most common defect,
and it doesn't announce itself:

```js
[...document.querySelectorAll('.slide')].map((s,i) =>
  ({slide: i+1, overflows: s.scrollHeight > s.clientHeight + 1}))
```

Before publishing, look at it at phone size. Resize to roughly 844x390 and
confirm the deck scales as one piece — three columns stay three columns. If
something reflowed, a `clamp()` escaped the build's pinning, or a media query
crept into a slide.

## Publish

Build the fragment, then publish it:

```bash
python deck-src/build_deck.py artifact "Deck Name-v1.html"
```

This differs from the local build in two ways that matter. It strips the
`<html>`/`<head>`/`<body>` wrapper — the Artifact tool supplies its own, and a
nested document breaks the page — and it **refuses to build** if any `{{TOKEN}}`
is still unfilled, because a literal `{{DECK_TITLE}}` in a shared deck is the
kind of thing you only notice after sending the link.

Use `--exclude` to drop slides from the shared copy while keeping them in the
master (an internal appendix, a slide with numbers not everyone should see):

```bash
python deck-src/build_deck.py artifact "Deck Name-v1.html" --exclude 09-appendix.html
```

Then publish with the **Artifact tool**, passing that file as `file_path`,
plus a `favicon` and a one-sentence `description`. Load the `artifact-design`
skill first, as that tool requires.

**Updating an existing deck:** call Artifact again with the *same* `file_path`
and it redeploys to the same URL — the link you already sent keeps working. If
the deck was published in an earlier session, pass its `url` (find it with
`action: "list"`); without it you'll mint a new URL and the old link goes stale.
Keep the favicon stable across redeploys.

Artifacts start private. Sharing is the user's call — hand them the URL, don't
distribute it.

## Naming

Per Westland house style: `{Deck Name}-v{N}.html`, no space before the `v`.
`_local-preview.html` keeps its leading underscore — that marks it as a build
output, not a deliverable, and it's regenerated constantly.

Bump the version for each round that leaves your hands. Keep the previous file;
a superseded deck is a record of what was shown, and someone will ask.

## What not to break

Five things in the template are load-bearing. Each cost real debugging to get
right, so change them deliberately:

- **The fixed canvas.** Slides render at 1600x980 and the whole deck is scaled
  to fit. Nothing reflows, so what you approved on a monitor is exactly what
  arrives on a phone. Don't add width media queries to `.slide`.
- **The scale guard in `_mobile.html`.** `fitDeck()` refuses to write a
  `--deck-scale` of `0`. A viewport dimension can measure 0 when the deck is
  parsed in a background or offscreen tab, or mid-rotation on iOS — and
  `scale(0)` doesn't degrade, it renders the entire deck invisible and stays
  that way, because `resize` may never fire afterward. Keep all three parts: the
  `if(s>0)` bail that preserves the last good value, the **timer** ladder retry
  (`requestAnimationFrame` never fires in a tab that isn't compositing), and the
  `ResizeObserver` backstop, which catches real layout changes that raise no
  `resize` event. Don't collapse it back to a one-line `setProperty`.
- **Pinned type.** The build rewrites every `clamp(min, Nvw, max)` to its
  desktop max. Author with clamps anyway — they document intent, and they're the
  fallback if the mobile layer is ever dropped.
- **Everything inlined.** Images become base64 data URIs. An artifact runs under
  a strict CSP with no external requests: a CDN font, a linked stylesheet, or a
  remote image renders as nothing. This is also why charts are hand-built SVG
  rather than a charting library.
- **The rotate gate.** Portrait phones get a "rotate to landscape" screen
  instead of an unreadable 16:9 deck squeezed into a tall viewport. It's gated
  on `pointer:coarse` so narrow desktop windows never see it — which also means
  a desktop browser can't exercise it. To check it, force
  `#rotateHint{display:flex}` and look.

## Reference files

| File | When to read it |
|------|-----------------|
| `references/design-system.md` | Authoring slides — the full class vocabulary, brand tokens, chart conventions, logo and cover rules. Read before writing slide markup. |
| `references/worked-example-internal-proposal.md` | Structuring an argument — the slide arc for a proposal deck and what holds up in the room. Read when the deck has to persuade, not just inform. |
