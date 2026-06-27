import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import holidays
from streamlit_calendar import calendar
from supabase import create_client, Client
from ortools.sat.python import cp_model
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.worksheet.page import PageMargins
from openpyxl.utils import get_column_letter
import re
import io
import time
import os
import streamlit.components.v1 as components

# ------------------------------------------------------------------
# 1. ตั้งค่าหน้าเว็บ & เวทมนตร์ CSS (Modern UI)
# ------------------------------------------------------------------
st.set_page_config(page_title="PharmSuk App", layout="wide", page_icon="💊")

# 💥 ระบบสะกิดเซิร์ฟเวอร์ป้องกันแอปหลับ (Anti-Sleep Keep-Alive)
components.html(
    """
    <script>
    setInterval(function() {
        window.parent.document.dispatchEvent(new Event('mousemove'));
    }, 240000);
    </script>
    """,
    height=0, width=0
)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;500;600&display=swap');
    
    html, body, [class*="css"], .stMarkdown, .stText, p, h1, h2, h3, h4, h5, h6 {
        font-family: 'Kanit', sans-serif !important;
    }
    
    .block-container { 
        padding-top: 1.5rem !important; 
        padding-bottom: 2rem !important; 
    }
    
    /* แก้ไข CSS ให้พุ่งเป้าไปที่ปุ่ม Submit เท่านั้น เพื่อไม่ให้กระทบ input อื่นๆ */
    .stButton>button, div[data-testid="stFormSubmitButton"] button {
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
    }
    .stButton>button:hover, div[data-testid="stFormSubmitButton"] button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1) !important;
    }
    
    div[data-testid="stExpander"] {
        border: 1px solid rgba(240,242,246,0.5) !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
        border-radius: 10px !important;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0px 0px;
        padding: 10px 16px;
        background-color: #f8f9fa;
    }
    .stTabs [data-baseweb="tab"] p {
        color: #154360 !important; 
        font-weight: 500 !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #E8DAEF !important;
        border-bottom: 3px solid #9B59B6 !important;
    }
    .stTabs [aria-selected="true"] p {
        color: #4A235A !important;
        font-weight: 600 !important;
    }
    
    div[data-testid="stMetricValue"] {
        font-size: 2rem !important;
        color: #9B59B6 !important;
        font-weight: 600 !important;
    }
    
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(21,67,96,1) 0%, rgba(77,208,225,1) 100%);
        color: white !important;
    }
    [data-testid="stSidebar"] .stMarkdown p, 
    [data-testid="stSidebar"] .stRadio label p {
        color: rgba(255,255,255,0.9) !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.1) !important;
    }

    [data-testid="stSidebar"] [data-baseweb="radio"] > div:first-child {
        display: none !important;
    }
    
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        padding: 12px 15px;
        border-radius: 8px;
        margin-bottom: 5px;
        transition: all 0.2s ease;
        cursor: pointer;
        width: 100%;
        background-color: rgba(255,255,255,0.05) !important;
        border: 1px solid transparent !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        background-color: rgba(255,255,255,0.1) !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        background-color: rgba(255,255,255,0.25) !important;
        border-left: 5px solid #ffffff !important;
        border-radius: 4px 8px 8px 4px !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
        color: white !important;
        font-weight: 600 !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        background-color: transparent !important;
        color: rgba(255,255,255,0.8) !important;
        border: 1px solid rgba(255,255,255,0.3) !important;
        border-radius: 8px !important;
        font-weight: 400 !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background-color: rgba(255,255,255,0.1) !important;
        color: #ffffff !important;
        border-color: #ffffff !important;
    }

    [data-testid="stSidebar"] img {
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
        margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    raw_url = st.secrets["supabase"]["url"]
    raw_key = st.secrets["supabase"]["key"]
    return create_client(raw_url.strip().rstrip('/'), raw_key.strip())

try:
    supabase: Client = init_connection()
except Exception:
    supabase = None

# ------------------------------------------------------------------
# ฟังก์ชันเกราะป้องกัน Error
# ------------------------------------------------------------------
def safe_idx(lst, val, default=0):
    try: return lst.index(val)
    except ValueError: return default

def get_thai_date(date_obj):
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, "%Y-%m-%d").date()
    thai_months = ["", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    thai_days = ["วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัสบดี", "วันศุกร์", "วันเสาร์", "วันอาทิตย์"]
    return f"{thai_days[date_obj.weekday()]}ที่ {date_obj.day} {thai_months[date_obj.month]} {date_obj.year + 543}"

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
        is_leave = "ลางาน" in req_type
        status = "⏳ รออนุมัติ" if is_leave else "✅ อนุมัติแล้ว"
        if is_leave and "ลาป่วย" in detail: status = "✅ อนุมัติแล้ว" 
        supabase.table("requests").insert({"user_name": user_name, "req_type": req_type, "req_date": req_date.strftime("%Y-%m-%d"), "detail": detail, "status": status}).execute()

def update_request_status(req_id, new_status):
    if supabase: supabase.table("requests").update({"status": new_status}).eq("id", req_id).execute()

def delete_request(req_id):
    if supabase: supabase.table("requests").delete().eq("id", req_id).execute()

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
        except: return False
    return False

def add_user_db(username, password, full_name, role, real_name="", surname="", email="", position="", display_order=99):
    if supabase:
        data = {
            "username": username, "password": password, "full_name": full_name, "role": role,
            "real_name": real_name, "surname": surname, "email": email, "position": position,
            "display_order": display_order
        }
        supabase.table("users").insert(data).execute()

def update_user_role(username, role):
    if supabase: supabase.table("users").update({"role": role}).eq("username", username).execute()

def update_user_order(username, new_order):
    if supabase: supabase.table("users").update({"display_order": new_order}).eq("username", username).execute()

def delete_user_db(username):
    if supabase: supabase.table("users").delete().eq("username", username).execute()

def update_user_profile(username, real_name, surname, email, position):
    if supabase:
        data = {"real_name": real_name, "surname": surname, "email": email, "position": position}
        supabase.table("users").update(data).eq("username", username).execute()

def update_user_password(username, new_password):
    if supabase:
        supabase.table("users").update({"password": new_password}).eq("username", username).execute()

if 'pt_daily_db' not in st.session_state: st.session_state.pt_daily_db = [] 

VALID_TIMES = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]
time_slots = [f"{VALID_TIMES[i]}-{VALID_TIMES[i+1]}" for i in range(16)]

