"""
Westland Construction — Proposal Schedule Plan PDF Generator
v3: Correct logo, overview on cover, WBS KeepTogether, risk columns fixed,
    question responses section, procurement monthly wording, no status/delivery on cover.
"""

import os
import copy
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    Image, KeepTogether, HRFlowable, Preformatted
)
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate, Frame

# ── Westland Brand Colors ──
RICH_BLACK    = HexColor('#101820')
WESTLAND_TEAL = HexColor('#174A5B')
CONCRETE_GREY = HexColor('#A2A2A1')
WESTLAND_BLUE = HexColor('#5489A3')
GOTHAM_GREY   = HexColor('#7C878E')
MAGNETIC_GREY = HexColor('#98A4AE')
LIGHT_BG      = HexColor('#F4F5F6')
DARK_NAVY     = HexColor('#1B3A4B')
WHITE         = white

# ── Page Setup ──
PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT_MARGIN   = 1.0 * inch
RIGHT_MARGIN  = 1.0 * inch
TOP_MARGIN    = 1.25 * inch
BOTTOM_MARGIN = 0.85 * inch
AVAIL_WIDTH   = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN


def get_westland_styles():
    styles = {}
    styles['DocTitle'] = ParagraphStyle(
        'DocTitle', fontName='Helvetica-Bold', fontSize=26, leading=32,
        textColor=WESTLAND_TEAL, spaceAfter=4, alignment=TA_LEFT,
    )
    styles['ProjectName'] = ParagraphStyle(
        'ProjectName', fontName='Helvetica', fontSize=16, leading=20,
        textColor=WESTLAND_BLUE, spaceAfter=12, alignment=TA_LEFT,
    )
    styles['H1'] = ParagraphStyle(
        'H1', fontName='Helvetica-Bold', fontSize=16, leading=20,
        textColor=WESTLAND_TEAL, spaceBefore=20, spaceAfter=8, alignment=TA_LEFT,
    )
    styles['H2'] = ParagraphStyle(
        'H2', fontName='Helvetica-Bold', fontSize=11, leading=14,
        textColor=WESTLAND_TEAL, spaceBefore=12, spaceAfter=6, alignment=TA_LEFT,
    )
    styles['Body'] = ParagraphStyle(
        'Body', fontName='Helvetica', fontSize=10, leading=14,
        textColor=RICH_BLACK, spaceAfter=6, alignment=TA_LEFT,
    )
    styles['BodyBold'] = ParagraphStyle(
        'BodyBold', fontName='Helvetica-Bold', fontSize=10, leading=14,
        textColor=RICH_BLACK, spaceAfter=6, alignment=TA_LEFT,
    )
    styles['Bullet'] = ParagraphStyle(
        'Bullet', fontName='Helvetica', fontSize=10, leading=14,
        textColor=RICH_BLACK, spaceAfter=3, leftIndent=18, bulletIndent=6,
    )
    styles['TableHeader'] = ParagraphStyle(
        'TH', fontName='Helvetica-Bold', fontSize=9, leading=12,
        textColor=WHITE, alignment=TA_LEFT,
    )
    styles['TableCell'] = ParagraphStyle(
        'TC', fontName='Helvetica', fontSize=9, leading=12,
        textColor=RICH_BLACK, alignment=TA_LEFT,
    )
    styles['MetaLabel'] = ParagraphStyle(
        'MetaLabel', fontName='Helvetica-Bold', fontSize=10, leading=14,
        textColor=RICH_BLACK,
    )
    styles['MetaValue'] = ParagraphStyle(
        'MetaValue', fontName='Helvetica', fontSize=10, leading=14,
        textColor=RICH_BLACK,
    )
    return styles


# ── Doc Template ──
class WestlandDocTemplate(BaseDocTemplate):
    def __init__(self, filename, logo_path=None, **kwargs):
        self.logo_path = logo_path
        self.project_name = kwargs.pop('project_name', '')
        self.prepared_date = kwargs.pop('prepared_date', '')
        super().__init__(filename, **kwargs)

        frame = Frame(
            LEFT_MARGIN, BOTTOM_MARGIN, AVAIL_WIDTH,
            PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN, id='main'
        )
        self.addPageTemplates([
            PageTemplate(id='AllPages', frames=[frame],
                         onPage=self._draw_header_footer),
        ])

    def _draw_header_footer(self, canvas, doc):
        canvas.saveState()
        # Header line
        hdr_y = PAGE_HEIGHT - 0.55 * inch
        canvas.setStrokeColor(WESTLAND_TEAL)
        canvas.setLineWidth(1)
        canvas.line(LEFT_MARGIN, hdr_y, PAGE_WIDTH - RIGHT_MARGIN, hdr_y)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(GOTHAM_GREY)
        canvas.drawString(LEFT_MARGIN, hdr_y + 6, self.project_name)
        canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, hdr_y + 6, 'Proposal Schedule Plan')
        # Footer line
        ftr_y = 0.55 * inch
        canvas.setStrokeColor(WESTLAND_TEAL)
        canvas.setLineWidth(0.5)
        canvas.line(LEFT_MARGIN, ftr_y, PAGE_WIDTH - RIGHT_MARGIN, ftr_y)
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(CONCRETE_GREY)
        canvas.drawString(LEFT_MARGIN, ftr_y - 12, 'Westland Construction')
        canvas.drawCentredString(PAGE_WIDTH / 2, ftr_y - 12, f'Page {doc.page}')
        canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, ftr_y - 12, self.prepared_date)
        canvas.restoreState()


