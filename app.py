import streamlit as st
from datetime import datetime, date, timedelta
import holidays
from streamlit_calendar import calendar

# ------------------------------------------------------------------
# ตั้งค่าหน้าเว็บ
# ------------------------------------------------------------------
st.set_page_config(page_title="PharmSuk Calendar", layout="wide", page_icon="💊")
st.markdown("<style>.block-container { padding-top: 2rem; }</style>", unsafe_allow_html=True)

# ------------------------------------------------------------------
# ข้อมูลพื้นฐาน
# ------------------------------------------------------------------
pharmacist_list = ['เต้น', 'แอน', 'กอล์ฟ', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'มุก', 'ริน', 'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์']
time_slots = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]

# ดึงวันหยุดไทยของปีปัจจุบัน
current_year = datetime.now().year
th_holidays = holidays.Thailand(years=[current_year, current_year+1])

# ------------------------------------------------------------------
# Sidebar Menu (ระบบนำทาง)
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 💊 PharmSuk System")
    st.markdown("ศูนย์รวมข้อมูลตารางเวรห้องยา")
    st.divider()
    page = st.radio("เลือกเมนูการทำงาน", ["🗓️ ปฏิทินห้องยา (ภาพรวม)", "📝 ฟอร์มลงข้อมูล (ลา/งานพิเศษ)"])
    st.divider()
    st.markdown("*📝 Note: ในอนาคตหน้ารัน AI จัดตารางเวร จะมาอยู่เป็นเมนูที่ 3 ตรงนี้ครับ*")

# ==================================================================
# หน้าที่ 1: ปฏิทินภาพรวม
# ==================================================================
if page == "🗓️ ปฏิทินห้องยา (ภาพรวม)":
    st.title("🗓️ ปฏิทินภาพรวม PharmSuk")
    st.markdown("รวมข้อมูลวันหยุด วันลา งานพิเศษ และออกเวร เพื่อประกอบการพิจารณาจัดตาราง")

    # 1. จำลองข้อมูล Event ที่คนลงไว้ (Mockup Data)
    # ในอนาคต ข้อมูลก้อนนี้จะถูกดูดมาจาก Database
    today_str = date.today().strftime("%Y-%m-%d")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    events = [
        {"title": "เต้น (ลาเต็มวัน)", "start": today_str, "end": today_str, "backgroundColor": "#F44336", "borderColor": "#F44336"}, # สีแดง=ลา
        {"title": "มุก (สอน Robot)", "start": f"{today_str}T13:00:00", "end": f"{today_str}T15:00:00", "backgroundColor": "#2196F3"}, # สีฟ้า=งานพิเศษ
        {"title": "กอล์ฟ (สอน Robot)", "start": f"{today_str}T13:00:00", "end": f"{today_str}T15:00:00", "backgroundColor": "#2196F3"},
        {"title": "อ๊อฟฟี่ (ออกเวรดึก)", "start": f"{today_str}T08:30:00", "end": f"{today_str}T10:30:00", "backgroundColor": "#9C27B0"}, # สีม่วง=ออกเวรดึก
        {"title": "เต้น (ออกเวรดึก)", "start": f"{today_str}T08:30:00", "end": f"{today_str}T10:30:00", "backgroundColor": "#9C27B0"},
        {"title": "ออย (ออกเวรเย็น)", "start": f"{tomorrow_str}T15:30:00", "end": f"{tomorrow_str}T16:00:00", "backgroundColor": "#FF9800"}, # สีส้ม=ออกเวรเย็น
        {"title": "ใบเตย (ออกเวรเย็น)", "start": f"{tomorrow_str}T15:30:00", "end": f"{tomorrow_str}T16:00:00", "backgroundColor": "#FF9800"},
        {"title": "ริน (แทนตึกเก่า)", "start": tomorrow_str, "end": tomorrow_str, "backgroundColor": "#795548"}, # สีน้ำตาล=ไปแทน
    ]

    # 2. นำวันหยุดนักขัตฤกษ์ของไทย ยัดใส่เข้าไปใน Calendar อัตโนมัติ
    for hol_date, hol_name in th_holidays.items():
        events.append({
            "title": f"🇹🇭 {hol_name}",
            "start": str(hol_date),
            "end": str(hol_date),
            "display": "background", # ทำให้เป็นแถบสีทึบเต็มช่องวันนั้น
            "backgroundColor": "#FFEBEE", # พื้นหลังสีแดงอ่อน
            "textColor": "#D32F2F"
        })

    # 3. ตั้งค่าหน้าตาปฏิทิน
    calendar_options = {
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay"
        },
        "initialView": "dayGridMonth",
        "slotMinTime": "08:00:00",
        "slotMaxTime": "17:00:00",
        "allDayText": "ตลอดวัน",
        "locale": "th", # เปลี่ยนเป็นภาษาไทย
    }

    # แสดงผล Calendar
    st.write("---")
    calendar(events=events, options=calendar_options, custom_css="""
        .fc-event-title { font-weight: bold; font-size: 14px; }
        .fc-day-sun, .fc-day-sat { background-color: #FAFAFA; } 
    """)
    
    # Legend อธิบายสี
    st.markdown("""
    **ความหมายของสี:** <span style='color:#F44336; font-weight:bold;'>■ ลางาน</span> | 
    <span style='color:#2196F3; font-weight:bold;'>■ งานพิเศษ</span> | 
    <span style='color:#9C27B0; font-weight:bold;'>■ ออกเวรดึก</span> | 
    <span style='color:#FF9800; font-weight:bold;'>■ ออกเวรเย็น</span> | 
    <span style='color:#795548; font-weight:bold;'>■ แทนห้องยาอื่น</span>
    """, unsafe_allow_html=True)


