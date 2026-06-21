import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import holidays
from streamlit_calendar import calendar
from supabase import create_client, Client

# ------------------------------------------------------------------
# 1. ตั้งค่าหน้าเว็บ & เชื่อมต่อฐานข้อมูล Supabase
# ------------------------------------------------------------------
st.set_page_config(page_title="PharmSuk App", layout="wide", page_icon="💊")
st.markdown("<style>.block-container { padding-top: 2rem; }</style>", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

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
        # พิเศษสำหรับการลาป่วยตามเงื่อนไข: อนุมัติทันทีไม่ต้องรอ
        if "ลาป่วย" in req_type:
            data["status"] = "✅ อนุมัติแล้ว"
            
        supabase.table("requests").insert(data).execute()

def update_request_status(req_id, new_status):
    if supabase:
        supabase.table("requests").update({"status": new_status}).eq("id", req_id).execute()

# สถานะการล็อกอิน (Session State)
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

# ดึงข้อมูลจากฐานข้อมูลจริง
users_db = fetch_users()
pharmacist_list = sorted([u['full_name'] for u in users_db.values() if u['role'] != 'System'])
time_slots = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]

# ------------------------------------------------------------------
# 3. ระบบ Login & Logout
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
                user = username.lower()
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
# 4. เมนูหลัก (หลังล็อกอินสำเร็จ)
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
# หน้า: 🗓️ ปฏิทินห้องยา & ลงข้อมูล (เห็นทุกคน)
# ==================================================================
if page == "🗓️ ปฏิทินห้องยา & ลงข้อมูล":
    st.title("🗓️ ปฏิทินภาพรวม & ลงข้อมูล")
    
    # 💥 แก้ไขข้อ 1: สลับเอาปฏิทินมาเป็น Tab แรกตามคำขอ
    tab1, tab2 = st.tabs(["📅 ดูปฏิทินรวมห้องยา", "📝 ฟอร์มลงข้อมูลของคุณ"])
    
    all_requests = fetch_requests()
    
    with tab1:
        st.markdown("*(ปฏิทินดึงข้อมูลแบบ Real-time จากฐานข้อมูล)*")
        events = []
        
        # ค้นหาข้อจำกัดโควตาลาต่อวัน (เช่น นับจำนวนการลาพักร้อนที่ได้รับอนุมัติในแต่ละวัน)
        # เผื่อนำมาโชว์ตัวแจ้งเตือนบนปฏิทิน
        for req in all_requests:
            if req["status"] == "✅ อนุมัติแล้ว": 
                color = "#4CAF50" # สีเขียว
            elif req["status"] == "⏳ รออนุมัติ": 
                color = "#FFC107" # สีเหลือง
            else: 
                continue # ข้ามรายการที่ปฏิเสธ
            
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
        **ความหมายของสถานะบนปฏิทิน:** <span style='color:#FFC107; font-weight:bold;'>■ ⏳ รออนุมัติ</span> | 
        <span style='color:#4CAF50; font-weight:bold;'>■ ✅ อนุมัติแล้ว</span>
        """, unsafe_allow_html=True)

    with tab2:
        # 💥 แก้ไขข้อ 2: นำ UI ฟอร์มตัวเลือก Dropdown และวิทยุแบบละเอียดจากเวอร์ชันแรกกลับมา
        st.subheader(f"บันทึกข้อมูลของ: {user_info['full_name']}")
        
        # เมนูประเภทใหญ่
        main_type = st.radio("เลือกหมวดหมู่ที่ต้องการลงปฏิทิน", 
                             ["🏖️ ลางาน (พักร้อน/ป่วย/กิจ)", "💼 งานพิเศษ/อบรม/ประชุม", "🌅 ออกเวร (ดึก/เย็น)", "🟠 ส่งคนไปแทนห้องยาอื่น", "🔔 แจ้งเตือนอื่น ๆ"], 
                             horizontal=True)
        st.divider()
        
        with st.form("user_request_detailed_form"):
            req_date = st.date_input("วันที่ต้องการบันทึกข้อมูล")
            
            # 1. 🏖️ หมวดลางาน
            if "ลางาน" in main_type:
                leave_cat = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาไปอบรมประเภท module", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
                leave_time = st.selectbox("ช่วงเวลาการลา", ["เต็มวัน", "ครึ่งวันเช้า", "ครึ่งวันบ่าย"])
                pt_name = st.text_input("ระบุชื่อ Part-time ที่มาแทน (กรณีลาเกินโควตา 2 คน หรือตามระเบียบหัวหน้า)", placeholder="ใส่ชื่อ พาร์ทไทม์ (ถ้ามี)")
                
                # รวมข้อมูลรายละเอียดส่งบันทึก
                pt_info = f" [PT แทน: {pt_name}]" if pt_name else ""
                detail_str = f"{leave_cat} ({leave_time}){pt_info}"
                req_type_save = f"ลางาน: {leave_cat}"

            # 2. 💼 หมวดงานพิเศษ
            elif "งานพิเศษ" in main_type:
                task_cat = st.selectbox("เลือกงานพิเศษ", ["หาหมอ", "ประชุม", "อบรม Module", "สอน Robot", "อื่นๆ (ระบุในช่องด้านล่าง)"])
                custom_task = st.text_input("ระบุงานพิเศษอื่นๆ (กรณีเลือกหัวข้อ อื่นๆ)", placeholder="เช่น งานวิจัยห้องยา, เตรียมความพร้อมตรวจประเมิน")
                
                c1, c2 = st.columns(2)
                with c1: start_t = st.selectbox("ตั้งแต่เวลา", time_slots, index=0)
                with c2: end_t = st.selectbox("ถึงเวลา", time_slots, index=len(time_slots)-1)
                
                final_task_name = custom_task if task_cat == "อื่นๆ (ระบุในช่องด้านล่าง)" else task_cat
                detail_str = f"งานพิเศษ: {final_task_name} ({start_t} - {end_t} น.)"
                req_type_save = "งานพิเศษ"

            # 3. 🌅 หมวดออกเวร
            elif "ออกเวร" in main_type:
                shift_cat = st.radio("ประเภทการออกเวร", ["ออกเวรดึก (ล็อกเวลา 8.30-10.30 น.)", "ออกเวรเย็น (ระบุห้องยาที่จะอยู่ต่อ)"])
                
                if "ออกเวรดึก" in shift_cat:
                    detail_str = "ออกเวรดึก (พักเช้า 8.30-10.30 น.)"
                else:
                    room_cat = st.selectbox("สถานที่อยู่เวรต่อตอนเย็น", ["ชั้น 1", "ชั้นอื่น ตึกพระเทพ", "ตึกเก่า"])
                    detail_str = f"ออกเวรเย็น (อยู่เวรต่อห้องยา: {room_cat})"
                    
                req_type_save = "ออกเวร"

            # 4. 🟠 หมวดส่งคนไปแทนห้องยาอื่น
            elif "แทนห้องยาอื่น" in main_type:
                replace_loc = st.text_input("ระบุสถานที่/ห้องยาที่ต้องไปแทน", placeholder="เช่น ห้องยาผู้ป่วยนอกตึกเก่า")
                c1, c2 = st.columns(2)
                with c1: r_start = st.selectbox("ตั้งแต่เวลา ", time_slots, index=0)
                with c2: r_end = st.selectbox("ถึงเวลา ", time_slots, index=len(time_slots)-1)
                
                detail_str = f"ไปแทนที่: {replace_loc} ({r_start} - {r_end} น.)"
                req_type_save = "แทนห้องยาอื่น"

            # 5. 🔔 แจ้งเตือนอื่น ๆ
            else:
                alert_msg = st.text_input("ข้อความแจ้งเตือนพิเศษให้ทุกคนทราบ", placeholder="เช่น วันนี้ผู้ป่วยนัดแน่นเป็นพิเศษ 400 ราย")
                detail_str = f"📢 แจ้งเตือน: {alert_msg}"
                req_type_save = "แจ้งเตือนพิเศษ"
            
            submitted = st.form_submit_button("ส่งข้อมูลเข้าสู่ระบบ Cloud", type="primary")
            if submitted:
                add_request(user_info['full_name'], req_type_save, req_date, detail_str)
                st.success(f"✅ บันทึกข้อมูล '{detail_str}' ไปยังฐานข้อมูลเรียบร้อยแล้ว!")
                st.rerun()

# ==================================================================
# หน้า: 🔐 อนุมัติคำขอ (เฉพาะ Admin)
# ==================================================================
elif page == "🔐 อนุมัติคำขอ (Approve)":
    st.title("🔐 จัดการคำขอลางานและงานพิเศษ")
    
    all_requests = fetch_requests()
    pending_reqs = [r for r in all_requests if r["status"] == "⏳ รออนุมัติ"]
    
    if not pending_reqs:
        st.info("🎉 เยี่ยมมาก! ไม่มีคำขอลาหรืองานพิเศษค้างในระบบ")
    else:
        st.warning(f"มีคำขอรอการอนุมัติจำนวน {len(pending_reqs)} รายการ")
        for req in pending_reqs:
            with st.container():
                st.markdown(f"**ผู้ขอ:** {req['user_name']} | **วันที่เวร:** {req['req_date']} | **หมวดหมู่:** {req['req_type']}")
                st.markdown(f"📝 **รายละเอียด:** {req['detail']} *(ส่งคำขอเมื่อ: {req['created_at'][:16]})*")
                
                c1, c2, c3 = st.columns([1, 1, 8])
                with c1:
                    if st.button("✅ อนุมัติ", key=f"app_{req['id']}"):
                        update_request_status(req['id'], "✅ อนุมัติแล้ว")
                        st.success("อนุมัติสำเร็จ!")
                        st.rerun()
                with c2:
                    if st.button("❌ ปฏิเสธ", key=f"rej_{req['id']}"):
                        update_request_status(req['id'], "❌ ไม่อนุมัติ")
                        st.error("ปฏิเสธคำขอแล้ว")
                        st.rerun()
                st.divider()
                
    st.subheader("ประวัติการจัดการ 10 รายการล่าสุด")
    history_reqs = [r for r in all_requests if r["status"] != "⏳ รออนุมัติ"][:10]
    if history_reqs:
        df = pd.DataFrame(history_reqs)
        st.dataframe(df[['user_name', 'req_date', 'req_type', 'detail', 'status']], use_container_width=True)

# ==================================================================
# หน้า: ⚙️ รันตาราง AI ประจำวัน (เฉพาะ Admin)
# ==================================================================
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ AI จัดตารางปฏิบัติงาน (PharmSuk v3.0)")
    st.markdown("ระบบจะทำการดึงข้อมูลเวรที่ได้รับ **✅ อนุมัติแล้ว** จากฐานข้อมูลมาคำนวณอัตโนมัติ")
    
    target_date = st.date_input("เลือกวันที่ต้องการจัดตารางเวร")
    
    all_requests = fetch_requests()
    approved_today = [r for r in all_requests if r["req_date"] == target_date.strftime("%Y-%m-%d") and r["status"] == "✅ อนุมัติแล้ว"]
    
    st.write(f"📥 **สรุปข้อมูลและเงื่อนไขประจำวันที่ {target_date.strftime('%d/%m/%Y')}:**")
    
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
        st.success("✅ วันนี้กำลังพลอยู่ครบ 100% ไม่มีข้อมูลคนลาหรือติดภาระงานพิเศษใดๆ")
        
    st.divider()
    st.button("🚀 เริ่มรันสมองกล AI เพื่อสร้างตาราง Excel", type="primary", use_container_width=True)

# ==================================================================
# หน้า: 👥 จัดการผู้ใช้งาน (เฉพาะ Admin)
# ==================================================================
elif page == "👥 จัดการผู้ใช้งาน":
    st.title("👥 จัดการสิทธิ์และรายชื่อบุคลากร")
    df_users = pd.DataFrame(users_db.values())
    st.dataframe(df_users[['username', 'full_name', 'role']], use_container_width=True)