# ── Table Helper ──
def make_branded_table(headers, rows, col_widths=None, styles_dict=None):
    if styles_dict is None:
        styles_dict = get_westland_styles()
    header_row = [Paragraph(h, styles_dict['TableHeader']) for h in headers]
    data_rows = [[Paragraph(str(c), styles_dict['TableCell']) for c in row] for row in rows]
    all_data = [header_row] + data_rows
    if col_widths is None:
        col_widths = [AVAIL_WIDTH / len(headers)] * len(headers)
    t = Table(all_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK_NAVY),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ('GRID', (0, 0), (-1, -1), 0.5, CONCRETE_GREY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


def section_divider():
    return HRFlowable(width='100%', thickness=1, color=WESTLAND_TEAL,
                      spaceBefore=6, spaceAfter=10)


# ══════════════════════════════════════════════════════════════
# SECTION BUILDERS
# ══════════════════════════════════════════════════════════════

def build_cover_page(data, styles, logo_path=None):
    """Cover page: logo, title, meta, then Project Overview — all on page 1."""
    elements = []

    # Logo
    if logo_path and os.path.exists(logo_path):
        from reportlab.lib.utils import ImageReader
        img_reader = ImageReader(logo_path)
        iw, ih = img_reader.getSize()
        aspect = iw / ih
        logo_w = 2.4 * inch
        logo_h = logo_w / aspect
        logo = Image(logo_path, width=logo_w, height=logo_h)
        logo.hAlign = 'LEFT'
        elements.append(logo)
        elements.append(Spacer(1, 24))

    # Title block
    elements.append(Paragraph('Proposal Schedule Plan', styles['DocTitle']))
    elements.append(Paragraph(data['project_name'], styles['ProjectName']))
    elements.append(section_divider())

    # Meta grid — just Prepared / Prepared By (no Status or Delivery)
    meta_data = [
        [Paragraph('<b>Prepared:</b>', styles['MetaLabel']),
         Paragraph(data.get('prepared_date', ''), styles['MetaValue']),
         Paragraph('<b>Prepared By:</b>', styles['MetaLabel']),
         Paragraph(data.get('prepared_by', ''), styles['MetaValue'])],
    ]
    meta_table = Table(meta_data, colWidths=[0.95*inch, 2.0*inch, 1.05*inch, AVAIL_WIDTH - 4.0*inch])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 16))

    # Project Overview directly on cover
    elements.append(Paragraph('1. Project Overview', styles['H1']))
    fields = [
        ('Project Name', data.get('project_name', '')),
        ('Project Type', data.get('project_type', '')),
        ('Location', data.get('location', '')),
        ('Contract Duration', data.get('contract_duration', '')),
        ('Anticipated NTP', data.get('ntp_date', '')),
        ('Substantial Completion', data.get('sc_date', '')),
        ('Final Completion', data.get('fc_date', '')),
        ('Liquidated Damages', data.get('ld_info', '')),
    ]
    for label, value in fields:
        if value:
            elements.append(Paragraph(f"<b>{label}:</b> {value}", styles['Body']))
    elements.append(section_divider())

    return elements


def build_schedule_basis(data, styles):
    elements = []
    elements.append(Paragraph('2. Schedule Basis', styles['H1']))

    if data.get('reference_schedules'):
        elements.append(Paragraph('2.1 Reference Schedules Analyzed', styles['H2']))
        headers = ['#', 'Project Name', 'File', 'Activities', 'Ratio', 'Key Takeaway']
        rows = []
        for i, ref in enumerate(data['reference_schedules'], 1):
            rows.append([str(i), ref.get('name', ''), ref.get('file', ''),
                         str(ref.get('activities', '')), ref.get('ratio', ''),
                         ref.get('takeaway', '')])
        elements.append(make_branded_table(
            headers, rows,
            col_widths=[0.3*inch, 1.3*inch, 0.9*inch, 0.6*inch, 0.5*inch, AVAIL_WIDTH - 3.6*inch]
        ))
        elements.append(Spacer(1, 8))

    # Bid documents analyzed
    if data.get('bid_documents'):
        elements.append(Paragraph('2.2 Bid Documents Analyzed', styles['H2']))
        for doc_item in data['bid_documents']:
            elements.append(Paragraph(f"&bull; {doc_item}", styles['Bullet']))
        elements.append(Spacer(1, 6))

    # Question responses / interview inputs
    if data.get('question_responses'):
        elements.append(Paragraph('2.3 Planning Interview Responses', styles['H2']))
        elements.append(Paragraph(
            'The following responses were provided during the schedule planning process and '
            'informed the assumptions, sequencing, and duration estimates in this plan.',
            styles['Body']
        ))
        for i, qr in enumerate(data['question_responses'], 1):
            q = qr.get('question', '')
            a = qr.get('response', '')
            elements.append(Paragraph(f"<b>{i}. {q}</b>", styles['Body']))
            elements.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;{a}", styles['Body']))
        elements.append(Spacer(1, 6))

    if data.get('assumptions'):
        section_num = '2.4' if data.get('question_responses') else '2.3' if data.get('bid_documents') else '2.2'
        elements.append(Paragraph(f'{section_num} Schedule Assumptions', styles['H2']))
        for i, assumption in enumerate(data['assumptions'], 1):
            elements.append(Paragraph(f"{i}. {assumption}", styles['Bullet']))

    elements.append(section_divider())
    return elements


