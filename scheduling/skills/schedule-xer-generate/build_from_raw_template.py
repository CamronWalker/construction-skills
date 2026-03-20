"""
Reference: Generate a P6-importable XER by surgically replacing data in a working template.

This script demonstrates the template-based approach described in the schedule-xer-generate SKILL.md.
It produces a 96-task elementary school schedule (Mountain View Elementary) that imports cleanly
into Primavera P6 and scores A- (91.4) on quality backcheck.

To adapt for a new project:
  1. Update `src` to point to any real P6 export (the template)
  2. Update `out_path` to your desired output location
  3. Replace the PROJECT DATA section with your project's WBS, activities, and relationships
  4. Keep everything else — the parsing, make_r_line(), reassembly, and write patterns are reusable

Key patterns to preserve:
  - Read template as bytes, decode cp1252
  - Preserve %T and %F lines byte-for-byte from template
  - Use make_r_line() so %R field count always matches %F
  - Clone PROJECT/SCHEDOPTIONS from template, override only needed fields
  - Skip ACTVTYPE/ACTVCODE/TASKACTV tables
  - Single %E at end of file
  - Write with CRLF line endings and cp1252 encoding
"""

# ── Read the working template as raw lines ───────────────────────────────
# Point this at any real P6 export — the smallest working file is best.
src = 'TEMPLATE_XER_PATH_HERE  # e.g., /path/to/Provo Airport SRE Building - 2026-02-26.xer'

with open(src, 'rb') as f:
    raw = f.read()
content = raw.decode('cp1252')
template_lines = content.split('\r\n')

# ── Parse template into sections, preserving raw %F lines ────────────────
sections = []  # list of {name, f_line, r_lines, e_line}
header_line = None
current = None

for line in template_lines:
    if not line.strip():
        continue
    parts = line.split('\t')
    marker = parts[0]
    if marker == 'ERMHDR':
        header_line = line
    elif marker == '%T':
        current = {'name': parts[1], 't_line': line, 'f_line': None, 'r_lines': [], 'e_line': None}
        sections.append(current)
    elif marker == '%F' and current:
        current['f_line'] = line
        current['fields'] = parts[1:]
    elif marker == '%R' and current:
        current['r_lines'].append(line)
    elif marker == '%E' and current:
        current['e_line'] = line
        current = None

print(f"Template sections: {[s['name'] for s in sections]}")

# ── Helper: build a %R line matching a template's %F field count ─────────
def make_r_line(fields, data_dict):
    """Build a %R line with exactly len(fields) values."""
    vals = []
    for f in fields:
        vals.append(str(data_dict.get(f, '')))
    return '%R\t' + '\t'.join(vals)

# ── Get field lists from template sections ───────────────────────────────
def get_section(name):
    for s in sections:
        if s['name'] == name:
            return s
    return None

proj_sec = get_section('PROJECT')
cal_sec = get_section('CALENDAR')
sched_sec = get_section('SCHEDOPTIONS')
wbs_sec = get_section('PROJWBS')
task_sec = get_section('TASK')
pred_sec = get_section('TASKPRED')

proj_fields = proj_sec['fields']
cal_fields = cal_sec['fields']
sched_fields = sched_sec['fields']
wbs_fields = wbs_sec['fields']
task_fields = task_sec['fields']
pred_fields = pred_sec['fields']

print(f"PROJECT: {len(proj_fields)} fields")
print(f"CALENDAR: {len(cal_fields)} fields")
print(f"TASK: {len(task_fields)} fields")
print(f"TASKPRED: {len(pred_fields)} fields")
print(f"PROJWBS: {len(wbs_fields)} fields")

# ── Parse the template's existing PROJECT record as our base ─────────────
tmpl_proj_parts = proj_sec['r_lines'][0].split('\t')[1:]
tmpl_proj = dict(zip(proj_fields, tmpl_proj_parts))

# ── Parse the template's existing SCHEDOPTIONS record as our base ────────
tmpl_sched_parts = sched_sec['r_lines'][0].split('\t')[1:]
tmpl_sched = dict(zip(sched_fields, tmpl_sched_parts))

