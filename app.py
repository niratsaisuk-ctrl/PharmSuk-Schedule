import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import holidays
from streamlit_calendar import calendar
from supabase import create_client, Client
from ortools.sat.python import cp_model
import re
import io

# ------------------------------------------------------------------
# 1. ตั้งค่าหน้าเว็บ & เชื่อมต่อฐานข้อมูล Supabase
# ------------------------------------------------------------------
st.set_page_config(page_title="PharmSuk App", layout="wide", page_icon="💊")
st.markdown("<style>.block-container { padding-top: 2rem; }</style>", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    raw_url = st.secrets["supabase"]["url"]
    raw_key = st.secrets["supabase"]["key"]
    return create_client(raw_url.strip().rstrip('/'), raw_key.strip())

try:
    supabase: Client = init_connection()
    db_status = "🟢 เชื่อมต่อฐานข้อมูลสำเร็จ"
except Exception as e:
    supabase = None
    db_status = f"🔴 เชื่อมต่อล้มเหลว: {e}"

# ------------------------------------------------------------------
# 2. ระบบจัดการข้อมูล Cloud (รวมตาราง)
# ------------------------------------------------------------------
def fetch_users():
    if supabase:
        res = supabase.table("users").select("*").execute()
        return {user['username']: user for user in res.data}
    return {}

def add_user_db(username, password, full_name, role):
    if supabase: supabase.table("users").insert({"username": username, "password": password, "full_name": full_name, "role": role}).execute()

def update_user_role(username, new_role):
    if supabase: supabase.table("users").update({"role": new_role}).eq("username", username).execute()

def delete_user_db(username):
    if supabase: supabase.table("users").delete().eq("username", username).execute()

def fetch_requests():
    if supabase:
        res = supabase.table("requests").select("*").order("created_at", desc=True).execute()
        return res.data
    return []

def add_request(user_name, req_type, req_date, detail):
    if supabase:
        is_leave = "ลางาน" in req_type
        status = "⏳ รออนุมัติ" if is_leave else "✅ อนุมัติแล้ว"
        if is_leave and "ลาป่วย" in detail: status = "✅ อนุมัติแล้ว" 
        supabase.table("requests").insert({"user_name": user_name, "req_type": req_type, "req_date": req_date.strftime("%Y-%m-%d"), "detail": detail, "status": status}).execute()

def update_request_status(req_id, new_status):
    if supabase: supabase.table("requests").update({"status": new_status}).eq("id", req_id).execute()

def delete_request(req_id):
    if supabase: supabase.table("requests").delete().eq("id", req_id).execute()

# ฟังก์ชันบันทึกตารางที่จัดเสร็จแล้วลง Supabase
def save_schedule_to_db(target_date_str, html_table):
    if supabase:
        try:
            res = supabase.table("schedules").select("id").eq("schedule_date", target_date_str).execute()
            data = {"schedule_date": target_date_str, "html_content": html_table, "created_at": datetime.now().isoformat()}
            if len(res.data) > 0:
                supabase.table("schedules").update(data).eq("schedule_date", target_date_str).execute()
            else:
                supabase.table("schedules").insert(data).execute()
            return True
        except:
            return False
    return False

if 'pt_daily_db' not in st.session_state: st.session_state.pt_daily_db = [] 

users_db = fetch_users()
core_list = ['เต้น', 'แอน', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'ริน', 'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์']
for u in users_db.values():
    if u['full_name'] not in core_list and u['role'] != 'System': core_list.append(u['full_name'])
base_pharmacist_list = core_list

time_slots = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]
time_labels = [f"{time_slots[i]}-{time_slots[i+1]}" for i in range(16)]
th_holidays = holidays.Thailand(years=datetime.now().year)

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

def load_db_to_dashboard(approved_today, all_requests, target_date_str):
    leaves, tasks, shifts, bo_list = [], [], [], []
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    
    for r in approved_today:
        if "ลางาน" in r['req_type']:
            l_type = "เต็มวัน"
            if "ครึ่งวันเช้า" in r['detail']: l_type = "ครึ่งวันเช้า (08.30-13.00)"
            elif "ครึ่งวันบ่าย" in r['detail']: l_type = "ครึ่งวันบ่าย (12.00-16.30)"
            elif "ลาป่วย" in r['detail']: l_type = "ลาป่วยฉุกเฉิน"
            s_time, e_time = "08.30", "16.30"
            times = re.findall(r'\d{2}\.\d{2}', r['detail'])
            if len(times) >= 2: s_time, e_time = times[0], times[1]
            leaves.append({"user_name": r['user_name'], "leave_type": l_type, "start": s_time, "end": e_time, "detail": r['detail']})
            
        elif "งานพิเศษ" in r['req_type']:
            times = re.findall(r'\d{2}\.\d{2}', r['detail'])
            tasks.append({
                "user_name": r['user_name'], 
                "task_name": r['detail'].split('(')[0].replace('งานพิเศษ:', '').strip(),
                "start": times[0] if len(times)>0 else "08.30", 
                "end": times[1] if len(times)>1 else "16.30",
            })
            
        elif "ออกเวร" in r['req_type']:
            s_type = "ออกเวรดึก" if "ดึก" in r['detail'] else "ออกเวรเย็น"
            room = "ชั้น 1"
            if "พระเทพ" in r['detail']: room = "ตึกพระเทพ"
            elif "ตึกเก่า" in r['detail']: room = "ตึกเก่า"
            shifts.append({"user_name": r['user_name'], "shift_type": s_type, "room": room, "start": "08.30", "end": "10.30", "time_slot": "15.00-15.30"})

    for r in all_requests:
        if r['req_type'] == "Back Office" and r['status'] == "✅ อนุมัติแล้ว":
            try:
                start_dt = datetime.strptime(r['req_date'], "%Y-%m-%d").date()
                parts = r['detail'].split('|') 
                if len(parts) >= 4:
                    end_dt = datetime.strptime(parts[1], "%Y-%m-%d").date()
                    if start_dt <= target_dt <= end_dt:
                        times = parts[2].split('-')
                        bo_list.append({"user_name": r['user_name'], "task_name": parts[3], "start": times[0], "end": times[1] if len(times)>1 else "16.30"})
            except: pass
            
    return leaves, tasks, shifts, bo_list