def build_wbs_section(data, styles):
    """WBS in monospace grey box — wrapped in KeepTogether so it doesn't split."""
    elements = []
    heading = Paragraph('3. Work Breakdown Structure', styles['H1'])

    wbs_parts = []
    if data.get('wbs_tree_text'):
        mono_style = ParagraphStyle(
            'WBSMono', fontName='Courier', fontSize=9, leading=13,
            textColor=RICH_BLACK, leftIndent=10, rightIndent=10,
        )
        lines = data['wbs_tree_text'].strip().split('\n')
        content_parts = []
        for line in lines:
            display_line = line.replace(' ', '&nbsp;')
            content_parts.append(Paragraph(display_line, mono_style))

        box_data = [[content_parts]]
        box = Table(box_data, colWidths=[AVAIL_WIDTH])
        box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
            ('BOX', (0, 0), (-1, -1), 0.5, CONCRETE_GREY),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        wbs_parts.append(box)

    rationale_parts = []
    if data.get('wbs_rationale'):
        rationale_parts.append(Spacer(1, 8))
        rationale_parts.append(Paragraph(data['wbs_rationale'], styles['Body']))

    divider = section_divider()

    # Try to keep heading + WBS box together; rationale can flow
    elements.append(KeepTogether([heading] + wbs_parts))
    elements.extend(rationale_parts)
    elements.append(divider)
    return elements


def build_phase_timeline(data, styles):
    elements = []
    elements.append(Paragraph('4. Phase Timeline Summary', styles['H1']))
    elements.append(Paragraph(
        'Estimated durations by construction phase. All durations are in working days '
        'and represent the expected elapsed time for each phase based on reference '
        'schedule analysis and scope review.',
        styles['Body']
    ))
    if data.get('phase_timeline'):
        headers = ['Phase', 'Est. Duration', 'Activities', 'Key Driver']
        rows = [[p.get('phase', ''), p.get('duration', ''),
                 str(p.get('activities', '')), p.get('key_driver', '')] for p in data['phase_timeline']]
        elements.append(make_branded_table(
            headers, rows,
            col_widths=[1.7*inch, 0.95*inch, 0.8*inch, AVAIL_WIDTH - 3.45*inch]
        ))
    elements.append(section_divider())
    return elements


def build_logic_section(data, styles):
    elements = []
    elements.append(Paragraph('5. Logic Network Description', styles['H1']))
    if data.get('phase_sequencing'):
        elements.append(Paragraph('5.1 Phase-to-Phase Sequencing', styles['H2']))
        for seq in data['phase_sequencing']:
            elements.append(Paragraph(f"&bull; {seq}", styles['Bullet']))
        elements.append(Spacer(1, 6))
    if data.get('logic_chains'):
        elements.append(Paragraph('5.2 Within-Phase Logic Chains', styles['H2']))
        for phase, chain in data['logic_chains'].items():
            elements.append(Paragraph(f"<b>{phase}:</b> {chain}", styles['Body']))
        elements.append(Spacer(1, 6))
    if data.get('cross_phase_ties'):
        elements.append(Paragraph('5.3 Cross-Phase Ties', styles['H2']))
        for tie in data['cross_phase_ties']:
            elements.append(Paragraph(f"&bull; {tie}", styles['Bullet']))
    if data.get('relationship_standards'):
        elements.append(Paragraph('5.4 Relationship Standards', styles['H2']))
        for std in data['relationship_standards']:
            elements.append(Paragraph(f"&bull; {std}", styles['Bullet']))
    elements.append(section_divider())
    return elements


def build_construction_sequence(data, styles):
    elements = []
    elements.append(Paragraph('6. Construction Sequence', styles['H1']))
    if data.get('overall_approach'):
        elements.append(Paragraph('6.1 Overall Approach', styles['H2']))
        elements.append(Paragraph(data['overall_approach'], styles['Body']))
    if data.get('phase_narratives'):
        elements.append(Paragraph('6.2 Phase-by-Phase Narrative', styles['H2']))
        for phase, narrative in data['phase_narratives'].items():
            elements.append(Paragraph(f"<b>{phase}</b> — {narrative}", styles['Body']))
    elements.append(section_divider())
    return elements


