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
# 2. ระบบจัดการข้อมูล Cloud
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

# ------------------------------------------------------------------
# 3. สมองกล AI จัดตารางเวร (OR-Tools)
# ------------------------------------------------------------------
def get_time_idx(t_str):
    mapping = {t_str: idx for idx, t_str in enumerate(time_slots[:16])}
    return mapping.get(t_str, 0)

def generate_ai_schedule(dash_leaves, dash_tasks, dash_shifts, dash_subs, dash_pts):
    num_slots = 16
    main_tasks = ["จ่ายยา", "Ver CPOE", "Ver PS", "Match + C"]
    all_tasks = main_tasks + ["พัก", "จ2", "Check out", "เบิกยา", "ลง ADR", "งานพิเศษ", "ออกเวรดึก", "ว่าง"]
    
    pt_names = [f"PT-{pt['name']}" for pt in dash_pts]
    all_staff = base_pharmacist_list + pt_names
    
    # คำนวณช่วงเวลาที่ไม่อยู่ (ว่าง) ของแต่ละคน
    absent_slots = {p: set() for p in all_staff}
    
    # 1. จัดการเวลาลางาน (เต็มวัน/ครึ่งวัน/ลาป่วย)
    for l in dash_leaves:
        p = l['user_name']
        if p not in all_staff: continue
        
        if l['leave_type'] == 'เต็มวัน':
            absent_slots[p].update(range(16))
        elif l['leave_type'] == 'ครึ่งวันเช้า (08.30-13.00)':
            absent_slots[p].update(range(0, 9)) # บล็อก 08.30 ถึง 13.00 (index 0 ถึง 8)
        elif l['leave_type'] == 'ครึ่งวันบ่าย (12.00-16.30)':
            absent_slots[p].update(range(7, 16)) # บล็อก 12.00 ถึง 16.30 (index 7 ถึง 15)
        elif l['leave_type'] == 'ลาป่วยฉุกเฉิน':
            s_idx = get_time_idx(l['start'])
            e_idx = get_time_idx(l['end'])
            absent_slots[p].update(range(s_idx, e_idx if e_idx > s_idx else 16))

    # 2. จัดการช่วงเวลาที่ PT ไม่ได้เข้างาน
    for pt in dash_pts:
        p_name = f"PT-{pt['name']}"
        s_idx, e_idx = get_time_idx(pt['start']), get_time_idx(pt['end'])
        e_idx = e_idx if e_idx > 0 else 16
        for t in range(16):
            if t < s_idx or t >= e_idx: absent_slots[p_name].add(t)

    # ------------------ เริ่มสร้าง AI Model ------------------
    model = cp_model.CpModel()
    x = {}
    
    for p in all_staff:
        for t in range(num_slots):
            for tsk in all_tasks: x[(p, t, tsk)] = model.NewBoolVar(f'x_{p}_{t}_{tsk}')
                
    for p in all_staff:
        for t in range(num_slots): model.AddExactlyOne(x[(p, t, tsk)] for tsk in all_tasks)
            
    # บังคับช่อง "ว่าง" สำหรับคนที่ลา หรือพาร์ทไทม์ที่ไม่ได้เข้างาน
    for p in all_staff:
        for t in range(num_slots):
            if t in absent_slots[p]: model.Add(x[(p, t, "ว่าง")] == 1)
            else: model.Add(x[(p, t, "ว่าง")] == 0)

    # ล็อกหน้าที่เฉพาะ (ถ้าเขาไม่ได้ลาช่วงเช้า)
    fixed_assignments = {"โบ้ท": "จ2", "ปอนด์": "Check out", "ฟอร์จูน": "เบิกยา", "อ๊อฟฟี่": "ลง ADR"}
    for p, tsk in fixed_assignments.items():
        if p in all_staff:
            if 0 not in absent_slots[p]: model.Add(x[(p, 0, tsk)] == 1)
            if 1 not in absent_slots[p]: model.Add(x[(p, 1, tsk)] == 1)

    # กฎ: ออกเวรดึก (พักเช้า 8.30-10.30)
    for sh in dash_shifts:
        p = sh['user_name']
        if p in all_staff and sh['shift_type'] == 'ออกเวรดึก':
            for t in range(4):
                if t not in absent_slots[p]: model.Add(x[(p, t, "ออกเวรดึก")] == 1)

    # กฎ: งานพิเศษ & แทนห้องยาอื่น
    for tsk in dash_tasks + dash_subs:
        p = tsk['user_name']
        if p not in all_staff: continue
        s_idx = get_time_idx(tsk['start'])
        e_idx = get_time_idx(tsk['end'])
        e_idx = e_idx if e_idx > 0 else 16
        
        task_name = "แทนห้องยาอื่น" if "แทน" in tsk.get('task_name', tsk.get('detail', '')) else "งานพิเศษ"
        for t in range(s_idx, e_idx):
            if t not in absent_slots[p]: model.Add(x[(p, t, task_name)] == 1)

    # กฎ: การพักของพาร์ทไทม์
    for pt in dash_pts:
        p_name = f"PT-{pt['name']}"
        if p_name not in all_staff: continue
        
        b_type = pt.get('break_type', 'ไม่พักเลย')
        b_time = pt.get('break_time', None)
        
        if b_type != "ไม่พักเลย" and b_time:
            b_s_idx = get_time_idx(b_time)
            
            if b_type == "พัก 1 ชั่วโมง":
                if b_s_idx < 16 and b_s_idx not in absent_slots[p_name]: model.Add(x[(p_name, b_s_idx, "พัก")] == 1)
                if b_s_idx + 1 < 16 and (b_s_idx + 1) not in absent_slots[p_name]: model.Add(x[(p_name, b_s_idx + 1, "พัก")] == 1)
                for t in range(16):
                    if t != b_s_idx and t != (b_s_idx + 1) and t not in absent_slots[p_name]:
                        model.Add(x[(p_name, t, "พัก")] == 0)
                        
            elif b_type == "พักครึ่งชั่วโมง":
                if b_s_idx < 16 and b_s_idx not in absent_slots[p_name]: model.Add(x[(p_name, b_s_idx, "พัก")] == 1)
                for t in range(16):
                    if t != b_s_idx and t not in absent_slots[p_name]:
                        model.Add(x[(p_name, t, "พัก")] == 0)
        else:
            for t in range(16):
                if t not in absent_slots[p_name]: model.Add(x[(p_name, t, "พัก")] == 0)

    # จำนวนคนประจำจุด (หลวมๆ)
    present_staff = [p for p in all_staff if len(absent_slots[p]) < 16]
    if len(present_staff) >= 6:
        for t in range(num_slots):
            model.Add(sum(x[(p, t, "จ่ายยา")] for p in all_staff) >= 2)
            model.Add(sum(x[(p, t, "Ver CPOE")] for p in all_staff) >= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 8.0
    status = solver.Solve(model)
    
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        data = []
        pt_dict = {f"PT-{pt['name']}": pt for pt in dash_pts}
        shift_dict = {sh['user_name']: sh for sh in dash_shifts if sh['shift_type'] == 'ออกเวรเย็น'}
        
        for p in all_staff:
            row = {"รายชื่อเภสัชกร": p}
            for t in range(num_slots):
                assigned_task = ""
                for tsk in all_tasks:
                    if solver.Value(x[(p, t, tsk)]) == 1:
                        assigned_task = tsk
                        break
                        
                # ต่อท้ายห้องสำหรับ PT หรือเวรเย็น
                if assigned_task not in ["พัก", "ว่าง"]:
                    if p in pt_dict and "ทั่วไป" not in pt_dict[p]["room"]:
                        assigned_task = f"{assigned_task} ({pt_dict[p]['room'].replace('ประจำ', '')})"
                    elif p in shift_dict:
                        assigned_task = f"{assigned_task} [เวรเย็น:{shift_dict[p]['room']}]"
                        
                row[time_labels[t]] = assigned_task
            data.append(row)
        return pd.DataFrame(data)
    else:
        return None

# ------------------------------------------------------------------
# 4. ฟังก์ชันดึงข้อมูลแปลงเข้า State แผงควบคุม AI
# ------------------------------------------------------------------
def load_db_to_dashboard(approved_today):
    leaves, tasks, shifts = [], [], []
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
                "detail": r['detail']
            })
            
        elif "ออกเวร" in r['req_type']:
            s_type = "ออกเวรดึก" if "ดึก" in r['detail'] else "ออกเวรเย็น"
            room = "ชั้น 1"
            if "พระเทพ" in r['detail']: room = "ตึกพระเทพ"
            elif "ตึกเก่า" in r['detail']: room = "ตึกเก่า"
            shifts.append({"user_name": r['user_name'], "shift_type": s_type, "room": room, "detail": r['detail']})
            
    return leaves, tasks, shifts

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
        menu_options.extend(["🔐 อนุมัติคำขอ (Approve)", "⚙️ รันตาราง AI ประจำวัน", "👥 จัดการบุคลากร & Part-time"])
    page = st.radio("เลือกเมนู", menu_options, label_visibility="collapsed")

