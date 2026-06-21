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
# 2. ระบบจัดการข้อมูล Cloud (Supabase CRUD)
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

# 💥 แก้ไขข้อ 2: เพิ่มฟังก์ชันลบ/ยกเลิกคำขอออกจากตารางฐานข้อมูล
def delete_request(req_id):
    if supabase:
        supabase.table("requests").delete().eq("id", req_id).execute()

# 💥 แก้ไขข้อ 3: ฟังก์ชันเกี่ยวกับจัดการ Part-time รายวันเข้าฐานข้อมูล (ประยุกต์ใช้ตาราง requests หรือจำลองผ่าน state ชั่วคราว)
if 'pt_daily_db' not in st.session_state:
    st.session_state.pt_daily_db = [] # โครงสร้าง: {"date": "YYYY-MM-DD", "name": "ชื่อ PT", "detail": "ขึ้นแทนใคร/ห้องไหน"}

users_db = fetch_users()
base_pharmacist_list = ['เต้น', 'แอน', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'ริน', 'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์']
time_slots = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]
time_labels = [f"{time_slots[i]}-{time_slots[i+1]}" for i in range(16)]

# ระบบเรียกวันหยุดของประเทศไทยประจำปีปัจจุบัน
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

def generate_ai_schedule(available_staff, tasks_today):
    num_slots = 16
    main_tasks = ["จ่ายยา", "Ver CPOE", "Ver PS", "Match + C"]
    all_tasks = main_tasks + ["พัก", "จ2", "Check out", "เบิกยา", "ลง ADR", "งานพิเศษ", "ออกเวรดึก"]
    
    model = cp_model.CpModel()
    x = {}
    
    for p in available_staff:
        for t in range(num_slots):
            for tsk in all_tasks:
                x[(p, t, tsk)] = model.NewBoolVar(f'x_{p}_{t}_{tsk}')
                
    for p in available_staff:
        for t in range(num_slots):
            model.AddExactlyOne(x[(p, t, tsk)] for tsk in all_tasks)
            
    # ล็อกตำแหน่งเช้าเฉพาะบุคคล (หากพนักงานเหล่านั้นอยู่ในรายชื่อปฏิบัติงานวันนั้น)
    fixed_assignments = {"โบ้ท": "จ2", "ปอนด์": "Check out", "ฟอร์จูน": "เบิกยา", "อ๊อฟฟี่": "ลง ADR"}
    for p, tsk in fixed_assignments.items():
        if p in available_staff:
            model.Add(x[(p, 0, tsk)] == 1)
            model.Add(x[(p, 1, tsk)] == 1)
            
    # ดึงข้อมูลมาล็อกเวลาในโมเดล AI
    for req in tasks_today:
        p = req['user_name']
        if p not in available_staff: continue
        
        detail = req['detail']
        req_type = req.get('req_type', '')
        
        if "ออกเวรดึก" in detail:
            for t in range(4):
                model.Add(x[(p, t, "ออกเวรดึก")] == 1)
        elif "งานพิเศษ" in req_type or "แทนห้องยาอื่น" in req_type or "งานพิเศษ" in detail:
            times = re.findall(r'\d{2}\.\d{2}', detail)
            if len(times) >= 2:
                start_idx, end_idx = get_time_idx(times[0]), get_time_idx(times[1])
                for t in range(start_idx, min(end_idx if end_idx > 0 else 16, 16)):
                    model.Add(x[(p, t, "งานพิเศษ")] == 1)
                    
    if len(available_staff) >= 6:
        for t in range(num_slots):
            model.Add(sum(x[(p, t, "จ่ายยา")] for p in available_staff) >= 2)
            model.Add(sum(x[(p, t, "Ver CPOE")] for p in available_staff) >= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
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
# 4. หน้าจอ UI หน้า Login
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
            submit = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True)
            
            if submit:
                user = username.lower().strip()
                if user in users_db and users_db[user]['password'] == password:
                    st.session_state.logged_in = True
                    st.session_state.current_user = users_db[user]
                    st.success("ล็อกอินสำเร็จ!")
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