def build_milestone_table(data, styles):
    elements = []
    elements.append(Paragraph('7. Milestone Schedule', styles['H1']))
    if data.get('milestones'):
        headers = ['Milestone', 'Target Date', 'Type', 'Constraint', 'Source']
        rows = [[m.get('name', ''), m.get('date', ''), m.get('type', ''),
                 m.get('constraint', ''), m.get('source', '')] for m in data['milestones']]
        elements.append(make_branded_table(
            headers, rows,
            col_widths=[1.8*inch, 1.0*inch, 0.8*inch, 0.85*inch, AVAIL_WIDTH - 4.45*inch]
        ))
    elements.append(section_divider())
    return elements


def build_procurement_section(data, styles):
    elements = []
    elements.append(Paragraph('8. Procurement &amp; Long-Lead Items', styles['H1']))
    if data.get('procurement_items'):
        headers = ['Item', 'Lead Time', 'Submittal By', 'Need On Site', 'Notes']
        rows = [[p.get('item', ''), p.get('lead_time', ''), p.get('submittal_by', ''),
                 p.get('need_on_site', ''), p.get('notes', '')] for p in data['procurement_items']]
        elements.append(make_branded_table(
            headers, rows,
            col_widths=[1.6*inch, 0.8*inch, 0.9*inch, 0.9*inch, AVAIL_WIDTH - 4.2*inch]
        ))
        elements.append(Spacer(1, 10))

    elements.append(Paragraph('8.1 Procurement Assumptions &amp; Qualifications', styles['H2']))
    elements.append(Paragraph(
        'The procurement lead times shown above represent professional estimates based on '
        'current market conditions and manufacturer-published timelines at the time of bid '
        'preparation. These durations are Westland Construction\'s best assessment and are '
        'subject to change based on actual submittal review periods, manufacturer backlog, '
        'supply chain conditions, and owner approval timelines.',
        styles['Body']
    ))
    elements.append(Paragraph(
        '<b>If actual lead times exceed the estimates shown in this schedule, the resulting '
        'delay constitutes a justified basis for a Time Impact Analysis (TIA) and may support '
        'a formal change order for schedule relief.</b> For example, if an air handling unit is '
        'estimated at 16 weeks and the manufacturer confirms 40 weeks at time of order, the '
        'difference represents an excusable delay beyond Westland\'s control.',
        styles['Body']
    ))
    elements.append(Paragraph(
        'Westland Construction will track procurement status through the submittal and '
        'fabrication process and will notify the Owner promptly if any lead time exceeds the '
        'baseline assumption. Procurement status will be reported monthly, and any item '
        'exceeding the baseline lead time will be formally documented in the monthly schedule '
        'update for the Owner\'s record.',
        styles['Body']
    ))

    if data.get('procurement_qualifications'):
        elements.append(Spacer(1, 4))
        for i, qual in enumerate(data['procurement_qualifications'], 1):
            elements.append(Paragraph(f"{i}. {qual}", styles['Bullet']))

    elements.append(section_divider())
    return elements


def build_risk_register(data, styles):
    elements = []
    elements.append(Paragraph('9. Risk Register', styles['H1']))
    if data.get('risks'):
        headers = ['#', 'Risk Item', 'Impact', 'Likelihood', 'Mitigation Strategy', 'Schedule Impact']
        rows = []
        for i, r in enumerate(data['risks'], 1):
            rows.append([str(i), r.get('risk', ''), r.get('impact', ''),
                         r.get('likelihood', ''), r.get('mitigation', ''),
                         r.get('schedule_impact', '')])
        # Fixed column widths — wider for text-heavy columns
        elements.append(make_branded_table(
            headers, rows,
            col_widths=[0.3*inch, 1.2*inch, 0.65*inch, 0.9*inch, 1.85*inch, AVAIL_WIDTH - 4.9*inch]
        ))
    elements.append(section_divider())
    return elements


def build_calendar_section(data, styles):
    elements = []
    elements.append(Paragraph('10. Calendar &amp; Work Hours', styles['H1']))
    fields = [
        ('Standard Calendar', data.get('calendar_type', '')),
        ('Work Hours', data.get('work_hours', '')),
        ('Weather Allowances', data.get('weather', '')),
        ('Holidays', data.get('holidays', '')),
        ('Overtime Provisions', data.get('overtime', '')),
    ]
    for label, value in fields:
        if value:
            elements.append(Paragraph(f"<b>{label}:</b> {value}", styles['Body']))
    elements.append(section_divider())
    return elements


def build_bid_assumptions(data, styles):
    elements = []
    elements.append(Paragraph('Bid-Time Assumptions &amp; Qualifications', styles['H1']))
    elements.append(Paragraph(
        'The following assumptions were made during bid preparation and form the basis for '
        'durations, sequencing, and resource loading in this proposal schedule. Any changes '
        'to these assumptions after contract award may require schedule revision.',
        styles['Body']
    ))
    elements.append(Spacer(1, 6))
    if data.get('bid_assumptions'):
        for i, assumption in enumerate(data['bid_assumptions'], 1):
            cat = assumption.get('category', '')
            text = assumption.get('text', '')
            header_text = f"<b>{i}. {cat}:</b> {text}" if cat else f"<b>{i}.</b> {text}"
            elements.append(Paragraph(header_text, styles['Body']))
            elements.append(Spacer(1, 2))
    elements.append(section_divider())
    return elements