# ==================================================================
# หน้าที่ 2: ฟอร์มลงข้อมูล
# ==================================================================
elif page == "📝 ฟอร์มลงข้อมูล (ลา/งานพิเศษ)":
    st.title("📝 ฟอร์มลงข้อมูลบุคลากร")
    st.markdown("เลือกประเภทที่ต้องการลงข้อมูลให้ระบบและหัวหน้าห้องยารับทราบ")
    
    # สร้าง Tab แยกประเภทฟอร์มให้ดูสะอาดตา
    tab1, tab2, tab3, tab4 = st.tabs(["🏖️ ลางาน (ลาป่วย/พักร้อน)", "💼 งานพิเศษ/อบรม", "🌅 ออกเวรดึก/เย็น", "🔔 แจ้งเตือนทั่วไป"])
    
    # --- Tab 1: ลางาน ---
    with tab1:
        st.subheader("บันทึกการลางาน")
        with st.form("leave_form"):
            c1, c2 = st.columns(2)
            with c1: req_name = st.selectbox("ชื่อผู้ลา", pharmacist_list)
            with c2: leave_type = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
            
            c3, c4 = st.columns(2)
            with c3: leave_date = st.date_input("วันที่ลา")
            with c4: leave_duration = st.selectbox("ช่วงเวลา", ["เต็มวัน", "ครึ่งเช้า", "ครึ่งบ่าย"])
            
            leave_note = st.text_input("หมายเหตุ (เช่น ชื่อ PT ที่มาแทน)")
            
            submit_leave = st.form_submit_button("ส่งคำขออนุมัติ")
            if submit_leave:
                if leave_type == "ลาพักร้อน":
                    st.success(f"✅ บันทึกคำขอ 'ลาพักร้อน' ของ {req_name} วันที่ {leave_date} สำเร็จ (รอหัวหน้าอนุมัติ)")
                    st.info("💡 ระบบแจ้งเตือน: ขณะนี้มีผู้ลาพักร้อนในวันที่เลือกแล้ว 1 คน (โควตาเหลือ 1 คน)")
                else:
                    st.warning(f"⚠️ บันทึก 'ลาป่วยฉุกเฉิน' ของ {req_name} สำเร็จ! ระบบจะไฮไลต์ให้แอดมินทราบทันที")

    # --- Tab 2: งานพิเศษ ---
    with tab2:
        st.subheader("บันทึกงานพิเศษ / อบรม")
        with st.form("task_form"):
            t_name = st.selectbox("ชื่อผู้ปฏิบัติงาน", pharmacist_list)
            t_category = st.selectbox("ประเภทงาน", ["หาหมอ", "ประชุม", "อบรม Module", "สอน Robot", "อื่นๆ (ระบุเอง)"])
            if t_category == "อื่นๆ (ระบุเอง)":
                t_custom = st.text_input("ระบุชื่องาน")
            
            st.markdown("ช่วงเวลา (ทำต่อเนื่องได้หลายวัน)")
            d1, d2 = st.columns(2)
            with d1: t_start_date = st.date_input("วันที่เริ่ม")
            with d2: t_end_date = st.date_input("วันที่สิ้นสุด (ถ้าวันเดียวให้เลือกวันเดิม)")
            
            t1, t2 = st.columns(2)
            with t1: t_start_time = st.selectbox("ตั้งแต่เวลา", time_slots)
            with t2: t_end_time = st.selectbox("ถึงเวลา", time_slots)
            
            submit_task = st.form_submit_button("บันทึกงานพิเศษ")
            if submit_task:
                st.success(f"✅ บันทึกงานพิเศษสำเร็จ ข้อมูลจะถูกนำไปรันตาราง AI อัตโนมัติ โดยไม่ต้องรออนุมัติ")

    # --- Tab 3: ออกเวร ---
    with tab3:
        st.subheader("บันทึกตารางออกเวร")
        off_type = st.radio("ประเภทการออกเวร", ["ออกเวรดึก (พักช่วงเช้า)", "ออกเวรเย็น (ทำต่อช่วงเย็น)"], horizontal=True)
        with st.form("off_form"):
            o_name = st.selectbox("ชื่อเภสัชกร", pharmacist_list)
            o_date = st.date_input("วันที่ออกเวร")
            
            if off_type == "ออกเวรดึก (พักช่วงเช้า)":
                o1, o2 = st.columns(2)
                with o1: o_start = st.selectbox("เวลาเริ่มพัก", ["08.30"], disabled=True)
                with o2: o_end = st.selectbox("เวลาหมดพัก", ["09.30", "10.00", "10.30"], index=2)
            else:
                o_loc = st.selectbox("สถานที่อยู่เวรต่อ", ["ชั้น 1", "ตึกพระเทพ ชั้นอื่น", "ตึกเก่า"])
                o_time = st.selectbox("รอบเวลาพักเวรเย็น", ["15.00 - 15.30", "15.30 - 16.00", "16.00 - 16.30"])
            
            submit_off = st.form_submit_button("บันทึกตารางออกเวร")
            if submit_off:
                st.success(f"✅ บันทึกข้อมูลการออกเวรของ {o_name} สำเร็จ")

    # --- Tab 4: แจ้งเตือนทั่วไป ---
    with tab4:
        st.subheader("สร้างข้อความแจ้งเตือนปะหน้าปฏิทิน")
        with st.form("alert_form"):
            a_date = st.date_input("วันที่ต้องการแจ้งเตือน")
            a_msg = st.text_input("ข้อความแจ้งเตือน (เช่น วันนี้ผู้ป่วยแน่น, มีงานประเมิน)")
            submit_alert = st.form_submit_button("ปักหมุดแจ้งเตือน")
            if submit_alert:
                st.success("✅ ปักหมุดข้อความบนปฏิทินสำเร็จ ทุกคนจะเห็นข้อความนี้")