# เมนูบาร์ควบคุมระดับสิทธิ์
user_info = st.session_state.current_user
with st.sidebar:
    st.markdown(f"### 👤 สวัสดี, คุณ {user_info['full_name']}")
    st.markdown(f"**ระดับสิทธิ์:** `{user_info['role']}`")
    st.button("🚪 ออกจากระบบ", on_click=logout, use_container_width=True)
    st.divider()
    
    st.markdown("**📌 เมนูการทำงาน**")
    menu_options = ["🗓️ ปฏิทินห้องยา & ลงข้อมูล"]
    if user_info['role'] == 'Admin':
        menu_options.extend([
            "🔐 อนุมัติคำขอ (Approve)", 
            "⚙️ รันตาราง AI ประจำวัน", 
            "👥 จัดการบุคลากร & Part-time"
        ])
    page = st.radio("เลือกเมนู", menu_options, label_visibility="collapsed")

# ==================================================================
# หน้า 1: ปฏิทินห้องยา & ลงข้อมูล
# ==================================================================
if page == "🗓️ ปฏิทินห้องยา & ลงข้อมูล":
    st.title("🗓️ ปฏิทินภาพรวม & ลงข้อมูลบุคลากร")
    tab1, tab2, tab3 = st.tabs(["📅 ดูปฏิทินรวมห้องยา", "📝 ฟอร์มลงข้อมูลของคุณ", "❌ จัดการ/ยกเลิกคำขอของคุณ"])
    all_requests = fetch_requests()
    
    with tab1:
        st.markdown("*(ดึงข้อมูลตารางและสถานะวันลาแบบ Real-time จากระบบ Cloud)*")
        events = []
        
        # 💥 แก้ไขข้อ 1: แทรกวันหยุดนักขัตฤกษ์ของประเทศไทยลงในปฏิทินรวม
        for h_date, h_name in th_holidays.items():
            events.append({
                "title": f"🇹🇭 วันหยุด: {h_name}",
                "start": h_date.strftime("%Y-%m-%d"),
                "backgroundColor": "#E74C3C", # สีแดงสดสำหรับวันหยุดราชการ
                "allDay": True
            })
            
        for req in all_requests:
            if req["status"] == "✅ อนุมัติแล้ว": color = "#4CAF50"
            elif req["status"] == "⏳ รออนุมัติ": color = "#FFC107"
            else: continue
            events.append({"title": f"[{req['status'][0]}] {req['user_name']} - {req['detail']}", "start": req["req_date"], "backgroundColor": color})
            
        # ดึงรายชื่อพาร์ทไทม์รายวันมาโชว์บนปฏิทินด้วยเพื่อความชัดเจน
        for pt in st.session_state.pt_daily_db:
            events.append({
                "title": f"🏃 Part-time: {pt['name']} ({pt['detail']})",
                "start": pt["date"],
                "backgroundColor": "#3498DB" # สีฟ้าสำหรับพาร์ทไทม์
            })
            
        calendar(events=events, options={"headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth"}, "initialView": "dayGridMonth"})
        st.markdown("**คำอธิบายแถบสี:** <span style='color:#E74C3C; font-weight:bold;'>■ วันหยุดนักขัตฤกษ์</span> | <span style='color:#FFC107; font-weight:bold;'>■ ⏳ รออนุมัติ</span> | <span style='color:#4CAF50; font-weight:bold;'>■ ✅ อนุมัติแล้ว</span> | <span style='color:#3498DB; font-weight:bold;'>■ พาร์ทไทม์รายวัน</span>", unsafe_allow_html=True)

    with tab2:
        st.subheader(f"บันทึกข้อมูลของ: {user_info['full_name']}")
        main_type = st.radio("เลือกหมวดหมู่ที่ต้องการลงปฏิทิน", ["🏖️ ลางาน (พักร้อน/ป่วย/กิจ)", "💼 งานพิเศษ/อบรม/ประชุม", "🌅 ออกเวร (ดึก/เย็น)", "🟠 ส่งคนไปแทนห้องยาอื่น"], horizontal=True)
        st.divider()
        
        with st.form("user_request_detailed_form"):
            req_date = st.date_input("วันที่ต้องการเลือกบันทึก")
            
            if "ลางาน" in main_type:
                leave_cat = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาไปอบรมประเภท module", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
                leave_time = st.selectbox("ช่วงเวลาการลา", ["เต็มวัน", "ครึ่งวันเช้า", "ครึ่งวันบ่าย"])
                pt_name = st.text_input("ระบุชื่อ Part-time ที่มาแทน (ถ้ามี)", placeholder="ใส่ชื่อพาร์ทไทม์มาแทนคุมโควตา")
                detail_str = f"{leave_cat} ({leave_time}){f' [PT แทน: {pt_name}]' if pt_name else ''}"
                req_type_save = f"ลางาน: {leave_cat}"
            elif "งานพิเศษ" in main_type:
                task_cat = st.selectbox("เลือกงานพิเศษ", ["หาหมอ", "ประชุม", "อบรม Module", "สอน Robot", "อื่นๆ"])
                custom_task = st.text_input("ระบุงานพิเศษอื่นๆ", placeholder="ระบุภารกิจ")
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
            else:
                replace_loc = st.text_input("ระบุสถานที่ไปแทน", placeholder="ระบุ")
                c1, c2 = st.columns(2)
                with c1: r_start = st.selectbox("ตั้งแต่เวลา ", time_slots, index=0)
                with c2: r_end = st.selectbox("ถึงเวลา ", time_slots, index=len(time_slots)-1)
                detail_str = f"ไปแทนที่: {replace_loc} ({r_start} - {r_end} น.)"
                req_type_save = "แทนห้องยาอื่น"
            
            if st.form_submit_button("ส่งข้อมูลเข้าสู่ระบบ Cloud", type="primary"):
                add_request(user_info['full_name'], req_type_save, req_date, detail_str)
                st.success(f"✅ บันทึกคำขอเรียบร้อยแล้ว!")
                st.rerun()

    # 💥 แก้ไขข้อ 2: แท็บสำหรับกดยกเลิกข้อมูล/ลบข้อมูลคำขอของตนเองออกไปจากฐานข้อมูล
    with tab3:
        st.subheader("❌ รายการคำขอของคุณในระบบ")
        my_reqs = [r for r in all_requests if r["user_name"] == user_info['full_name']]
        if not my_reqs:
            st.info("ไม่มีรายการคำขอของคุณในระบบขณะนี้")
        else:
            for r in my_reqs:
                c1, c2 = st.columns([7, 3])
                with c1:
                    st.write(f"📅 **วันที่:** {r['req_date']} | **ประเภท:** {r['req_type']} | **สถานะ:** {r['status']}\n📝 รายละเอียด: {r['detail']}")
                with c2:
                    if st.button("🗑️ กดยกเลิกข้อมูลคำขอนี้", key=f"del_{r['id']}", type="secondary"):
                        delete_request(r['id'])
                        st.success("ลบรายการออกจากระบบฐานข้อมูลเรียบร้อยแล้ว!")
                        st.rerun()
                st.divider()

