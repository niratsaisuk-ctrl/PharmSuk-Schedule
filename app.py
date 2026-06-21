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
    clean_url = raw_url.strip().rstrip('/')
    clean_key = raw_key.strip()
    return create_client(clean_url, clean_key)

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

def fetch_requests():
    if supabase:
        res = supabase.table("requests").select("*").order("created_at", desc=True).execute()
        return res.data
    return []

def add_request(user_name, req_type, req_date, detail):
    if supabase:
        data = {
            "user_name": user_name,
            "req_type": req_type,
            "req_date": req_date.strftime("%Y-%m-%d"),
            "detail": detail,
            "status": "⏳ รออนุมัติ"
        }
        if "ลาป่วย" in detail:
            data["status"] = "✅ อนุมัติแล้ว"
        supabase.table("requests").insert(data).execute()

def update_request_status(req_id, new_status):
    if supabase:
        supabase.table("requests").update({"status": new_status}).eq("id", req_id).execute()

users_db = fetch_users()
pharmacist_list = ['เต้น', 'แอน', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'ริน', 'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์']
time_slots = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]
time_labels = [f"{time_slots[i]}-{time_slots[i+1]}" for i in range(16)] # สำหรับโชว์บนหัว Excel

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

# ------------------------------------------------------------------
# 3. AI จัดตารางเวร (OR-Tools)
# ------------------------------------------------------------------
def get_time_idx(t_str):
    mapping = {t_str: idx for idx, t_str in enumerate(time_slots[:16])}
    return mapping.get(t_str, 0)

def generate_ai_schedule(available_staff, tasks_today):
    num_slots = 16
    main_tasks = ["จ่ายยา", "Ver CPOE", "Ver PS", "Match + C"]
    all_tasks = main_tasks + ["พัก", "จ2", "Check out", "เบิกยา", "ลง ADR", "งานพิเศษ", "ออกเวรดึก"]
    
    model = cp_model.CpModel()
    x = {}
    
    # ประกาศตัวแปรความน่าจะเป็น
    for p in available_staff:
        for t in range(num_slots):
            for tsk in all_tasks:
                x[(p, t, tsk)] = model.NewBoolVar(f'x_{p}_{t}_{tsk}')
                
    # กฎ 1: 1 คน ทำ 1 หน้าที่ ในแต่ละช่วงเวลา
    for p in available_staff:
        for t in range(num_slots):
            model.AddExactlyOne(x[(p, t, tsk)] for tsk in all_tasks)
            
    # กฎ 2: ล็อกหน้าที้เฉพาะกิจช่วงเช้า (8.30-9.30 น. = slot 0 และ 1)
    fixed_assignments = {"โบ้ท": "จ2", "ปอนด์": "Check out", "ฟอร์จูน": "เบิกยา", "อ๊อฟฟี่": "ลง ADR"}
    for p, tsk in fixed_assignments.items():
        if p in available_staff:
            model.Add(x[(p, 0, tsk)] == 1)
            model.Add(x[(p, 1, tsk)] == 1)
            
    # กฎ 3: ดึงข้อมูลที่ Approve แล้ว (ออกเวร, งานพิเศษ) มาล็อกเวลาใน AI
    for req in tasks_today:
        p = req['user_name']
        if p not in available_staff: continue
        
        detail = req['detail']
        req_type = req['req_type']
        
        if "ออกเวรดึก" in detail:
            # พักเช้า 8.30 - 10.30 (slot 0 ถึง 3)
            for t in range(4):
                model.Add(x[(p, t, "ออกเวรดึก")] == 1)
                
        elif "งานพิเศษ" in req_type or "แทนห้องยาอื่น" in req_type:
            # ค้นหาเวลา เช่น 13.00 - 15.00
            times = re.findall(r'\d{2}\.\d{2}', detail)
            if len(times) >= 2:
                start_idx, end_idx = get_time_idx(times[0]), get_time_idx(times[1])
                # ถ้าเป็นเวลา 16.30 จะเกิน index ให้ cap ไว้ที่ 16
                for t in range(start_idx, min(end_idx if end_idx > 0 else 16, 16)):
                    model.Add(x[(p, t, "งานพิเศษ")] == 1)
                    
    # กฎ 4: บังคับขั้นต่ำให้มีคนอยู่จุดจ่ายยาและ Ver เสมอ (ป้องกัน AI ให้ทุกคนไปพักพร้อมกัน)
    if len(available_staff) >= 10:
        for t in range(num_slots):
            model.Add(sum(x[(p, t, "จ่ายยา")] for p in available_staff) >= 2)
            model.Add(sum(x[(p, t, "Ver CPOE")] for p in available_staff) >= 2)
            model.Add(sum(x[(p, t, "Ver PS")] for p in available_staff) >= 1)

    # รัน AI
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0 # จำกัดเวลาคิดไม่เกิน 10 วิ
    status = solver.Solve(model)
    
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        data = []
        for p in available_staff:
            row = {"รายชื่อเภสัชกร": p}
            for t in range(num_slots):
                assigned_task = ""
                for tsk in all_tasks:
                    if solver.Value(x[(p, t, tsk)]) == 1:
                        assigned_task = tsk
                        break
                row[time_labels[t]] = assigned_task
            data.append(row)
        return pd.DataFrame(data)
    else:
        return None

# ------------------------------------------------------------------
# 4. หน้าจอ UI
# ------------------------------------------------------------------
def login_page():
    st.markdown("<h1 style='text-align: center; color: #2E86C1;'>💊 PharmSuk</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: gray;'>ระบบจัดตารางเวรและบุคลากร ห้องยา</h4>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align: center; font-size:12px; color: gray;'>Database: {db_status}</p>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username (ชื่อเล่นภาษาอังกฤษ)")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True)
            
            if submit:
                user = username.lower().strip()
                if user in users_db and users_db[user]['password'] == password:
                    st.session_state.logged_in = True
                    st.session_state.current_user = users_db[user]
                    st.success("ล็อกอินสำเร็จ! กำลังพาท่านเข้าสู่ระบบ...")
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

# เมนูด้านซ้าย
user_info = st.session_state.current_user
with st.sidebar:
    st.markdown(f"### 👤 สวัสดี, คุณ {user_info['full_name']}")
    st.markdown(f"**ระดับสิทธิ์:** `{user_info['role']}`")
    st.button("🚪 ออกจากระบบ", on_click=logout, use_container_width=True)
    st.divider()
    
    st.markdown("**📌 เมนูการทำงาน**")
    menu_options = ["🗓️ ปฏิทินห้องยา & ลงข้อมูล"]
    if user_info['role'] == 'Admin':
        menu_options.extend(["🔐 อนุมัติคำขอ (Approve)", "⚙️ รันตาราง AI ประจำวัน", "👥 จัดการผู้ใช้งาน"])
    page = st.radio("เลือกเมนู", menu_options, label_visibility="collapsed")

