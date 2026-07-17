#!/usr/bin/env python3
"""Convert a Teams meeting-transcript resource (JSON) into readable markdown.

Input is the JSON object returned by the Microsoft 365 connector's
`read_resource` on a `meeting-transcript:///events/...` URI, saved to a file.
Its shape (validated 2026-07-16 against a real Westland Teams meeting):

    {
      "meeting":     { "subject": str, "startDateTime": iso, "endDateTime": iso, ... },
      "transcripts": [ { "id": str, "createdDateTime": iso, "endDateTime": iso,
                         "content": "<WebVTT blob>" }, ... ]
    }

`content` is a single WebVTT string, NOT structured speaker-turn objects.
Speaker names are inline VTT voice tags: `<v Speaker Name>spoken text</v>`.

This script is deliberately dumb: it parses the VTT and emits markdown speaker
turns. It does NOT summarize and does NOT write YAML frontmatter — the calling
agent adds the frontmatter summary block on top after reading this output.

Usage:
    python transcript_json_to_md.py <input.json> <output.md>
    python transcript_json_to_md.py <input.json>            # writes to stdout

Design notes learned from the real data:
  * `\r\n` line endings throughout — normalize before splitting.
  * Cues are NOT strictly chronological (cross-talk overlaps) — preserve array
    order, never sort by timestamp.
  * `transcripts` may hold more than one segment for a recurring occurrence —
    loop and concatenate.
  * A cue may have no `<v>` tag (unattributed speech) — handle gracefully.
  * HTML entities (`&amp;`, `&lt;`, ...) may appear — unescape them.
  * Consecutive cues by the same speaker are coalesced into one turn so the
    output reads as dialogue, not 200 one-word lines.
"""

import argparse
import html
import json
import re
import sys

# VTT timestamp line, e.g. "00:04:06.420 --> 00:04:06.820" (hours optional).
_TS_LINE = re.compile(
    r"^\s*(?P<start>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<end>(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{1,3})"
)
# Voice tag: <v Speaker Name>text</v>  (closing tag optional in the wild).
_VOICE = re.compile(r"<v\s+([^>]+?)>(.*?)(?:</v>)?$", re.DOTALL)
# Any residual VTT/HTML tag (<c>, <lang>, <b>, stray <v ...>, etc.).
_TAG = re.compile(r"<[^>]+>")


def _hms_to_label(ts: str) -> str:
    """'00:04:06.420' -> '04:06'; '01:02:03.000' -> '1:02:03'. Best-effort."""
    ts = ts.replace(",", ".").split(".", 1)[0]
    parts = ts.split(":")
    try:
        parts = [int(p) for p in parts]
    except ValueError:
        return ts
    if len(parts) == 3:
        h, m, s = parts
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    if len(parts) == 2:
        m, s = parts
        return f"{m:02d}:{s:02d}"
    return ts


def _clean(text: str) -> str:
    """Strip residual tags, unescape entities, collapse whitespace."""
    text = _TAG.sub("", text)
    text = html.unescape(text)
    return " ".join(text.split()).strip()


def parse_vtt(content: str):
    """Parse a WebVTT blob into ordered (start_label, speaker, text) tuples.

    Speaker is None when the cue carries no <v> voice tag. Array order is
    preserved (cross-talk means timestamps are not monotonic).
    """
    if not content:
        return []
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    # WebVTT cues are separated by blank lines. Split on 2+ newlines.
    blocks = re.split(r"\n\s*\n", content)
    turns = []
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        # Find the timestamp line; text is everything after it. A leading cue
        # id line (before the timestamp) is ignored. Skip the WEBVTT header and
        # NOTE/STYLE/REGION blocks.
        ts_idx = None
        for i, ln in enumerate(lines):
            if _TS_LINE.match(ln):
                ts_idx = i
                break
        if ts_idx is None:
            continue  # header, NOTE, STYLE, or malformed block
        start = _TS_LINE.match(lines[ts_idx]).group("start")
        payload = "\n".join(lines[ts_idx + 1:]).strip()
        if not payload:
            continue
        m = _VOICE.search(payload)
        if m:
            speaker = _clean(m.group(1)) or None
            spoken = _clean(m.group(2))
        else:
            speaker = None
            spoken = _clean(payload)
        if spoken:
            turns.append((_hms_to_label(start), speaker, spoken))
    return turns


def coalesce(turns):
    """Merge consecutive cues by the same speaker into one dialogue turn.

    Keeps the first cue's timestamp label for the merged turn.
    """
    merged = []
    for label, speaker, spoken in turns:
        if merged and merged[-1][1] == speaker:
            merged[-1] = (merged[-1][0], speaker, merged[-1][2] + " " + spoken)
        else:
            merged.append((label, speaker, spoken))
    return merged


def render(data) -> str:
    """Render the transcript JSON object to a markdown body (no frontmatter)."""
    # Be liberal about the input shape.
    if isinstance(data, str):
        data = {"transcripts": [{"content": data}]}
    meeting = data.get("meeting") or {}
    transcripts = data.get("transcripts")
    if transcripts is None:
        # Maybe the whole object IS a single transcript.
        transcripts = [data] if data.get("content") else []

    out = []
    subject = (meeting.get("subject") or "Meeting").strip()
    out.append(f"# {subject} — Transcript\n")
    if meeting.get("startDateTime"):
        out.append(f"- **Meeting series start:** {meeting['startDateTime']}")
    out.append(f"- **Transcript segments:** {len(transcripts)}\n")

    if not transcripts:
        out.append("_No transcript content was present in the resource._\n")
        return "\n".join(out)

    multi = len(transcripts) > 1
    for idx, tr in enumerate(transcripts, 1):
        turns = coalesce(parse_vtt(tr.get("content") or ""))
        if multi:
            when = tr.get("createdDateTime", "")
            out.append(f"\n## Segment {idx}{f' — {when}' if when else ''}\n")
        else:
            out.append("\n## Transcript\n")
        if not turns:
            out.append("_(segment contained no readable speech)_\n")
            continue
        for label, speaker, spoken in turns:
            who = speaker if speaker else "Unknown speaker"
            out.append(f"**[{label}] {who}:** {spoken}\n")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("input_json", help="Path to the saved transcript JSON file.")
    ap.add_argument("output_md", nargs="?",
                    help="Path to write markdown to. Omit for stdout.")
    args = ap.parse_args(argv)

    # Files are always written UTF-8; make stdout/stderr UTF-8 too so a caller
    # capturing stdout on a legacy Windows code page doesn't mangle em-dashes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    with open(args.input_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    body = render(data)

    if args.output_md:
        with open(args.output_md, "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"Wrote {args.output_md} ({len(body)} chars).", file=sys.stderr)
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