current_year = datetime.now().year
th_holidays = holidays.Thailand(years=[current_year - 1, current_year, current_year + 1])

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.current_user = None

if 'auth_mode' not in st.session_state:
    st.session_state.auth_mode = 'login'

if "gen_df" not in st.session_state: st.session_state.gen_df = None
if "gen_html" not in st.session_state: st.session_state.gen_html = None
if "gen_excel" not in st.session_state: st.session_state.gen_excel = None
if "show_balloons" not in st.session_state: st.session_state.show_balloons = False

# ------------------------------------------------------------------
# ฟังก์ชัน UI Login 
# ------------------------------------------------------------------
def login_page():
    col_img1, col_img2, col_img3 = st.columns([1, 2, 1])
    with col_img2:
        if os.path.exists("banner.png"):
            st.markdown(
                """
                <style>
                    [data-testid="stImage"] > img {
                        border-radius: 0px !important;
                        box-shadow: none !important;
                        background-color: transparent !important;
                    }
                </style>
                """,
                unsafe_allow_html=True
            )
            st.image("banner.png", use_container_width=True)
        else:
            st.markdown("<h1 style='text-align: center; color: #154360;'>💊 PharmSuk</h1>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.session_state.get('auth_mode', 'login') == 'login':
            with st.form("login_form"):
                st.markdown("<h3 style='text-align: center; margin-top:0;'>เข้าสู่ระบบ</h3>", unsafe_allow_html=True)
                login_val = st.text_input("Username หรือ Email")
                password = st.text_input("Password", type="password")
                
                submit_btn = st.form_submit_button("เข้าสู่ระบบ", type="primary", use_container_width=True)
                forgot_btn = st.form_submit_button("ลืมรหัสผ่าน?", type="secondary", use_container_width=True)
                
                if submit_btn:
                    user_input = login_val.lower().strip()
                    matched_user = None
                    
                    users_db = fetch_users()
                    if user_input in users_db:
                        matched_user = users_db[user_input]
                    else:
                        for u in users_db.values():
                            if u.get('email') and u.get('email').lower().strip() == user_input and user_input != "":
                                matched_user = u
                                break
                                
                    if matched_user and matched_user['password'] == password:
                        st.session_state.logged_in = True
                        st.session_state.current_user = matched_user
                        st.rerun()
                    else: 
                        st.error("❌ Username/Email หรือ Password ไม่ถูกต้อง")
                        
                if forgot_btn:
                    st.session_state.auth_mode = 'forgot'
                    st.rerun()
        else:
            with st.form("forgot_form"):
                st.markdown("<h3 style='text-align: center; margin-top:0;'>กู้คืนรหัสผ่าน</h3>", unsafe_allow_html=True)
                f_user = st.text_input("Username")
                f_email = st.text_input("อีเมล (Email) ที่ลงทะเบียนไว้")
                new_pass = st.text_input("ตั้งรหัสผ่านใหม่", type="password")
                
                reset_btn = st.form_submit_button("รีเซ็ตรหัสผ่าน", type="primary", use_container_width=True)
                back_btn = st.form_submit_button("กลับไปหน้าเข้าสู่ระบบ", type="secondary", use_container_width=True)
                
                if reset_btn:
                    user_clean = f_user.lower().strip()
                    users_db = fetch_users()
                    if user_clean in users_db and users_db[user_clean].get('email') == f_email and f_email != "":
                        update_user_password(user_clean, new_pass)
                        st.success("✅ เปลี่ยนรหัสผ่านสำเร็จ! กรุณาเข้าสู่ระบบใหม่")
                        time.sleep(2)
                        st.session_state.auth_mode = 'login'
                        st.rerun()
                    else:
                        st.error("❌ Username หรือ Email ไม่ถูกต้อง หรือยังไม่ได้ผูกอีเมลไว้")
                
                if back_btn:
                    st.session_state.auth_mode = 'login'
                    st.rerun()

def logout():
    st.session_state.logged_in = False
    st.session_state.current_user = None

if not st.session_state.logged_in:
    login_page()
    st.stop()

# ------------------------------------------------------------------
# ระบบดักจับการ Login & สลับมุมมองหน้าจอ (Context Switch)
# ------------------------------------------------------------------
user_info = st.session_state.current_user
if user_info is None:
    st.session_state.logged_in = False
    st.rerun()

def get_std_pos(u):
    p = u.get('position')
    # กำหนดให้แปลงค่า NULL หรือตำแหน่งอื่นๆ เป็น 'เภสัชกร' ไว้ก่อนเป็น Default
    return p if p in ["เภสัชกร", "ผู้ช่วยเภสัชกร"] else "เภสัชกร"

with st.sidebar:
    if os.path.exists("banner.png"):
        st.image("banner.png", use_container_width=True)
        
    real_name = (user_info.get('real_name') or "").strip()
    surname = (user_info.get('surname') or "").strip()
    
    if real_name or surname:
        display_name = f"{real_name} {surname}".strip()
    else:
