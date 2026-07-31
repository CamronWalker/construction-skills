# Deck design system

The class vocabulary in `_00_head.html`. Compose slides from these rather than
writing new CSS — a deck that uses six known patterns reads as one document; a
deck where every slide invents its own layout reads as a scrapbook.

- [Brand tokens](#brand-tokens)
- [Slide skeleton](#slide-skeleton)
- [Title slide and the cover](#title-slide-and-the-cover)
- [Logos](#logos)
- [Body patterns](#body-patterns)
- [Charts](#charts)
- [Screenshots](#screenshots)
- [Adding an asset](#adding-an-asset)
- [Typography rules](#typography-rules)

## Brand tokens

CSS variables on `:root`. Use the variable, never the hex — a rebrand should be
one edit. These are the deliverable-neutral Westland palette; a PowerPoint build
of the same deck should pull the same values.

| Token | Hex | Use |
|-------|-----|-----|
| `--teal` | `#17546B` | Primary accent: eyebrows, rules, card tops, links, emphasis |
| `--navy` | `#1B2A38` | Headings inside cards, big numbers |
| `--ink` | `#16202b` | Body text that should carry weight |
| `--slate` | `#46566b` | Default body text |
| `--muted` | `#8a97a7` | Footers, labels, axis text |
| `--line` | `#e4e9ef` | Borders, grid lines |
| `--panel` | `#f3f7fa` | Card and pill fill |
| `--paper` | `#ffffff` | Slide background |
| `--you` | `#b3402f` | Red: variance, risk, "left alone this happens" |
| `--ask` | `#2e7d32` | Green: returns, gains, the upside |
| `--gold` | `#c9a24a` | Third data series |
| `--steel` / `--steel-lt` | `#6E9BB4` / `#a9c4d4` | Secondary series, dashed placeholders |

Deck background outside the slide is `#0b1219` — near-black, so the white slide
reads as a page floating on a dark surface.

## Slide skeleton

Every content slide is the same four parts. Keep them; the repetition is what
makes the deck feel designed.

```html
<section class="slide">
  <div class="chead">
    <div><div class="eyebrow">SECTION LABEL</div><h2>The claim, as a sentence.</h2></div>
    <img class="clogo" src="{{LOGO_DARK}}" alt="Westland">
  </div>
  <div class="crule"></div>
  <div class="cbody">
    <!-- one body pattern from below -->
  </div>
  <div class="cfoot"><span>{{FOOTER_LEFT}}</span><span>{{PRESENTER}}</span></div>
</section>
```

`.cbody` is `flex:1` and vertically centered — content finds its own place, so
don't add spacer divs. `.cfoot` carries a right pad that keeps its text out from
under the floating nav control; don't remove it.

Headlines are claims, not labels. "Buyout is 74% covered" beats "Buyout status".
The eyebrow carries the category so the headline doesn't have to.

## Title slide and the cover

`cover.jpg` is the official Westland cover: the WESTLAND CONSTRUCTION wordmark
is baked into the top-left and the chevron mark into the top-right of the image
itself. That is why `.tcover` starts at `top:37%` — deck titling sits below the
printed header, not on top of it. Moving it up collides with the wordmark.

`object-position:center top` keeps the header anchored when the canvas is a
different aspect than the photo. `.tc-sub` caps at `24em`; two lines maximum.

Every text element on the cover carries a `text-shadow`. The photo has bright
sparks in it — without the shadow, white type disappears into them.

To use a different photo, replace `assets/cover.jpg`. If it has no printed
wordmark, add the light logo to the title slide and move `.tcover` up.

## Logos

Two variants, and picking wrong makes the logo vanish:

- `{{LOGO_DARK}}` — dark wordmark, for the white slide header. This is the one
  nearly every slide uses.
- `{{LOGO_LIGHT}}` — white/grey wordmark, for dark or photographic backgrounds.

Always `class="clogo"` in `.chead` so it sizes and aligns consistently, and
always `alt="Westland"`.

## Body patterns

**`ul.big`** — the default. Three or four bullets, each a claim in bold, with
supporting detail in a nested `<small>`. Resist a fifth bullet; split the slide.

**`.leadin`** — one framing sentence above the bullets. Wrap the operative
phrase in `<b>` and it renders teal.

**`.tri`** — three-up comparison or taxonomy. Add `hot` to the card you're
arguing for (`class="card hot"`); the highlight is the argument. Use `.fn` for
the category, `.verb` for the one-word idea, `.desc` for the sentence, `.when`
pinned to the bottom.

**`.cols`** + `.card`** — two-up for anything that isn't a three-way split.

**`.askrow`** + `.pill`** — a row of stat tiles. Number in `.n`, label in `.l`.

**`.roihero`** + `.roitile`** — three big numbers, green by default. Add
`trivial` to the tile holding the cost or the ask, which turns it teal and
shrinks the number so the returns dominate the comparison.

**`.note`** — the caveat, the assumption, the "so what". Add `swan` for an
amber variant when it's a risk rather than a clarification.

**`.berg`** — iceberg: `.above` for what people see, `.wline`, then `.below` for
the mass underneath. `.chips` in the visible zone, `.mass` in the hidden one.
Good for scope that is mostly invisible.

**`.commit`** — a two-column list of dated commitments. Bold the timeframe.

## Charts

Hand-built SVG, drawn by an IIFE in `_99_tail.html`. No chart library: the deck
has to survive as one file with no network, and an artifact's CSP blocks CDNs.

The pattern:

```html
<!-- in the slide -->
<div class="chartwrap"><svg id="myChart" viewBox="0 0 1000 470" role="img" aria-label="..."></svg></div>
<div class="legend" id="myLegend"></div>
```

```js
/* in _99_tail.html */
try{(function(){
  const W=1000,H=470,mL=58,mR=40,mT=28,mB=48,pw=W-mL-mR,ph=H-mT-mB;
  const x=..., y=...;            // map data to viewBox coordinates
  let s='';                       // build the markup as a string
  document.getElementById('myChart').innerHTML=s;
})();}catch(e){console.error('myChart',e);}
```

Conventions worth keeping:

- **`try/catch` every chart.** One bad chart shouldn't take navigation down with
  it — the deck stays usable and the failure shows up in the console.
- **`viewBox="0 0 1000 470"`** and author in those units. The deck scaler
  handles the rest; never compute against `window`.
- **Label the point, not the axes.** A red annotation reading "18 pts behind"
  next to the gap does more than a legend. Charts here argue.
- **Build the legend in JS** from the same colour constants as the marks, so
  they can't drift apart.
- **Say when numbers are illustrative.** A small footnote under the chart. A
  reader who later discovers a number was made up discounts the whole deck.

## Screenshots

Use `.shot` for the real thing, `.dash` for a placeholder while you're waiting
on it. Keep the placeholder in the deck rather than dropping the slide — an
obviously unfinished slide reads as honest; a missing one reads as a hole in the
argument.

Follow with `.dashcap` stating the *question the screen answers*, not a
description of the screen.

Capture full-window, no cursor, and check for anything in view that shouldn't be
shared — names, dollar figures, other projects. Downscale to roughly 1600px wide
before inlining; a 4K screenshot inflates the artifact by megabytes and looks no
better inside a 1600px canvas.

## Adding an asset

1. Drop the file in `deck-src/assets/`.
2. Add `"{{MY_ASSET}}": "my-file.png"` to `assets/manifest.json`.
3. Reference `{{MY_ASSET}}` in a slide.

Images are base64-inlined as data URIs. Files ending `.b64`, `.html`, `.svg` or
`.txt` are inlined verbatim, which is how you embed a pre-built chart fragment.
The build fails loudly if a manifest entry has no file, and notes any entry no
slide uses.

## Typography rules

Author sizes as `clamp(min, Nvw, max)`; the build pins each to its `max`. The
clamp documents intent and survives as the fallback if the mobile layer is
dropped, but the deck ships at fixed desktop sizes because the canvas scales.

That scale factor is computed in `_mobile.html`, which is guarded against ever
writing a non-positive value — `scale(0)` renders the whole deck invisible and
does not recover on its own. Read *What not to break* in `SKILL.md` before
changing the scaler.

The type is deliberately large. These decks get read on phones and projected in
rooms where someone is at the back. If a slide needs small type to fit, it has
too much on it — split it.
