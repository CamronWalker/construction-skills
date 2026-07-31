#!/usr/bin/env python3
"""Build a Westland slide deck from its parts.

Two targets, one source tree:

    python build_deck.py local
        -> ../_local-preview.html   (standalone file for the preview server)

    python build_deck.py artifact "Deck Name-v1.html" [--exclude 09-appendix.html]
        -> a body-only fragment ready for the Artifact tool

Both targets assemble _00_head.html + slides/*.html (filename order) +
_99_tail.html, inline every asset from assets/manifest.json, pin responsive
font clamps to their desktop values, and inject the phone/touch layer.

Reorder slides by renaming files in slides/. Retire one by moving it to
slides/_archive/ (that directory is not globbed).
"""
import argparse
import base64
import json
import mimetypes
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

SRC = pathlib.Path(__file__).resolve().parent      # the deck-src directory
DECK_ROOT = SRC.parent                             # the project folder holding it
ASSETS = SRC / "assets"

INLINE_VERBATIM = {".b64", ".html", ".svg", ".txt"}
CANVAS_NOTE = "_mobile.html"


def load_assets(text):
    """Replace every {{PLACEHOLDER}} in the manifest with its inlined asset.

    Images become base64 data URIs so the deck stays a single file — an
    artifact has no second request to make, and a colleague who saves the
    local preview to their desktop still sees every screenshot.
    """
    manifest_path = ASSETS / "manifest.json"
    if not manifest_path.exists():
        return text, 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    inlined = 0
    for placeholder, filename in manifest.items():
        path = ASSETS / filename
        if not path.exists():
            sys.exit(f"ERROR: manifest lists {filename}, but {path} is missing.")
        if path.suffix.lower() in INLINE_VERBATIM:
            payload = path.read_text(encoding="utf-8").strip()
        else:
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            payload = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        if placeholder in text:
            text = text.replace(placeholder, payload)
            inlined += 1
        else:
            print(f"  note: {placeholder} is in the manifest but unused by any slide")
    return text, inlined


def assemble(exclude=()):
    head = (SRC / "_00_head.html").read_text(encoding="utf-8")
    tail = (SRC / "_99_tail.html").read_text(encoding="utf-8")
    mobile = (SRC / CANVAS_NOTE).read_text(encoding="utf-8")

    slides = [p for p in sorted((SRC / "slides").glob("*.html"))
              if p.name not in set(exclude) and not p.name.startswith("_")]
    if not slides:
        sys.exit("ERROR: no slides found in slides/*.html")

    text = head + "".join(p.read_text(encoding="utf-8") for p in slides) + tail
    text, inlined = load_assets(text)

    # Pin every clamp(min, Nvw, max) to its desktop max. The fixed-canvas
    # scaler shrinks the deck as one piece, so responsive type would fight it:
    # text would reflow to a different layout than the one that was reviewed.
    text = re.sub(r"clamp\([^,()]+,[^,()]+,\s*([^)]+?)\s*\)", r"\1", text)

    # Inject the phone layer before the FINAL </body>. An embedded chart iframe
    # can carry its own </body> via srcdoc, so anchor on the last one.
    idx = text.rfind("</body>")
    if idx == -1:
        sys.exit("ERROR: no </body> anchor found — is _99_tail.html intact?")
    text = text[:idx] + mobile + "\n" + text[idx:]

    return text, slides, inlined


def check_placeholders(text, strict):
    # Authoring notes live in HTML comments and legitimately mention tokens
    # that aren't wired up yet — scan the rendered content only.
    visible = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    leftover = sorted(set(re.findall(r"\{\{[A-Z0-9_]+\}\}", visible)))
    if not leftover:
        return
    msg = "unresolved placeholder(s): " + ", ".join(leftover)
    if strict:
        sys.exit(f"ERROR: {msg}\n  Fill these in (or add them to assets/manifest.json) before publishing.")
    print(f"  WARNING: {msg}")


def build_local():
    text, slides, inlined = assemble()
    check_placeholders(text, strict=False)

    out = DECK_ROOT / "_local-preview.html"
    out.write_text(text, encoding="utf-8")

    # The preview server config lives with the deck so `preview_start` can find
    # it. Written once; never overwritten, in case it has been customized.
    launch = DECK_ROOT / ".claude" / "launch.json"
    if not launch.exists():
        launch.parent.mkdir(parents=True, exist_ok=True)
        launch.write_text(json.dumps({
            "version": "0.0.1",
            "configurations": [{
                "name": "deck-preview",
                "runtimeExecutable": "python",
                "runtimeArgs": ["-m", "http.server", "8080"],
                "port": 8080,
            }],
        }, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {launch.relative_to(DECK_ROOT)} (preview server config)")

    print(f"BUILT {out.name}: {len(text):,} chars, {len(slides)} slides, {inlined} assets inlined")
    for p in slides:
        print("   ", p.name)
    print("\n  Serve it:  preview_start {\"name\": \"deck-preview\"}  ->  http://localhost:8080/_local-preview.html")
    return 0


def build_artifact(out_path, exclude):
    text, slides, inlined = assemble(exclude=exclude)
    check_placeholders(text, strict=True)

    # De-wrap to a body-only fragment: the Artifact tool supplies its own
    # doctype/<head>/<body>, and a nested document breaks the published page.
    start = text.index("<style>")
    end = text.rindex("</body>")
    frag = re.sub(r"</head>\s*<body[^>]*>", "\n", text[start:end], count=1)

    for banned in ("<!DOCTYPE", "<html", "<head", "<body"):
        if banned.lower() in frag.lower():
            sys.exit(f"ERROR: fragment still contains {banned} — it must be body content only.")

    out = pathlib.Path(out_path)
    out.write_text(frag, encoding="utf-8")

    mb = len(frag.encode("utf-8")) / 1_048_576
    print(f"WROTE {out.name}: {len(frag):,} chars ({mb:.2f} MB), {len(slides)} slides, {inlined} assets inlined")
    if exclude:
        print(f"  excluded: {', '.join(exclude)}")
    n_sections = len(re.findall(r"""class=["']slide\b""", frag))
    print(f"  slide sections: {n_sections}")
    print(f"  contains <iframe>: {'<iframe' in frag}")
    if mb > 5:
        print("  WARNING: over 5 MB — consider downscaling screenshots before publishing.")
    print(f"\n  Publish it:  Artifact tool, file_path = {out}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="target", required=True)
    sub.add_parser("local", help="build ../_local-preview.html for the preview server")
    a = sub.add_parser("artifact", help="build a body-only fragment for the Artifact tool")
    a.add_argument("out", help="output path, e.g. \"Deck Name-v1.html\"")
    a.add_argument("--exclude", nargs="*", default=[],
                   help="slide filenames to drop from the shared copy (e.g. an internal appendix)")
    args = ap.parse_args()
    return build_local() if args.target == "local" else build_artifact(args.out, args.exclude)


if __name__ == "__main__":
    raise SystemExit(main())