# ═══════════════════════════════════════════════════════════════════════════
# NEW PROJECT DATA
# ═══════════════════════════════════════════════════════════════════════════
PROJECT_ID = '99501'
OBS_ID = get_section('OBS')['r_lines'][0].split('\t')[1]  # reuse template OBS ID
CLNDR_5DAY = '99601'
CLNDR_6DAY = '99602'
CLNDR_7DAY = '99603'
PREFIX = 'MVES'
START_DATE = '2026-07-06 08:00'
CREATE_DATE = '2026-03-20 08:00'

# ── PROJECT record (clone template, override key fields) ─────────────────
new_proj = tmpl_proj.copy()
new_proj.update({
    'proj_id': PROJECT_ID, 'proj_short_name': PREFIX, 'clndr_id': CLNDR_5DAY,
    'task_code_base': '1000', 'task_code_step': '10',
    'plan_start_date': START_DATE, 'plan_end_date': '', 'scd_end_date': '',
    'add_date': CREATE_DATE, 'last_tasksum_date': '', 'fcst_start_date': '',
    'task_code_prefix': PREFIX, 'add_by_name': 'cwalker',
    'last_recalc_date': '', 'last_schedule_date': '', 'next_data_date': '',
    'sum_base_proj_id': '', 'base_type_id': '', 'orig_proj_id': '',
    'source_proj_id': '', 'acct_id': '',
})
proj_sec['r_lines'] = [make_r_line(proj_fields, new_proj)]

# ── CALENDAR records ─────────────────────────────────────────────────────
# Clone the template's first calendar record as base
tmpl_cal_parts = cal_sec['r_lines'][0].split('\t')[1:]
tmpl_cal = dict(zip(cal_fields, tmpl_cal_parts))

cal5_data = '(0||CalendarData()((0||DaysOfWeek()((0||1()())(0||2()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||3()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||4()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||5()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||6()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||7()()))(0||Exceptions()(0||0(d|46023)()))))'
cal6_data = '(0||CalendarData()((0||DaysOfWeek()((0||1()())(0||2()((0||0(s|07:00|f|12:00)())(0||1(s|12:30|f|17:30)())))(0||3()((0||0(s|07:00|f|12:00)())(0||1(s|12:30|f|17:30)())))(0||4()((0||0(s|07:00|f|12:00)())(0||1(s|12:30|f|17:30)())))(0||5()((0||0(s|07:00|f|12:00)())(0||1(s|12:30|f|17:30)())))(0||6()((0||0(s|07:00|f|12:00)())(0||1(s|12:30|f|17:30)())))(0||7()((0||0(s|07:00|f|12:00)())(0||1(s|12:30|f|17:30)())))))(0||Exceptions())))'
cal7_data = '(0||CalendarData()((0||DaysOfWeek()((0||1()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||2()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||3()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||4()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||5()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||6()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))(0||7()((0||0(s|08:00|f|12:00)())(0||1(s|13:00|f|17:00)())))))(0||Exceptions())))'

def make_cal(cid, name, data, default='N', dhr='8', whr='40', mhr='172', yhr='2000'):
    c = tmpl_cal.copy()
    c.update({
        'clndr_id': cid, 'default_flag': default, 'clndr_name': name,
        'proj_id': PROJECT_ID, 'base_clndr_id': '', 'last_chng_date': CREATE_DATE,
        'clndr_type': 'CA_Project', 'day_hr_cnt': dhr, 'week_hr_cnt': whr,
        'month_hr_cnt': mhr, 'year_hr_cnt': yhr, 'rsrc_private': 'N',
        'clndr_data': data,
    })
    return c

cal_sec['r_lines'] = [
    make_r_line(cal_fields, make_cal(CLNDR_5DAY, 'Standard 5-Day', cal5_data, 'Y')),
    make_r_line(cal_fields, make_cal(CLNDR_6DAY, '6-Day', cal6_data, dhr='10', whr='60', mhr='258', yhr='3000')),
    make_r_line(cal_fields, make_cal(CLNDR_7DAY, '7-Day', cal7_data, dhr='8', whr='56', mhr='240', yhr='2920')),
]

# ── SCHEDOPTIONS ─────────────────────────────────────────────────────────
new_sched = tmpl_sched.copy()
new_sched['proj_id'] = PROJECT_ID
sched_sec['r_lines'] = [make_r_line(sched_fields, new_sched)]

# ── WBS ──────────────────────────────────────────────────────────────────
wbs_counter = 30000
def next_wbs():
    global wbs_counter; v = wbs_counter; wbs_counter += 1; return str(v)