# ----------------- หน้า 1: ปฏิทิน & ฟอร์ม -----------------
if page == "🗓️ ปฏิทินห้องยา & ลงข้อมูล":
    st.title("🗓️ ปฏิทินภาพรวม & ลงข้อมูลบุคลากร")
    tab1, tab2 = st.tabs(["📅 ดูปฏิทินรวมห้องยา", "📝 ฟอร์มลงข้อมูลของคุณ"])
    all_requests = fetch_requests()
    
    with tab1:
        events = []
        for req in all_requests:
            if req["status"] == "✅ อนุมัติแล้ว": color = "#4CAF50"
            elif req["status"] == "⏳ รออนุมัติ": color = "#FFC107"
            else: continue
            
            events.append({"title": f"[{req['status'][0]}] {req['user_name']} - {req['detail']}", "start": req["req_date"], "backgroundColor": color})
            
        calendar(events=events, options={"headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth"}, "initialView": "dayGridMonth"})
        st.markdown("**สัญลักษณ์:** <span style='color:#FFC107; font-weight:bold;'>■ ⏳ รออนุมัติ</span> | <span style='color:#4CAF50; font-weight:bold;'>■ ✅ อนุมัติแล้ว</span>", unsafe_allow_html=True)

    with tab2:
        st.subheader(f"บันทึกข้อมูลของ: {user_info['full_name']}")
        main_type = st.radio("เลือกหมวดหมู่ที่ต้องการลงปฏิทิน", ["🏖️ ลางาน (พักร้อน/ป่วย/กิจ)", "💼 งานพิเศษ/อบรม/ประชุม", "🌅 ออกเวร (ดึก/เย็น)", "🟠 ส่งคนไปแทนห้องยาอื่น", "🔔 แจ้งเตือนอื่น ๆ"], horizontal=True)
        st.divider()
        
        with st.form("user_request_detailed_form"):
            req_date = st.date_input("วันที่ต้องการเลือกบันทึก")
            
            if "ลางาน" in main_type:
                leave_cat = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาไปอบรมประเภท module", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
                leave_time = st.selectbox("ช่วงเวลาการลา", ["เต็มวัน", "ครึ่งวันเช้า", "ครึ่งวันบ่าย"])
                pt_name = st.text_input("ระบุชื่อ Part-time ที่มาแทน (ถ้ามี)", placeholder="ใส่ชื่อบุคลากร พาร์ทไทม์")
                detail_str = f"{leave_cat} ({leave_time}){f' [PT แทน: {pt_name}]' if pt_name else ''}"
                req_type_save = f"ลางาน: {leave_cat}"
            elif "งานพิเศษ" in main_type:
                task_cat = st.selectbox("เลือกงานพิเศษ", ["หาหมอ", "ประชุม", "อบรม Module", "สอน Robot", "อื่นๆ"])
                custom_task = st.text_input("ระบุงานพิเศษอื่นๆ", placeholder="ระบุ")
                c1, c2 = st.columns(2)
                with c1: start_t = st.selectbox("ตั้งแต่เวลา", time_slots, index=0)
                with c2: end_t = st.selectbox("ถึงเวลา", time_slots, index=len(time_slots)-1)
                final_task = custom_task if task_cat == "อื่นๆ" else task_cat
                detail_str = f"งานพิเศษ: {final_task} ({start_t} - {end_t} น.)"
                req_type_save = "งานพิเศษ"
            elif "ออกเวร" in main_type:
                shift_cat = st.radio("ประเภทการออกเวร", ["ออกเวรดึก (ล็อกเวลาพัก 8.30-10.30 น.)", "ออกเวรเย็น (ระบุห้องยาที่จะปฏิบัติงานต่อ)"])
                if "ออกเวรดึก" in shift_cat: detail_str = "ออกเวรดึก (พักเช้า 8.30-10.30 น.)"
                else: detail_str = f"ออกเวรเย็น (เวรต่อห้องยา: {st.selectbox('สถานที่อยู่เวรต่อ', ['ชั้น 1', 'ตึกพระเทพ', 'ตึกเก่า'])})"
                req_type_save = "ออกเวร"
            elif "แทนห้องยาอื่น" in main_type:
                replace_loc = st.text_input("ระบุสถานที่ไปแทน", placeholder="ระบุ")
                c1, c2 = st.columns(2)
                with c1: r_start = st.selectbox("ตั้งแต่เวลา ", time_slots, index=0)
                with c2: r_end = st.selectbox("ถึงเวลา ", time_slots, index=len(time_slots)-1)
                detail_str = f"ไปแทนที่: {replace_loc} ({r_start} - {r_end} น.)"
                req_type_save = "แทนห้องยาอื่น"
            else:
                detail_str = f"📢 แจ้งเตือน: {st.text_input('ข้อความแจ้งเตือนพิเศษ')}"
                req_type_save = "แจ้งเตือนพิเศษ"
            
            if st.form_submit_button("ส่งข้อมูลเข้าสู่ระบบ Cloud", type="primary"):
                add_request(user_info['full_name'], req_type_save, req_date, detail_str)
                st.success(f"✅ บันทึกคำขอเรียบร้อยแล้ว!")
                st.rerun()