def build_decision_log(data, styles):
    elements = []
    elements.append(Paragraph('Decision Log', styles['H1']))
    if data.get('decisions'):
        headers = ['#', 'Decision', 'Rationale', 'Date']
        rows = []
        for i, d in enumerate(data['decisions'], 1):
            rows.append([str(i), d.get('decision', ''), d.get('rationale', ''),
                         d.get('date', '')])
        elements.append(make_branded_table(
            headers, rows,
            col_widths=[0.3*inch, 2.0*inch, AVAIL_WIDTH - 3.2*inch, 0.9*inch]
        ))
    elements.append(section_divider())
    return elements


# ── Main Generator ──
def generate_proposal_schedule_pdf(data, output_path, logo_path=None):
    styles = get_westland_styles()
    doc = WestlandDocTemplate(
        output_path, logo_path=logo_path,
        project_name=data.get('project_name', ''),
        prepared_date=data.get('prepared_date', ''),
        pagesize=letter,
        leftMargin=LEFT_MARGIN, rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
    )

    story = []
    story.extend(build_cover_page(data, styles, logo_path))
    story.extend(build_schedule_basis(data, styles))
    if data.get('bid_assumptions'):
        story.extend(build_bid_assumptions(data, styles))
    story.extend(build_wbs_section(data, styles))
    story.extend(build_phase_timeline(data, styles))
    story.extend(build_logic_section(data, styles))
    story.extend(build_construction_sequence(data, styles))
    story.extend(build_milestone_table(data, styles))
    story.extend(build_procurement_section(data, styles))
    story.extend(build_risk_register(data, styles))
    story.extend(build_calendar_section(data, styles))
    if data.get('decisions'):
        story.extend(build_decision_log(data, styles))

    doc.build(story)
    return output_path


# ══════════════════════════════════════════════════════════════
# CLI: python generate_proposal_schedule_pdf.py <data.json> [output.pdf] [logo.png]
# ══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print('Usage: python generate_proposal_schedule_pdf.py <data.json> [output.pdf] [logo.png]')
        sys.exit(1)

    json_path = sys.argv[1]
    with open(json_path, 'r') as f:
        data = json.load(f)

    output = sys.argv[2] if len(sys.argv) > 2 else json_path.replace('.json', '.pdf')
    logo = sys.argv[3] if len(sys.argv) > 3 else data.get('logo_path', None)

    generate_proposal_schedule_pdf(data, output, logo_path=logo)
    print(f'Generated: {output}')


