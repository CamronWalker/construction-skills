# Worked example — an internal proposal deck

A composite of the deck patterns that have worked for internal proposals: the
kind that argues for a change in how the company operates and needs a decision
at the end. Read this when the deck has to *persuade*, not just report. For a
status report or a schedule update, most of this doesn't apply.

## The arc

Eleven slides. The order is the argument:

1. **Title** — cover page, one-line framing of the ask.
2. **The gap** — a three-up naming the categories the room already thinks in,
   with the missing one marked `hot`. This slide does most of the work: it
   establishes that something is absent before anything is requested.
3. **Demo** — a real screenshot of the thing running.
4. **The mechanism** — a chart showing how the problem develops if untouched.
5. **Second demo** — another real screenshot, different tool.
6. **What exists today** — the story so far.
7. **The demand** — why the work keeps arriving.
8. **The iceberg** — visible surface above the waterline, the real mass below.
9. **The evidence** — the specific numbers behind the case.
10. **ROI** — three big tiles, cost tile in `trivial` teal beside green returns.
11. **Close** — dated commitments.

## What holds up in the room

**Name the gap before making the ask.** The opening slides request nothing. By
the time the ask lands at the end, the room has already agreed something is
missing. Reversed — ask first — everything after becomes justification, and
justification invites argument.

**Real screenshots beat descriptions.** A slide that is one screenshot and one
caption ends a category of skepticism that no amount of prose does. Keep a
labelled placeholder until the real capture exists; don't cut the slide.

**Label illustrative numbers as illustrative.** Where figures are modelled, say
so in a footnote on that slide. Credibility on the real numbers depends on being
visibly honest about the modelled ones — and someone will check.

**Put the cost next to the return.** `.roitile.trivial` renders the ask in
smaller teal type beside larger green returns. The comparison is the argument;
the styling gets out of the way.

**Commit to something dated.** Close on dated deliverables, not a summary. It
gives the room something to say yes to.

**Few words, large type.** Under forty words a slide. The presenter speaks; the
slide anchors.

## Decisions worth reusing

**Decide per audience what goes in the shared copy.** The `--exclude` flag drops
slides from the published fragment while the master keeps all of them. Sensitive
figures, internal appendices, anything that belongs in the room but not in a
forwarded link — make that call deliberately for each audience rather than
publishing whatever happens to be in `slides/`. Once a link is out, assume it
travels.

**Take the DRAFT badge off for the final build.** It lives commented out in
`_99_tail.html`. Uncomment while iterating so nobody mistakes a draft for the
deck; delete before publishing.

**Republish to one URL.** Redeploy every revision to the same artifact URL so a
link already sitting in someone's inbox stays current. A new URL per round
leaves stale copies circulating with no way to catch them.

**Retire slides, don't delete them.** Move superseded slides to
`slides/_archive/`, which the build doesn't glob. Cut material comes back more
often than you'd expect. Renumber the live slides; leave the archive alone.