def force_sync_dashboard(target_date_str, all_requests):
    approved_today = [r for r in all_requests if r["req_date"] == target_date_str and r["status"] == "✅ อนุมัติแล้ว"]
    pts_today = [pt for pt in st.session_state.pt_daily_db if pt["date"] == target_date_str]
    leaves, tasks, shifts, bo_list = load_db_to_dashboard(approved_today, all_requests, target_date_str)
    
    st.session_state.dash_leaves = leaves
    st.session_state.dash_tasks = tasks
    st.session_state.dash_shifts = shifts
    st.session_state.dash_bo = bo_list
    st.session_state.dash_pts = pts_today
    st.session_state.dash_subs = [] 
    
    st.session_state.dash_locks = [
        {"user_name": "โบ้ท", "type": "task", "task_name": "จ2", "start": "08.30", "end": "09.30"},
        {"user_name": "ปอนด์", "type": "task", "task_name": "Check out", "start": "08.30", "end": "09.30"},
        {"user_name": "ฟอร์จูน", "type": "task", "task_name": "เบิกยา", "start": "08.30", "end": "09.30"},
        {"user_name": "อ๊อฟฟี่", "type": "task", "task_name": "ลง ADR", "start": "08.30", "end": "09.30"}
    ]
    st.session_state.dash_date = target_date_str
    st.session_state.dash_hash = len(all_requests) + len(pts_today)

# ------------------------------------------------------------------
# 3. สมองกล AI จัดตารางเวร (อิงตาม VER 137 ของจริง 100%)
# ------------------------------------------------------------------
def get_time_idx(t_str):
    mapping = {t_str: idx for idx, t_str in enumerate(time_slots[:16])}
    return mapping.get(t_str, 0)

# คืนชีพหมวดหมู่งานจาก Ver 137
dispensing_tasks = [f"จ่าย {i}" for i in range(4, 12)] # จ่าย 4 ถึง จ่าย 11
ver_cpoe_tasks = ["Ver 1 INC", "Ver 2/ปณ.", "Ver 3/A", "Ver 4", "Ver 5", "Ver 6"]
ver_ps_tasks = ["Ver PS1", "Ver PS2", "Ver PS3", "Ver PS4", "Ver PS5"]
base_main_tasks = dispensing_tasks + ver_cpoe_tasks + ver_ps_tasks + ["Match + C"]

def generate_ai_schedule(dash_leaves, dash_tasks, dash_shifts, dash_subs, dash_pts, dash_bo, dash_locks):
    num_slots = 16
    
    dynamic_tasks = set()
    for t in dash_tasks + dash_subs + dash_bo: dynamic_tasks.add(t.get('task_name', 'งานพิเศษ'))
    for l in dash_locks:
        if l['type'] == 'task': dynamic_tasks.add(l['task_name'])
            
    # หมวดหมู่งานทั้งหมดตาม Ver 137
    all_tasks = base_main_tasks + ["Matching", "พัก", "ออกเวรดึก", "ออกเวรเย็น", "ว่าง"] + list(dynamic_tasks)
    
    pt_names = [f"PT-{pt['name']}" for pt in dash_pts]
    all_staff = base_pharmacist_list + pt_names
    
    absent_slots = {p: set() for p in all_staff}
    
    for l in dash_leaves:
        p = l['user_name']
        if p not in all_staff: continue
        if l['leave_type'] == 'เต็มวัน': absent_slots[p].update(range(16))
        elif l['leave_type'] == 'ครึ่งวันเช้า (08.30-13.00)': absent_slots[p].update(range(0, 9))
        elif l['leave_type'] == 'ครึ่งวันบ่าย (12.00-16.30)': absent_slots[p].update(range(7, 16))
        elif l['leave_type'] == 'ลาป่วยฉุกเฉิน':
            s_idx, e_idx = get_time_idx(l['start']), get_time_idx(l['end'])
            absent_slots[p].update(range(s_idx, e_idx if e_idx > s_idx else 16))

    for pt in dash_pts:
        p_name = f"PT-{pt['name']}"
        s_idx, e_idx = get_time_idx(pt['start']), get_time_idx(pt['end'])
        e_idx = e_idx if e_idx > 0 else 16
        for t in range(16):
            if t < s_idx or t >= e_idx: absent_slots[p_name].add(t)

    model = cp_model.CpModel()
    x = {}
    for p in all_staff:
        for t in range(num_slots):
            for tsk in all_tasks: x[(p, t, tsk)] = model.NewBoolVar(f'x_{p}_{t}_{tsk}')
                
    for p in all_staff:
        for t in range(num_slots): model.AddExactlyOne(x[(p, t, tsk)] for tsk in all_tasks)
            
    for p in all_staff:
        for t in range(num_slots):
            if t in absent_slots[p]: model.Add(x[(p, t, "ว่าง")] == 1)
            else: model.Add(x[(p, t, "ว่าง")] == 0)

    for l in dash_locks:
        p = l['user_name']
        if p not in all_staff: continue
        if l['type'] == 'task':
            s_idx, e_idx = get_time_idx(l['start']), get_time_idx(l['end'])
            for t in range(s_idx, e_idx):
                if t not in absent_slots[p]: model.Add(x[(p, t, l['task_name'])] == 1)
        elif l['type'] == 'break':
            s_idx, e_idx = get_time_idx(l['start']), get_time_idx(l['end'])
            for t in range(s_idx, e_idx):
                if t not in absent_slots[p]: model.Add(x[(p, t, "พัก")] == 1)
        elif l['type'] == 'no_dispense':
            for t in range(16):
                for disp_t in dispensing_tasks:
                    if t not in absent_slots[p]: model.Add(x[(p, t, disp_t)] == 0)

    for sh in dash_shifts:
        p = sh['user_name']
        if p not in all_staff: continue
        if sh['shift_type'] == 'ออกเวรดึก':
            s_idx, e_idx = get_time_idx(sh.get('start', '08.30')), get_time_idx(sh.get('end', '10.30'))
            for t in range(s_idx, e_idx):
                if t < 16 and t not in absent_slots[p]: model.Add(x[(p, t, "ออกเวรดึก")] == 1)
        elif sh['shift_type'] == 'ออกเวรเย็น':
            t_idx = get_time_idx(sh.get('time_slot', '15.00-15.30').split('-')[0])
            if t_idx < 16 and t_idx not in absent_slots[p]: model.Add(x[(p, t_idx, "ออกเวรเย็น")] == 1)

    for tsk in dash_tasks + dash_subs + dash_bo:
        p = tsk['user_name']
        if p not in all_staff: continue
        s_idx, e_idx = get_time_idx(tsk['start']), get_time_idx(tsk['end'])
        e_idx = e_idx if e_idx > 0 else 16
        t_name = tsk.get('task_name', 'งานพิเศษ')
        for t in range(s_idx, e_idx):
            if t not in absent_slots[p]: model.Add(x[(p, t, t_name)] == 1)

    # กฎพักพาร์ทไทม์
    for pt in dash_pts:
        p_name = f"PT-{pt['name']}"
        if p_name not in all_staff: continue
        b_type, b_time = pt.get('break_type', 'ไม่พักเลย'), pt.get('break_time', None)
        if b_type != "ไม่พักเลย" and b_time:
            b_s_idx = get_time_idx(b_time)
            if b_type == "พัก 1 ชั่วโมง":
                if b_s_idx < 16 and b_s_idx not in absent_slots[p_name]: model.Add(x[(p_name, b_s_idx, "พัก")] == 1)
                if b_s_idx + 1 < 16 and (b_s_idx + 1) not in absent_slots[p_name]: model.Add(x[(p_name, b_s_idx + 1, "พัก")] == 1)
                for t in range(16):
                    if t != b_s_idx and t != (b_s_idx + 1) and t not in absent_slots[p_name]: model.Add(x[(p_name, t, "พัก")] == 0)
            elif b_type == "พักครึ่งชั่วโมง":
                if b_s_idx < 16 and b_s_idx not in absent_slots[p_name]: model.Add(x[(p_name, b_s_idx, "พัก")] == 1)
                for t in range(16):
                    if t != b_s_idx and t not in absent_slots[p_name]: model.Add(x[(p_name, t, "พัก")] == 0)
        else:
            for t in range(16):
                if t not in absent_slots[p_name]: model.Add(x[(p_name, t, "พัก")] == 0)

    # 💥 คืนชีพกฎจ่ายยาของ FT (อิง Ver 137)
    for p in all_staff:
        if not p.startswith("PT-"):
            # จ่ายยารวมกันห้ามเกิน 7 สล็อต (3.5 ชม.)
            model.Add(sum(x[(p, t, dt)] for t in range(num_slots) for dt in dispensing_tasks) <= 7)
            # กฎห้าม 7 คู่ 8
            has_7 = model.NewBoolVar(f"has_7_{p}")
            has_8 = model.NewBoolVar(f"has_8_{p}")
            for t in range(num_slots):
                model.AddImplication(x[(p, t, "จ่าย 7")] == 1, has_7)
                model.AddImplication(x[(p, t, "จ่าย 8")] == 1, has_8)
            model.Add(has_7 + has_8 <= 1)

    # กฎขั้นต่ำสุดในการยืนระบบ (เพื่อป้องกัน Error ตึงเกินไป ยอมให้ยืดหยุ่นได้บ้าง)
    for t in range(num_slots):
        model.Add(sum(x[(p, t, "จ่าย 7")] for p in all_staff) + sum(x[(p, t, "จ่าย 8")] for p in all_staff) >= 1)
        model.Add(sum(x[(p, t, "Ver 1 INC")] for p in all_staff) >= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0 # จำกัดเวลาไม่ให้ Cloud ค้าง
    status = solver.Solve(model)
    
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        data = []
        shift_dict = {sh['user_name']: sh for sh in dash_shifts if sh['shift_type'] == 'ออกเวรเย็น'}
        for p in all_staff:
            row = {"รายชื่อเภสัชกร": p}
            for t in range(num_slots):
                assigned_task = ""
                for tsk in all_tasks:
                    if solver.Value(x[(p, t, tsk)]) == 1:
                        assigned_task = tsk
                        break
                        
                if assigned_task == "ออกเวรดึก": assigned_task = "พัก (ออกเวรดึก)"
                elif assigned_task == "ออกเวรเย็น": assigned_task = f"พัก (ก่อนเวรเย็น {shift_dict[p]['room']})"
                elif p in shift_dict and assigned_task not in ["พัก", "ว่าง", "ออกเวรดึก"]:
                    assigned_task = f"{assigned_task} [เวรเย็น:{shift_dict[p]['room']}]"
                        
                row[time_labels[t]] = assigned_task
            data.append(row)
        return pd.DataFrame(data)
    else:
        return None

# ------------------------------------------------------------------
# 4. ฟังก์ชันจัดการสี (Color Styling & HTML Export) แบบ Ver 137
# ------------------------------------------------------------------
def get_color_style(val_str):
    if pd.isna(val_str): return ''
    val = str(val_str)
    # 🎨 สีสไตล์ High Contrast & Clear Category แบบ Ver 137
    if 'จ่าย' in val: return 'background-color: #7DCEA0; color: white; font-weight: bold; text-align: center;'
    if 'Ver PS' in val: return 'background-color: #C39BD3; color: white; font-weight: bold; text-align: center;'
    if 'Ver' in val: return 'background-color: #F8C471; color: white; font-weight: bold; text-align: center;'
    if 'Match' in val:
        if 'Match + C' in val: return 'background-color: #5DADE2; color: #8B0000; font-weight: bold; text-align: center;'
        return 'background-color: #5DADE2; color: white; font-weight: bold; text-align: center;'
    if 'พัก' in val: return 'background-color: #F1948A; color: white; font-weight: bold; text-align: center;'
    if 'ลา' in val: return 'background-color: #808080; color: white; font-weight: bold; text-align: center;'
    if 'ว่าง' in val or '-' in val: return 'background-color: #F2F3F4; color: #808080; text-align: center;'
    return 'background-color: #FFFFFF; color: black; text-align: center;'

def build_html_table(df, date_str):
    # ฟังก์ชันสร้าง HTML เพื่อดาวน์โหลดเป็นรูป/PDF ได้โดยอิงฟอนต์ Sarabun
    html = f"""
    <html><head><meta charset="utf-8">
    <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Sarabun', sans-serif; background-color: white; padding: 20px; }}
        h2 {{ text-align: center; color: #333; }}
        table {{ border-collapse: collapse; width: 100%; font-size: 17px; }}
        th, td {{ border: 1px solid #444; text-align: center; padding: 10px; height: 35px; }}
        th {{ background-color: #f4f6f8; font-size: 19px; }}
        .task-dispense {{ background-color: #7DCEA0; color: white; font-weight: bold; }}
        .task-cpoe {{ background-color: #F8C471; color: white; font-weight: bold; }}
        .task-ps {{ background-color: #C39BD3; color: white; font-weight: bold; }}
        .task-match {{ background-color: #5DADE2; color: white; font-weight: bold; }}
        .task-matchc {{ background-color: #5DADE2; color: #8B0000; font-weight: bold; }}
        .task-break {{ background-color: #F1948A; color: white; font-weight: bold; }}
        .task-leave {{ background-color: #808080; color: white; font-weight: bold; }}
        .task-empty {{ background-color: #F2F3F4; color: #808080; }}
        .task-custom {{ background-color: #FFFFFF; color: black; }}
    </style>
    </head><body>
    <h2>ตารางปฏิบัติงานห้องยา วันที่ {date_str}</h2>
    <table><tr>{"".join(f"<th>{col}</th>" for col in df.columns)}</tr>
    """
    for _, row in df.iterrows():
        html += "<tr>"
        for col in df.columns:
            val = str(row[col]) if pd.notna(row[col]) else ""
            cls = "task-custom"
            if 'จ่าย' in val: cls = "task-dispense"
            elif 'Ver PS' in val: cls = "task-ps"
            elif 'Ver' in val: cls = "task-cpoe"
            elif 'Match + C' in val: cls = "task-matchc"
            elif 'Match' in val: cls = "task-match"
            elif 'พัก' in val: cls = "task-break"
            elif 'ลา' in val: cls = "task-leave"
            elif 'ว่าง' in val or '-' in val: cls = "task-empty"
            html += f"<td class='{cls}'>{val}</td>"
        html += "</tr>"
    html += "</table></body></html>"
    return html

# ------------------------------------------------------------------
# 5. UI Login & Sidebar
# ------------------------------------------------------------------
def login_page():
    st.markdown("<h1 style='text-align: center; color: #2E86C1;'>💊 PharmSuk</h1>", unsafe_allow_html=True)
    st.write("---")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username (ชื่อเล่นภาษาอังกฤษ)")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("เข้าสู่ระบบ", use_container_width=True):
                user = username.lower().strip()
                if user in users_db and users_db[user]['password'] == password:
                    st.session_state.logged_in = True
                    st.session_state.current_user = users_db[user]
                    st.rerun()
                else: st.error("❌ Username หรือ Password ไม่ถูกต้อง")

def logout():
    st.session_state.logged_in = False
    st.session_state.current_user = None
    st.rerun()

if not st.session_state.logged_in:
    login_page()
    st.stop()

user_info = st.session_state.current_user
with st.sidebar:
    st.markdown(f"### 👤 คุณ {user_info['full_name']} ({user_info['role']})")
    st.button("🚪 ออกจากระบบ", on_click=logout, use_container_width=True)
    st.divider()
    
    menu_options = ["🗓️ ปฏิทินห้องยา & ลงข้อมูล"]
    if user_info['role'] == 'Admin':
        menu_options.extend(["🔐 อนุมัติคำขอ (Approve)", "⚙️ รันตาราง AI ประจำวัน", "🏃 จัดการพาร์ทไทม์", "👥 จัดการผู้ใช้งาน"])
    page = st.radio("เลือกเมนู", menu_options, label_visibility="collapsed")

# ==================================================================
# หน้า 1: ปฏิทินห้องยา & ลงข้อมูล
# ==================================================================
if page == "🗓️ ปฏิทินห้องยา & ลงข้อมูล":
    st.title("🗓️ ปฏิทินภาพรวม & ลงข้อมูลบุคลากร")
    tab1, tab2, tab3 = st.tabs(["📅 ดูปฏิทินรวม", "📝 ฟอร์มลงข้อมูล", "❌ จัดการคำขอของคุณ"])
    all_requests = fetch_requests()
    
    with tab1:
        filter_option = st.selectbox("🔍 กรองข้อมูลบนปฏิทิน:", ["แสดงทั้งหมด", "เฉพาะลางาน", "เฉพาะออกเวรดึก", "เฉพาะออกเวรเย็น", "เฉพาะงานพิเศษ / Back Office", "เฉพาะแจ้งเตือน"])
        st.write("---")
        events = []
        calendar_css = ".fc-day-sat { background-color: #f4f6f8 !important; } .fc-day-sun { background-color: #f4f6f8 !important; } .fc-event { white-space: normal !important; word-wrap: break-word !important; } .fc-event-title { white-space: normal !important; overflow: hidden !important; }"
        
        def get_priority(r):
            rt = r["req_type"]
            if r["user_name"] == "SYSTEM_REQ": return 2
            if "ลางาน" in rt: return 1
            if "แจ้งเตือน" in rt: return 2
            if "งานพิเศษ" in rt: return 3
            if "Back Office" in rt: return 4
            if "ออกเวร" in rt: return 5
            return 99

        sorted_requests = sorted(all_requests, key=get_priority)
        for h_date, h_name in th_holidays.items():
            events.append({"start": h_date.strftime("%Y-%m-%d"), "display": "background", "backgroundColor": "#FFCDD2", "priority": 0})
            events.append({"title": f"🇹🇭 {h_name}", "start": h_date.strftime("%Y-%m-%d"), "backgroundColor": "#E74C3C", "textColor": "white", "allDay": True, "priority": 0})
            
        for req in sorted_requests:
            rt = req["req_type"]
            dt = req["detail"]
            if filter_option == "เฉพาะลางาน" and "ลางาน" not in rt: continue
            if filter_option == "เฉพาะออกเวรดึก" and ("ออกเวร" not in rt or "ดึก" not in dt): continue
            if filter_option == "เฉพาะออกเวรเย็น" and ("ออกเวร" not in rt or "เย็น" not in dt): continue
            if filter_option == "เฉพาะงานพิเศษ / Back Office" and "งานพิเศษ" not in rt and "Back Office" not in rt: continue
            if filter_option == "เฉพาะแจ้งเตือน" and "แจ้งเตือน" not in rt and req["user_name"] != "SYSTEM_REQ": continue

            prio = get_priority(req)
            if req["user_name"] == "SYSTEM_REQ":
                events.append({"title": f"🚨 {dt}", "start": req["req_date"], "backgroundColor": "#E67E22", "priority": prio})
                continue
            if rt == "Back Office":
                parts = dt.split('|')
                if len(parts) >= 4:
                    e_date = (datetime.strptime(parts[1], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                    events.append({"title": f"💻 {req['user_name']}: {parts[3]}", "start": req["req_date"], "end": e_date, "backgroundColor": "#9B59B6", "priority": prio})
                continue

            if req["status"] == "✅ อนุมัติแล้ว": color = "#4CAF50"
            elif req["status"] == "⏳ รออนุมัติ": color = "#FFC107"
            else: continue
            events.append({"title": f"[{req['status'][0]}] {req['user_name']} - {dt}", "start": req["req_date"], "backgroundColor": color, "priority": prio})
            
        if filter_option == "แสดงทั้งหมด":
            for pt in st.session_state.pt_daily_db:
                events.append({"title": f"🏃 PT: {pt['name']} ({pt['start']}-{pt['end']})", "start": pt["date"], "backgroundColor": "#3498DB", "priority": 6})
            
        calendar_options = {"headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth,timeGridWeek,timeGridDay"}, "initialView": "dayGridMonth", "displayEventTime": False, "eventDisplay": "block", "eventOrder": "priority"}
        cal_clicked = calendar(events=events, options=calendar_options, custom_css=calendar_css)
        if cal_clicked.get("eventClick"): st.info(f"🔎 **รายละเอียด:** {cal_clicked['eventClick']['event']['title']}")

    with tab2:
        form_options = ["🏖️ ลางาน", "💼 งานพิเศษ", "💻 งาน Back Office (ระยะยาว)", "🌅 ออกเวร", "🔔 แจ้งเตือน"]
        if user_info['role'] == 'Admin': form_options.insert(4, "🟠 ส่งคนไปแทนห้องยาอื่น")
        main_type = st.radio("เลือกหมวดหมู่:", form_options, horizontal=True)
        st.divider()
        req_user_save = user_info['full_name']
        
        if "ลางาน" in main_type:
            req_date = st.date_input("วันที่:")
            leave_cat = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาไปอบรม module", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
            leave_time = st.selectbox("ช่วงเวลา", ["เต็มวัน", "ครึ่งวันเช้า (08.30-13.00)", "ครึ่งวันบ่าย (12.00-16.30)"])
            detail_str = f"{leave_cat} ({leave_time})"
            if "ลาป่วย" in leave_cat:
                c1, c2 = st.columns(2)
                with c1: s_t = st.selectbox("เริ่มลา", time_slots, index=0)
                with c2: e_t = st.selectbox("ถึง", time_slots, index=len(time_slots)-1)
                detail_str = f"{leave_cat} ({s_t}-{e_t} น.)"
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request(req_user_save, f"ลางาน: {leave_cat}", req_date, detail_str)
                st.rerun()
                
        elif "Back Office" in main_type:
            task_name = st.text_input("ชื่องาน Back Office")
            c1, c2 = st.columns(2)
            bo_s_date, bo_e_date = c1.date_input("เริ่มวันที่"), c2.date_input("ถึงวันที่")
            sc1, sc2 = st.columns(2)
            bo_s_t, bo_e_t = sc1.selectbox("เวลาเริ่ม", time_slots, index=0), sc2.selectbox("ถึงเวลา", time_slots, index=len(time_slots)-1)
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                if task_name:
                    add_request(req_user_save, "Back Office", bo_s_date, f"BO|{bo_e_date.strftime('%Y-%m-%d')}|{bo_s_t}-{bo_e_t}|{task_name}")
                    st.rerun()
            
        elif "งานพิเศษ" in main_type:
            req_date = st.date_input("วันที่:")
            task_cat = st.selectbox("เลือกงานพิเศษ", ["หาหมอ", "ประชุม", "สอน Robot", "อื่นๆ"])
            custom_task = st.text_input("ระบุ (ถ้าเลือกอื่นๆ)")
            c1, c2 = st.columns(2)
            with c1: s_t = st.selectbox("เริ่ม", time_slots, index=0)
            with c2: e_t = st.selectbox("ถึง", time_slots, index=len(time_slots)-1)
            final_task = custom_task if task_cat == "อื่นๆ" else task_cat
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request(req_user_save, "งานพิเศษ", req_date, f"งานพิเศษ: {final_task} ({s_t}-{e_t} น.)")
                st.rerun()
            
        elif "ออกเวร" in main_type:
            req_date = st.date_input("วันที่:")
            shift_cat = st.radio("ประเภท", ["ออกเวรดึก (พัก 8.30-10.30 น.)", "ออกเวรเย็น"])
            if "ออกเวรดึก" in shift_cat: detail_str = "ออกเวรดึก (พักเช้า 8.30-10.30 น.)"
            else: detail_str = f"ออกเวรเย็น (ห้องยา: {st.selectbox('สถานที่', ['ชั้น 1', 'ชั้นอื่นตึกพระเทพ', 'ตึกเก่า'])})"
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request(req_user_save, "ออกเวร", req_date, detail_str)
                st.rerun()
            
        elif "แทนห้องยาอื่น" in main_type:
            req_date = st.date_input("วันที่:")
            replace_loc = st.text_input("สถานที่ไปแทน")
            c1, c2 = st.columns(2)
            with c1: r_s = st.selectbox("เริ่ม", time_slots, index=0)
            with c2: r_e = st.selectbox("ถึง", time_slots, index=len(time_slots)-1)
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request("SYSTEM_REQ", "แทนห้องยาอื่น", req_date, f"ไปแทนที่: {replace_loc} ({r_s}-{r_e} น.)")
                st.rerun()
            
        elif "แจ้งเตือน" in main_type:
            req_date = st.date_input("วันที่:")
            detail_str = f"📢 แจ้งเตือน: {st.text_area('ข้อความ')}"
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request(req_user_save, "แจ้งเตือน / ส่งเคส", req_date, detail_str)
                st.rerun()

    with tab3:
        my_reqs = [r for r in all_requests if r["user_name"] == user_info['full_name'] or (user_info['role'] == 'Admin' and r["user_name"] == "SYSTEM_REQ")]
        for r in my_reqs:
            c1, c2 = st.columns([8, 2])
            c1.write(f"📅 {r['req_date']} | **{r['req_type']}** | {r['status']}\n📝 {r['detail']}")
            if c2.button("🗑️ ยกเลิก", key=f"del_{r['id']}"):
                delete_request(r['id'])
                st.rerun()

# ==================================================================
# หน้า 2: อนุมัติคำขอ
# ==================================================================
elif page == "🔐 อนุมัติคำขอ (Approve)":
    st.title("🔐 จัดการคำขอลางาน")
    pending_reqs = [r for r in fetch_requests() if r["status"] == "⏳ รออนุมัติ"]
    for req in pending_reqs:
        st.write(f"**ผู้ขอ:** {req['user_name']} | **วันที่:** {req['req_date']} | **รายละเอียด:** {req['detail']}")
        c1, c2, _ = st.columns([1, 1, 8])
        if c1.button("✅ อนุมัติ", key=f"app_{req['id']}"):
            update_request_status(req['id'], "✅ อนุมัติแล้ว")
            st.rerun()
        if c2.button("❌ ปฏิเสธ", key=f"rej_{req['id']}"):
            update_request_status(req['id'], "❌ ไม่อนุมัติ")
            st.rerun()

# ==================================================================
# หน้า 3: ⚙️ รันตาราง AI (และบันทึก/ส่งออกข้อมูล)
# ==================================================================
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ บอร์ดควบคุมและจัดตารางเวร AI")
    
    col_t1, col_t2 = st.columns([7, 3])
    target_date = col_t1.date_input("เลือกวันที่ต้องการจัดตาราง", key="ai_target_date")
    target_date_str = target_date.strftime("%Y-%m-%d")
    
    all_requests = fetch_requests()
    approved_today = [r for r in all_requests if r["req_date"] == target_date_str and r["status"] == "✅ อนุมัติแล้ว"]
    pts_today = [pt for pt in st.session_state.pt_daily_db if pt["date"] == target_date_str]
    current_hash = len(all_requests) + len(pts_today)

    if 'dash_date' not in st.session_state or st.session_state.dash_date != target_date_str or st.session_state.get('dash_hash', -1) != current_hash:
        force_sync_dashboard(target_date_str, all_requests)
    
    if col_t2.button("🔄 ดึงข้อมูลล่าสุดจากปฏิทิน", use_container_width=True):
        force_sync_dashboard(target_date_str, all_requests)
        st.rerun()

    st.markdown(f"---")
    st.subheader(f"🛠️ แผงควบคุมกำลังพลอิสระ (วันที่ {target_date.strftime('%d/%m/%Y')})")
    
    tab_l, tab_pt, tab_t, tab_bo, tab_sh, tab_sub, tab_lock = st.tabs([
        "🏖️ ลา", "🏃 PT", "💼 พิเศษ", "💻 Back Office", "🌅 ดึก/เย็น", "🟠 ไปแทน", "🔒 ล็อก/เว้น"
    ])
    
    # [เนื้อหา Tab ซ่อนปุ่มต่างๆ เหมือน V12 ปกติเพื่อประหยัดที่บรรทัด]
    with tab_l:
        for idx, l in enumerate(st.session_state.dash_leaves):
            st.info(f"👤 {l['user_name']} -> {l['leave_type']}")
    with tab_pt:
        for idx, pt in enumerate(st.session_state.dash_pts):
            st.success(f"🏃 {pt['name']} ({pt['start']}-{pt['end']} น.) | {pt['break_type']}")
    with tab_t:
        for idx, t in enumerate(st.session_state.dash_tasks):
            st.warning(f"💼 {t['user_name']} -> {t['task_name']} ({t['start']}-{t['end']} น.)")
    with tab_bo:
        for idx, bo in enumerate(st.session_state.dash_bo):
            st.markdown(f"💻 {bo['user_name']} -> {bo['task_name']} ({bo['start']}-{bo['end']})")
    with tab_sh:
        for idx, sh in enumerate(st.session_state.dash_shifts):
            st.error(f"🌅 {sh['user_name']} -> {sh['shift_type']}")
    with tab_sub:
        for idx, s in enumerate(st.session_state.dash_subs):
            st.info(f"✔️ ส่ง **{s['user_name']}** ไป {s['task_name']}")
    with tab_lock:
        for idx, l in enumerate(st.session_state.dash_locks):
            st.info(f"🔒 {l['user_name']} -> {l['type']}")

    st.divider()
    if st.button("🚀 ประมวลผลสมองกล AI สร้างตาราง", type="primary", use_container_width=True):
        with st.spinner("🤖 AI กำลังคำนวณตำแหน่งและบล็อกเวลา ตามกฎ Ver 137..."):
            df_schedule = generate_ai_schedule(
                st.session_state.dash_leaves,
                st.session_state.dash_tasks,
                st.session_state.dash_shifts,
                st.session_state.dash_subs,
                st.session_state.dash_pts,
                st.session_state.dash_bo,
                st.session_state.dash_locks
            )
            
            if df_schedule is not None:
                st.success("🎉 AI คำนวณตารางเสร็จสมบูรณ์!")
                
                # 1. เทสีบนหน้าเว็บ
                styled_df = df_schedule.style.map(get_color_style)
                st.dataframe(styled_df, use_container_width=True)
                
                # 2. แปลงเป็น Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_schedule.to_excel(writer, index=False, sheet_name='ตารางเวร')
                excel_data = output.getvalue()
                
                # 3. แปลงเป็นรูปภาพ (HTML รูปแบบตารางสีเพื่อโหลดไปเซฟหรือพริ้นต์)
                html_data = build_html_table(df_schedule, target_date_str)
                
                c1, c2, c3 = st.columns(3)
                c1.download_button(label="📥 ดาวน์โหลดไฟล์ Excel", data=excel_data, file_name=f"Schedule_{target_date_str}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                c2.download_button(label="🖼️ ดาวน์โหลดรูปตาราง (HTML/PNG)", data=html_data.encode('utf-8'), file_name=f"Schedule_{target_date_str}.html", mime="text/html", use_container_width=True)
                if c3.button("💾 บันทึกตารางลง Database", use_container_width=True):
                    if save_schedule_to_db(target_date_str, html_data):
                        st.success("✅ บันทึกตารางเข้าสู่ระบบ Cloud เรียบร้อยแล้ว!")
                    else:
                        st.error("❌ บันทึกล้มเหลว")
            else:
                st.error("⚠️ AI คำนวณล้มเหลว (กำลังพลไม่เพียงพอ หรือมีการล็อกเวลาชนกันจนจัดตารางไม่ได้)")

# ==================================================================
# หน้า 4: 🏃 จัดการพาร์ทไทม์ และ หน้า 5: จัดการผู้ใช้
# ==================================================================
elif page == "🏃 จัดการพาร์ทไทม์":
    st.title("🏃 จัดการข้อมูลบุคลากร Part-time ล่วงหน้า")
    with st.container(border=True):
        pt_date = st.date_input("วันที่ PT มาทำงาน", key="pt_db_date")
        pt_name = st.text_input("ชื่อ PT", placeholder="เช่น สมชาย")
        c1, c2 = st.columns(2)
        with c1: pt_start = st.selectbox("ตั้งแต่เวลา", time_slots, index=0)
        with c2: pt_end = st.selectbox("ถึงเวลา", time_slots, index=len(time_slots)-1)
        pt_break_type = st.radio("การพักเบรก", ["พัก 1 ชั่วโมง", "พักครึ่งชั่วโมง", "ไม่พักเลย"], horizontal=True)
        pt_break_time = st.selectbox("ระบุเวลาเริ่มพัก", time_slots) if pt_break_type != "ไม่พักเลย" else None
        if st.button("➕ บันทึกพาร์ทไทม์ลงระบบ", type="primary"):
            if pt_name:
                st.session_state.pt_daily_db.append({"date": pt_date.strftime("%Y-%m-%d"), "name": pt_name, "start": pt_start, "end": pt_end, "break_type": pt_break_type, "break_time": pt_break_time})
                st.rerun()

elif page == "👥 จัดการผู้ใช้งาน":
    st.title("👥 จัดการรายชื่อและสิทธิ์แอปพลิเคชัน")
    with st.form("add_user_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1: new_user = st.text_input("Username")
        with c2: new_pass = st.text_input("Password")
        with c3: new_name = st.text_input("ชื่อเล่น")
        with c4: new_role = st.selectbox("สิทธิ์", ["Staff", "Admin"])
        if st.form_submit_button("บันทึก", type="primary") and new_user and new_name:
            add_user_db(new_user, new_pass, new_name, new_role)
            st.rerun()
