---
name: pm-closeout-status-dashboard
description: >
  Build and update interactive HTML closeout status dashboards from Excel tracking spreadsheets.
  Use this skill whenever the user mentions closeout tracking, closeout dashboard, closeout status,
  subcontractor closeouts, warranty/O&M tracking, or wants to visualize project closeout progress.
  Also trigger when the user says "update the dashboard" or "rebuild the dashboard" in the context
  of project closeouts. Works with any project — not limited to a specific one.
  Accepts both manual closeout spreadsheets and Procore submittal log exports (auto-detected).
---

# PM Closeout Status Dashboard

Generates a self-contained interactive HTML dashboard from an Excel closeout tracking spreadsheet. The dashboard shows subcontractor progress across up to 5 closeout categories (Warranty, O&M, As-Built Drawings, Attic Stock, Training) with charts, filters, toggles, and detail tables.

Supports two input formats, auto-detected from headers:

1. **Manual closeout spreadsheet** — one row per spec/scope item, columns for each category status
2. **Procore submittal log export** — exported from Procore's Submittals tool, filtered to Closeout and As-Built types

## When to use

- User wants to create a new closeout dashboard from a spreadsheet
- User says "update the dashboard" (re-read the Excel and regenerate)
- User wants to add/remove categories or change how items are classified
- User uploads or references a closeout tracking Excel file
- User uploads or references a Procore submittal log export

## How it works

There is a Python script at `scripts/build_dashboard.py` that does everything:

1. Reads the Excel file
2. Auto-detects input format (manual or Procore) from row-1 headers
3. Detects column positions from headers
4. Normalizes subcontractor name variants into canonical names
5. Classifies each item (received, outstanding, or not applicable)
6. Summarizes notes per sub (single generated summary instead of dumping raw notes)
7. Generates a single self-contained HTML file with embedded data, Chart.js charts, and interactive controls

## Quick start

To build or update a dashboard, run the script:

```bash
python3 <skill-path>/scripts/build_dashboard.py \
  --input "path/to/Closeout Status.xlsx" \
  --output "path/to/Dashboard.html" \
  --title "Project Name — Closeout Dashboard"
```

That's it. The script handles everything including the "Last updated" date in the header.

## Input format: Manual spreadsheet

The script auto-detects columns by matching header names (case-insensitive, partial match). It looks for these headers in row 1:

| Header contains | Category |
|----------------|----------|
| `subcontractor` or `sub` | Subcontractor name (required, must be first) |
| `spec` | Spec number |
| `description` or `desc` | Spec description |
| `warranty` | Warranty status |
| `o&m` or `o and m` or `operation` | O&M status |
| `as-built` or `as built` or `asbuilt` | As-Built Drawings |
| `attic` | Attic Stock |
| `training` | Training |
| `note` | Notes |

Columns can be in any order. Missing categories are simply omitted from the dashboard. The only required columns are Subcontractor and at least one status category.

### Cell value classification (manual format)

| Cell value | Classification | Meaning |
|-----------|---------------|---------|
| Blank / empty | Not applicable | Excluded from totals entirely |
| `NA`, `N/A`, `See Below` | Not applicable | Excluded from totals |
| `X`, `Received`, `Complete` | Received | Item complete |
| Starts with `X,` (e.g. `X, SHOP DWGS`) | Received | Complete — text after comma is just a note about what was required |
| Anything else | Outstanding | `Required`, `O`, descriptive text, etc. — anything not blank or received is outstanding |

## Input format: Procore submittal log export

The script detects Procore format when row-1 headers include at least 3 of: `Type`, `Status`, `Responsible Contractor`, `Title`.

### Which rows are included

Only rows where the Procore **Type** column is one of these are included:

- **Closeout** — the primary closeout submittal type
- **As-Built** — as-built drawing submittals