def add_wbs(short, name, parent, seq, is_root=False):
    wid = next_wbs()
    d = {f: '' for f in wbs_fields}
    d.update({
        'wbs_id': wid, 'proj_id': PROJECT_ID, 'obs_id': OBS_ID,
        'seq_num': str(seq), 'est_wt': '1',
        'proj_node_flag': 'Y' if is_root else 'N',
        'sum_data_flag': 'Y' if is_root else 'N',
        'status_code': 'WS_Open', 'wbs_short_name': short, 'wbs_name': name,
        'parent_wbs_id': parent,
        'ev_user_pct': '0', 'ev_etc_user_value': '0',
        'orig_cost': '0.0000', 'indep_remain_total_cost': '0.0000',
        'ann_dscnt_rate_pct': '0', 'indep_remain_work_qty': '0',
        'ev_compute_type': 'EC_Cmp_pct', 'ev_etc_compute_type': 'EE_PF_cpi',
    })
    wbs_sec['r_lines'].append(make_r_line(wbs_fields, d))
    return wid

wbs_sec['r_lines'] = []
root     = add_wbs(PREFIX, 'MOUNTAIN VIEW ELEMENTARY SCHOOL', '', 1, True)
precon   = add_wbs('1', 'PRECONSTRUCTION', root, 2)
design   = add_wbs('2', 'DESIGN', root, 3)
procure  = add_wbs('3', 'PROCUREMENT', root, 4)
constr   = add_wbs('4', 'CONSTRUCTION', root, 5)
summary  = add_wbs('5', 'SUMMARY & MILESTONES', root, 6)
site_init  = add_wbs('1', 'SITEWORK', constr, 7)
site_i     = add_wbs('1', 'INITIAL SITEWORK', site_init, 8)
site_c     = add_wbs('2', 'SITEWORK COMPLETION', site_init, 9)
struct     = add_wbs('2', 'STRUCTURE & SUBROUGH', constr, 10)
exterior   = add_wbs('3', 'EXTERIOR CLOSURE', constr, 11)
int_rough  = add_wbs('4', 'INTERIOR ROUGH', constr, 12)
int_finish = add_wbs('5', 'INTERIOR FINISH', constr, 13)
mep_sys    = add_wbs('6', 'MEP SYSTEMS', constr, 14)
closeout   = add_wbs('7', 'COMMISSIONING & CLOSEOUT', constr, 15)
proc_conc  = add_wbs('1', 'CONCRETE', procure, 16)
proc_steel = add_wbs('2', 'STRUCTURAL STEEL', procure, 17)
proc_mep   = add_wbs('3', 'MEP EQUIPMENT', procure, 18)
proc_fin   = add_wbs('4', 'FINISH MATERIALS', procure, 19)

# ── TASKS ────────────────────────────────────────────────────────────────
task_counter = 40000; task_code_seq = 10
def next_task():
    global task_counter; v = task_counter; task_counter += 1; return str(v)

def add_task(wbs, name, dur, ttype='TT_Task', cstr_type='', cstr_date=''):
    global task_code_seq
    tid = next_task()
    code = f'{PREFIX}{task_code_seq:04d}'; task_code_seq += 10
    d = {f: '' for f in task_fields}
    d.update({
        'task_id': tid, 'proj_id': PROJECT_ID, 'wbs_id': wbs,
        'clndr_id': CLNDR_5DAY, 'phys_complete_pct': '0',
        'rev_fdbk_flag': 'N', 'est_wt': '0', 'lock_plan_flag': 'N',
        'auto_compute_act_flag': 'Y', 'complete_pct_type': 'CP_Drtn',
        'task_type': ttype, 'duration_type': 'DT_FixedDUR2',
        'status_code': 'TK_NotStart', 'task_code': code, 'task_name': name,
        'remain_drtn_hr_cnt': str(dur), 'target_drtn_hr_cnt': str(dur),
        'act_work_qty': '0', 'remain_work_qty': '0', 'target_work_qty': '0',
        'target_equip_qty': '0', 'act_equip_qty': '0', 'remain_equip_qty': '0',
        'cstr_date': cstr_date, 'cstr_type': cstr_type,
        'priority_type': 'PT_Top',
        'act_this_per_work_qty': '0', 'act_this_per_equip_qty': '0',
        'create_date': CREATE_DATE, 'update_date': CREATE_DATE,
        'create_user': 'cwalker', 'update_user': 'cwalker',
    })
    task_sec['r_lines'].append(make_r_line(task_fields, d))
    return tid

task_sec['r_lines'] = []

# Summary & Milestones
ntp=add_task(summary,'Notice to Proceed',0,'TT_Mile','CS_SNET',START_DATE)
sc=add_task(summary,'Substantial Completion',0,'TT_FinMile')
fc=add_task(summary,'Final Completion',0,'TT_FinMile')
# Preconstruction
p_kick=add_task(precon,'Owner Kick-Off Meeting',16)
p_survey=add_task(precon,'Site Investigation & Survey',40)
p_phase=add_task(precon,'Develop Project Phasing Plan',40)
p_subs=add_task(precon,'Establish Subcontractor Awards',120)
p_permit=add_task(precon,'Building Permit Application',80)
p_perm_rx=add_task(precon,'Building Permit Received',0,'TT_Mile')
# Design
d_dd=add_task(design,'Design Development Review',80)
d_cd50=add_task(design,'Construction Documents 50%',120)
d_cd100=add_task(design,'Construction Documents 100%',120)
d_ifc=add_task(design,'IFC Documents Issued',0,'TT_FinMile')
# Procurement
pr_conc_sub=add_task(proc_conc,'Submit Concrete Mix Designs',40)
pr_conc_app=add_task(proc_conc,'Approve Concrete Mix Designs',80)
pr_stl_sub=add_task(proc_steel,'Submit Structural Steel Shop Drawings',80)
pr_stl_app=add_task(proc_steel,'Approve Structural Steel Shop Drawings',120)
pr_stl_fab=add_task(proc_steel,'Fabricate Structural Steel',240)
pr_stl_del=add_task(proc_steel,'Deliver Structural Steel',40)
pr_mep_sub=add_task(proc_mep,'Submit HVAC Equipment',80)
pr_mep_app=add_task(proc_mep,'Approve HVAC Equipment',120)
pr_mep_fab=add_task(proc_mep,'Fabricate & Deliver HVAC Equipment',320)
pr_fin_sub=add_task(proc_fin,'Submit Finish Materials',80)
pr_fin_app=add_task(proc_fin,'Approve Finish Materials',120)
pr_fin_fab=add_task(proc_fin,'Fabricate & Deliver Finish Materials',240)
# Initial Sitework
s_mob=add_task(site_i,'Mobilization',40)
s_eros=add_task(site_i,'Erosion Control & SWPPP',24)
s_clear=add_task(site_i,'Clear & Grub Site',40)
s_rough=add_task(site_i,'Rough Grading',80)
s_storm=add_task(site_i,'Underground Utilities - Storm',120)
s_sani=add_task(site_i,'Underground Utilities - Sanitary',80)
s_water=add_task(site_i,'Underground Utilities - Water',80)
s_elec=add_task(site_i,'Underground Electrical Distribution',80)
# Structure
st_exc=add_task(struct,'Excavate Footings',40)
st_form=add_task(struct,'Form Footings',40)
st_rebar=add_task(struct,'Rebar Footings',24)
st_pour=add_task(struct,'Pour Footings',24)
st_strip=add_task(struct,'Strip Footing Forms',16)
st_fwall=add_task(struct,'Foundation Walls',120)
st_wtrp=add_task(struct,'Waterproof Foundation',40)
st_bkfl=add_task(struct,'Backfill Foundation',40)
st_slprp=add_task(struct,'Slab on Grade - Prep & Vapor Barrier',40)
st_slpor=add_task(struct,'Slab on Grade - Rebar & Pour',40)
st_steel=add_task(struct,'Erect Structural Steel',120)
st_deck=add_task(struct,'Install Metal Deck',80)
st_eslab=add_task(struct,'Pour Elevated Slab',40)
st_mason=add_task(struct,'Masonry Walls',160)
# Exterior
ex_frame=add_task(exterior,'Exterior Framing',120)
ex_sheath=add_task(exterior,'Sheathing & Weather Barrier',80)
ex_win=add_task(exterior,'Window Installation',80)
ex_doors=add_task(exterior,'Exterior Door Frames & Hardware',40)
ex_clad=add_task(exterior,'Exterior Cladding & Brick Veneer',200)
ex_roof_u=add_task(exterior,'Roofing - Underlayment & Membrane',80)
ex_roof_m=add_task(exterior,'Roofing - Sheet Metal & Flashing',80)
ex_roof_i=add_task(exterior,'Roofing - Final Inspection',16)
# Interior Rough
ir_frame=add_task(int_rough,'Interior Metal Stud Framing',200)
ir_plumb=add_task(int_rough,'Rough Plumbing',160)
ir_hvac=add_task(int_rough,'Rough HVAC Ductwork',160)
ir_elec=add_task(int_rough,'Rough Electrical',160)
ir_fire=add_task(int_rough,'Fire Sprinkler Rough-In',120)
ir_lowv=add_task(int_rough,'Low Voltage Rough-In',80)
ir_insul=add_task(int_rough,'Insulation',80)
ir_dw_h=add_task(int_rough,'Drywall Hang',160)
ir_dw_tf=add_task(int_rough,'Drywall Tape & Finish',160)
# Interior Finish
if_prime=add_task(int_finish,'Interior Paint - Prime',80)
if_paint=add_task(int_finish,'Interior Paint - Finish Coats',120)
if_tile=add_task(int_finish,'Ceramic Tile',120)
if_mill=add_task(int_finish,'Millwork & Casework',120)
if_count=add_task(int_finish,'Countertops',40)
if_floor=add_task(int_finish,'Carpet & Resilient Flooring',120)
if_idoor=add_task(int_finish,'Interior Door Slabs & Hardware',40)
if_acc=add_task(int_finish,'Toilet Accessories & Partitions',40)
if_ceil=add_task(int_finish,'Ceiling Grid & Tile',120)
if_gym=add_task(int_finish,'Gymnasium Flooring & Equipment',80)
if_play=add_task(int_finish,'Playground Equipment Installation',80)
# MEP Systems
ms_hvac=add_task(mep_sys,'HVAC Equipment Set',80)
ms_ctrl=add_task(mep_sys,'HVAC Controls & TAB',80)
ms_plfix=add_task(mep_sys,'Plumbing Fixtures & Trim',80)
ms_panel=add_task(mep_sys,'Electrical Panels & Switchgear',40)
ms_edev=add_task(mep_sys,'Electrical Trim - Devices & Covers',80)
ms_light=add_task(mep_sys,'Light Fixtures',80)
ms_falm=add_task(mep_sys,'Fire Alarm - Devices & Testing',40)
ms_ftest=add_task(mep_sys,'Fire Sprinkler Trim & Test',40)
# Sitework Completion
sc_fine=add_task(site_c,'Fine Grading',80)
sc_curb=add_task(site_c,'Curb Gutter & Sidewalks',120)
sc_base=add_task(site_c,'Asphalt Base Course',40)
sc_wear=add_task(site_c,'Asphalt Wearing Course',24)
sc_strip=add_task(site_c,'Striping & Signage',24)
sc_land=add_task(site_c,'Landscape & Irrigation',120)
sc_fence=add_task(site_c,'Site Fencing & Playground Fencing',40)
# Closeout
co_comm=add_task(closeout,'MEP Commissioning',80)
co_punch=add_task(closeout,'Punch List Walk',40)
co_pfix=add_task(closeout,'Punch List Completion',120)
co_clean=add_task(closeout,'Final Clean',40)
co_train=add_task(closeout,'Owner Training',24)
co_close=add_task(closeout,'Closeout Documents',80)

