import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import holidays
from streamlit_calendar import calendar
from supabase import create_client, Client

# ------------------------------------------------------------------
# 1. ตั้งค่าหน้าเว็บ & เชื่อมต่อฐานข้อมูล Supabase (พร้อมระบบล้าง URL ป้องกัน Error)
# ------------------------------------------------------------------
st.set_page_config(page_title="PharmSuk App", layout="wide", page_icon="💊")
st.markdown("<style>.block-container { padding-top: 2rem; }</style>", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    # ดึงค่า Secrets มาแล้วใช้คำสั่งตัดช่องว่าง/เครื่องหมายทับที่อาจจะเกินมาทิ้งทันที
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
# 2. ระบบดึงข้อมูลและบันทึกข้อมูลไปยัง Supabase
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
        # เงื่อนไขพิเศษ: ถ้าเป็นลาป่วยฉุกเฉิน ให้ระบบอนุมัติอัตโนมัติทันที
        if "ลาป่วย" in detail:
            data["status"] = "✅ อนุมัติแล้ว"
            
        supabase.table("requests").insert(data).execute()

def update_request_status(req_id, new_status):
    if supabase:
        supabase.table("requests").update({"status": new_status}).eq("id", req_id).execute()

# เรียกใช้งานการจำลองและดึงข้อมูลพื้นฐาน
users_db = fetch_users()
pharmacist_list = sorted([u['full_name'] for u in users_db.values() if u['role'] != 'System'])
time_slots = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]

# ตรวจสอบสถานะล็อกอินเดิม
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

# ------------------------------------------------------------------
# 3. ระบบหน้าจอ Login & Logout
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

# ==================================================================
# 4. เมนูจัดการด้านข้าง (Sidebar Control)
# ==================================================================
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
            "👥 จัดการผู้ใช้งาน"
        ])
    
    page = st.radio("เลือกเมนู", menu_options, label_visibility="collapsed")

