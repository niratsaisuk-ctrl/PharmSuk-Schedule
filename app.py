import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import holidays
from streamlit_calendar import calendar

# ------------------------------------------------------------------
# 1. ตั้งค่าหน้าเว็บ
# ------------------------------------------------------------------
st.set_page_config(page_title="PharmSuk App", layout="wide", page_icon="💊")
st.markdown("<style>.block-container { padding-top: 2rem; }</style>", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. จำลองฐานข้อมูล (Mock Database ด้วย Session State)
# ------------------------------------------------------------------
# จำลองตารางรายชื่อผู้ใช้งาน (Users Table)
if 'users_db' not in st.session_state:
    st.session_state.users_db = {
        'ten': {'name': 'เต้น', 'password': '1234', 'role': 'Staff'},
        'aof': {'name': 'อ๊อฟฟี่', 'password': '1234', 'role': 'Staff'},
        'golf': {'name': 'กอล์ฟ', 'password': '1234', 'role': 'Admin'}, # หัวหน้า
        'mook': {'name': 'มุก', 'password': '1234', 'role': 'Admin'}, # หัวหน้า
        'mind': {'name': 'มายด์', 'password': '1234', 'role': 'Admin'} # คนจัดตาราง
    }

# จำลองตารางเก็บคำขอลา/งานพิเศษ (Requests Table)
if 'requests_db' not in st.session_state:
    st.session_state.requests_db = []

# สถานะการล็อกอิน
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

# ข้อมูลพื้นฐาน
pharmacist_list = ['เต้น', 'แอน', 'กอล์ฟ', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'ริน', 'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์', 'มุก']
time_slots = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]