# ── RELATIONSHIPS ────────────────────────────────────────────────────────
pred_counter = 50000
def next_pred():
    global pred_counter; v = pred_counter; pred_counter += 1; return str(v)

def add_pred(succ, pred, ptype='PR_FS', lag=0):
    pid = next_pred()
    d = {f: '' for f in pred_fields}
    d.update({'task_pred_id': pid, 'task_id': succ, 'pred_task_id': pred,
              'proj_id': PROJECT_ID, 'pred_proj_id': PROJECT_ID,
              'pred_type': ptype, 'lag_hr_cnt': str(lag)})
    pred_sec['r_lines'].append(make_r_line(pred_fields, d))

pred_sec['r_lines'] = []
# All relationships (same as before)
add_pred(p_kick,ntp);add_pred(d_dd,ntp)
add_pred(p_survey,p_kick);add_pred(p_phase,p_kick)
add_pred(p_subs,p_survey);add_pred(p_subs,p_phase);add_pred(p_subs,d_dd)
add_pred(p_permit,d_cd100);add_pred(p_perm_rx,p_permit)
add_pred(d_cd50,d_dd);add_pred(d_cd100,d_cd50);add_pred(d_ifc,d_cd100)
add_pred(pr_conc_sub,d_cd50);add_pred(pr_conc_app,pr_conc_sub)
add_pred(pr_stl_sub,d_cd50);add_pred(pr_stl_app,pr_stl_sub)
add_pred(pr_stl_fab,pr_stl_app);add_pred(pr_stl_del,pr_stl_fab)
add_pred(pr_mep_sub,d_cd50);add_pred(pr_mep_app,pr_mep_sub);add_pred(pr_mep_fab,pr_mep_app)
add_pred(pr_fin_sub,d_cd100);add_pred(pr_fin_app,pr_fin_sub);add_pred(pr_fin_fab,pr_fin_app)
add_pred(s_mob,p_perm_rx);add_pred(s_mob,p_subs);add_pred(s_mob,d_ifc)
add_pred(s_eros,s_mob);add_pred(s_clear,s_eros);add_pred(s_rough,s_clear)
add_pred(s_storm,s_rough);add_pred(s_sani,s_storm,'PR_SS',40)
add_pred(s_water,s_sani,'PR_SS',40);add_pred(s_elec,s_water,'PR_SS',40)
add_pred(st_exc,s_rough);add_pred(st_form,st_exc);add_pred(st_rebar,st_form)
add_pred(st_pour,st_rebar);add_pred(st_pour,pr_conc_app)
add_pred(st_strip,st_pour);add_pred(st_fwall,st_strip)
add_pred(st_wtrp,st_fwall);add_pred(st_bkfl,st_wtrp)
add_pred(st_slprp,st_bkfl);add_pred(st_slprp,s_storm);add_pred(st_slprp,st_wtrp)
add_pred(st_slpor,st_slprp);add_pred(st_steel,st_slpor);add_pred(st_steel,pr_stl_del)
add_pred(st_deck,st_steel);add_pred(st_eslab,st_deck)
add_pred(st_mason,st_steel,'PR_SS',40)
add_pred(ex_frame,st_steel);add_pred(ex_frame,st_mason,'PR_SS',80)
add_pred(ex_sheath,ex_frame);add_pred(ex_win,ex_sheath);add_pred(ex_doors,ex_sheath)
add_pred(ex_clad,ex_sheath,'PR_SS',40);add_pred(ex_clad,ex_win,'PR_FF',0)
add_pred(ex_roof_u,st_deck);add_pred(ex_roof_m,ex_roof_u)
add_pred(ex_roof_i,ex_roof_m);add_pred(ex_frame,st_eslab)
add_pred(ir_frame,ex_sheath)
add_pred(ir_plumb,ir_frame,'PR_SS',40);add_pred(ir_hvac,ir_frame,'PR_SS',40)
add_pred(ir_elec,ir_frame,'PR_SS',40);add_pred(ir_fire,ir_plumb,'PR_FF',0)
add_pred(ir_lowv,ir_elec,'PR_SS',40)
add_pred(ir_insul,ir_plumb,'PR_FF',0);add_pred(ir_insul,ir_hvac,'PR_FF',0)
add_pred(ir_insul,ir_elec,'PR_FF',0);add_pred(ir_insul,ir_fire,'PR_FF',0)
add_pred(ir_insul,ir_lowv,'PR_FF',0)
add_pred(ir_dw_h,ir_insul);add_pred(ir_dw_tf,ir_dw_h)
add_pred(if_prime,ir_dw_tf);add_pred(if_paint,if_prime)
add_pred(if_tile,if_prime,'PR_SS',40);add_pred(if_mill,if_paint)
add_pred(if_mill,pr_fin_fab);add_pred(if_count,if_mill)
add_pred(if_floor,if_paint);add_pred(if_idoor,if_paint);add_pred(if_acc,if_tile)
add_pred(if_ceil,if_paint);add_pred(if_ceil,ir_dw_tf)
add_pred(if_gym,if_prime);add_pred(if_play,sc_fine)
add_pred(ms_hvac,pr_mep_fab);add_pred(ms_hvac,ex_roof_i);add_pred(ms_hvac,ir_hvac)
add_pred(ms_ctrl,ms_hvac);add_pred(ms_plfix,if_tile);add_pred(ms_plfix,ir_plumb)
add_pred(ms_plfix,if_acc,'PR_FF',0);add_pred(ms_panel,ir_elec)
add_pred(ms_edev,if_paint);add_pred(ms_edev,ms_panel)
add_pred(ms_light,if_ceil);add_pred(ms_light,ms_edev,'PR_SS',0)
add_pred(ms_falm,ms_light);add_pred(ms_ftest,ir_fire)
add_pred(ms_ftest,if_ceil,'PR_FF',0)
add_pred(sc_fine,s_elec,'PR_FF',0);add_pred(sc_fine,st_bkfl)
add_pred(sc_curb,sc_fine);add_pred(sc_base,sc_curb);add_pred(sc_base,sc_fine)
add_pred(sc_wear,sc_base);add_pred(sc_strip,sc_wear)
add_pred(sc_land,sc_fine,'PR_SS',40);add_pred(sc_fence,sc_curb)
add_pred(co_comm,ms_ctrl);add_pred(co_comm,ms_falm);add_pred(co_comm,ms_ftest)
add_pred(co_comm,ms_plfix);add_pred(co_comm,if_ceil)
add_pred(co_punch,co_comm);add_pred(co_punch,sc_strip);add_pred(co_punch,sc_land)
add_pred(co_punch,sc_fence);add_pred(co_punch,if_floor);add_pred(co_punch,if_idoor)
add_pred(co_punch,if_gym);add_pred(co_punch,if_play);add_pred(co_punch,if_count)
add_pred(co_punch,ms_light);add_pred(co_punch,ms_edev)
add_pred(co_punch,ex_clad);add_pred(co_punch,ex_doors)
add_pred(co_pfix,co_punch);add_pred(co_clean,co_pfix)
add_pred(co_train,co_clean);add_pred(co_close,co_clean,'PR_SS',0)
add_pred(sc,co_clean);add_pred(sc,sc_land);add_pred(sc,sc_strip);add_pred(sc,sc_fence)
add_pred(fc,sc);add_pred(fc,co_train);add_pred(fc,co_close)