# Below is only kept as a reference for the expected data structure — not executed.
SAMPLE_DATA_REFERENCE = {
    'project_name': 'Orem Community Recreation Center',
    'project_type': 'New Construction — Municipal Recreation Facility',
    'location': 'Orem, Utah',
    'contract_duration': '18 months',
    'ntp_date': 'April 14, 2026',
    'sc_date': 'October 14, 2027',
    'fc_date': 'December 14, 2027',
    'ld_info': '$2,500/calendar day after Substantial Completion',
    'delivery_method': 'CM/GC',
    'prepared_by': 'Camron Walker / Westland Construction',
    'prepared_date': 'March 26, 2026',
    'status': 'Draft',

    'reference_schedules': [
        {'name': 'Provo Rock Canyon Pavilion', 'file': 'PRC.xer', 'activities': 87,
         'ratio': '1.72:1', 'takeaway': 'Site work sequencing & MEP coordination'},
        {'name': 'Springville Community Center', 'file': 'SCC.xer', 'activities': 112,
         'ratio': '1.65:1', 'takeaway': 'Aquatics facility phasing & envelope sequence'},
        {'name': 'AF Fitness Center Renovation', 'file': 'AFFC.xer', 'activities': 64,
         'ratio': '1.58:1', 'takeaway': 'Interior finish sequencing in occupied facility'},
    ],

    'bid_documents': [
        'Project Manual (Divisions 00-33) — contract requirements, schedule spec (Section 01 32 16)',
        'Architectural Plans (A1.0 through A9.3) — building layout, area takeoffs',
        'Structural Plans (S1.0 through S5.2) — steel & concrete scope',
        'MEP Plans (M1.0-M4.2, E1.0-E6.1, P1.0-P3.4) — mechanical, electrical, plumbing scope',
        'Civil Plans (C1.0 through C4.1) — site grading, utilities, parking',
    ],

    # Question responses from the planning interview
    'question_responses': [
        {'question': 'What is the anticipated work week?',
         'response': '5-day standard. 6-day available for recovery but not in the baseline.'},
        {'question': 'Are there any phasing or occupied building constraints?',
         'response': 'No — single-phase new construction, full site access from NTP.'},
        {'question': 'Any known long-lead equipment the owner is furnishing?',
         'response': 'Yes — aquatics mechanical equipment (pumps, filters, heaters, chemical systems). Owner expects delivery by Month 10.'},
        {'question': 'What is the expected structural system?',
         'response': 'Structural steel frame with composite metal deck at Level 2. Spread footings with CMU/CIP foundation walls.'},
        {'question': 'Any geotechnical concerns from the report?',
         'response': 'Standard soil conditions per January 2026 geotech report. No rock, no dewatering required.'},
        {'question': 'Will the building permit be in hand at NTP?',
         'response': 'No — expect 4 weeks from NTP to permit issuance. Schedule needs to account for this.'},
        {'question': 'How do you want interior finishes organized?',
         'response': 'By functional area — Lobby/Admin, Gymnasium, Aquatics, and Level 2 Fitness. Aquatics has specialized waterproofing and tile that takes significantly longer.'},
        {'question': 'What calendar and holidays should we use?',
         'response': 'Standard Westland 5-day calendar with 7 observed holidays. Work hours 7:00 AM to 3:30 PM.'},
    ],

    'assumptions': [
        'NTP assumed April 14, 2026 per owner verbal communication.',
        '5-day work week standard; 6-day weeks available for critical path recovery.',
        'Steel fabrication lead time of 12 weeks from approval of shop drawings.',
        'Owner-furnished aquatics equipment delivered by Month 10.',
        'Geotechnical report indicates standard soil conditions — no rock excavation.',
        'Building permit expected within 4 weeks of application.',
        'One concrete subcontractor for foundations and slab-on-grade.',
        'No winter concrete protection required for April start (foundations complete by Sept).',
    ],

    'wbs_tree_text': """\
OREM COMMUNITY RECREATION CENTER (OCRC)
    SUMMARY & MILESTONES
    PROCUREMENT
        SUBMITTALS - APPROVALS - FABRICATION - DELIVERY
            STRUCTURAL STEEL
            AQUATICS MECHANICAL EQUIPMENT
            ROOFTOP HVAC UNITS
            ELECTRICAL SWITCHGEAR
            ELEVATOR
            GYM FLOORING SYSTEM
            WINDOWS & STOREFRONT
    CONSTRUCTION
        SITEWORK
            INITIAL SITEWORK
            SITEWORK COMPLETION
        FOUNDATIONS
        STRUCTURAL STEEL & DECK
        BUILDING ENVELOPE
            ROOFING
            EXTERIOR WALLS & GLAZING
        MEP ROUGH-IN
            MECHANICAL
            ELECTRICAL
            PLUMBING
            FIRE PROTECTION
        INTERIOR FINISHES
            LEVEL 1 - LOBBY & ADMIN
            LEVEL 1 - GYMNASIUM
            LEVEL 1 - AQUATICS
            LEVEL 2 - FITNESS & MULTI-PURPOSE
        COMMISSIONING & CLOSEOUT""",

    'wbs_rationale': (
        'Phase-based at the top level, matching the Provo Rock Canyon and Springville reference '
        'patterns. Procurement broken out by major trade for submittal chain tracking. '
        'Interior finishes split by functional area because the aquatics area has 40% longer '
        'finish duration due to specialized waterproofing and tile work.'
    ),

    'phase_timeline': [
        {'phase': 'Preconstruction & Permitting', 'duration': '30 days', 'activities': 6,
         'key_driver': 'Building permit lead time (4 weeks)'},
        {'phase': 'Sitework', 'duration': '35 days', 'activities': 9,
         'key_driver': 'Underground utility installation (12 days)'},
        {'phase': 'Foundations', 'duration': '40 days', 'activities': 8,
         'key_driver': 'CMU/CIP wall pours & aquatics waterproofing'},
        {'phase': 'Structural Steel & Deck', 'duration': '30 days', 'activities': 5,
         'key_driver': 'Steel erection (15 days) + elevated slab'},
        {'phase': 'Building Envelope', 'duration': '45 days', 'activities': 7,
         'key_driver': 'Roofing + exterior wall framing (east to west)'},
        {'phase': 'MEP Rough-In', 'duration': '50 days', 'activities': 14,
         'key_driver': 'Aquatics mechanical room (long-lead equipment)'},
        {'phase': 'Interior Finishes', 'duration': '60 days', 'activities': 20,
         'key_driver': 'Aquatics waterproofing & tile (longest area)'},
        {'phase': 'Commissioning & Closeout', 'duration': '35 days', 'activities': 8,
         'key_driver': 'TAB, controls commissioning, owner training'},
        {'phase': 'Procurement (parallel)', 'duration': '120 days', 'activities': 19,
         'key_driver': 'Aquatics equipment (16 weeks) & steel (12 weeks)'},
    ],

    'phase_sequencing': [
        'Preconstruction \u2192 Site Work: FS (permit gates NTP)',
        'Site Work \u2192 Foundations: FS with 5-day lag (allow grading cure)',
        'Foundations \u2192 Structural Steel: FS (steel erect after foundation walls complete)',
        'Structural Steel \u2192 Building Envelope: SS with 10-day lag (envelope follows steel by area)',
        'Building Envelope \u2192 MEP Rough-In: SS with 5-day lag (MEP starts in dried-in areas)',
        'MEP Rough-In \u2192 Interior Finishes: FS by area (drywall after rough-in inspection)',
        'Interior Finishes \u2192 Commissioning & Closeout: FS',
    ],
    'logic_chains': {
        'Site Work': 'Mobilize \u2192 Erosion Control \u2192 Clear & Grub \u2192 Excavate \u2192 Utilities \u2192 Backfill \u2192 Grade',
        'Foundations': 'Excavate Footings \u2192 Form \u2192 Rebar \u2192 Pour \u2192 Strip \u2192 Walls \u2192 Waterproof \u2192 Backfill',
        'MEP': 'Underground \u2192 Rough-In (by discipline, SS ties) \u2192 Overhead \u2192 Trim \u2192 Test & Balance',
        'Finishes': 'Frame \u2192 Rough MEP \u2192 Inspect \u2192 Insulate \u2192 Drywall \u2192 Tape & Finish \u2192 Paint \u2192 Flooring \u2192 Trim',
    },
    'cross_phase_ties': [
        'Steel delivery milestone tied to shop drawing approval (Preconstruction \u2192 Structure)',
        'Aquatics plumbing rough-in tied to pool shell pour (Foundations \u2192 MEP)',
        'Roofing completion gates interior finish start (Envelope \u2192 Finishes)',
    ],
    'relationship_standards': [
        'Default relationship type: FS',
        'SS used for: MEP rough-in by discipline (parallel trades), envelope/structure overlap',
        'FF used for: punchlist/closeout activities only',
        'Target relationship ratio: 1.8:1',
        'Lag usage: minimized; only where physical cure time or delivery wait is required',
    ],

    'overall_approach': (
        'Linear construction sequence starting from the east side of the building and progressing '
        'west. The aquatics wing (west) has the longest interior finish duration due to specialized '
        'waterproofing, tile, and mechanical work, so it begins MEP rough-in first. The gymnasium '
        'and lobby areas follow. Level 2 fitness areas are on the critical path due to the elevated '
        'slab pour dependency.'
    ),
    'phase_narratives': {
        'Mobilization & Site Work': (
            'Mobilize in Week 1, establish SWPPP controls, begin mass excavation. Underground '
            'utilities run concurrent with building pad preparation. 3 weeks of site work '
            'before foundation excavation begins.'
        ),
        'Foundation & Structure': (
            'Spread footings and CMU/CIP foundation walls. Steel erection begins immediately '
            'after foundation walls are complete. Metal deck and elevated slab follow steel by area.'
        ),
        'Building Envelope': (
            'Roof deck and roofing begin as soon as steel is topped out. Exterior wall framing '
            'and sheathing follow from east to west. Window installation follows wall completion by area.'
        ),
        'MEP Rough-In': (
            'Aquatics mechanical room starts first (long-lead equipment). Rough-in by discipline '
            'with SS ties. Fire protection follows ductwork by 5 days. Electrical follows mechanical '
            'by area. Above-ceiling inspection gates drywall.'
        ),
        'Interior Finishes': (
            'Area-by-area: Lobby/Admin first, then Gymnasium, then Aquatics (longest duration), '
            'then Level 2 Fitness. Each area follows the standard finish chain: frame, rough, '
            'insulate, drywall, tape & finish, paint, flooring, trim.'
        ),
        'Commissioning & Closeout': (
            'TAB and controls commissioning begin 6 weeks before Substantial Completion. Punchlist '
            'and final inspections run parallel. Owner training scheduled 2 weeks before turnover.'
        ),
    },

    'milestones': [
        {'name': 'Notice to Proceed', 'date': 'April 14, 2026', 'type': 'Start Milestone',
         'constraint': 'SNET', 'source': 'Contract'},
        {'name': 'Building Permit Received', 'date': 'May 12, 2026', 'type': 'Finish Milestone',
         'constraint': 'None', 'source': 'Assumption'},
        {'name': 'Steel Erection Complete', 'date': 'October 2026', 'type': 'Finish Milestone',
         'constraint': 'None', 'source': 'Logic-driven'},
        {'name': 'Building Dried In', 'date': 'January 2027', 'type': 'Finish Milestone',
         'constraint': 'None', 'source': 'Logic-driven'},
        {'name': 'Substantial Completion', 'date': 'October 14, 2027', 'type': 'Finish Milestone',
         'constraint': 'FNET', 'source': 'Contract'},
        {'name': 'Final Completion', 'date': 'December 14, 2027', 'type': 'Finish Milestone',
         'constraint': 'FNET', 'source': 'Contract'},
    ],

    'procurement_items': [
        {'item': 'Structural Steel', 'lead_time': '12 weeks', 'submittal_by': 'Month 1',
         'need_on_site': 'Month 4', 'notes': 'Critical path — early submittal required'},
        {'item': 'Aquatics Mechanical Equipment', 'lead_time': '16 weeks', 'submittal_by': 'Month 1',
         'need_on_site': 'Month 8', 'notes': 'Pool pumps, filters, heaters — owner spec'},
        {'item': 'Rooftop HVAC Units', 'lead_time': '10 weeks', 'submittal_by': 'Month 2',
         'need_on_site': 'Month 6', 'notes': '3 units per mechanical plans'},
        {'item': 'Gym Flooring System', 'lead_time': '8 weeks', 'submittal_by': 'Month 6',
         'need_on_site': 'Month 12', 'notes': 'Maple hardwood — requires acclimation period'},
        {'item': 'Elevator', 'lead_time': '14 weeks', 'submittal_by': 'Month 2',
         'need_on_site': 'Month 10', 'notes': 'Hydraulic passenger elevator'},
    ],
    'procurement_qualifications': [
        'Lead times are based on manufacturer quotes and industry norms as of bid date. Actual lead times will be confirmed at time of order.',
        'Submittal review periods assume 14 calendar days for architect/engineer review per specification requirements.',
        'Any owner-directed substitution that increases lead time beyond the baseline estimate is an excusable delay.',
        'Westland will provide procurement status in the monthly schedule update and will formally document any item exceeding baseline lead time.',
    ],

    'risks': [
        {'risk': 'Steel fabrication delay', 'impact': 'High', 'likelihood': 'Medium',
         'mitigation': 'Early submittal, weekly fabricator check-ins',
         'schedule_impact': '2-4 weeks'},
        {'risk': 'Aquatics waterproofing rework', 'impact': 'High', 'likelihood': 'Low',
         'mitigation': 'Pre-qualified applicator, third-party inspection',
         'schedule_impact': '2-3 weeks'},
        {'risk': 'Winter weather delays', 'impact': 'Medium', 'likelihood': 'Medium',
         'mitigation': 'April NTP allows foundations before winter; envelope by Jan',
         'schedule_impact': '1-2 weeks'},
        {'risk': 'Owner-furnished equipment late', 'impact': 'Medium', 'likelihood': 'Medium',
         'mitigation': 'Monthly procurement tracking with owner',
         'schedule_impact': '1-3 weeks'},
        {'risk': 'Unforeseen subsurface conditions', 'impact': 'High', 'likelihood': 'Low',
         'mitigation': 'Geotech report reviewed — low risk per borings',
         'schedule_impact': '1-2 weeks'},
    ],

    'calendar_type': '5-Day Work Week (Monday-Friday)',
    'work_hours': '7:00 AM - 3:30 PM (8 hours with 30-min lunch)',
    'weather': 'No winter concrete protection required for April start schedule',
    'holidays': 'Per Westland standard calendar — 7 observed holidays',
    'overtime': '6-day weeks available for critical path recovery at PM discretion',

    'bid_assumptions': [
        {'category': 'Schedule Start', 'text': 'NTP of April 14, 2026 per owner verbal communication. If NTP is delayed, the Substantial Completion date shifts day-for-day.'},
        {'category': 'Work Week', 'text': 'Standard 5-day work week (40 hrs). Overtime/Saturday work available for critical path recovery but not included in baseline durations.'},
        {'category': 'Subcontractor Availability', 'text': 'All major subcontractors (steel, mechanical, electrical, plumbing) are available for the proposed schedule. No trade stacking beyond standard coordination.'},
        {'category': 'Permit Timeline', 'text': 'Building permit issued within 4 weeks of NTP. Any delay in permit issuance shifts the schedule by the same duration.'},
        {'category': 'Structural Steel', 'text': '12-week fabrication lead time from shop drawing approval. Steel erection crew of 4 ironworkers + crane for 3-week erection duration.'},
        {'category': 'Owner-Furnished Equipment', 'text': 'Aquatics mechanical equipment (pumps, filters, heaters, chemical systems) delivered to site by Month 10. Westland not responsible for procurement delays on owner-furnished items.'},
        {'category': 'Soil Conditions', 'text': 'Standard soil conditions per geotechnical report dated January 2026. No rock excavation, dewatering, or soil remediation included.'},
        {'category': 'Phasing', 'text': 'Single-phase construction with no occupied building constraints. Full site access from NTP through Final Completion.'},
        {'category': 'Weather', 'text': 'April start allows all foundation and structural work to be completed before winter. No winter concrete protection costs or schedule impacts are included in this baseline.'},
        {'category': 'Inspections', 'text': 'Building inspections scheduled within 48 hours of request per city standard. No schedule impact from inspection wait times unless city backlog exceeds 5 business days.'},
    ],

    'decisions': [
        {'decision': 'Use 5-day calendar as baseline', 'rationale': 'Contract does not require 6-day; keeps overtime as float recovery option', 'date': 'March 26, 2026'},
        {'decision': 'Split interior finishes by functional area', 'rationale': 'Aquatics has 40% longer finish duration; enables earlier turnover of non-aquatics spaces', 'date': 'March 26, 2026'},
        {'decision': 'Start aquatics MEP rough-in first', 'rationale': 'Longest interior duration on critical path; early start reduces overall schedule risk', 'date': 'March 26, 2026'},
    ],
}


# End of reference data structure