# ==================================================================
# หน้าจอที่ 1: 🗓️ ปฏิทินห้องยา & ลงข้อมูล (สลับเอาปฏิทินรวมขึ้นก่อน)
# ==================================================================
if page == "🗓️ ปฏิทินห้องยา & ลงข้อมูล":
    st.title("🗓️ ปฏิทินภาพรวม & ลงข้อมูลบุคลากร")
    
    tab1, tab2 = st.tabs(["📅 ดูปฏิทินรวมห้องยา", "📝 ฟอร์มลงข้อมูลของคุณ"])
    all_requests = fetch_requests()
    
    with tab1:
        st.markdown("*(ดึงข้อมูลตารางและสถานะวันลาแบบ Real-time จากระบบ Cloud)*")
        events = []
        
        for req in all_requests:
            if req["status"] == "✅ อนุมัติแล้ว": 
                color = "#4CAF50" # แถบสีเขียว
            elif req["status"] == "⏳ รออนุมัติ": 
                color = "#FFC107" # แถบสีเหลือง
            else: 
                continue # ข้ามรายการที่โดนยกเลิกหรือปฏิเสธ
            
            events.append({
                "title": f"[{req['status'][0]}] {req['user_name']} - {req['detail']}",
                "start": req["req_date"],
                "backgroundColor": color
            })
            
        calendar_options = {
            "headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth"},
            "initialView": "dayGridMonth",
        }
        calendar(events=events, options=calendar_options)
        
        st.markdown("""
        **สัญลักษณ์สีคำขอ:** <span style='color:#FFC107; font-weight:bold;'>■ ⏳ รออนุมัติ</span> | 
        <span style='color:#4CAF50; font-weight:bold;'>■ ✅ อนุมัติแล้ว</span>
        """, unsafe_allow_html=True)

    with tab2:
        st.subheader(f"บันทึกข้อมูลของ: {user_info['full_name']}")
        
        # กล่องเลือกหมวดหมู่หลักในการลงข้อมูล
        main_type = st.radio("เลือกหมวดหมู่ที่ต้องการลงปฏิทิน", 
                             ["🏖️ ลางาน (พักร้อน/ป่วย/กิจ)", "💼 งานพิเศษ/อบรม/ประชุม", "🌅 ออกเวร (ดึก/เย็น)", "🟠 ส่งคนไปแทนห้องยาอื่น", "🔔 แจ้งเตือนอื่น ๆ"], 
                             horizontal=True)
        st.divider()
        
        with st.form("user_request_detailed_form"):
            req_date = st.date_input("วันที่ต้องการเลือกบันทึก")
            
            # 1. 🏖️ ละเอียดหมวดลางาน พร้อมพาร์ทไทม์แทน
            if "ลางาน" in main_type:
                leave_cat = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาไปอบรมประเภท module", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
                leave_time = st.selectbox("ช่วงเวลาการลา", ["เต็มวัน", "ครึ่งวันเช้า", "ครึ่งวันบ่าย"])
                pt_name = st.text_input("ระบุชื่อ Part-time ที่มาแทน (กรณีลาเกินโควตา 2 คน)", placeholder="ใส่ชื่อบุคลากร พาร์ทไทม์ (ถ้ามี)")
                
                pt_info = f" [PT แทน: {pt_name}]" if pt_name else ""
                detail_str = f"{leave_cat} ({leave_time}){pt_info}"
                req_type_save = f"ลางาน: {leave_cat}"

            # 2. 💼 ละเอียดหมวดงานพิเศษและช่วงเวลาช่วงครึ่งชั่วโมง
            elif "งานพิเศษ" in main_type:
                task_cat = st.selectbox("เลือกงานพิเศษ", ["หาหมอ", "ประชุม", "อบรม Module", "สอน Robot", "อื่นๆ (ระบุในช่องด้านล่าง)"])
                custom_task = st.text_input("ระบุงานพิเศษอื่นๆ (กรณีเลือกหัวข้อ อื่นๆ)", placeholder="เช่น ทำวิจัยฝ่ายเภสัชกรรม")
                
                c1, c2 = st.columns(2)
                with c1: start_t = st.selectbox("ตั้งแต่เวลา", time_slots, index=0)
                with c2: end_t = st.selectbox("ถึงเวลา", time_slots, index=len(time_slots)-1)
                
                final_task_name = custom_task if task_cat == "อื่นๆ (ระบุในช่องด้านล่าง)" else task_cat
                detail_str = f"งานพิเศษ: {final_task_name} ({start_t} - {end_t} น.)"
                req_type_save = "งานพิเศษ"

            # 3. 🌅 ละเอียดหมวดออกเวร ดึก/เย็น และเลือกห้องต่อเวร
            elif "ออกเวร" in main_type:
                shift_cat = st.radio("ประเภทการออกเวร", ["ออกเวรดึก (ล็อกเวลาพัก 8.30-10.30 น.)", "ออกเวรเย็น (ระบุห้องยาที่จะปฏิบัติงานต่อ)"])
                
                if "ออกเวรดึก" in shift_cat:
                    detail_str = "ออกเวรดึก (พักเช้า 8.30-10.30 น.)"
                else:
                    room_cat = st.selectbox("สถานที่อยู่เวรต่อตอนเย็น", ["ชั้น 1", "ชั้นอื่น ตึกพระเทพ", "ตึกเก่า"])
                    detail_str = f"ออกเวรเย็น (เวรต่อห้องยา: {room_cat})"
                    
                req_type_save = "ออกเวร"

            # 4. 🟠 ละเอียดหมวดส่งคนไปแทนห้องยาอื่น
            elif "แทนห้องยาอื่น" in main_type:
                replace_loc = st.text_input("ระบุสถานที่/ห้องยาที่ต้องไปปฏิบัติงานแทน", placeholder="เช่น ห้องยาผู้ป่วยในชั้น 3")
                c1, c2 = st.columns(2)
                with c1: r_start = st.selectbox("ตั้งแต่เวลา ", time_slots, index=0)
                with c2: r_end = st.selectbox("ถึงเวลา ", time_slots, index=len(time_slots)-1)
                
                detail_str = f"ไปแทนที่: {replace_loc} ({r_start} - {r_end} น.)"
                req_type_save = "แทนห้องยาอื่น"

            # 5. 🔔 แจ้งเตือนทั่วไป
            else:
                alert_msg = st.text_input("ข้อความแจ้งเตือนพิเศษให้ทุกคนทราบในระบบ", placeholder="เช่น วันนี้คลังยาใหญ่เข้าตรวจเช็กระบบ")
                detail_str = f"📢 แจ้งเตือน: {alert_msg}"
                req_type_save = "แจ้งเตือนพิเศษ"
            
            submitted = st.form_submit_button("ส่งข้อมูลเข้าสู่ระบบ Cloud", type="primary")
            if submitted:
                add_request(user_info['full_name'], req_type_save, req_date, detail_str)
                st.success(f"✅ บันทึกคำขอเรียบร้อยแล้ว!")
                st.rerun()