# ------------------------------------------------------------------
# 3. ระบบ Login & Logout
# ------------------------------------------------------------------
def login_page():
    st.markdown("<h1 style='text-align: center; color: #2E86C1;'>💊 PharmSuk</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: gray;'>ระบบจัดตารางเวรและบุคลากร ห้องยา</h4>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.info("💡 **ทดลองใช้งาน:**\n- แบบ Staff พิมพ์ Username: `ten` รหัส: `1234`\n- แบบ Admin พิมพ์ Username: `mind` รหัส: `1234`")
        with st.form("login_form"):
            username = st.text_input("Username (ชื่อเล่นภาษาอังกฤษ)")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("เข้าสู่ระบบ", use_container_width=True)
            
            if submit:
                user = username.lower()
                if user in st.session_state.users_db and st.session_state.users_db[user]['password'] == password:
                    st.session_state.logged_in = True
                    st.session_state.current_user = st.session_state.users_db[user]
                    st.success("ล็อกอินสำเร็จ! กำลังพาท่านเข้าสู่ระบบ...")
                    st.rerun()
                else:
                    st.error("❌ Username หรือ Password ไม่ถูกต้อง")

def logout():
    st.session_state.logged_in = False
    st.session_state.current_user = None
    st.rerun()

# ==================================================================
# หากยังไม่ล็อกอิน ให้โชว์แค่หน้า Login
# ==================================================================
if not st.session_state.logged_in:
    login_page()
    st.stop()

# ==================================================================
# 4. เมนูหลัก (หลังล็อกอินสำเร็จ)
# ==================================================================
user_info = st.session_state.current_user

with st.sidebar:
    st.markdown(f"### 👤 สวัสดี, คุณ {user_info['name']}")
    st.markdown(f"**ระดับสิทธิ์:** `{user_info['role']}`")
    st.button("🚪 ออกจากระบบ", on_click=logout, use_container_width=True)
    st.divider()
    
    st.markdown("**📌 เมนูการทำงาน**")
    # เมนูที่ทุกคนเห็น
    menu_options = ["🗓️ ปฏิทินห้องยา & ลงข้อมูล"]
    
    # เมนูที่เห็นเฉพาะ Admin
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
        st.subheader(f"บันทึกข้อมูลของ: {user_info['name']}")
        req_type = st.selectbox("เลือกประเภทที่ต้องการแจ้ง", ["ลางาน (พักร้อน/ป่วย/กิจ)", "งานพิเศษ/อบรม/ประชุม", "ออกเวร (ดึก/เย็น)"])
        
        with st.form("user_request_form"):
            req_date = st.date_input("วันที่")
            req_detail = st.text_input("รายละเอียด (เช่น ลาครึ่งเช้า, สอน Robot 13.00-15.00)")
            
            submitted = st.form_submit_button("ส่งข้อมูลเข้าสู่ระบบ", type="primary")
            if submitted:
                # บันทึกข้อมูลลง Session State
                new_req = {
                    "id": len(st.session_state.requests_db) + 1,
                    "name": user_info['name'],
                    "type": req_type,
                    "date": req_date.strftime("%Y-%m-%d"),
                    "detail": req_detail,
                    "status": "⏳ รออนุมัติ", # สถานะตั้งต้น
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                st.session_state.requests_db.append(new_req)
                st.success(f"✅ บันทึกคำขอเรียบร้อยแล้ว กรุณารอแอดมินตรวจสอบ")

    with tab2:
        st.markdown("*(ปฏิทินจะดึงข้อมูลที่ได้รับอนุมัติแล้วมาแสดงเป็นแถบสี)*")
        # โค้ดสร้างปฏิทินแบบง่าย (จำลอง)
        events = []
        # แสดงเฉพาะงานที่แอดมินกดอนุมัติแล้ว หรือ รออนุมัติ
        for req in st.session_state.requests_db:
            color = "#4CAF50" if req["status"] == "✅ อนุมัติแล้ว" else "#FFC107"
            events.append({
                "title": f"[{req['status'][0]}] {req['name']} - {req['detail']}",
                "start": req["date"],
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
    
    pending_reqs = [r for r in st.session_state.requests_db if r["status"] == "⏳ รออนุมัติ"]
    
    if not pending_reqs:
        st.info("🎉 เยี่ยมมาก! ไม่มีคำขอค้างในระบบ")
    else:
        st.warning(f"มีคำขอรอการอนุมัติจำนวน {len(pending_reqs)} รายการ")
        for req in pending_reqs:
            with st.container():
                st.markdown(f"**ผู้ขอ:** {req['name']} | **วันที่:** {req['date']} | **ประเภท:** {req['type']}")
                st.markdown(f"📝 **รายละเอียด:** {req['detail']} (ส่งเมื่อ: {req['timestamp']})")
                
                c1, c2, c3 = st.columns([1, 1, 8])
                with c1:
                    if st.button("✅ อนุมัติ", key=f"app_{req['id']}"):
                        req["status"] = "✅ อนุมัติแล้ว"
                        st.rerun()
                with c2:
                    if st.button("❌ ปฏิเสธ", key=f"rej_{req['id']}"):
                        req["status"] = "❌ ไม่อนุมัติ"
                        st.rerun()
                st.divider()
                
    st.subheader("ประวัติการจัดการ")
    history_reqs = [r for r in st.session_state.requests_db if r["status"] != "⏳ รออนุมัติ"]
    if history_reqs:
        df = pd.DataFrame(history_reqs)
        st.dataframe(df[['name', 'date', 'type', 'detail', 'status']], use_container_width=True)

# ==================================================================
# หน้า: ⚙️ รันตาราง AI ประจำวัน (เฉพาะ Admin)
# ==================================================================
elif page == "⚙️ รันตาราง AI ประจำวัน":
    st.title("⚙️ AI จัดตารางปฏิบัติงาน")
    st.markdown("ระบบจะทำการดึงข้อมูลที่ได้รับ **✅ อนุมัติแล้ว** มาจัดตารางโดยอัตโนมัติ")
    
    target_date = st.date_input("เลือกวันที่ต้องการรันตาราง")
    
    # จำลองการดึงข้อมูลที่ตรงกับวันที่เลือก และสถานะ=อนุมัติแล้ว
    approved_today = [r for r in st.session_state.requests_db if r["date"] == target_date.strftime("%Y-%m-%d") and r["status"] == "✅ อนุมัติแล้ว"]
    
    st.write("📥 **ข้อมูลที่ดึงมาได้สำหรับวันนี้:**")
    if approved_today:
        for r in approved_today:
            st.code(f"{r['name']} -> {r['type']} ({r['detail']})")
    else:
        st.info("ไม่มีข้อมูลลาหรืองานพิเศษในวันนี้")
        
    st.button("🚀 เริ่มรัน AI เพื่อสร้าง Excel", type="primary", use_container_width=True)
    st.markdown("*(โค้ด AI เวอร์ชั่น 137.0 จะถูกนำมาเชื่อมต่อที่ปุ่มนี้ในอนาคตครับ!)*")

# ==================================================================
# หน้า: 👥 จัดการผู้ใช้งาน (เฉพาะ Admin)
# ==================================================================
elif page == "👥 จัดการผู้ใช้งาน":
    st.title("👥 จัดการสิทธิ์และรหัสผ่าน")
    st.markdown("ตารางข้อมูลบุคลากรในระบบ")
    
    # แสดงข้อมูล User ทั้งหมด
    user_list = []
    for username, data in st.session_state.users_db.items():
        user_list.append({"Username": username, "ชื่อ": data['name'], "ระดับสิทธิ์": data['role'], "รหัสผ่าน": "***"})
    
    st.table(pd.DataFrame(user_list))
    st.info("ในระบบจริง หน้านี้จะสามารถกดเปลี่ยนรหัสผ่าน หรือเปลี่ยนสิทธิ์จาก Staff เป็น Admin ให้เพื่อนร่วมงานได้ครับ")