# ==================================================================
# หน้า 2: อนุมัติคำขอ (เฉพาะ Admin)
# ==================================================================
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

# ==================================================================
# หน้า 3: ⚙️ หน้ารันตาราง AI ประจำวัน + 💥 แก้ไขข้อ 4: บอร์ดจัดเตรียมหน้างานแบบละเอียดก่อนรัน
# ==================================================================
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ แผงควบคุมและจัดเตรียมข้อมูลก่อนรันตารางเวร AI")
    
    target_date = st.date_input("เลือกวันที่ที่ต้องการวางแผนจัดตารางปฏิบัติงาน", key="ai_target_date")
    target_date_str = target_date.strftime("%Y-%m-%d")
    
    # ดึงข้อมูลจากฐานข้อมูลหลัก
    all_requests = fetch_requests()
    approved_today = [r for r in all_requests if r["req_date"] == target_date_str and r["status"] == "✅ อนุมัติแล้ว"]
    
    # ดึงรายชื่อพาร์ทไทม์รายวันของวันนี้
    pts_today = [pt for pt in st.session_state.pt_daily_db if pt["date"] == target_date_str]
    
    st.markdown("---")
    st.subheader(f"🛠️ หน้าต่าง Dashboard ปรับแต่งกำลังพลประจำวันที่ {target_date.strftime('%d/%m/%Y')}")
    st.caption("Admin สามารถเพิ่ม/ลด รายชื่อคนลา หรือเพิ่มภารกิจหน้างานตรงนี้ได้ทันที โดยไม่มีผลกระทบกับข้อมูลปฏิทินถาวรของพนักงาน")
    
    # สร้างการจัดการรายชื่อคนลาชั่วคราวสำหรับหน้างานนี้
    init_leaves = [r["user_name"] for r in approved_today if "ลางาน" in r["req_type"]]
    
    col_dash1, col_dash2 = st.columns(2)
    
    with col_dash1:
        st.markdown("##### 👤 1. รายชื่อผู้ตรวจพบการลางาน (ติ๊กออกเพื่อยกเลิก หรือติ๊กเลือกเพิ่มคนลาหน้างาน)")
        final_leaves = []
        for p in base_pharmacist_list:
            is_checked = p in init_leaves
            if st.checkbox(f"🔴 ลาพักงาน: เภสัชกร{p}", value=is_checked, key=f"dash_leave_{p}"):
                final_leaves.append(p)
                
    with col_dash2:
        st.markdown("##### 💼 2. รายชื่อพาร์ทไทม์ (Part-time) ที่เข้ามาช่วยงานในวันนี้")
        if pts_today:
            for pt in pts_today:
                st.success(f"🏃 {pt['name']} -> รายละเอียดภารกิจ: {pt['detail']}")
        else:
            st.info("วันนี้ไม่มีรายชื่อพาร์ทไทม์ขึ้นระบบไว้ (เพิ่มได้ที่เมนู จัดการบุคลากร & Part-time ทางซ้ายมือ)")
            
        st.markdown("##### 📑 3. รายการล็อกภารกิจพิเศษหน้างานประจำวันนี้")
        final_tasks = list(approved_today)
        
        # กล่องให้แอดมินแอดภารกิจด่วนหน้างานชั่วคราว
        with st.expander("➕ เพิ่มภารกิจด่วนหน้างานด่วนชั่วคราว (ก่อนกดรัน)"):
            quick_p = st.selectbox("เลือกเภสัชกร", base_pharmacist_list, key="quick_p")
            quick_task = st.text_input("รายละเอียดงานและช่วงเวลา", placeholder="เช่น งานพิเศษ: ประชุม (13.00-15.00 น.)", key="quick_t")
            if st.button("บันทึกภารกิจด่วนลงคิวรัน", key="btn_quick_task"):
                if quick_task:
                    final_tasks.append({"user_name": quick_p, "req_type": "งานพิเศษ", "detail": quick_task})
                    st.success("เพิ่มลงคิวจัดตารางชั่วคราวเรียบร้อย!")
                    st.rerun()

    st.divider()
    
    # ปุ่มคำนวณของ AI
    if st.button("🚀 เริ่มรันสมองกล AI เพื่อประมวลผลตาราง Excel ของวันนี้", type="primary", use_container_width=True):
        with st.spinner("🤖 AI กำลังคำนวณสมการตามเงื่อนไขบอร์ดบริหารหน้างาน..."):
            
            # รวมกำลังพลหลัก หักลบคนลา แล้วบวกด้วยพาร์ทไทม์ที่เพิ่มเข้ามา
            working_staff = [p for p in base_pharmacist_list if p not in final_leaves]
            for pt in pts_today:
                working_staff.append(f"PT-{pt['name']}") # เพิ่มชื่อพาร์ทไทม์เข้าไปร่วมในกระดานรันเวร
                
            df_schedule = generate_ai_schedule(working_staff, final_tasks)
            
            if df_schedule is not None:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_schedule.to_excel(writer, index=False, sheet_name='ตารางปฏิบัติงานห้องยา')
                excel_data = output.getvalue()
                
                st.success("🎉 AI คำนวณเสร็จสมบูรณ์! ตารางนี้เป็นไปตามการปรับแต่งหน้างานของ Admin 100%")
                
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์ตารางปฏิบัติงาน Excel ประจำวัน",
                    data=excel_data,
                    file_name=f"ตารางเวรห้องยา_{target_date_str}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary"
                )
                st.dataframe(df_schedule, use_container_width=True)
            else:
                st.error("⚠️ AI คำนวณล้มเหลว: กำลังพลน้อยเกินไปหรือไม่สามารถจัดตารางให้ลงล็อกตามกฎได้ กรุณาปรับเปลี่ยนรายชื่อคนลาในบอร์ดด้านบนครับ")