# ==================================================================
# หน้าจอที่ 2: 🔐 อนุมัติคำขอ (เฉพาะ Admin/หัวหน้าห้องยา เข้าได้)
# ==================================================================
elif page == "🔐 อนุมัติคำขอ (Approve)":
    st.title("🔐 จัดการคำขอลางานและงานพิเศษบุคลากร")
    
    all_requests = fetch_requests()
    pending_reqs = [r for r in all_requests if r["status"] == "⏳ รออนุมัติ"]
    
    if not pending_reqs:
        st.info("🎉 เยี่ยมมาก! ไม่มีคำขอลางานหรืองานพิเศษค้างอยู่ในระบบ")
    else:
        st.warning(f"มีคำขอรอการตรวจสอบและอนุมัติจำนวน {len(pending_reqs)} รายการ")
        for req in pending_reqs:
            with st.container():
                st.markdown(f"**ผู้ขอ:** {req['user_name']} | **วันที่ขอเวร:** {req['req_date']} | **ประเภทหมวดหมู่:** {req['req_type']}")
                st.markdown(f"📝 **รายละเอียดที่บันทึกมา:** {req['detail']} *(ส่งเข้าระบบเมื่อ: {req['created_at'][:16]})*")
                
                c1, c2, c3 = st.columns([1, 1, 8])
                with c1:
                    if st.button("✅ อนุมัติ", key=f"app_{req['id']}"):
                        update_request_status(req['id'], "✅ อนุมัติแล้ว")
                        st.success("ทำรายการอนุมัติสำเร็จ!")
                        st.rerun()
                with c2:
                    if st.button("❌ ปฏิเสธ", key=f"rej_{req['id']}"):
                        update_request_status(req['id'], "❌ ไม่อนุมัติ")
                        st.error("ปฏิเสธคำขอนี้เรียบร้อย")
                        st.rerun()
                st.divider()
                
    st.subheader("ประวัติการจัดการ 10 รายการล่าสุด")
    history_reqs = [r for r in all_requests if r["status"] != "⏳ รออนุมัติ"][:10]
    if history_reqs:
        df = pd.DataFrame(history_reqs)
        st.dataframe(df[['user_name', 'req_date', 'req_type', 'detail', 'status']], use_container_width=True)

# ==================================================================
# หน้าจอที่ 3: ⚙️ รันตาราง AI ประจำวัน (เฉพาะ Admin/หัวหน้าห้องยา เข้าได้)
# ==================================================================
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ AI จัดตารางปฏิบัติงานประจำวันห้องยา")
    st.markdown("ระบบจะทําการตัดชื่อผู้ลาและจัดตำแหน่งงานพิเศษโดยดึงข้อมูลที่ได้รับ **✅ อนุมัติแล้ว** มาคำนวณ")
    
    target_date = st.date_input("เลือกวันที่ที่ต้องการจัดตารางปฏิบัติงาน")
    
    all_requests = fetch_requests()
    approved_today = [r for r in all_requests if r["req_date"] == target_date.strftime("%Y-%m-%d") and r["status"] == "✅ อนุมัติแล้ว"]
    
    st.write(f"📥 **สรุปเงื่อนไขและข้อมูลที่ตรวจพบประจำวันที่ {target_date.strftime('%d/%m/%Y')}:**")
    
    leaves_today = []
    tasks_today = []
    
    if approved_today:
        for r in approved_today:
            st.info(f"👤 {r['user_name']} -> {r['detail']}")
            if "ลางาน" in r['req_type']:
                leaves_today.append(r['user_name'])
            else:
                tasks_today.append(r)
    else:
        st.success("✅ วันนี้ไม่มีกำลังพลลางานหรือติดภารกิจพิเศษ (เภสัชกรสแตนด์บายครบ 100%)")
        
    st.divider()
    st.button("🚀 เริ่มรันสมองกล AI เพื่อประมวลผลตาราง Excel", type="primary", use_container_width=True)

# ==================================================================
# หน้าจอที่ 4: 👥 จัดการผู้ใช้งาน (เฉพาะ Admin/หัวหน้าห้องยา เข้าได้)
# ==================================================================
elif page == "👥 จัดการผู้ใช้งาน":
    st.title("👥 ระบบจัดการสิทธิ์และรายชื่อบุคลากรห้องยา")
    st.markdown("รายชื่อเภสัชกรที่มีสิทธิ์เข้าใช้งานระบบแอปพลิเคชันขณะนี้")
    
    df_users = pd.DataFrame(users_db.values())
    st.dataframe(df_users[['username', 'full_name', 'role']], use_container_width=True)