# ═══════════════════════════════════════════════════════════════════════════
# REASSEMBLE AND WRITE
# ═══════════════════════════════════════════════════════════════════════════

# Update header
new_header = header_line.replace('2026-02-26', '2026-03-20').replace(
    'khartvigsen', 'cwalker').replace('Kelton Hartvigsen', 'Camron Walker')

# Tables to skip (reference old project data we can't populate)
skip_tables = {'ACTVTYPE', 'ACTVCODE', 'TASKACTV'}

output_lines = [new_header]
for sec in sections:
    if sec['name'] in skip_tables:
        continue
    output_lines.append(sec['t_line'])   # %T line — byte-for-byte from template
    output_lines.append(sec['f_line'])   # %F line — byte-for-byte from template
    output_lines.extend(sec['r_lines'])  # %R lines — new data
output_lines.append('%E')  # single %E at end of file

out_path = 'OUTPUT_XER_PATH_HERE  # e.g., /path/to/Mountain View Elementary School - 2026-03-20.xer'
with open(out_path, 'wb') as f:
    f.write('\r\n'.join(output_lines).encode('cp1252'))
    f.write(b'\r\n')

# ── Verify ───────────────────────────────────────────────────────────────
with open(out_path, 'rb') as f:
    check = f.read().decode('cp1252')
print(f"\nFile written: {len(check)} bytes")
# Check field/value alignment per table
current_f_count = None
current_table = None
for line in check.split('\r\n'):
    parts = line.split('\t')
    if parts[0] == '%T':
        current_table = parts[1]
        current_f_count = None
    elif parts[0] == '%F':
        current_f_count = len(parts) - 1
    elif parts[0] == '%R' and current_f_count is not None:
        rcount = len(parts) - 1
        if current_f_count != rcount:
            print(f"  MISMATCH in {current_table}: %F={current_f_count}, %R={rcount}")
crlf_count = check.count('\r\n')
print(f"CRLF line endings: {crlf_count}")

n = len(task_sec['r_lines'])
nr = len(pred_sec['r_lines'])
print(f"Tasks: {n}, Relationships: {nr}, Ratio: {nr/n:.2f}:1")
print("Done!")