# ==================================================================
# หน้า 4: 💥 แก้ไขข้อ 3: เมนูสำหรับให้ Admin จัดการรายชื่อผู้ใช้ & และจัดการข้อมูลผู้ทำงาน Part-time รายวัน
# ==================================================================
elif page == "👥 จัดการบุคลากร & Part-time":
    st.title("👥 ระบบบริหารจัดการกำลังพล & บุคลากร Part-time")
    
    tab_pt1, tab_pt2 = st.tabs(["🏃 บริหารข้อมูลผู้ปฏิบัติงาน Part-time รายวัน", "👥 รายชื่อบุคลากรประจำในระบบ"])
    
    with tab_pt1:
        st.subheader("📝 ฟอร์มลงและแก้ไขข้อมูลบุคลากร Part-time รายวัน")
        st.caption("หน้าต่างสำหรับ เต้น, มายด์ หรือหัวหน้าห้องยา ในการเพิ่มและยกเลิกรายชื่อพาร์ทไทม์ในแต่ละวัน")
        
        with st.form("pt_daily_form"):
            pt_date = st.date_input("เลือกวันที่พาร์ทไทม์จะมาปฏิบัติงาน", key="pt_date_input")
            pt_name = st.text_input("ระบุชื่อของพาร์ทไทม์", placeholder="เช่น พจนีย์, สมชาย")
            pt_detail = st.text_input("รายละเอียด/ห้องยาที่มาช่วยปฏิบัติงาน", placeholder="เช่น มาแทนคุณแอน, ประจำชั้น 1 ช่วงเย็น")
            
            if st.form_submit_button("➕ บันทึกข้อมูลพาร์ทไทม์ลงระบบ Cloud", type="primary"):
                if pt_name and pt_detail:
                    st.session_state.pt_daily_db.append({
                        "date": pt_date.strftime("%Y-%m-%d"),
                        "name": pt_name,
                        "detail": pt_detail
                    })
                    st.success(f"บันทึกข้อมูล คุณ {pt_name} ประจำวันที่ {pt_date.strftime('%d/%m/%Y')} สำเร็จ!")
                    st.rerun()
                else:
                    st.error("กรุณากรอกข้อมูลชื่อและรายละเอียดพาร์ทไทม์ให้ครบถ้วน")
                    
        st.write("---")
        st.subheader("📋 รายการประวัติข้อมูลบุคลากร Part-time ในระบบ")
        if not st.session_state.pt_daily_db:
            st.info("ปัจจุบันยังไม่มีข้อมูลการลงทะเบียนพาร์ทไทม์รายวันในระบบ")
        else:
            for idx, pt in enumerate(st.session_state.pt_daily_db):
                c1, c2 = st.columns([7, 3])
                with c1:
                    st.warning(f"📅 **วันที่มาขึ้นเวร:** {pt['date']} | **ชื่อพาร์ทไทม์:** {pt['name']} | **ภารกิจ:** {pt['detail']}")
                with c2:
                    if st.button("🗑️ ลบ/แก้ไขข้อมูล PT", key=f"del_pt_{idx}"):
                        st.session_state.pt_daily_db.pop(idx)
                        st.success("ลบข้อมูลพาร์ทไทม์เรียบร้อยแล้ว!")
                        st.rerun()
                st.divider()

    with tab_pt2:
        st.subheader("รายชื่อบุคลากรประจำที่มีสิทธิ์เข้าใช้งานระบบ PharmSuk")
        df_users = pd.DataFrame(users_db.values())
        st.dataframe(df_users[['username', 'full_name', 'role']], use_container_width=True)