All other types are skipped (Product Info & Shop Drawing, Shop Drawing, Sample, Document, Plans, Complete, Other, Financial Review, Pay Request, Payroll, Prints, Product Information, Product Manual, Specification, SSSF, Change Orders, etc.). These are regular construction submittals, not closeout deliverables.

### How categories are determined

Since Procore doesn't have separate columns for each closeout category, the script parses the **Title** field using keyword patterns to determine which of the 5 categories each row belongs to:

| Keywords in title | Category assigned |
|------------------|-------------------|
| `warranty`, `warranties` | Warranty |
| `o&m`, `o and m`, `maintenance`, `operation` | O&M |
| `as-built`, `as built` | As-Built Drawings |
| `attic stock`, `spare parts` | Attic Stock |
| `training`, `commissioning` | Training |

A single Procore row can belong to **multiple categories** if the title contains multiple keywords. For example, "Flooring Closeout - Warranties/O&M Manuals/Attic Stock" flags Warranty + O&M + Attic Stock. That row appears once in the detail table with all three category columns checked.

If a row's Type is "Closeout" but the title doesn't match any keyword pattern, it defaults to **O&M** (since most generic closeout submittals are O&M documents).

If the Type is "As-Built", the As-Built category is always included regardless of title keywords.

### Status mapping

| Procore Status | Dashboard classification |
|---------------|------------------------|
| Closed | Received |
| Open | Outstanding |
| Draft | Skipped entirely |

### Subcontractor names

Procore uses the **Responsible Contractor** column. Names are normalized the same way as manual format (suffix stripping + mapping dictionary). Since you'll never mix manual and Procore data for the same project, sub names come from whichever format is in use.

## Sub name normalization

The script strips common suffixes (Inc, Co., Company, LLC, Corp) and applies a manual mapping dictionary for known variants. When creating a dashboard for a new project, you may need to add project-specific mappings to the `--name-map` argument or let the script auto-detect duplicates.

## Note summarization

When a subcontractor has multiple notes across their line items, the dashboard shows a single consolidated summary instead of dumping every raw note. The script filters out non-contextual values (bare "O", "X", "Received", short "needed" phrases) and combines the remaining notes into a concise summary sentence. If there's only one real note, it shows as-is.

Note: Procore exports don't typically have a notes column, so note summarization primarily applies to manual format.

## Dashboard features

- **KPI cards**: Overall % complete, items received, outstanding, total tracked, subs complete
- **Category toggles**: Warranty and O&M on by default; As-Built, Attic Stock, Training off by default. All toggles dynamically update charts, cards, and tables.
- **Charts**: Stacked bar (progress by category), horizontal bar (outstanding by sub)
- **Sub cards**: Color-coded left border (red-yellow-green by % complete), progress bars per category, consolidated notes
- **Show Items toggle**: Reveals outstanding spec-level detail under each progress bar, color-coded by category
- **Search and filter**: Text search + dropdown filter by subcontractor
- **Detail table**: Full line-item view with per-category status, column visibility follows toggles
- **Brand colors**: Uses `--primary` and `--secondary` color args (defaults to Westland teal/blue)

## Customization arguments

```
--input         Path to Excel file (required)
--output        Path for output HTML (required)
--title         Dashboard title (default: "Closeout Dashboard")
--primary       Primary brand color hex (default: #174A5B)
--secondary     Secondary brand color hex (default: #5489A3)
--default-on    Comma-separated categories on by default (default: warranty,om)
--name-map      JSON file with sub name mappings (optional)
--training-expected  Comma-separated sub names expected to have training (optional)
--format        Input format: auto (default), manual, or procore
```

## Updating an existing dashboard

Just re-run the same command. The script re-reads the Excel file and overwrites the HTML. The "Last updated" date updates automatically. Column positions are re-detected each time, so if the user adds/moves columns in the spreadsheet, it just works.

## Sample files

- `assets/sample_closeout.xlsx` — Example spreadsheet with realistic data (manual format)
- `assets/sample_dashboard.html` — Dashboard generated from the sample data
