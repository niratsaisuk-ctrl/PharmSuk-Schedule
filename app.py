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

from supabase import create_client, Client
from postgrest import APIError # เพิ่มบรรทัดนี้

@st.cache_resource
def init_connection():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    # เพิ่ม options เข้าไปเพื่อให้มั่นใจว่าชี้ไปที่ public api
    return create_client(url, key)

try:
    supabase: Client = init_connection()
    db_status = "🟢 เชื่อมต่อฐานข้อมูลสำเร็จ"
except Exception as e:
    supabase = None
    db_status = f"🔴 เชื่อมต่อล้มเหลว: {e}"

# ------------------------------------------------------------------
# 2. ระบบดึงข้อมูลและบันทึกข้อมูล
# ------------------------------------------------------------------
def fetch_users():
    if supabase:
        res = supabase.table("users").select("*").execute()
        # แปลงเป็น dict ให้ใช้งานง่าย { 'username': {ข้อมูล} }
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
        supabase.table("requests").insert(data).execute()

def update_request_status(req_id, new_status):
    if supabase:
        supabase.table("requests").update({"status": new_status}).eq("id", req_id).execute()

# สถานะการล็อกอิน (Session State)
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

# ดึงข้อมูลมาเก็บไว้ในตัวแปร
users_db = fetch_users()
pharmacist_list = [u['full_name'] for u in users_db.values() if u['role'] != 'System']
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
    
    tab1, tab2 = st.tabs(["📝 ฟอร์มลงข้อมูลของคุณ", "📅 ดูปฏิทินรวมห้องยา"])
    
    with tab1:
        st.subheader(f"บันทึกข้อมูลของ: {user_info['full_name']}")
        req_type = st.selectbox("เลือกประเภทที่ต้องการแจ้ง", ["ลางาน (พักร้อน/ป่วย/กิจ)", "งานพิเศษ/อบรม/ประชุม", "ออกเวร (ดึก/เย็น)"])
        
        with st.form("user_request_form"):
            req_date = st.date_input("วันที่")
            req_detail = st.text_input("รายละเอียด (เช่น ลาครึ่งเช้า, สอน Robot 13.00-15.00)")
            
            submitted = st.form_submit_button("ส่งข้อมูลเข้าสู่ระบบ", type="primary")
            if submitted:
                add_request(user_info['full_name'], req_type, req_date, req_detail)
                st.success(f"✅ บันทึกคำขอเรียบร้อยแล้ว!")
                st.rerun() # รีเฟรชหน้าเพื่ออัปเดตข้อมูล

    with tab2:
        st.markdown("*(ปฏิทินดึงข้อมูลแบบ Real-time จากฐานข้อมูล)*")
        events = []
        all_requests = fetch_requests()
        
        for req in all_requests:
            if req["status"] == "✅ อนุมัติแล้ว": color = "#4CAF50" # สีเขียว
            elif req["status"] == "⏳ รออนุมัติ": color = "#FFC107" # สีเหลือง
            else: continue # ข้ามคำขอที่ถูกปฏิเสธ
            
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

# ==================================================================
# หน้า: 🔐 อนุมัติคำขอ (เฉพาะ Admin)
# ==================================================================
elif page == "🔐 อนุมัติคำขอ (Approve)":
    st.title("🔐 จัดการคำขอลางานและงานพิเศษ")
    
    all_requests = fetch_requests()
    pending_reqs = [r for r in all_requests if r["status"] == "⏳ รออนุมัติ"]
    
    if not pending_reqs:
        st.info("🎉 เยี่ยมมาก! ไม่มีคำขอค้างในระบบ")
    else:
        st.warning(f"มีคำขอรอการอนุมัติจำนวน {len(pending_reqs)} รายการ")
        for req in pending_reqs:
            with st.container():
                st.markdown(f"**ผู้ขอ:** {req['user_name']} | **วันที่:** {req['req_date']} | **ประเภท:** {req['req_type']}")
                st.markdown(f"📝 **รายละเอียด:** {req['detail']} (ส่งเมื่อ: {req['created_at'][:16]})")
                
                c1, c2, c3 = st.columns([1, 1, 8])
                with c1:
                    if st.button("✅ อนุมัติ", key=f"app_{req['id']}"):
                        update_request_status(req['id'], "✅ อนุมัติแล้ว")
                        st.rerun()
                with c2:
                    if st.button("❌ ปฏิเสธ", key=f"rej_{req['id']}"):
                        update_request_status(req['id'], "❌ ไม่อนุมัติ")
                        st.rerun()
                st.divider()
                
    st.subheader("ประวัติการจัดการล่าสุด")
    history_reqs = [r for r in all_requests if r["status"] != "⏳ รออนุมัติ"][:10] # โชว์ 10 อันดับล่าสุด
    if history_reqs:
        df = pd.DataFrame(history_reqs)
        st.dataframe(df[['user_name', 'req_date', 'req_type', 'detail', 'status']], use_container_width=True)

# ==================================================================
# หน้า: ⚙️ รันตาราง AI ประจำวัน (เฉพาะ Admin)
# ==================================================================
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ AI จัดตารางปฏิบัติงาน")
    st.markdown("ระบบจะดึงข้อมูล **✅ อนุมัติแล้ว** จากฐานข้อมูลมาจัดตารางโดยอัตโนมัติ")
    
    target_date = st.date_input("เลือกวันที่ต้องการรันตาราง")
    
    all_requests = fetch_requests()
    approved_today = [r for r in all_requests if r["req_date"] == target_date.strftime("%Y-%m-%d") and r["status"] == "✅ อนุมัติแล้ว"]
    
    st.write(f"📥 **ข้อมูลที่ AI มองเห็นในวันที่ {target_date.strftime('%Y-%m-%d')}:**")
    if approved_today:
        for r in approved_today:
            st.code(f"{r['user_name']} -> {r['req_type']} ({r['detail']})")
    else:
        st.info("ไม่มีข้อมูลลาหรืองานพิเศษในวันนี้ (รันตารางด้วยรายชื่อเต็ม)")
        
    st.button("🚀 เริ่มรัน AI (จำลอง)", type="primary", use_container_width=True)

# ==================================================================
# หน้า: 👥 จัดการผู้ใช้งาน (เฉพาะ Admin)
# ==================================================================
elif page == "👥 จัดการผู้ใช้งาน":
    st.title("👥 จัดการสิทธิ์และรายชื่อบุคลากร")
    
    df_users = pd.DataFrame(users_db.values())
    st.dataframe(df_users[['username', 'full_name', 'role']], use_container_width=True)
    st.info("💡 ในอนาคตคุณจะสามารถแก้ไขสิทธิ์ หรือเปลี่ยนรหัสผ่านให้บุคลากรได้จากหน้านี้ครับ")
