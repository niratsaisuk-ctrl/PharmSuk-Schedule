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
# 2. ระบบจัดการข้อมูล Cloud (Supabase CRUD)
# ------------------------------------------------------------------
def fetch_users():
    if supabase:
        res = supabase.table("users").select("*").execute()
        return {user['username']: user for user in res.data}
    return {}

def add_user_db(username, password, full_name, role):
    if supabase:
        supabase.table("users").insert({"username": username, "password": password, "full_name": full_name, "role": role}).execute()

def update_user_role(username, new_role):
    if supabase:
        supabase.table("users").update({"role": new_role}).eq("username", username).execute()

def delete_user_db(username):
    if supabase:
        supabase.table("users").delete().eq("username", username).execute()

def fetch_requests():
    if supabase:
        res = supabase.table("requests").select("*").order("created_at", desc=True).execute()
        return res.data
    return []

def add_request(user_name, req_type, req_date, detail):
    if supabase:
        is_leave = "ลางาน" in req_type
        status = "⏳ รออนุมัติ" if is_leave else "✅ อนุมัติแล้ว"
        if is_leave and "ลาป่วย" in detail:
            status = "✅ อนุมัติแล้ว" 
            
        data = {
            "user_name": user_name,
            "req_type": req_type,
            "req_date": req_date.strftime("%Y-%m-%d"),
            "detail": detail,
            "status": status
        }
        supabase.table("requests").insert(data).execute()

def update_request_status(req_id, new_status):
    if supabase:
        supabase.table("requests").update({"status": new_status}).eq("id", req_id).execute()

def delete_request(req_id):
    if supabase:
        supabase.table("requests").delete().eq("id", req_id).execute()

if 'pt_daily_db' not in st.session_state:
    st.session_state.pt_daily_db = [] 

users_db = fetch_users()

core_list = ['เต้น', 'แอน', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'ริน', 'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์']
for u in users_db.values():
    if u['full_name'] not in core_list and u['role'] != 'System':
        core_list.append(u['full_name'])
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