# ==================================================================
# หน้า 1: ปฏิทินห้องยา & ลงข้อมูล
# ==================================================================
if page == "🗓️ ปฏิทินห้องยา & ลงข้อมูล":
    st.title("🗓️ ปฏิทินภาพรวม & ลงข้อมูลบุคลากร")
    tab1, tab2, tab3 = st.tabs(["📅 ดูปฏิทินรวม", "📝 ฟอร์มลงข้อมูล", "❌ จัดการคำขอของคุณ"])
    all_requests = fetch_requests()
    
    with tab1:
        events = []
        for h_date, h_name in th_holidays.items():
            events.append({"start": h_date.strftime("%Y-%m-%d"), "display": "background", "backgroundColor": "#FFCDD2"})
            events.append({"title": f"🇹🇭 {h_name}", "start": h_date.strftime("%Y-%m-%d"), "backgroundColor": "#E74C3C", "textColor": "white", "allDay": True})
            
        for req in all_requests:
            if req["user_name"] == "SYSTEM_REQ":
                events.append({"title": f"🚨 {req['detail']}", "start": req["req_date"], "backgroundColor": "#E67E22"})
                continue
            if req["status"] == "✅ อนุมัติแล้ว": color = "#4CAF50"
            elif req["status"] == "⏳ รออนุมัติ": color = "#FFC107"
            else: continue
            events.append({"title": f"[{req['status'][0]}] {req['user_name']} - {req['detail']}", "start": req["req_date"], "backgroundColor": color})
            
        for pt in st.session_state.pt_daily_db:
            events.append({"title": f"🏃 PT: {pt['name']} ({pt['start']}-{pt['end']})", "start": pt["date"], "backgroundColor": "#3498DB"})
            
        calendar(events=events, options={"headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth"}, "initialView": "dayGridMonth"})

    with tab2:
        form_options = ["🏖️ ลางาน", "💼 งานพิเศษ", "🌅 ออกเวร", "🔔 แจ้งเตือน"]
        if user_info['role'] == 'Admin': form_options.insert(3, "🟠 ส่งคนไปแทนห้องยาอื่น")
        main_type = st.radio("เลือกหมวดหมู่:", form_options, horizontal=True)
        st.divider()
        req_date = st.date_input("วันที่:")
        
        req_user_save = user_info['full_name']
        if "ลางาน" in main_type:
            leave_cat = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาไปอบรม module", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
            leave_time = st.selectbox("ช่วงเวลา", ["เต็มวัน", "ครึ่งวันเช้า (08.30-13.00)", "ครึ่งวันบ่าย (12.00-16.30)"])
            detail_str = f"{leave_cat} ({leave_time})"
            if "ลาป่วย" in leave_cat:
                c1, c2 = st.columns(2)
                with c1: s_t = st.selectbox("เริ่มลา", time_slots, index=0)
                with c2: e_t = st.selectbox("ถึง", time_slots, index=len(time_slots)-1)
                detail_str = f"{leave_cat} ({s_t}-{e_t} น.)"
            req_type_save = f"ลางาน: {leave_cat}"
            
        elif "งานพิเศษ" in main_type:
            task_cat = st.selectbox("เลือกงานพิเศษ", ["หาหมอ", "ประชุม", "สอน Robot", "อื่นๆ"])
            custom_task = st.text_input("ระบุ (ถ้าเลือกอื่นๆ)")
            c1, c2 = st.columns(2)
            with c1: s_t = st.selectbox("เริ่ม", time_slots, index=0)
            with c2: e_t = st.selectbox("ถึง", time_slots, index=len(time_slots)-1)
            final_task = custom_task if task_cat == "อื่นๆ" else task_cat
            detail_str = f"งานพิเศษ: {final_task} ({s_t}-{e_t} น.)"
            req_type_save = "งานพิเศษ"
            
        elif "ออกเวร" in main_type:
            shift_cat = st.radio("ประเภท", ["ออกเวรดึก (พัก 8.30-10.30 น.)", "ออกเวรเย็น"])
            if "ออกเวรดึก" in shift_cat: detail_str = "ออกเวรดึก (พักเช้า 8.30-10.30 น.)"
            else: detail_str = f"ออกเวรเย็น (ห้องยา: {st.selectbox('สถานที่', ['ชั้น 1', 'ชั้นอื่นตึกพระเทพ', 'ตึกเก่า'])})"
            req_type_save = "ออกเวร"
            
        elif "แทนห้องยาอื่น" in main_type:
            replace_loc = st.text_input("สถานที่ไปแทน")
            c1, c2 = st.columns(2)
            with c1: r_s = st.selectbox("เริ่ม", time_slots, index=0)
            with c2: r_e = st.selectbox("ถึง", time_slots, index=len(time_slots)-1)
            detail_str = f"ไปแทนที่: {replace_loc} ({r_s}-{r_e} น.)"
            req_type_save, req_user_save = "แทนห้องยาอื่น", "SYSTEM_REQ"
            
        elif "แจ้งเตือน" in main_type:
            detail_str = f"📢 แจ้งเตือน: {st.text_area('ข้อความ')}"
            req_type_save = "แจ้งเตือน / ส่งเคส"
        
        if st.button("ส่งข้อมูลเข้าสู่ระบบ Cloud", type="primary"):
            add_request(req_user_save, req_type_save, req_date, detail_str)
            st.rerun()

    with tab3:
        my_reqs = [r for r in all_requests if r["user_name"] == user_info['full_name'] or (user_info['role'] == 'Admin' and r["user_name"] == "SYSTEM_REQ")]
        for r in my_reqs:
            c1, c2 = st.columns([8, 2])
            c1.write(f"📅 {r['req_date']} | **{r['req_type']}** | {r['status']}\n📝 {r['detail']}")
            if c2.button("🗑️ ยกเลิก", key=f"del_{r['id']}"):
                delete_request(r['id'])
                st.rerun()
            st.divider()

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
        st.divider()