# ----------------- หน้า 2: อนุมัติ -----------------
elif page == "🔐 อนุมัติคำขอ (Approve)":
    st.title("🔐 จัดการคำขอลางานและงานพิเศษบุคลากร")
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
                    if st.button("✅ อนุมัติ", key=f"app_{req['id']}"):
                        update_request_status(req['id'], "✅ อนุมัติแล้ว")
                        st.rerun()
                with c2:
                    if st.button("❌ ปฏิเสธ", key=f"rej_{req['id']}"):
                        update_request_status(req['id'], "❌ ไม่อนุมัติ")
                        st.rerun()
                st.divider()

# ----------------- หน้า 3: AI จัดตาราง -----------------
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ AI จัดตารางปฏิบัติงานประจำวันห้องยา")
    st.markdown("ระบบจะดึงข้อมูลที่ได้รับ **✅ อนุมัติแล้ว** จากฐานข้อมูลมาหักชื่อคนลาและจัดตำแหน่งงานพิเศษให้อัตโนมัติ")
    
    target_date = st.date_input("เลือกวันที่ที่ต้องการจัดตารางปฏิบัติงาน")
    all_requests = fetch_requests()
    approved_today = [r for r in all_requests if r["req_date"] == target_date.strftime("%Y-%m-%d") and r["status"] == "✅ อนุมัติแล้ว"]
    
    st.write(f"📥 **สรุปข้อมูลกำลังพลประจำวันที่ {target_date.strftime('%d/%m/%Y')}:**")
    leaves_today = []
    tasks_today = []
    
    if approved_today:
        for r in approved_today:
            st.info(f"👤 {r['user_name']} -> {r['detail']}")
            if "ลางาน" in r['req_type']: leaves_today.append(r['user_name'])
            else: tasks_today.append(r)
    else:
        st.success("✅ วันนี้กำลังพลครบ 100% ไม่มีข้อมูลคนลาหรือติดภารกิจ")
        
    st.divider()
    
    if st.button("🚀 เริ่มรันสมองกล AI เพื่อประมวลผลตาราง Excel", type="primary", use_container_width=True):
        with st.spinner("🤖 AI กำลังคำนวณสมการเพื่อหาตารางที่ดีที่สุด... (รอประมาณ 2-5 วินาที)"):
            
            # หักชื่อคนลาออกจากรายชื่อ 19 คน
            available_staff = [p for p in pharmacist_list if p not in leaves_today]
            
            # โยนเข้าสมองกล OR-Tools
            df_schedule = generate_ai_schedule(available_staff, tasks_today)
            
            if df_schedule is not None:
                # แปลงเป็น Excel ในอากาศ (Memory)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_schedule.to_excel(writer, index=False, sheet_name='ตารางเวรประจำวัน')
                excel_data = output.getvalue()
                
                st.success("🎉 AI คำนวณตารางเสร็จสมบูรณ์! ตารางนี้ไร้ข้อขัดแย้งและถูกตามกฎ 100%")
                
                # โชว์ปุ่มดาวน์โหลด
                st.download_button(
                    label="📥 คลิกที่นี่เพื่อดาวน์โหลดตาราง Excel ไปใช้งาน",
                    data=excel_data,
                    file_name=f"Schedule_PharmSuk_{target_date.strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
                
                st.dataframe(df_schedule, use_container_width=True)
            else:
                st.error("⚠️ AI หาทางออกไม่เจอ (อาจจะลางานกันเยอะเกินไปจนคนจัดตารางไม่พอ) กรุณาตรวจสอบกำลังพลอีกครั้งครับ")

# ----------------- หน้า 4: จัดการผู้ใช้งาน -----------------
elif page == "👥 จัดการผู้ใช้งาน":
    st.title("👥 ระบบจัดการสิทธิ์และรายชื่อบุคลากรห้องยา")
    st.dataframe(pd.DataFrame(users_db.values())[['username', 'full_name', 'role']], use_container_width=True)