def generate_ai_schedule(working_staff, tasks_today, pts_today):
    num_slots = 16
    main_tasks = ["จ่ายยา", "Ver CPOE", "Ver PS", "Match + C"]
    all_tasks = main_tasks + ["พัก", "จ2", "Check out", "เบิกยา", "ลง ADR", "งานพิเศษ", "ออกเวรดึก", "ว่าง"]
    
    pt_names = [f"PT-{pt['name']}" for pt in pts_today]
    all_staff = working_staff + pt_names
    
    model = cp_model.CpModel()
    x = {}
    
    for p in all_staff:
        for t in range(num_slots):
            for tsk in all_tasks:
                x[(p, t, tsk)] = model.NewBoolVar(f'x_{p}_{t}_{tsk}')
                
    for p in all_staff:
        for t in range(num_slots):
            model.AddExactlyOne(x[(p, t, tsk)] for tsk in all_tasks)
            
    fixed_assignments = {"โบ้ท": "จ2", "ปอนด์": "Check out", "ฟอร์จูน": "เบิกยา", "อ๊อฟฟี่": "ลง ADR"}
    for p, tsk in fixed_assignments.items():
        if p in all_staff:
            model.Add(x[(p, 0, tsk)] == 1)
            model.Add(x[(p, 1, tsk)] == 1)
            
    for req in tasks_today:
        p = req['user_name']
        if p not in all_staff: continue
        
        detail = req['detail']
        req_type = req.get('req_type', '')
        
        if "ออกเวรดึก" in detail:
            for t in range(4): model.Add(x[(p, t, "ออกเวรดึก")] == 1)
        elif "งานพิเศษ" in req_type or "แทนห้องยาอื่น" in req_type or "งานพิเศษ" in detail:
            times = re.findall(r'\d{2}\.\d{2}', detail)
            if len(times) >= 2:
                s_idx, e_idx = get_time_idx(times[0]), get_time_idx(times[1])
                for t in range(s_idx, min(e_idx if e_idx > 0 else 16, 16)):
                    model.Add(x[(p, t, "งานพิเศษ")] == 1)

    # 💥 กฎ Part-time โฉมใหม่ (รองรับพักครึ่งชั่วโมง และหนึ่งชั่วโมงแบบระบุเวลาเป๊ะๆ)
    for pt in pts_today:
        p_name = f"PT-{pt['name']}"
        if p_name not in all_staff: continue
        s_idx, e_idx = get_time_idx(pt['start']), get_time_idx(pt['end'])
        e_idx = e_idx if e_idx > 0 else 16
        
        for t in range(num_slots):
            if t < s_idx or t >= e_idx:
                model.Add(x[(p_name, t, "ว่าง")] == 1)
            else:
                model.Add(x[(p_name, t, "ว่าง")] == 0)
                
        b_type = pt.get('break_type', 'ไม่พักเลย')
        b_time = pt.get('break_time', None)
        
        if b_type != "ไม่พักเลย" and b_time:
            b_s_idx = get_time_idx(b_time)
            
            if b_type == "พัก 1 ชั่วโมง":
                # บังคับพัก 2 ช่องติดกัน
                if b_s_idx < 16: model.Add(x[(p_name, b_s_idx, "พัก")] == 1)
                if b_s_idx + 1 < 16: model.Add(x[(p_name, b_s_idx + 1, "พัก")] == 1)
                # ห้ามพักช่องอื่น
                for t in range(num_slots):
                    if t != b_s_idx and t != (b_s_idx + 1):
                        model.Add(x[(p_name, t, "พัก")] == 0)
                        
            elif b_type == "พักครึ่งชั่วโมง":
                # บังคับพักแค่ 1 ช่อง
                if b_s_idx < 16: model.Add(x[(p_name, b_s_idx, "พัก")] == 1)
                for t in range(num_slots):
                    if t != b_s_idx:
                        model.Add(x[(p_name, t, "พัก")] == 0)
        else:
            # ทำงานยิงยาว
            model.Add(sum(x[(p_name, t, "พัก")] for t in range(num_slots)) == 0)

    for p in all_staff:
        if p not in pt_names:
            for t in range(num_slots): model.Add(x[(p, t, "ว่าง")] == 0)
                    
    if len(all_staff) >= 6:
        for t in range(num_slots):
            model.Add(sum(x[(p, t, "จ่ายยา")] for p in all_staff) >= 2)
            model.Add(sum(x[(p, t, "Ver CPOE")] for p in all_staff) >= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 8.0
    status = solver.Solve(model)
    
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        data = []
        pt_dict = {f"PT-{pt['name']}": pt for pt in pts_today}
        for p in all_staff:
            row = {"รายชื่อเภสัชกร": p}
            for t in range(num_slots):
                assigned_task = ""
                for tsk in all_tasks:
                    if solver.Value(x[(p, t, tsk)]) == 1:
                        assigned_task = tsk
                        break
                if p in pt_dict and assigned_task not in ["พัก", "ว่าง"]:
                    room = pt_dict[p]["room"]
                    if "ทั่วไป" not in room: assigned_task = f"{assigned_task} ({room.replace('ประจำ', '')})"
                row[time_labels[t]] = assigned_task
            data.append(row)
        return pd.DataFrame(data)
    else:
        return None

# ------------------------------------------------------------------
# 4. UI Login & Sidebar
# ------------------------------------------------------------------
def login_page():
    st.markdown("<h1 style='text-align: center; color: #2E86C1;'>💊 PharmSuk</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: gray;'>ระบบจัดตารางเวรและบุคลากร ห้องยา</h4>", unsafe_allow_html=True)
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
                else:
                    st.error("❌ Username หรือ Password ไม่ถูกต้อง")

def logout():
    st.session_state.logged_in = False
    st.session_state.current_user = None
    st.rerun()

if not st.session_state.logged_in:
    login_page()
    st.stop()

user_info = st.session_state.current_user
with st.sidebar:
    st.markdown(f"### 👤 สวัสดี, คุณ {user_info['full_name']}")
    st.markdown(f"**ระดับสิทธิ์:** `{user_info['role']}`")
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
    tab1, tab2, tab3 = st.tabs(["📅 ดูปฏิทินรวมห้องยา", "📝 ฟอร์มลงข้อมูลของคุณ", "❌ จัดการ/ยกเลิกคำขอของคุณ"])
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
        st.markdown("**สถานะปฏิทิน:** <span style='color:#E74C3C; font-weight:bold;'>■ วันหยุด</span> | <span style='color:#FFC107; font-weight:bold;'>■ รออนุมัติ</span> | <span style='color:#4CAF50; font-weight:bold;'>■ อนุมัติแล้ว</span> | <span style='color:#E67E22; font-weight:bold;'>■ ต้องการคนไปแทน</span> | <span style='color:#3498DB; font-weight:bold;'>■ พาร์ทไทม์</span>", unsafe_allow_html=True)

    with tab2:
        st.subheader(f"บันทึกข้อมูลของ: {user_info['full_name']}")
        
        form_options = ["🏖️ ลางาน (พักร้อน/ป่วย/กิจ)", "💼 งานพิเศษ/อบรม/ประชุม", "🌅 ออกเวร (ดึก/เย็น)", "🔔 แจ้งเตือน / ส่งเคส"]
        if user_info['role'] == 'Admin':
            form_options.insert(3, "🟠 ส่งคนไปแทนห้องยาอื่น (ตั้ง Requirement)")
            
        main_type = st.radio("เลือกหมวดหมู่ที่ต้องการลงปฏิทิน", form_options, horizontal=True)
        st.divider()
        req_date = st.date_input("วันที่ต้องการเลือกบันทึก")
        
        req_user_save = user_info['full_name']
        
        if "ลางาน" in main_type:
            leave_cat = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาไปอบรมประเภท module", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
            leave_time = st.selectbox("ช่วงเวลาการลา", ["เต็มวัน", "ครึ่งวันเช้า", "ครึ่งวันบ่าย"])
            pt_name = st.text_input("ระบุชื่อ Part-time ที่มาแทน (ถ้ามี)")
            detail_str = f"{leave_cat} ({leave_time}){f' [PT แทน: {pt_name}]' if pt_name else ''}"
            req_type_save = f"ลางาน: {leave_cat}"
            
        elif "งานพิเศษ" in main_type:
            task_cat = st.selectbox("เลือกงานพิเศษ", ["หาหมอ", "ประชุม", "อบรม Module", "สอน Robot", "อื่นๆ"])
            custom_task = st.text_input("ระบุงานพิเศษอื่นๆ")
            c1, c2 = st.columns(2)
            with c1: start_t = st.selectbox("ตั้งแต่เวลา", time_slots, index=0)
            with c2: end_t = st.selectbox("ถึงเวลา", time_slots, index=len(time_slots)-1)
            final_task = custom_task if task_cat == "อื่นๆ" else task_cat
            detail_str = f"งานพิเศษ: {final_task} ({start_t} - {end_t} น.)"
            req_type_save = "งานพิเศษ"
            
        elif "ออกเวร" in main_type:
            shift_cat = st.radio("ประเภทการออกเวร", ["ออกเวรดึก (ล็อกเวลาพัก 8.30-10.30 น.)", "ออกเวรเย็น (ระบุห้องยาที่จะปฏิบัติงานต่อ)"])
            if "ออกเวรดึก" in shift_cat: 
                detail_str = "ออกเวรดึก (พักเช้า 8.30-10.30 น.)"
            else: 
                room_cat = st.selectbox('สถานที่อยู่เวรต่อ', ['ชั้น 1', 'ชั้นอื่นตึกพระเทพ', 'ตึกเก่า'])
                detail_str = f"ออกเวรเย็น (เวรต่อห้องยา: {room_cat})"
            req_type_save = "ออกเวร"
            
        elif "แทนห้องยาอื่น" in main_type:
            replace_loc = st.text_input("ระบุสถานที่ต้องการให้ไปแทน", placeholder="เช่น ห้องยาผู้ป่วยในชั้น 3")
            c1, c2 = st.columns(2)
            with c1: r_start = st.selectbox("ตั้งแต่เวลา ", time_slots, index=0)
            with c2: r_end = st.selectbox("ถึงเวลา ", time_slots, index=len(time_slots)-1)
            detail_str = f"ไปแทนที่: {replace_loc} ({r_start}-{r_end} น.)"
            req_type_save = "แทนห้องยาอื่น"
            req_user_save = "SYSTEM_REQ"
            
        elif "แจ้งเตือน / ส่งเคส" in main_type:
            alert_msg = st.text_area("รายละเอียดเคส หรือข้อความแจ้งเตือน")
            detail_str = f"📢 แจ้งเตือน/เคส: {alert_msg}"
            req_type_save = "แจ้งเตือน / ส่งเคส"
        
        st.divider()
        if st.button("ส่งข้อมูลเข้าสู่ระบบ Cloud", type="primary", use_container_width=True):
            add_request(req_user_save, req_type_save, req_date, detail_str)
            st.success("✅ บันทึกข้อมูลเข้าสู่ระบบแล้ว!")
            st.rerun()

    with tab3:
        st.subheader("❌ รายการคำขอของคุณในระบบ")
        my_reqs = [r for r in all_requests if r["user_name"] == user_info['full_name'] or (user_info['role'] == 'Admin' and r["user_name"] == "SYSTEM_REQ")]
        if not my_reqs:
            st.info("ไม่มีรายการคำขอในระบบขณะนี้")
        else:
            for r in my_reqs:
                c1, c2 = st.columns([7, 3])
                with c1: st.write(f"📅 **วันที่:** {r['req_date']} | **ประเภท:** {r['req_type']} | **สถานะ:** {r['status']}\n📝 รายละเอียด: {r['detail']}")
                with c2:
                    if st.button("🗑️ กดยกเลิกข้อมูล", key=f"del_{r['id']}", type="secondary"):
                        delete_request(r['id'])
                        st.rerun()
                st.divider()

# ==================================================================
# หน้า 2: อนุมัติคำขอ (เฉพาะ Admin)
# ==================================================================
elif page == "🔐 อนุมัติคำขอ (Approve)":
    st.title("🔐 จัดการคำขอลางาน (ลางานเท่านั้น)")
    all_requests = fetch_requests()
    pending_reqs = [r for r in all_requests if r["status"] == "⏳ รออนุมัติ"]
    
    if not pending_reqs: st.info("🎉 เยี่ยมมาก! ไม่มีคำขอค้างอยู่ในระบบ")
    else:
        for req in pending_reqs:
            with st.container():
                st.markdown(f"**ผู้ขอ:** {req['user_name']} | **วันที่ขอ:** {req['req_date']} | **ประเภท:** {req['req_type']}")
                st.markdown(f"📝 **รายละเอียด:** {req['detail']}")
                c1, c2, _ = st.columns([1, 1, 8])
                with c1:
                    if st.button("✅ อนุมัติให้ลา", key=f"app_{req['id']}"):
                        update_request_status(req['id'], "✅ อนุมัติแล้ว")
                        st.rerun()
                with c2:
                    if st.button("❌ ปฏิเสธ", key=f"rej_{req['id']}"):
                        update_request_status(req['id'], "❌ ไม่อนุมัติ")
                        st.rerun()
                st.divider()

# ==================================================================
# หน้า 3: ⚙️ รันตาราง AI (Admin Board)
# ==================================================================
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ แผงควบคุมและจัดเตรียมข้อมูลก่อนรันตารางเวร AI")
    
    target_date = st.date_input("เลือกวันที่ที่ต้องการวางแผนจัดตารางปฏิบัติงาน", key="ai_target_date")
    target_date_str = target_date.strftime("%Y-%m-%d")
    
    # ดักเคลียร์ข้อมูลความจำชั่วคราวเวลาเปลี่ยนวัน
    if 'ai_current_date' not in st.session_state or st.session_state.ai_current_date != target_date_str:
        st.session_state.ai_current_date = target_date_str
        st.session_state.sub_assignments = [] # ล้างคิวคนไปแทน
    
    all_requests = fetch_requests()
    approved_today = [r for r in all_requests if r["req_date"] == target_date_str and r["status"] == "✅ อนุมัติแล้ว"]
    pts_today = [pt for pt in st.session_state.pt_daily_db if pt["date"] == target_date_str]
    
    st.markdown("---")
    st.subheader(f"🛠️ บอร์ดปรับแต่งกำลังพลก่อนรัน (วันที่ {target_date.strftime('%d/%m/%Y')})")
    
    col_dash1, col_dash2 = st.columns(2)
    
    with col_dash1:
        # 💥 แก้ไขข้อ 1: ล้างความรกรุงรัง เปลี่ยนเป็นกล่อง Multiselect สะอาดตา
        st.markdown("##### 👤 1. จัดการรายชื่อคนลางาน")
        st.caption("คลิกที่กล่องเพื่อเพิ่มชื่อ หรือกด X ท้ายชื่อเพื่อลบคนลาออก (อิงข้อมูลตั้งต้นจากปฏิทิน)")
        
        init_leaves = [r["user_name"] for r in approved_today if "ลางาน" in r["req_type"]]
        final_leaves = st.multiselect("รายชื่อเภสัชกรที่ลาพักในวันนี้:", base_pharmacist_list, default=init_leaves)
                
    with col_dash2:
        st.markdown("##### 💼 2. รายชื่อพาร์ทไทม์ (PT) ของวันนี้")
        if pts_today:
            for pt in pts_today:
                st.success(f"🏃 {pt['name']} ({pt['start']}-{pt['end']} น.) | {pt['break_type']} | {pt['room']}")
        else:
            st.info("ไม่มี PT ขึ้นระบบในวันนี้")
            
        st.markdown("##### 📑 3. เพิ่มคิวงานด่วนหน้างาน")
        final_tasks = list(approved_today)
        with st.expander("➕ เพิ่มภารกิจด่วน (ไม่ต้องผ่านปฏิทิน)"):
            quick_p = st.selectbox("เลือกเภสัชกร", base_pharmacist_list)
            quick_task = st.text_input("รายละเอียด", placeholder="งานพิเศษ: ประชุม (13.00-15.00 น.)")
            if st.button("เพิ่มคิวรันหน้างาน"):
                if quick_task:
                    final_tasks.append({"user_name": quick_p, "req_type": "งานพิเศษ", "detail": quick_task})
                    st.success("เพิ่มลงบอร์ดชั่วคราวแล้ว!")
                    st.rerun()

    st.write("---")
    
    # 💥 แก้ไขข้อ 2: ระบบส่งคนไปแทน แบบ Multi-assign กดเพิ่มได้ไม่อั้น!
    st.markdown("##### 🔄 4. ระบบจัดสรรเภสัชกรไปแทนห้องยาอื่น (ดึงคิวความต้องการจากปฏิทิน)")
    sys_reqs = [r for r in all_requests if r["req_date"] == target_date_str and r["req_type"] == "แทนห้องยาอื่น" and r["user_name"] == "SYSTEM_REQ"]
    
    if sys_reqs:
        for r in sys_reqs:
            st.warning(f"🚨 ภารกิจ: {r['detail']}")
            
            # โชว์รายชื่อคนที่ถูกจับคู่ไปแล้ว
            req_subs = [s for s in st.session_state.sub_assignments if s['req_id'] == r['id']]
            for idx, sub in enumerate(req_subs):
                col_s1, col_s2 = st.columns([8, 2])
                col_s1.info(f"✔️ ส่งคุณ **{sub['user_name']}** ไปแทนเวลา {sub['start']} - {sub['end']} น.")
                if col_s2.button("❌ ลบ", key=f"del_sub_{r['id']}_{idx}"):
                    st.session_state.sub_assignments.remove(sub)
                    st.rerun()
            
            # ฟอร์มเพิ่มคนไปแทน
            with st.expander(f"➕ กดเพื่อเลือกผู้ปฏิบัติหน้าที่ไปแทนภารกิจนี้"):
                c1, c2, c3 = st.columns([2, 1, 1])
                
                # แกะเวลาแนะนำจากข้อความ
                times = re.findall(r'\d{2}\.\d{2}', r['detail'])
                def_s = time_slots.index(times[0]) if len(times) > 0 and times[0] in time_slots else 0
                def_e = time_slots.index(times[1]) if len(times) > 1 and times[1] in time_slots else len(time_slots)-1
                
                with c1: assigned_p = st.selectbox("เลือกผู้ไปแทน", base_pharmacist_list, key=f"p_{r['id']}")
                with c2: a_start = st.selectbox("เริ่ม", time_slots, index=def_s, key=f"s_{r['id']}")
                with c3: a_end = st.selectbox("สิ้นสุด", time_slots, index=def_e, key=f"e_{r['id']}")
                
                if st.button("บันทึกการส่งไปแทน", key=f"btn_{r['id']}", type="primary"):
                    st.session_state.sub_assignments.append({
                        "req_id": r['id'],
                        "user_name": assigned_p,
                        "req_type": "แทนห้องยาอื่น",
                        "detail": f"ไปแทนภารกิจ: {r['detail']} ({a_start}-{a_end} น.)",
                        "start": a_start,
                        "end": a_end
                    })
                    st.rerun()
    else:
        st.success("ไม่มีความต้องการส่งคนไปปฏิบัติงานแทนห้องยาอื่นในวันนี้")
        
    # นำคิวคนไปแทนทั้งหมด มารวมเข้ากับ Task หลักที่จะให้ AI รัน
    final_tasks.extend(st.session_state.sub_assignments)

    st.divider()
    if st.button("🚀 เริ่มรันสมองกล AI เพื่อสร้าง Excel", type="primary", use_container_width=True):
        with st.spinner("🤖 AI กำลังคำนวณการกระจายกำลังพลและจัดพักเบรก..."):
            
            working_staff = [p for p in base_pharmacist_list if p not in final_leaves]
            df_schedule = generate_ai_schedule(working_staff, final_tasks, pts_today)
            
            if df_schedule is not None:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_schedule.to_excel(writer, index=False, sheet_name='ตารางปฏิบัติงานห้องยา')
                excel_data = output.getvalue()
                
                st.success("🎉 AI คำนวณตารางเสร็จสมบูรณ์!")
                st.download_button(label="📥 ดาวน์โหลดไฟล์ตารางปฏิบัติงาน Excel", data=excel_data, file_name=f"ตารางเวรห้องยา_{target_date_str}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
                st.dataframe(df_schedule, use_container_width=True)
            else:
                st.error("⚠️ AI คำนวณล้มเหลว (คนจัดตารางไม่พอตามกฎเกณฑ์ หรือล็อกเวลาทับซ้อนกัน)")

# ==================================================================
# หน้า 4: 👥 จัดการบุคลากร & Part-time
# ==================================================================
elif page == "👥 จัดการบุคลากร & Part-time":
    st.title("👥 ระบบบริหารจัดการกำลังพล & บุคลากร Part-time")
    tab_pt1, tab_pt2 = st.tabs(["🏃 ลงเวลา/ข้อมูลพาร์ทไทม์รายวัน", "👥 จัดการรายชื่อและสิทธิ์การเข้าถึง"])
    
    with tab_pt1:
        st.subheader("📝 ฟอร์มข้อมูลบุคลากร Part-time (กำหนดเวลา & การพัก)")
        with st.container(border=True):
            pt_date = st.date_input("เลือกวันที่ PT จะมาทำงาน", key="pt_date_input")
            pt_name = st.text_input("ชื่อเล่นพาร์ทไทม์", placeholder="เช่น สมชาย")
            c1, c2 = st.columns(2)
            with c1: pt_start = st.selectbox("⏰ ตั้งแต่เวลา", time_slots, index=0)
            with c2: pt_end = st.selectbox("⏰ ถึงเวลา", time_slots, index=len(time_slots)-1)
            
            # 💥 แก้ไขข้อ 3: พาร์ทไทม์ 3 ตัวเลือกการพักเป๊ะๆ
            pt_break_type = st.radio("การพักเบรก", ["พัก 1 ชั่วโมง", "พักครึ่งชั่วโมง", "ไม่พักเลย"], horizontal=True)
            pt_break_time = None
            if pt_break_type != "ไม่พักเลย":
                pt_break_time = st.selectbox("ระบุเวลาเริ่มพัก", time_slots)
                
            pt_room = st.selectbox("สถานที่/ภารกิจ", ["ทั่วไป (AI สลับหน้าที่ให้)", "ประจำชั้น 1", "ประจำตึกพระเทพ", "ประจำตึกเก่า"])
            
            if st.button("➕ บันทึกข้อมูลพาร์ทไทม์ลงระบบ", type="primary", use_container_width=True):
                if pt_name:
                    st.session_state.pt_daily_db.append({
                        "date": pt_date.strftime("%Y-%m-%d"),
                        "name": pt_name,
                        "start": pt_start,
                        "end": pt_end,
                        "break_type": pt_break_type,
                        "break_time": pt_break_time,
                        "room": pt_room,
                        "detail": f"{pt_room} ({pt_start}-{pt_end})"
                    })
                    st.success("บันทึกข้อมูลสำเร็จ!")
                    st.rerun()
                else:
                    st.error("กรุณากรอกชื่อพาร์ทไทม์ก่อน")
                    
        st.write("---")
        st.subheader("📋 ประวัติข้อมูลพาร์ทไทม์ที่บันทึกไว้")
        if not st.session_state.pt_daily_db:
            st.info("ไม่มีข้อมูลพาร์ทไทม์ในระบบ")
        else:
            for idx, pt in enumerate(st.session_state.pt_daily_db):
                c1, c2 = st.columns([8, 2])
                b_text = f"{pt['break_type']} (เริ่ม {pt['break_time']})" if pt['break_type'] != 'ไม่พักเลย' else "ไม่พักเลย"
                with c1: st.warning(f"📅 **วันที่:** {pt['date']} | **ชื่อ:** {pt['name']} | **เวลา:** {pt['start']}-{pt['end']} | **เบรก:** {b_text} | **ตำแหน่ง:** {pt['room']}")
                with c2:
                    if st.button("🗑️ ลบ", key=f"del_pt_{idx}"):
                        st.session_state.pt_daily_db.pop(idx)
                        st.rerun()
                st.divider()

    with tab_pt2:
        st.subheader("➕ เพิ่มพนักงานเข้าระบบ (สำหรับแอดมิน)")
        with st.form("add_user_form"):
            c1, c2, c3, c4 = st.columns(4)
            with c1: new_user = st.text_input("Username (ภาษาอังกฤษ)", placeholder="เช่น mook")
            with c2: new_pass = st.text_input("Password", placeholder="เช่น 1234")
            with c3: new_name = st.text_input("ชื่อ/ชื่อเล่น", placeholder="เช่น มุก")
            with c4: new_role = st.selectbox("ระดับสิทธิ์", ["Staff", "Admin"])
            
            if st.form_submit_button("บันทึกผู้ใช้ใหม่", type="primary"):
                if new_user and new_pass and new_name:
                    add_user_db(new_user, new_pass, new_name, new_role)
                    st.success(f"เพิ่มคุณ {new_name} เข้าสู่ระบบเรียบร้อยแล้ว!")
                    st.rerun()
                else:
                    st.error("กรุณากรอกข้อมูลให้ครบถ้วน")
                    
        st.divider()
        st.subheader("📋 จัดการรายชื่อและสิทธิ์การเข้าถึง")
        
        c1, c2, c3, c4 = st.columns([2, 3, 3, 2])
        c1.markdown("**Username**")
        c2.markdown("**ชื่อบุคลากร**")
        c3.markdown("**ระดับสิทธิ์**")
        c4.markdown("**จัดการ**")
        st.write("---")
        
        for u in sorted(users_db.values(), key=lambda x: x['role']):
            c1, c2, c3, c4 = st.columns([2, 3, 3, 2])
            with c1: st.write(u['username'])
            with c2: st.write(u['full_name'])
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
                else:
                    st.write("*(ตัวคุณเอง)*")