# ==================================================================
# หน้า 3: ⚙️ รันตาราง AI (Super Admin Board แบบ Multi-Assign)
# ==================================================================
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ บอร์ดควบคุมและจัดตารางเวร AI")
    target_date = st.date_input("เลือกวันที่ต้องการจัดตาราง", key="ai_target_date")
    target_date_str = target_date.strftime("%Y-%m-%d")
    
    # ระบบ Sync ข้อมูลเข้า Dashboard อัตโนมัติเมื่อเปลี่ยนวัน
    if 'dash_date' not in st.session_state or st.session_state.dash_date != target_date_str:
        st.session_state.dash_date = target_date_str
        approved_today = [r for r in fetch_requests() if r["req_date"] == target_date_str and r["status"] == "✅ อนุมัติแล้ว"]
        pts_today = [pt for pt in st.session_state.pt_daily_db if pt["date"] == target_date_str]
        
        leaves, tasks, shifts = load_db_to_dashboard(approved_today)
        st.session_state.dash_leaves = leaves
        st.session_state.dash_tasks = tasks
        st.session_state.dash_shifts = shifts
        st.session_state.dash_pts = pts_today
        st.session_state.dash_subs = [] # เก็บรายชื่อที่แอดมินส่งไปแทน
        st.rerun() # Refresh 1 ครั้งเพื่อเคลียร์ UI

    st.markdown(f"---")
    st.subheader(f"🛠️ แผงควบคุมกำลังพลอิสระ (วันที่ {target_date.strftime('%d/%m/%Y')})")
    
    # --- 5 TABS การจัดการอิสระ ---
    tab_l, tab_pt, tab_t, tab_sh, tab_sub = st.tabs(["🏖️ ลางาน", "🏃 พาร์ทไทม์", "💼 งานพิเศษ", "🌅 ออกเวรดึก/เย็น", "🟠 ส่งไปแทน"])
    
    with tab_l:
        for idx, l in enumerate(st.session_state.dash_leaves):
            c1, c2 = st.columns([8, 2])
            c1.info(f"👤 {l['user_name']} -> {l['leave_type']} {f'({l['start']}-{l['end']} น.)' if l['leave_type'] == 'ลาป่วยฉุกเฉิน' else ''}")
            if c2.button("❌ ลบ", key=f"d_l_{idx}"):
                st.session_state.dash_leaves.pop(idx)
                st.rerun()
        with st.expander("➕ เพิ่มการลาหน้างาน"):
            add_l_u = st.selectbox("เภสัชกร", base_pharmacist_list, key="al_u")
            add_l_t = st.selectbox("ประเภทการลา", ["เต็มวัน", "ครึ่งวันเช้า (08.30-13.00)", "ครึ่งวันบ่าย (12.00-16.30)", "ลาป่วยฉุกเฉิน"], key="al_t")
            add_l_s, add_l_e = "08.30", "16.30"
            if add_l_t == "ลาป่วยฉุกเฉิน":
                cl1, cl2 = st.columns(2)
                with cl1: add_l_s = st.selectbox("เริ่ม", time_slots, index=0, key="al_s")
                with cl2: add_l_e = st.selectbox("สิ้นสุด", time_slots, index=len(time_slots)-1, key="al_e")
            if st.button("บันทึกเพิ่มการลา", type="primary"):
                st.session_state.dash_leaves.append({"user_name": add_l_u, "leave_type": add_l_t, "start": add_l_s, "end": add_l_e, "detail": "Manual Dashboard"})
                st.rerun()

    with tab_pt:
        for idx, pt in enumerate(st.session_state.dash_pts):
            c1, c2 = st.columns([8, 2])
            c1.success(f"🏃 {pt['name']} ({pt['start']}-{pt['end']} น.) | {pt['break_type']} {f'({pt['break_time']})' if pt['break_time'] else ''} | ประจำ: {pt['room']}")
            if c2.button("❌ ลบ", key=f"d_p_{idx}"):
                st.session_state.dash_pts.pop(idx)
                st.rerun()
        with st.expander("➕ เพิ่มพาร์ทไทม์หน้างาน (อิงระบบ 3 ตัวเลือกพัก)"):
            pt_name = st.text_input("ชื่อเล่น PT", key="ap_n")
            c1, c2 = st.columns(2)
            with c1: pt_start = st.selectbox("เริ่ม", time_slots, index=0, key="ap_s")
            with c2: pt_end = st.selectbox("ถึง", time_slots, index=len(time_slots)-1, key="ap_e")
            pt_b_type = st.radio("การพัก", ["พัก 1 ชั่วโมง", "พักครึ่งชั่วโมง", "ไม่พักเลย"], horizontal=True, key="ap_bt")
            pt_b_time = st.selectbox("เวลาเริ่มพัก", time_slots, key="ap_btime") if pt_b_type != "ไม่พักเลย" else None
            pt_room = st.selectbox("สถานที่", ["ทั่วไป", "ชั้น 1", "ตึกพระเทพ", "ตึกเก่า"], key="ap_r")
            if st.button("บันทึกเพิ่ม PT", type="primary"):
                if pt_name:
                    st.session_state.dash_pts.append({"name": pt_name, "start": pt_start, "end": pt_end, "break_type": pt_b_type, "break_time": pt_b_time, "room": pt_room})
                    st.rerun()

    with tab_t:
        for idx, t in enumerate(st.session_state.dash_tasks):
            c1, c2 = st.columns([8, 2])
            c1.warning(f"💼 {t['user_name']} -> {t['task_name']} ({t['start']}-{t['end']} น.)")
            if c2.button("❌ ลบ", key=f"d_t_{idx}"):
                st.session_state.dash_tasks.pop(idx)
                st.rerun()
        with st.expander("➕ เพิ่มงานพิเศษหน้างาน"):
            add_t_u = st.selectbox("เภสัชกร", base_pharmacist_list, key="at_u")
            add_t_n = st.text_input("ชื่องาน", placeholder="เช่น ประชุมหัวหน้า", key="at_n")
            c1, c2 = st.columns(2)
            with c1: add_t_s = st.selectbox("เริ่ม", time_slots, index=0, key="at_s")
            with c2: add_t_e = st.selectbox("ถึง", time_slots, index=len(time_slots)-1, key="at_e")
            if st.button("บันทึกเพิ่มงานพิเศษ", type="primary") and add_t_n:
                st.session_state.dash_tasks.append({"user_name": add_t_u, "task_name": add_t_n, "start": add_t_s, "end": add_t_e, "detail": "Manual Dashboard"})
                st.rerun()

    with tab_sh:
        for idx, sh in enumerate(st.session_state.dash_shifts):
            c1, c2 = st.columns([8, 2])
            c1.error(f"🌅 {sh['user_name']} -> {sh['shift_type']} {f'({sh['room']})' if sh['shift_type'] == 'ออกเวรเย็น' else ''}")
            if c2.button("❌ ลบ", key=f"d_sh_{idx}"):
                st.session_state.dash_shifts.pop(idx)
                st.rerun()
        with st.expander("➕ เพิ่มการออกเวรหน้างาน"):
            add_sh_u = st.selectbox("เภสัชกร", base_pharmacist_list, key="ash_u")
            add_sh_t = st.radio("ประเภท", ["ออกเวรดึก", "ออกเวรเย็น"], horizontal=True, key="ash_t")
            add_sh_r = st.selectbox("สถานที่ (กรณีออกเวรเย็น)", ["ชั้น 1", "ตึกพระเทพ", "ตึกเก่า"], key="ash_r") if add_sh_t == "ออกเวรเย็น" else "ไม่มี"
            if st.button("บันทึกเพิ่มออกเวร", type="primary"):
                st.session_state.dash_shifts.append({"user_name": add_sh_u, "shift_type": add_sh_t, "room": add_sh_r})
                st.rerun()

    with tab_sub:
        st.markdown("**คิวส่งคนไปแทนห้องยาอื่น (ระบบ Multi-Assign ส่งกี่คน/กี่ช่วงเวลาก็ได้)**")
        
        # แสดงรายการที่ส่งไปแล้ว
        for idx, s in enumerate(st.session_state.dash_subs):
            c1, c2 = st.columns([8, 2])
            c1.info(f"✔️ ส่ง **{s['user_name']}** ไป {s['task_name']} ({s['start']}-{s['end']} น.)")
            if c2.button("❌ ลบ", key=f"d_s_{idx}"):
                st.session_state.dash_subs.pop(idx)
                st.rerun()
                
        # ฟอร์มเลือกคนไปแทนเพิ่มเติมอิสระ
        with st.expander("➕ เพิ่มคนไปแทนอิสระ"):
            sub_u = st.selectbox("เภสัชกรที่จะส่งไป", base_pharmacist_list, key="sub_u")
            sub_loc = st.text_input("สถานที่ไปแทน", placeholder="เช่น OPD ชั้น 3", key="sub_loc")
            c1, c2 = st.columns(2)
            with c1: sub_s = st.selectbox("เริ่มเวลา", time_slots, index=0, key="sub_s")
            with c2: sub_e = st.selectbox("ถึงเวลา", time_slots, index=len(time_slots)-1, key="sub_e")
            
            if st.button("บันทึกส่งคนไปแทน", type="primary") and sub_loc:
                st.session_state.dash_subs.append({"user_name": sub_u, "task_name": f"แทน({sub_loc})", "start": sub_s, "end": sub_e})
                st.rerun()
                
        # โชว์ Request Alert จากระบบ
        sys_reqs = [r for r in fetch_requests() if r["req_date"] == target_date_str and r["user_name"] == "SYSTEM_REQ"]
        if sys_reqs:
            st.write("---")
            st.caption("🚨 แจ้งเตือนความต้องการคนไปแทนจากปฏิทิน (อ้างอิงเฉยๆ แอดมินสามารถไปกดเพิ่มคนในฟอร์มด้านบนได้เลย)")
            for r in sys_reqs: st.warning(r['detail'])

    st.divider()
    if st.button("🚀 ประมวลผลสมองกล AI สร้างตาราง Excel", type="primary", use_container_width=True):
        with st.spinner("🤖 AI กำลังคำนวณตำแหน่งและบล็อกเวลา..."):
            
            df_schedule = generate_ai_schedule(
                st.session_state.dash_leaves,
                st.session_state.dash_tasks,
                st.session_state.dash_shifts,
                st.session_state.dash_subs,
                st.session_state.dash_pts
            )
            
            if df_schedule is not None:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_schedule.to_excel(writer, index=False, sheet_name='ตารางเวร')
                
                st.success("🎉 AI คำนวณตารางและเจาะช่องเวลาเสร็จสมบูรณ์!")
                st.download_button(label="📥 ดาวน์โหลดไฟล์ตาราง Excel", data=output.getvalue(), file_name=f"ตารางเวร_{target_date_str}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
                st.dataframe(df_schedule, use_container_width=True)
            else:
                st.error("⚠️ AI คำนวณล้มเหลว (กำลังพลไม่เพียงพอ หรือมีการล็อกเวลาชนกันจนจัดตารางไม่ได้)")

# ==================================================================
# หน้า 4: 👥 จัดการบุคลากร & Part-time
# ==================================================================
elif page == "👥 จัดการบุคลากร & Part-time":
    st.title("👥 ระบบบริหารจัดการกำลังพล & บุคลากร Part-time")
    tab_pt1, tab_pt2 = st.tabs(["🏃 ลงทะเบียนพาร์ทไทม์ล่วงหน้า", "👥 จัดการสิทธิ์แอปพลิเคชัน"])
    
    with tab_pt1:
        st.subheader("📝 ฟอร์มข้อมูลพาร์ทไทม์ล่วงหน้า (ลงไว้เพื่อให้ไปโผล่ในปฏิทินรวม)")
        with st.container(border=True):
            pt_date = st.date_input("วันที่ PT มาทำงาน", key="pt_db_date")
            pt_name = st.text_input("ชื่อ PT", placeholder="เช่น สมชาย")
            c1, c2 = st.columns(2)
            with c1: pt_start = st.selectbox("ตั้งแต่เวลา", time_slots, index=0)
            with c2: pt_end = st.selectbox("ถึงเวลา", time_slots, index=len(time_slots)-1)
            
            pt_break_type = st.radio("การพักเบรก", ["พัก 1 ชั่วโมง", "พักครึ่งชั่วโมง", "ไม่พักเลย"], horizontal=True)
            pt_break_time = st.selectbox("ระบุเวลาเริ่มพัก", time_slots) if pt_break_type != "ไม่พักเลย" else None
            pt_room = st.selectbox("สถานที่/ภารกิจ", ["ทั่วไป (AI สลับให้)", "ประจำชั้น 1", "ประจำตึกพระเทพ", "ประจำตึกเก่า"])
            
            if st.button("➕ บันทึกพาร์ทไทม์ลงระบบ", type="primary"):
                if pt_name:
                    st.session_state.pt_daily_db.append({"date": pt_date.strftime("%Y-%m-%d"), "name": pt_name, "start": pt_start, "end": pt_end, "break_type": pt_break_type, "break_time": pt_break_time, "room": pt_room})
                    st.rerun()
                    
        for idx, pt in enumerate(st.session_state.pt_daily_db):
            c1, c2 = st.columns([8, 2])
            b_text = f"{pt['break_type']} ({pt['break_time']})" if pt['break_time'] else "ไม่พัก"
            c1.warning(f"📅 {pt['date']} | {pt['name']} | {pt['start']}-{pt['end']} | เบรก: {b_text} | {pt['room']}")
            if c2.button("🗑️ ลบ", key=f"del_pt_db_{idx}"):
                st.session_state.pt_daily_db.pop(idx)
                st.rerun()

    with tab_pt2:
        st.subheader("➕ เพิ่มพนักงานเข้าระบบ")
        with st.form("add_user_form"):
            c1, c2, c3, c4 = st.columns(4)
            with c1: new_user = st.text_input("Username")
            with c2: new_pass = st.text_input("Password")
            with c3: new_name = st.text_input("ชื่อเล่น")
            with c4: new_role = st.selectbox("สิทธิ์", ["Staff", "Admin"])
            if st.form_submit_button("บันทึก", type="primary") and new_user and new_name:
                add_user_db(new_user, new_pass, new_name, new_role)
                st.rerun()
                
        st.divider()
        st.subheader("📋 จัดการรายชื่อ")
        for u in sorted(users_db.values(), key=lambda x: x['role']):
            c1, c2, c3, c4 = st.columns([2, 3, 3, 2])
            c1.write(u['username'])
            c2.write(u['full_name'])
            with c3:
                new_r = st.selectbox("สิทธิ์", ["Staff", "Admin"], index=0 if u['role']=='Staff' else 1, key=f"role_{u['username']}", label_visibility="collapsed")
                if new_r != u['role']:
                    update_user_role(u['username'], new_r)
                    st.rerun()
            with c4:
                if u['username'] != user_info['username']: 
                    if st.button("🗑️ ลบ", key=f"del_u_{u['username']}"):
                        delete_user_db(u['username'])
                        st.rerun()
