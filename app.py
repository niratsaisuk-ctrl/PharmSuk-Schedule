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
    
    .stButton>button {
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
    }
    .stButton>button:hover {
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
    
    /* 💥 สีแถบเมนูข้าง (Sidebar) โทนน้ำเงิน-ฟ้า เข้ากับ Banner */
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

# 💥 ฟังก์ชันสำหรับจัดการผู้ใช้งาน
def add_user_db(username, password, full_name, role, real_name="", surname="", email="", position=""):
    if supabase:
        data = {
            "username": username, "password": password, "full_name": full_name, "role": role,
            "real_name": real_name, "surname": surname, "email": email, "position": position
        }
        supabase.table("users").insert(data).execute()

def update_user_role(username, role):
    if supabase: supabase.table("users").update({"role": role}).eq("username", username).execute()

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

users_db = fetch_users()
core_list = ['เต้น', 'แอน', 'กอล์ฟ', 'แม็ค', 'โบ้ท', 'ไม้เอก', 'กิ๊ฟ', 'ฟอร์จูน', 'มิ้ลค์', 'มุก', 'ริน', 'อ๊อฟฟี่', 'ออย', 'บี', 'มายด์', 'ขิม', 'บีม', 'มิ้น', 'ใบเตย', 'จีน่า', 'ปอนด์']
for u in users_db.values():
    if u['full_name'] not in core_list and u['role'] != 'System': core_list.append(u['full_name'])
base_pharmacist_list = core_list

VALID_TIMES = ["08.30", "09.00", "09.30", "10.00", "10.30", "11.00", "11.30", "12.00", "12.30", "13.00", "13.30", "14.00", "14.30", "15.00", "15.30", "16.00", "16.30"]
time_slots = [f"{VALID_TIMES[i]}-{VALID_TIMES[i+1]}" for i in range(16)]
th_holidays = holidays.Thailand(years=datetime.now().year)

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
# 3. ฟังก์ชันดึงข้อมูลเข้า Dashboard
# ------------------------------------------------------------------
def load_db_to_dashboard(approved_today, all_requests, target_date_str):
    leaves, tasks, shifts, bo_list = [], [], [], []
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    
    for r in approved_today:
        if "ลางาน" in r['req_type']:
            l_type = "ทั้งวัน"
            if "ครึ่งวันเช้า" in r['detail']: l_type = "เช้า"
            elif "ครึ่งวันบ่าย" in r['detail']: l_type = "บ่าย"
            elif "ลาป่วย" in r['detail']: l_type = "ฉุกเฉิน"
            
            s_time, e_time = "08.30", "16.30"
            times = re.findall(r'\d{2}\.\d{2}', r['detail'])
            if len(times) >= 2: s_time, e_time = times[0], times[1]
            
            if l_type == "ฉุกเฉิน":
                leaves.append({"user_name": r['user_name'], "leave_type": (s_time, e_time), "start": s_time, "end": e_time, "detail": r['detail']})
            else:
                leaves.append({"user_name": r['user_name'], "leave_type": l_type, "start": s_time, "end": e_time, "detail": r['detail']})
            
        elif "งานพิเศษ" in r['req_type']:
            times = re.findall(r'\d{2}\.\d{2}', r['detail'])
            tasks.append({"user_name": r['user_name'], "task_name": r['detail'].split('(')[0].replace('งานพิเศษ:', '').strip(), "start": times[0] if len(times)>0 else "08.30", "end": times[1] if len(times)>1 else "16.30"})
            
        elif "ออกเวร" in r['req_type']:
            s_type = "ออกเวรดึก" if "ดึก" in r['detail'] else "ออกเวรเย็น"
            room = "ชั้น 1"
            if "พระเทพ" in r['detail']: room = "ตึกพระเทพ"
            elif "ตึกเก่า" in r['detail']: room = "ตึกเก่า"
            shifts.append({"user_name": r['user_name'], "shift_type": s_type, "room": room, "start": "08.30", "end": "10.30", "time_slot": "15.00-15.30"})

    for r in all_requests:
        if r['req_type'] == "Back Office" and r['status'] == "✅ อนุมัติแล้ว":
            try:
                start_dt = datetime.strptime(r['req_date'], "%Y-%m-%d").date()
                parts = r['detail'].split('|') 
                if len(parts) >= 4:
                    end_dt = datetime.strptime(parts[1], "%Y-%m-%d").date()
                    if start_dt <= target_dt <= end_dt:
                        if len(parts) >= 5:
                            thai_days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
                            target_day_name = thai_days[target_dt.weekday()]
                            allowed_days = parts[4].split(',')
                            if target_day_name not in allowed_days: continue
                        
                        times = parts[2].split('-')
                        bo_list.append({"user_name": r['user_name'], "task_name": parts[3], "start": times[0], "end": times[1] if len(times)>1 else "16.30"})
            except: pass
            
    return leaves, tasks, shifts, bo_list

def force_sync_dashboard(target_date_str, all_requests):
    approved_today = [r for r in all_requests if r["req_date"] == target_date_str and r["status"] == "✅ อนุมัติแล้ว"]
    pts_today = [pt for pt in st.session_state.pt_daily_db if pt["date"] == target_date_str]
    leaves, tasks, shifts, bo_list = load_db_to_dashboard(approved_today, all_requests, target_date_str)
    
    st.session_state.dash_leaves = leaves
    st.session_state.dash_tasks = tasks
    st.session_state.dash_shifts = shifts
    st.session_state.dash_pts = pts_today
    st.session_state.dash_subs = [] 
    st.session_state.dash_locks = []
    
    st.session_state.dash_bo = bo_list
    
    st.session_state.dash_date = target_date_str
    st.session_state.dash_hash = len(all_requests) + len(pts_today)

# ------------------------------------------------------------------
# 4. สมองกล AI V137 ต้นฉบับ 100%
# ------------------------------------------------------------------
def time_to_slot(t_str): 
    return safe_idx(VALID_TIMES, t_str, 0)

dispensing_tasks = [f"จ่าย {i}" for i in range(4, 12)]
ver_cpoe_tasks = ["Ver 1 INC", "Ver 2/ปณ.", "Ver 3/A", "Ver 4", "Ver 5", "Ver 6", "Ver 7", "Ver 8", "Ver 9", "Ver 10"]
ver_ps_tasks = [f"Ver PS{i}" for i in range(1, 11)]
base_main_tasks = dispensing_tasks + ver_cpoe_tasks + ver_ps_tasks + ["Match + C", "Match + C2"]

def generate_schedule(DAY_OF_WEEK, LEAVES, CUSTOM_TASKS, PART_TIME, FIX_BREAKS, FIXED_MAIN_TASKS, SICK_PEOPLE, IS_MWF):
    ft_pharmacists = base_pharmacist_list
    head_pharmacists = ['กอล์ฟ', 'มุก'] 
    
    pt_pharmacists = [pt['name'] for pt in PART_TIME]
    all_pharmacists = ft_pharmacists + pt_pharmacists

    error_msgs = []
    leave_slots_check = {}
    
    for p in ft_pharmacists:
        if p in LEAVES:
            l_type = LEAVES[p]
            if l_type == 'ทั้งวัน': 
                l_range = range(0, 16)
            elif l_type == 'เช้า': 
                l_range = range(0, 9)
            elif l_type == 'บ่าย': 
                l_range = range(7, 16)
            else: 
                l_range = range(time_to_slot(l_type[0]), time_to_slot(l_type[1]))
            
            for t in l_range: 
                leave_slots_check[(p, t)] = l_type

    custom_slots_check = {}
    for (p, start, end), t_name in CUSTOM_TASKS.items():
        s_idx, e_idx = time_to_slot(start), time_to_slot(end)
        for t in range(s_idx, e_idx):
            if (p, t) in leave_slots_check:
                error_msgs.append(f"⚠️ **{p}**: ถูกตั้งให้ **ลา** และทำภารกิจ **{t_name}** ทับซ้อนกันเวลา {time_slots[t]}")
            if (p, t) in custom_slots_check:
                error_msgs.append(f"⚠️ **{p}**: ถูกตั้งภารกิจ **{custom_slots_check[(p, t)]}** และ **{t_name}** ทับซ้อนกันเวลา {time_slots[t]}")
            custom_slots_check[(p, t)] = t_name

    fixed_slots_check = {}
    for (p, start, end), t_name in FIXED_MAIN_TASKS.items():
        s_idx, e_idx = time_to_slot(start), time_to_slot(end)
        for t in range(s_idx, e_idx):
            if (p, t) in leave_slots_check:
                error_msgs.append(f"⚠️ **{p}**: ลา และล็อกงานหลัก **{t_name}** ทับซ้อนกันเวลา {time_slots[t]}")
            if (p, t) in custom_slots_check:
                error_msgs.append(f"⚠️ **{p}**: มีภารกิจ **{custom_slots_check[(p, t)]}** และล็อกงานหลัก **{t_name}** ทับซ้อนกันเวลา {time_slots[t]}")
            if (p, t) in fixed_slots_check:
                error_msgs.append(f"⚠️ **{p}**: ถูกล็อกงานหลัก **{fixed_slots_check[(p, t)]}** และ **{t_name}** ทับซ้อนกันเวลา {time_slots[t]}")
            fixed_slots_check[(p, t)] = t_name

    if error_msgs:
        unique_errors = list(dict.fromkeys(error_msgs))
        return None, "Validation Failed", "ตรวจพบปัญหาในการตั้งค่า กรุณาแก้ไข:\n\n" + "\n".join(unique_errors[:10])

    model = cp_model.CpModel()
    
    tasks = base_main_tasks + ['Matching', 'พัก', 'งานเฉพาะ', 'ลา', 'นอกเวลา', 'ว่าง']
             
    x = {}
    for p in all_pharmacists:
        for t in range(16):
            for task in tasks: 
                x[p, t, task] = model.NewBoolVar(f'x_{p}_{t}_{task}')
            model.AddExactlyOne(x[p, t, task] for task in tasks)
            model.Add(x[p, t, 'ว่าง'] == 0)

    if DAY_OF_WEEK == 'Wed_Fri': break_slots, b_groups = [6, 7, 8, 9, 10, 11], [(6,8), (8,10), (10,12)] 
    else: break_slots, b_groups = [5, 6, 7, 8, 9, 10], [(5,7), (7,9), (9,11)]

    active_ft = []
    leave_slots = set()
    half_day_leaves = set() 
    
    for p in ft_pharmacists:
        if p in LEAVES:
            l_type = LEAVES[p]
            if l_type == 'ทั้งวัน': 
                l_range = range(0, 16)
            elif l_type == 'เช้า': 
                l_range = range(0, 9)
                half_day_leaves.add(p)
            elif l_type == 'บ่าย': 
                l_range = range(7, 16)
                half_day_leaves.add(p)
            else: 
                l_range = range(time_to_slot(l_type[0]), time_to_slot(l_type[1]))
                half_day_leaves.add(p)
                
            if l_type != 'ทั้งวัน': active_ft.append(p)
            for t in l_range: 
                model.Add(x[p, t, 'ลา'] == 1)
                leave_slots.add((p, t))
        else: active_ft.append(p)

    for p in ft_pharmacists:
        for t in range(16):
            if (p, t) not in leave_slots: model.Add(x[p, t, 'ลา'] == 0)

    custom_dict_index = {}
    custom_task_slots_count = {p: 0 for p in ft_pharmacists} 
    for (p, start, end), task_name in CUSTOM_TASKS.items():
        s_idx, e_idx = time_to_slot(start), time_to_slot(end)
        for t in range(s_idx, e_idx):
            if (p, t) not in leave_slots:
                model.Add(x[p, t, 'งานเฉพาะ'] == 1)
                custom_dict_index[(p, t)] = task_name
                if p in ft_pharmacists: custom_task_slots_count[p] += 1
            
    for p in all_pharmacists:
        for t in range(16):
            if (p, t) not in custom_dict_index: model.Add(x[p, t, 'งานเฉพาะ'] == 0)

    for p in SICK_PEOPLE:
        if p in all_pharmacists:
            for t in range(16):
                for task in dispensing_tasks: model.Add(x[p, t, task] == 0)

    for (p, start, end), task_name in FIXED_MAIN_TASKS.items():
        s_idx, e_idx = time_to_slot(start), time_to_slot(end)
        for t in range(s_idx, e_idx): 
            if (p, t) not in leave_slots: model.Add(x[p, t, task_name] == 1)

    for p in head_pharmacists:
        fixed_slots = set()
        for (fp, s, e), t_name in FIXED_MAIN_TASKS.items():
            if fp == p:
                for t in range(time_to_slot(s), time_to_slot(e)): fixed_slots.add(t)

        for t in range(16):
            if t not in fixed_slots:
                for task in dispensing_tasks + ver_cpoe_tasks + ver_ps_tasks + ['Match + C', 'Match + C2']:
                    model.Add(x[p, t, task] == 0)

    reward_vars = []

    for pt in PART_TIME:
        p = pt['name']
        s_idx, e_idx = time_to_slot(pt['start']), time_to_slot(pt['end'])
        
        my_dispense_allowed = ['จ่าย 7', 'จ่าย 8']
        if len(PART_TIME) > 2: my_dispense_allowed.extend(['จ่าย 6', 'จ่าย 9'])
            
        pt_all_allowed = my_dispense_allowed + ['Matching', 'พัก', 'นอกเวลา']
        
        for t in range(16): 
            if t < s_idx or t >= e_idx: model.Add(x[p, t, 'นอกเวลา'] == 1)
            else: model.Add(x[p, t, 'นอกเวลา'] == 0)
        
        for t in range(max(0, s_idx), min(16, e_idx)):
            model.Add(sum(x[p, t, task] for task in pt_all_allowed) == 1)

        b_type, b_time = pt.get('break_type', 'ไม่พักเลย'), pt.get('break_time', None)
        if b_type != "ไม่พักเลย" and b_time:
            b_s_idx = time_to_slot(b_time)
            if b_type == "พัก 1 ชั่วโมง":
                if b_s_idx < 16: model.Add(x[p, b_s_idx, 'พัก'] == 1)
                if b_s_idx + 1 < 16: model.Add(x[p, b_s_idx + 1, 'พัก'] == 1)
                for t in range(16):
                    if t != b_s_idx and t != (b_s_idx + 1): model.Add(x[p, t, 'พัก'] == 0)
            elif b_type == "พักครึ่งชั่วโมง":
                if b_s_idx < 16: model.Add(x[p, b_s_idx, 'พัก'] == 1)
                for t in range(16):
                    if t != b_s_idx: model.Add(x[p, t, 'พัก'] == 0)
        else:
            for t in range(16): model.Add(x[p, t, 'พัก'] == 0)

        for d in my_dispense_allowed:
            d_sum = sum(x[p, t, d] for t in range(16))
            over_2 = model.NewIntVar(0, 16, f'pt_over_2_{p}_{d}')
            model.Add(over_2 >= d_sum - 2)
            model.Add(over_2 >= 0)
            reward_vars.append(over_2 * -80000) 

        d7_sum = sum(x[p, t, 'จ่าย 7'] for t in range(16))
        d8_sum = sum(x[p, t, 'จ่าย 8'] for t in range(16))
        diff_78 = model.NewIntVar(-16, 16, f'diff_78_{p}')
        model.Add(diff_78 == d7_sum - d8_sum)
        abs_diff_78 = model.NewIntVar(0, 16, f'abs_diff_78_{p}')
        model.AddAbsEquality(abs_diff_78, diff_78)
        reward_vars.append(abs_diff_78 * -30000)
        
    for p in pt_pharmacists:
        for t in range(14):
            model.Add(sum(x[p, t+k, 'Matching'] for k in range(3)) <= 2)

    b_group_vars_ft = {0: [], 1: [], 2: []}
    full_day_active_ft = [p for p in active_ft if p not in half_day_leaves]
    normal_ft_for_break = [p for p in full_day_active_ft if p not in head_pharmacists]
    
    for p in all_pharmacists:
        if p in ft_pharmacists:
            model.Add(sum(x[p, t, 'นอกเวลา'] for t in range(16)) == 0) 
            if p not in head_pharmacists:
                for t in range(16): model.Add(x[p, t, 'Matching'] == 0) 
        
        if p in full_day_active_ft:
            if p in head_pharmacists:
                break_sum = sum(x[p, t, 'พัก'] for t in range(16))
                model.Add(break_sum <= 2)
                reward_vars.append(break_sum * 100000) 
                
                for t in range(12, 16): model.Add(x[p, t, 'พัก'] == 0)
                for t in range(0, 5): model.Add(x[p, t, 'พัก'] == 0)
                    
                head_is_busy = False
                for t in break_slots:
                    if (p, t) in custom_slots_check or (p, t) in fixed_slots_check: head_is_busy = True
                
                if not head_is_busy:
                    for bg_idx, bg_range in enumerate(b_groups):
                        is_in_this_break = model.NewBoolVar(f'head_{p}_in_break_{bg_idx}')
                        model.Add(sum(x[p, t, 'พัก'] for t in range(*bg_range)) == 2).OnlyEnforceIf(is_in_this_break)
                        reward_vars.append(is_in_this_break * 200000)

            else:
                model.Add(sum(x[p, t, 'พัก'] for t in range(16)) == 2)
                choices = [model.NewBoolVar(f'choice_{p}_b{i}') for i in range(3)]
                if p in FIX_BREAKS and p in ft_pharmacists:
                    req_b = FIX_BREAKS[p]
                    for i in range(3): model.Add(choices[i] == (1 if i == req_b else 0))
                else:
                    model.AddExactlyOne(choices) 
                for i in range(3):
                    b_group_vars_ft[i].append(choices[i])
                    for t in range(*b_groups[i]): model.Add(x[p, t, 'พัก'] == 1).OnlyEnforceIf(choices[i])
                for t in range(16):
                    if t not in break_slots: model.Add(x[p, t, 'พัก'] == 0)
        elif p in ft_pharmacists:
            if p in head_pharmacists:
                break_sum = sum(x[p, t, 'พัก'] for t in range(16))
                model.Add(break_sum <= 2)
                reward_vars.append(break_sum * 100000)
                for t in range(12, 16): model.Add(x[p, t, 'พัก'] == 0)
                for t in range(0, 5): model.Add(x[p, t, 'พัก'] == 0)
            else:
                model.Add(sum(x[p, t, 'พัก'] for t in range(16)) == 0)

    total_active_ft_break = len(normal_ft_for_break) 
    if total_active_ft_break > 0:
        max_b_per_group = (total_active_ft_break // 3) + 2
        for i in range(3):
            model.Add(sum(b_group_vars_ft[i]) <= max_b_per_group) 
            model.Add(sum(b_group_vars_ft[i]) >= max(0, (total_active_ft_break // 3) - 1))

    # 1 Station per person
    for t in range(16):
        for task in tasks:
            if task not in ['พัก', 'งานเฉพาะ', 'ลา', 'นอกเวลา', 'ว่าง', 'Matching', 'Match + C2']:
                model.Add(sum(x[p, t, task] for p in all_pharmacists) <= 1)
        model.Add(sum(x[p, t, 'Match + C2'] for p in all_pharmacists) <= 1)

        if t < 2: 
            req_core = ['จ่าย 6', 'จ่าย 7', 'จ่าย 8', 'Ver 1 INC', 'Ver 2/ปณ.', 'Ver 3/A', 'Ver PS1', 'Match + C']
            reward_vars.append(sum(x[p, t, 'จ่าย 9'] for p in all_pharmacists) * 50000)
            model.Add(sum(x[p, t, 'จ่าย 9'] for p in all_pharmacists) <= 1)
        elif t == 2: 
            req_core = ['จ่าย 5', 'จ่าย 6', 'จ่าย 7', 'จ่าย 8', 'จ่าย 9', 'Ver 1 INC', 'Ver 2/ปณ.', 'Ver 3/A', 'Ver PS1', 'Match + C']
        else: 
            req_core = ['จ่าย 5', 'จ่าย 6', 'จ่าย 7', 'จ่าย 8', 'จ่าย 9', 'จ่าย 10', 'Ver 1 INC', 'Ver 2/ปณ.', 'Ver 3/A', 'Ver PS1', 'Match + C']
            
        for task in req_core: model.Add(sum(x[p, t, task] for p in all_pharmacists) == 1)

        if t < 2:
            model.Add(sum(x[p, t, 'จ่าย 4'] for p in all_pharmacists) == 0)
            model.Add(sum(x[p, t, 'จ่าย 5'] for p in all_pharmacists) == 0)
            model.Add(sum(x[p, t, 'จ่าย 10'] for p in all_pharmacists) == 0)
            model.Add(sum(x[p, t, 'จ่าย 11'] for p in all_pharmacists) == 0)

        if t not in break_slots:
            model.Add(sum(x[p, t, 'Ver PS2'] for p in all_pharmacists) == 1)
        else:
            model.Add(sum(x[p, t, 'Ver PS2'] for p in all_pharmacists) <= 1)
            ps2_sum = sum(x[p, t, 'Ver PS2'] for p in all_pharmacists)
            reward_vars.append(ps2_sum * 100000)

        if t < 3:
            model.Add(sum(x[p, t, 'จ่าย 10'] for p in all_pharmacists) <= 1)
            d10_sum = sum(x[p, t, 'จ่าย 10'] for p in all_pharmacists)
            reward_vars.append(d10_sum * 150000)

    for t in range(16):
        for i in range(2, 10): model.Add(sum(x[p, t, f'Ver PS{i+1}'] for p in all_pharmacists) <= sum(x[p, t, f'Ver PS{i}'] for p in all_pharmacists))
        for i in range(4, 10): model.Add(sum(x[p, t, f'Ver {i+1}'] for p in all_pharmacists) <= sum(x[p, t, f'Ver {i}'] for p in all_pharmacists))
        
        model.Add(sum(x[p, t, 'จ่าย 8'] for p in all_pharmacists) <= sum(x[p, t, 'จ่าย 7'] for p in all_pharmacists))
        model.Add(sum(x[p, t, 'จ่าย 6'] for p in all_pharmacists) <= sum(x[p, t, 'จ่าย 8'] for p in all_pharmacists))
        model.Add(sum(x[p, t, 'จ่าย 9'] for p in all_pharmacists) <= sum(x[p, t, 'จ่าย 6'] for p in all_pharmacists))
        model.Add(sum(x[p, t, 'จ่าย 5'] for p in all_pharmacists) <= sum(x[p, t, 'จ่าย 9'] for p in all_pharmacists))
        model.Add(sum(x[p, t, 'จ่าย 10'] for p in all_pharmacists) <= sum(x[p, t, 'จ่าย 5'] for p in all_pharmacists))
        model.Add(sum(x[p, t, 'จ่าย 4'] for p in all_pharmacists) <= sum(x[p, t, 'จ่าย 10'] for p in all_pharmacists))
        model.Add(sum(x[p, t, 'จ่าย 11'] for p in all_pharmacists) <= sum(x[p, t, 'จ่าย 4'] for p in all_pharmacists))

    for p in all_pharmacists:
        for t in range(15):
            for task1 in dispensing_tasks:
                for task2 in dispensing_tasks:
                    if task1 != task2: model.AddImplication(x[p, t, task1], x[p, t+1, task2].Not())

    for p in all_pharmacists:
        for cat in [dispensing_tasks, ver_cpoe_tasks, ver_ps_tasks, ['Match + C', 'Match + C2']]:
            for t in range(14): 
                model.Add(sum(x[p, t+k, task] for task in cat for k in range(3)) <= 2)

    is_disp_7_vars = []
    for p in ft_pharmacists:
        if p not in head_pharmacists:
            tot_disp = sum(x[p, t, task] for t in range(16) for task in dispensing_tasks)
            over_3hr_var = model.NewBoolVar(f'over_3hr_{p}')
            
            model.Add(tot_disp <= 6 + over_3hr_var)
            model.Add(tot_disp <= 7) 
            reward_vars.append(over_3hr_var * -500000) 
            is_disp_7_vars.append(over_3hr_var)
            
            if p in active_ft and p not in SICK_PEOPLE:
                has_heavy_custom_tasks = custom_task_slots_count[p] >= 6 
                is_half_day_leave = p in half_day_leaves
                short_disp = model.NewIntVar(0, 16, f'short_disp_{p}')
                
                if has_heavy_custom_tasks or is_half_day_leave: 
                    model.Add(short_disp >= 2 - tot_disp)
                else: 
                    model.Add(short_disp >= 4 - tot_disp)
                model.Add(short_disp >= 0)
                reward_vars.append(short_disp * -500000) 

            for d in ['จ่าย 6', 'จ่าย 7', 'จ่าย 8', 'จ่าย 9']: model.Add(sum(x[p, t, d] for t in range(16)) <= 2)
            for d in ['จ่าย 4', 'จ่าย 5', 'จ่าย 10', 'จ่าย 11']:
                total_d = sum(x[p, t, d] for t in range(16))
                over_d = model.NewIntVar(0, 16, f'over_{p}_{d}')
                model.Add(over_d >= total_d - 2)
                model.Add(over_d >= 0) 
                reward_vars.append(over_d * -2500) 

            done_disp_7 = model.NewBoolVar(f'done_disp_7_{p}')
            model.Add(sum(x[p, t, 'จ่าย 7'] for t in range(16)) > 0).OnlyEnforceIf(done_disp_7)
            model.Add(sum(x[p, t, 'จ่าย 7'] for t in range(16)) == 0).OnlyEnforceIf(done_disp_7.Not())

            done_disp_8 = model.NewBoolVar(f'done_disp_8_{p}')
            model.Add(sum(x[p, t, 'จ่าย 8'] for t in range(16)) > 0).OnlyEnforceIf(done_disp_8)
            model.Add(sum(x[p, t, 'จ่าย 8'] for t in range(16)) == 0).OnlyEnforceIf(done_disp_8.Not())
            model.Add(done_disp_7 + done_disp_8 <= 1)

            model.Add(sum(x[p, t, 'Match + C'] + x[p, t, 'Match + C2'] for t in range(16)) <= 2)

    model.Add(sum(is_disp_7_vars) <= 2) 

    for p in all_pharmacists:
        for t in range(14):
            is_disp_t = sum(x[p, t, d] for d in dispensing_tasks)
            is_disp_t1 = sum(x[p, t+1, d] for d in dispensing_tasks)
            is_disp_t2 = sum(x[p, t+2, d] for d in dispensing_tasks)
            too_long = model.NewBoolVar(f'too_long_disp_{p}_{t}')
            model.Add(is_disp_t + is_disp_t1 + is_disp_t2 <= 2 + too_long)
            reward_vars.append(too_long * -100000) 
            
            short_break = model.NewBoolVar(f'short_break_disp_{p}_{t}')
            model.Add(is_disp_t - is_disp_t1 + is_disp_t2 <= 1 + short_break)
            if p in ft_pharmacists: reward_vars.append(short_break * -2000000) 
            else: reward_vars.append(short_break * -500000)

    for p in all_pharmacists:
        for t in range(15):
            for task in dispensing_tasks + ver_cpoe_tasks + ver_ps_tasks + ['Match + C', 'Match + C2']:
                match_var = model.NewBoolVar(f'pair_{p}_{t}_{task}')
                model.AddImplication(match_var, x[p, t, task])
                model.AddImplication(match_var, x[p, t+1, task])
                if task in dispensing_tasks: reward_vars.append(match_var * 500000) 
                else: reward_vars.append(match_var * 150000)

    for p in ft_pharmacists:
        ft_iso_disp_vars = []
        for t in range(16):
            for d in dispensing_tasks:
                iso_disp = model.NewBoolVar(f'iso_disp_{p}_{t}_{d}')
                prev_v = x[p, t-1, d] if t > 0 else 0
                next_v = x[p, t+1, d] if t < 15 else 0
                model.Add(x[p, t, d] - prev_v - next_v <= iso_disp)
                ft_iso_disp_vars.append(iso_disp)
                reward_vars.append(iso_disp * -200000) 
        model.Add(sum(ft_iso_disp_vars) <= 2)

    for p in all_pharmacists:
        for t in range(16):
            for target_task in ['Ver 1 INC', 'Ver 2/ปณ.', 'Ver 3/A', 'Match + C', 'Ver PS1']:
                iso_var = model.NewBoolVar(f'iso_{target_task}_{p}_{t}')
                prev_v = x[p, t-1, target_task] if t > 0 else 0
                next_v = x[p, t+1, target_task] if t < 15 else 0
                model.Add(x[p, t, target_task] - prev_v - next_v <= iso_var)
                reward_vars.append(iso_var * -100000)

    for t in range(16):
        weights = {
            'จ่าย 7': 400000, 'จ่าย 8': 390000, 'จ่าย 6': 380000, 'จ่าย 9': 370000,
            'จ่าย 5': 360000, 'จ่าย 10': 350000, 'จ่าย 4': 300000, 'จ่าย 11': 290000, 
            'Ver 4': 50000, 'Ver PS3': 48000, 
            'Match + C2': 47000, 
            'Ver 5': 46000, 'Ver PS4': 44000, 
            'Ver 6': 42000, 'Ver PS5': 40000, 
            'Ver 7': 38000, 'Ver PS6': 36000, 
            'Ver 8': 34000, 'Ver PS7': 32000, 
            'Ver 9': 30000, 'Ver PS8': 28000, 
            'Ver 10': 26000, 'Ver PS9': 24000, 'Ver PS10': 22000,
            'Ver 1 INC': 85000, 'Ver 2/ปณ.': 80000, 'Ver 3/A': 75000, 
            'Ver PS1': 70000, 'Ver PS2': 65000, 'Match + C': 60000, 'Matching': 20000
        }
        if IS_MWF and (t in break_slots):
            weights['จ่าย 4'] = -50000 
            weights['จ่าย 11'] = -50000

        for task, weight in weights.items():
            for i, p in enumerate(all_pharmacists): reward_vars.append(x[p, t, task] * (weight + i))

    model.Maximize(sum(reward_vars))
    solver = cp_model.CpSolver()
    solver.parameters.num_workers = 8
    solver.parameters.max_time_in_seconds = 20.0  

    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule_data = []
        for p in all_pharmacists:
            row_data = {'ชื่อ/เวลา': p} 
            for t in range(16):
                assigned = ""
                for tsk in tasks:
                    if solver.Value(x[p, t, tsk]) == 1:
                        if tsk == 'งานเฉพาะ': assigned = custom_dict_index.get((p, t), 'งานเฉพาะ')
                        elif tsk in ['นอกเวลา', 'ว่าง']: assigned = '-'
                        elif tsk == 'ลา': assigned = 'ลา'
                        else: assigned = tsk
                row_data[time_slots[t]] = assigned
            schedule_data.append(row_data)
            
        df_result = pd.DataFrame(schedule_data)
        
        summary_row = {'ชื่อ/เวลา': 'P/C/D'} 
        for t_idx in range(16):
            time_col = time_slots[t_idx]
            w_count, x_count, disp_nums = 0, 0, []
            for p in all_pharmacists:
                val_str = str(df_result.loc[df_result['ชื่อ/เวลา'] == p, time_col].values[0])
                if 'Ver PS' in val_str: w_count += 1
                elif 'Ver' in val_str: x_count += 1
                elif 'จ่าย ' in val_str:
                    try: disp_nums.append(int(val_str.replace('จ่าย ', '').strip()))
                    except: pass
            yz_str = f"{min(disp_nums)}-{max(disp_nums)}" if disp_nums else "-"
            summary_row[time_col] = f"{w_count}/{x_count}/{yz_str}"
        df_result = pd.concat([df_result, pd.DataFrame([summary_row])], ignore_index=True)
        
        return df_result, "Success", ""
    else: 
        return None, "Infeasible", "เงื่อนไขตึงเกินไป หรือคนไม่พอจัดตาราง"

# ------------------------------------------------------------------
# 5. ฟังก์ชันสีและสร้างไฟล์ HTML & Excel สรุปผล
# ------------------------------------------------------------------
def get_cell_bg_hex(val_str):
    val = str(val_str)
    if '/' in val and '-' in val and val and val[0].isdigit(): return "FFF2CC"
    elif 'จ่าย ' in val: return "D5E8D4"
    elif 'Match' in val: return "DAE8FC"
    elif val == 'Matching': return "DAE8FC"
    elif 'Ver PS' in val: return "E1D5E7"
    elif 'Ver' in val: return "FFE6CC"
    elif val == 'พัก': return "F8CECC"
    elif val == 'ลา': return "E6E6E6" 
    elif val in ['-', 'ว่าง', 'นอกเวลา']: return "F5F5F5"
    return "F5F5F5"

def get_header_color(t_idx, day_of_week):
    if day_of_week == 'Normal':
        if t_idx in [0, 1, 3, 4, 11, 12]: return 'orange' 
        if t_idx in [2]: return 'yellow'                 
        if t_idx in [5, 6, 9, 10]: return 'pink'         
        if t_idx in [7, 8]: return 'purple'              
        if t_idx in [13, 14, 15]: return 'blue'          
    else: 
        if t_idx in [0, 1, 4, 5, 12, 13]: return 'orange' 
        if t_idx in [2, 3]: return 'yellow'              
        if t_idx in [6, 7, 10, 11]: return 'pink'        
        if t_idx in [8, 9]: return 'purple'              
        if t_idx in [14, 15]: return 'blue'              
    return None

header_color_map = {
    'orange': PatternFill(start_color='FFE6CC', end_color='FFE6CC', fill_type='solid'),
    'yellow': PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid'),
    'pink': PatternFill(start_color='F8CECC', end_color='F8CECC', fill_type='solid'),
    'purple': PatternFill(start_color='E1D5E7', end_color='E1D5E7', fill_type='solid'),
    'blue': PatternFill(start_color='DAE8FC', end_color='DAE8FC', fill_type='solid')
}
thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))

def build_html_table(df, selected_date_str, DAY_OF_WEEK):
    thai_date_str = get_thai_date(selected_date_str)
    def get_cell_style(val_str):
        bg = "#" + get_cell_bg_hex(val_str)
        color, weight = "black", "normal"
        
        if '/' in val_str and '-' in val_str and val_str and val_str[0].isdigit(): 
            weight = "bold"
        elif 'Match' in val_str and ('C' in val_str or 'C2' in val_str): 
            color, weight = "red", "bold"
        elif val_str == 'ลา': 
            color, weight = "black", "normal" 
        elif val_str in ['-', 'ว่าง', 'นอกเวลา']: 
            color = "#808080"
            
        return f"background-color: {bg}; color: {color}; font-weight: {weight}; border: 1px solid black; padding: 2px; text-align: center; font-size: 14px; white-space: nowrap; height: 30px; box-sizing: border-box;"
        
    def get_head_color_hex(t_idx, day_of_week):
        color_name = get_header_color(t_idx, day_of_week)
        mapping = {'orange': '#FFE6CC', 'yellow': '#FFF2CC', 'pink': '#F8CECC', 'purple': '#E1D5E7', 'blue': '#DAE8FC'}
        return mapping.get(color_name, '#FFFFFF')

    cols = df.columns.tolist()
    num_cols = len(cols)
    
    html = f"""
    <div id='capture-area' style='background-color: white; padding: 15px; display: inline-block; font-family: "Sarabun", sans-serif;'>
        <table style='border-collapse: collapse; table-layout: fixed; width: max-content; border: 2px solid #ddd; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border-radius: 8px; overflow: hidden;'>
            <tr>
                <td colspan='{num_cols}' style='text-align: center; font-size: 24px; font-weight: bold; border: none; padding-top: 5px; color: #333;'>
                    ตารางปฏิบัติงานเภสัชกร ห้องยาชั้น 1 อาคารสมเด็จพระเทพรัตน์
                </td>
            </tr>
            <tr>
                <td colspan='{num_cols}' style='text-align: center; font-size: 18px; font-weight: normal; border: none; padding-bottom: 15px; color: #666;'>
                    ประจำ{thai_date_str}
                </td>
            </tr>
            <tr>
    """
    for i, col in enumerate(cols):
        bg = "#FFFFFF" if i == 0 else get_head_color_hex(i - 1, DAY_OF_WEEK)
        col_width = "69px"
        html += f"<th style='background-color: {bg}; color: #333; border: 1px solid #ddd; padding: 2px; font-size: 15px; font-weight: bold; white-space: nowrap; height: 40px; width: {col_width}; min-width: {col_width}; max-width: {col_width}; overflow: hidden;'>{col}</th>"
    html += "</tr>"
    
    for _, row in df.iterrows():
        html += "<tr style='height: 30px;'>"
        for i, col in enumerate(cols):
            val = row[col]
            style = get_cell_style(val)
            col_width = "69px"
            if i == 0: 
                style = "background-color: #FFFFFF; color: #333; font-weight: bold; border: 1px solid #ddd; padding: 2px; text-align: center; font-size: 15px;"
            if _ == len(df)-1: 
                style = style.replace("font-weight: normal", "font-weight: bold")
            html += f"<td style='{style} width: {col_width}; min-width: {col_width}; max-width: {col_width}; overflow: hidden;'>{val}</td>"
        html += "</tr>"
    html += "</table></div>"
    return html

# ------------------------------------------------------------------
# 6. UI Login & Sidebar
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
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("เข้าสู่ระบบ", use_container_width=True):
                    user = username.lower().strip()
                    if user in users_db and users_db[user]['password'] == password:
                        st.session_state.logged_in = True
                        st.session_state.current_user = users_db[user]
                        st.rerun()
                    else: st.error("❌ Username หรือ Password ไม่ถูกต้อง")
            if st.button("ลืมรหัสผ่าน?", type="secondary", use_container_width=True):
                st.session_state.auth_mode = 'forgot'
                st.rerun()
        else:
            with st.form("forgot_form"):
                st.markdown("<h3 style='text-align: center; margin-top:0;'>กู้คืนรหัสผ่าน</h3>", unsafe_allow_html=True)
                f_user = st.text_input("Username")
                f_email = st.text_input("อีเมล (Email) ที่ลงทะเบียนไว้")
                new_pass = st.text_input("ตั้งรหัสผ่านใหม่", type="password")
                if st.form_submit_button("รีเซ็ตรหัสผ่าน", use_container_width=True):
                    user_clean = f_user.lower().strip()
                    if user_clean in users_db and users_db[user_clean].get('email') == f_email and f_email != "":
                        update_user_password(user_clean, new_pass)
                        st.success("✅ เปลี่ยนรหัสผ่านสำเร็จ! กรุณาเข้าสู่ระบบใหม่")
                        time.sleep(2)
                        st.session_state.auth_mode = 'login'
                        st.rerun()
                    else:
                        st.error("❌ Username หรือ Email ไม่ถูกต้อง หรือยังไม่ได้ผูกอีเมลไว้")
            if st.button("กลับไปหน้าเข้าสู่ระบบ", type="secondary", use_container_width=True):
                st.session_state.auth_mode = 'login'
                st.rerun()

def logout():
    st.session_state.logged_in = False
    st.session_state.current_user = None
    st.rerun()

if not st.session_state.logged_in:
    login_page()
    st.stop()

user_info = st.session_state.current_user
with st.sidebar:
    if os.path.exists("banner.png"):
        st.image("banner.png", use_container_width=True)
    st.markdown(f"### 👤 คุณ {user_info['full_name']} ({user_info['role']})")
    st.button("🚪 ออกจากระบบ", on_click=logout, use_container_width=True)
    st.divider()
    
    menu_options = ["🗓️ ปฏิทินห้องยา & ลงข้อมูล", "👤 ข้อมูลส่วนตัว"]
    if user_info['role'] == 'Admin':
        menu_options.extend(["🔐 อนุมัติคำขอ (Approve)", "📝 สร้างตารางทำงานประจำวัน", "🏃 จัดการพาร์ทไทม์", "👥 จัดการผู้ใช้งาน"])
    
    page = st.radio("เลือกเมนู", menu_options, label_visibility="collapsed")
    
    st.markdown("<br><hr style='margin:0; border-color: rgba(255,255,255,0.1);'><p style='text-align:center; color:rgba(255,255,255,0.4); font-size:12px; margin-top:5px;'>💡 PharmSuk v39</p>", unsafe_allow_html=True)

# ==================================================================
# หน้า 1: ปฏิทินห้องยา & ลงข้อมูล
# ==================================================================
if page == "🗓️ ปฏิทินห้องยา & ลงข้อมูล":
    st.title("PharmSuk 🗓️ ปฏิทินห้องยา & ลงข้อมูล")
    tab1, tab2, tab3 = st.tabs(["📅 ดูปฏิทินรวม", "📝 ฟอร์มลงข้อมูล", "จัดการข้อมูลของคุณ"])
    all_requests = fetch_requests()
    
    leave_queues = {}
    leaves_by_date = {}
    sorted_for_queue = sorted(all_requests, key=lambda x: x.get('created_at', ''))
    for r in sorted_for_queue:
        if "ลางาน" in r['req_type'] and ("ลาพักร้อน" in r['detail'] or "ลากิจ" in r['detail']):
            dk = r['req_date']
            leaves_by_date[dk] = leaves_by_date.get(dk, 0) + 1
            leave_queues[r['id']] = leaves_by_date[dk]
    
    with tab1:
        filter_option = st.selectbox("🔍 กรองข้อมูลบนปฏิทิน:", ["แสดงทั้งหมด", "เฉพาะลางาน", "เฉพาะออกเวรดึก", "เฉพาะออกเวรเย็น", "เฉพาะงานพิเศษ / Back Office", "เฉพาะแจ้งเตือน"])
        st.write("---")
        events = []
        calendar_css = ".fc-day-sat { background-color: rgba(244,246,248,0.5) !important; } .fc-day-sun { background-color: rgba(244,246,248,0.5) !important; } .fc-event { white-space: normal !important; word-wrap: break-word !important; } .fc-event-title { white-space: normal !important; overflow: hidden !important; }"
        
        def get_priority(r):
            rt = r["req_type"]
            if r["user_name"] == "SYSTEM_REQ": return 2
            if "ลางาน" in rt: return 1
            if "แจ้งเตือน" in rt: return 2
            if "งานพิเศษ" in rt: return 3
            if "Back Office" in rt: return 4
            if "ออกเวร" in rt: return 5
            return 99

        sorted_requests = sorted(all_requests, key=get_priority)
        for h_date, h_name in th_holidays.items():
            events.append({"start": h_date.strftime("%Y-%m-%d"), "display": "background", "backgroundColor": "#FFCDD2", "priority": 0})
            events.append({"title": f"🇹🇭 {h_name}", "start": h_date.strftime("%Y-%m-%d"), "backgroundColor": "#E74C3C", "textColor": "white", "allDay": True, "priority": 0})
            
        for req in sorted_requests:
            rt = req["req_type"]
            dt = req["detail"]
            if filter_option == "เฉพาะลางาน" and "ลางาน" not in rt: continue
            if filter_option == "เฉพาะออกเวรดึก" and ("ออกเวร" not in rt or "ดึก" not in dt): continue
            if filter_option == "เฉพาะออกเวรเย็น" and ("ออกเวร" not in rt or "เย็น" not in dt): continue
            if filter_option == "เฉพาะงานพิเศษ / Back Office" and "งานพิเศษ" not in rt and "Back Office" not in rt: continue
            if filter_option == "เฉพาะแจ้งเตือน" and "แจ้งเตือน" not in rt and req["user_name"] != "SYSTEM_REQ": continue

            prio = get_priority(req)
            
            s_time, e_time = "08.30", "16.30"
            times = re.findall(r'\d{2}\.\d{2}', dt)
            if len(times) >= 2: s_time, e_time = times[0], times[1]
            
            start_iso = f"{req['req_date']}T{s_time.replace('.', ':')}:00"
            end_iso = f"{req['req_date']}T{e_time.replace('.', ':')}:00"
            
            is_all_day = False
            if "ลางาน" in rt and ("เต็มวัน" in dt or "ทั้งวัน" in dt):
                is_all_day = True
            
            if rt == "Back Office":
                parts = dt.split('|')
                if len(parts) >= 4:
                    start_dt = datetime.strptime(req["req_date"], "%Y-%m-%d")
                    end_dt = datetime.strptime(parts[1], "%Y-%m-%d")
                    bo_s_t, bo_e_t = parts[2].split('-')[0], parts[2].split('-')[1]
                    bo_days = parts[4].split(',') if len(parts) >= 5 else ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
                    thai_days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
                    
                    curr_dt = start_dt
                    while curr_dt <= end_dt:
                        if thai_days[curr_dt.weekday()] in bo_days:
                            c_date_str = curr_dt.strftime("%Y-%m-%d")
                            events.append({
                                "title": f"💻 {req['user_name']}: {parts[3]}", 
                                "start": f"{c_date_str}T{bo_s_t.replace('.', ':')}:00", 
                                "end": f"{c_date_str}T{bo_e_t.replace('.', ':')}:00", 
                                "allDay": False,
                                "backgroundColor": "#9B59B6", 
                                "priority": prio
                            })
                        curr_dt += timedelta(days=1)
                continue

            if req["user_name"] == "SYSTEM_REQ":
                if "แจ้งเตือนโควตา" in rt:
                    events.append({"title": f"🛑 โควตาลา: {dt}", "start": req["req_date"], "allDay": True, "backgroundColor": "#C0392B", "textColor": "white", "priority": 1})
                else:
                    events.append({"title": f"🚨 {dt}", "start": start_iso if not is_all_day else req["req_date"], "end": end_iso if not is_all_day else None, "allDay": is_all_day, "backgroundColor": "#E67E22", "priority": prio})
                continue

            if req["status"] == "✅ อนุมัติแล้ว": color = "#4CAF50"
            elif req["status"] == "⏳ รออนุมัติ": color = "#FFC107"
            else: continue
            
            q_label = f"[คิว {leave_queues[req['id']]}] " if req['id'] in leave_queues else ""
            events.append({"title": f"{q_label}[{req['status'][0]}] {req['user_name']} - {dt}", "start": start_iso if not is_all_day else req["req_date"], "end": end_iso if not is_all_day else None, "allDay": is_all_day, "backgroundColor": color, "priority": prio})
            
        if filter_option == "แสดงทั้งหมด":
            for pt in st.session_state.pt_daily_db:
                start_iso = f"{pt['date']}T{pt['start'].replace('.', ':')}:00"
                end_iso = f"{pt['date']}T{pt['end'].replace('.', ':')}:00"
                events.append({"title": f"🏃 PT: {pt['name']}", "start": start_iso, "end": end_iso, "allDay": False, "backgroundColor": "#3498DB", "priority": 6})
            
        calendar_options = {"headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth,timeGridWeek,timeGridDay"}, "initialView": "dayGridMonth", "displayEventTime": True, "eventDisplay": "block", "eventOrder": "priority"}
        cal_clicked = calendar(events=events, options=calendar_options, custom_css=calendar_css)
        if cal_clicked.get("eventClick"): st.info(f"🔎 **รายละเอียด:** {cal_clicked['eventClick']['event']['title']}")

    with tab2:
        form_options = ["🏖️ ลางาน", "💼 งานพิเศษ", "💻 งาน Back Office", "🌅 ออกเวร", "🔔 แจ้งเตือน"]
        if user_info['role'] == 'Admin': 
            form_options.insert(4, "🟠 ส่งคนไปแทนห้องยาอื่น")
            form_options.append("⚙️ กำหนดโควตาลา")
            
        main_type = st.radio("เลือกหมวดหมู่:", form_options, horizontal=True)
        st.divider()
        req_user_save = user_info['full_name']
        
        if "ลางาน" in main_type:
            req_date = st.date_input("วันที่:")
            leave_cat = st.selectbox("ประเภทการลา", ["ลาพักร้อน", "ลาไปอบรม module", "ลาป่วย (ฉุกเฉิน)", "ลากิจ"])
            leave_time = st.selectbox("ช่วงเวลา", ["เต็มวัน", "ครึ่งวันเช้า (08.30-13.00)", "ครึ่งวันบ่าย (12.00-16.30)"])
            leave_remark = st.text_input("หมายเหตุ เช่น พาร์ทไทม์ที่มาแทน หรือ การมอบหมายงาน")
            
            detail_str = f"{leave_cat} ({leave_time})"
            if "ลาป่วย" in leave_cat:
                c1, c2 = st.columns(2)
                with c1: s_t = st.selectbox("เริ่มลา", VALID_TIMES, index=0)
                with c2: e_t = st.selectbox("ถึง", VALID_TIMES, index=len(VALID_TIMES)-1)
                detail_str = f"{leave_cat} ({s_t}-{e_t} น.)"
            
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                if leave_remark:
                    detail_str += f" | หมายเหตุ: {leave_remark}"
                add_request(req_user_save, f"ลางาน: {leave_cat}", req_date, detail_str)
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()
                
        elif "Back Office" in main_type:
            task_name = st.text_input("ชื่องาน Back Office")
            c1, c2 = st.columns(2)
            bo_s_date, bo_e_date = c1.date_input("เริ่มวันที่"), c2.date_input("ถึงวันที่")
            
            bo_days = st.multiselect("ทำในวันใดบ้าง", ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"], default=["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"])
            
            sc1, sc2 = st.columns(2)
            bo_s_t, bo_e_t = sc1.selectbox("เวลาเริ่ม", VALID_TIMES, index=0), sc2.selectbox("ถึงเวลา", VALID_TIMES, index=len(VALID_TIMES)-1)
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                if task_name:
                    days_str = ",".join(bo_days)
                    add_request(req_user_save, "Back Office", bo_s_date, f"BO|{bo_e_date.strftime('%Y-%m-%d')}|{bo_s_t}-{bo_e_t}|{task_name}|{days_str}")
                    st.success("✅ บันทึกข้อมูลสำเร็จ!")
                    time.sleep(1)
                    st.rerun()
            
        elif "งานพิเศษ" in main_type:
            req_date = st.date_input("วันที่:")
            task_cat = st.selectbox("เลือกงานพิเศษ", ["หาหมอ", "ประชุม", "สอน Robot", "อื่นๆ"])
            custom_task = st.text_input("ระบุ (ถ้าเลือกอื่นๆ)")
            c1, c2 = st.columns(2)
            with c1: s_t = st.selectbox("เริ่ม", VALID_TIMES, index=0)
            with c2: e_t = st.selectbox("ถึง", VALID_TIMES, index=len(VALID_TIMES)-1)
            final_task = custom_task if task_cat == "อื่นๆ" else task_cat
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request(req_user_save, "งานพิเศษ", req_date, f"งานพิเศษ: {final_task} ({s_t}-{e_t} น.)")
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()
            
        elif "ออกเวร" in main_type:
            req_date = st.date_input("วันที่:")
            shift_cat = st.radio("ประเภท", ["ออกเวรดึก (พัก 8.30-10.30 น.)", "ออกเวรเย็น"])
            if "ออกเวรดึก" in shift_cat: detail_str = "ออกเวรดึก (พักเช้า 8.30-10.30 น.)"
            else: detail_str = f"ออกเวรเย็น (ห้องยา: {st.selectbox('สถานที่', ['ชั้น 1', 'ชั้นอื่นตึกพระเทพ', 'ตึกเก่า'])})"
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request(req_user_save, "ออกเวร", req_date, detail_str)
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()
            
        elif "แทนห้องยาอื่น" in main_type:
            req_date = st.date_input("วันที่:")
            replace_loc = st.text_input("สถานที่ไปแทน")
            c1, c2 = st.columns(2)
            with c1: r_s = st.selectbox("เริ่ม", VALID_TIMES, index=0)
            with c2: r_e = st.selectbox("ถึง", VALID_TIMES, index=len(VALID_TIMES)-1)
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request("SYSTEM_REQ", "แทนห้องยาอื่น", req_date, f"ไปแทนที่: {replace_loc} ({r_s}-{r_e} น.)")
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()
                
        elif "กำหนดโควตาลา" in main_type:
            req_date = st.date_input("วันที่:")
            quota_num = st.number_input("จำนวนเภสัชที่อนุญาตให้ลาได้", min_value=0, max_value=10, value=1)
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request("SYSTEM_REQ", "แจ้งเตือนโควตา", req_date, f"เภสัช = {quota_num}")
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()
            
        elif "แจ้งเตือน" in main_type:
            req_date = st.date_input("วันที่:")
            detail_str = f"📢 แจ้งเตือน: {st.text_area('ข้อความ')}"
            if st.button("บันทึกข้อมูลลงปฏิทิน", type="primary"):
                add_request(req_user_save, "แจ้งเตือน / ส่งเคส", req_date, detail_str)
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()

    with tab3:
        st.subheader("📋 รายการข้อมูลของคุณ")
        my_reqs = [r for r in all_requests if r["user_name"] == user_info['full_name'] or (user_info['role'] == 'Admin' and r["user_name"] == "SYSTEM_REQ")]
        
        sub_tab1, sub_tab2 = st.tabs(["⏳ กำลังดำเนินการ", "🗄️ ประวัติของฉัน"])
        
        with sub_tab1:
            pending_my_reqs = [r for r in my_reqs if "รออนุมัติ" in r['status']]
            if not pending_my_reqs:
                st.info("ไม่มีคำขอที่กำลังดำเนินการในขณะนี้")
            for r in pending_my_reqs:
                with st.container(border=True):
                    cols = st.columns([1, 6, 2])
                    cols[0].markdown(f"<h2 style='text-align: center; margin:0;'>⏳</h2>", unsafe_allow_html=True)
                    cols[1].markdown(f"**{r['req_type']}** | วันที่: {r['req_date']}<br><span style='color:gray'>{r['detail']}</span>", unsafe_allow_html=True)
                    if cols[2].button("🗑️ ยกเลิกคำขอ", key=f"del_pen_{r['id']}", use_container_width=True):
                        update_request_status(r['id'], "🗑️ ถูกยกเลิก")
                        st.rerun()
        
        with sub_tab2:
            history_my_reqs = [r for r in my_reqs if "รออนุมัติ" not in r['status']]
            if not history_my_reqs:
                st.info("ไม่มีประวัติคำขอ")
            else:
                today_str = datetime.now().strftime("%Y-%m-%d")
                
                future_reqs = [r for r in history_my_reqs if r['req_date'] >= today_str and "อนุมัติแล้ว" in r['status']]
                past_reqs = [r for r in history_my_reqs if r not in future_reqs]
                
                st.markdown("**รายการที่กำลังจะมาถึง (วันนี้และอนาคต)**")
                if future_reqs:
                    with st.container(height=300):
                        for r in future_reqs:
                            c1, c2 = st.columns([8, 2])
                            c1.markdown(f"**✅ {r['req_type']}** | {r['req_date']} | {r['detail']}")
                            if c2.button("🗑️ ยกเลิกคำขอ", key=f"cancel_fut_{r['id']}", use_container_width=True):
                                update_request_status(r['id'], "🗑️ ถูกยกเลิก")
                                st.rerun()
                            st.divider()
                else:
                    st.markdown("<span style='color:gray'>- ไม่มีรายการ -</span>", unsafe_allow_html=True)
                        
                st.markdown("<br>", unsafe_allow_html=True)
                with st.expander("📁 ดูประวัติรายการที่ผ่านมาแล้ว"):
                    if past_reqs:
                        for r in past_reqs:
                            status_icon = "✅" if "อนุมัติแล้ว" in r['status'] else "❌" if "ไม่อนุมัติ" in r['status'] else "🗑️"
                            status_text = r['status']
                            st.markdown(f"**{status_icon} {r['req_type']}** | {r['req_date']} | {r['detail']} | สถานะ: {status_text}")
                            st.divider()
                    else:
                        st.markdown("<span style='color:gray'>- ไม่มีรายการ -</span>", unsafe_allow_html=True)

# ==================================================================
# เมนูใหม่: 👤 ข้อมูลส่วนตัว (My Profile)
# ==================================================================
elif page == "👤 ข้อมูลส่วนตัว":
    st.title("👤 ข้อมูลส่วนตัว (My Profile)")
    
    t1, t2 = st.tabs(["📝 ข้อมูลทั่วไป", "🔑 เปลี่ยนรหัสผ่าน"])
    with t1:
        with st.form("profile_form"):
            c1, c2 = st.columns(2)
            real_name = c1.text_input("ชื่อจริง", value=user_info.get('real_name', ''))
            surname = c2.text_input("นามสกุล", value=user_info.get('surname', ''))
            email = st.text_input("อีเมล (สำหรับใช้รีเซ็ตรหัสผ่าน)", value=user_info.get('email', ''))
            position = st.text_input("ตำแหน่งงาน", value=user_info.get('position', ''))
            
            st.info(f"**Username:** {user_info['username']} | **ชื่อในตาราง:** {user_info['full_name']} | **สิทธิ์:** {user_info['role']}")
            
            if st.form_submit_button("บันทึกข้อมูล", type="primary"):
                update_user_profile(user_info['username'], real_name, surname, email, position)
                st.success("✅ บันทึกข้อมูลสำเร็จ! (กรุณาเข้าสู่ระบบใหม่เพื่อให้ข้อมูลอัปเดต)")
                
    with t2:
        with st.form("password_form"):
            old_p = st.text_input("รหัสผ่านเดิม", type="password")
            new_p = st.text_input("รหัสผ่านใหม่", type="password")
            c_new_p = st.text_input("ยืนยันรหัสผ่านใหม่", type="password")
            if st.form_submit_button("เปลี่ยนรหัสผ่าน", type="primary"):
                if old_p != user_info['password']:
                    st.error("❌ รหัสผ่านเดิมไม่ถูกต้อง")
                elif new_p != c_new_p:
                    st.error("❌ รหัสผ่านใหม่ไม่ตรงกัน")
                else:
                    update_user_password(user_info['username'], new_p)
                    st.success("✅ เปลี่ยนรหัสผ่านสำเร็จ!")

# ==================================================================
# หน้า 2: อนุมัติคำขอ
# ==================================================================
elif page == "🔐 อนุมัติคำขอ (Approve)":
    st.title("🔐 จัดการคำขอลางานและประวัติ")
    
    all_requests = fetch_requests()
    leave_queues = {}
    leaves_by_date = {}
    sorted_for_queue = sorted(all_requests, key=lambda x: x.get('created_at', ''))
    for r in sorted_for_queue:
        if "ลางาน" in r['req_type'] and ("ลาพักร้อน" in r['detail'] or "ลากิจ" in r['detail']):
            dk = r['req_date']
            leaves_by_date[dk] = leaves_by_date.get(dk, 0) + 1
            leave_queues[r['id']] = leaves_by_date[dk]
            
    st.subheader("📌 คำขอที่รอการอนุมัติ (Action Required)")
    pending_reqs = [r for r in all_requests if r["status"] == "⏳ รออนุมัติ"]
    if not pending_reqs:
        st.success("🎉 ไม่มีคำขอที่รอการอนุมัติในขณะนี้")
    else:
        for req in pending_reqs:
            with st.container(border=True):
                created_str = req.get('created_at', '')[:19].replace('T', ' ')
                q_str = f" 🏷️ **[คิวที่ {leave_queues[req['id']]}]**" if req['id'] in leave_queues else ""
                
                st.markdown(f"**ผู้ขอ:** {req['user_name']} | **วันที่ขอลา:** {req['req_date']}{q_str} | **เวลาส่งคำขอ:** {created_str}")
                st.markdown(f"**รายละเอียด:** {req['detail']}")
                
                c1, c2, _ = st.columns([2, 2, 6])
                if c1.button("✅ อนุมัติ", key=f"app_{req['id']}", use_container_width=True):
                    update_request_status(req['id'], "✅ อนุมัติแล้ว")
                    st.rerun()
                if c2.button("❌ ปฏิเสธ", key=f"rej_{req['id']}", use_container_width=True):
                    update_request_status(req['id'], "❌ ไม่อนุมัติ")
                    st.rerun()

    st.divider()
    
    st.subheader("🗄️ ประวัติการอนุมัติทั้งหมด (History & Export)")
    history_reqs = [r for r in all_requests if r["status"] != "⏳ รออนุมัติ"]
    
    if history_reqs:
        df_history = pd.DataFrame(history_reqs)
        df_history['คิว'] = df_history['id'].map(lambda x: leave_queues.get(x, '-'))
        df_history['เวลาส่งคำขอ'] = df_history['created_at'].str[:19].str.replace('T', ' ')
        df_history = df_history[['req_date', 'user_name', 'req_type', 'detail', 'status', 'คิว', 'เวลาส่งคำขอ', 'id']]
        df_history.columns = ['วันที่', 'ผู้ขอ', 'ประเภท', 'รายละเอียด', 'สถานะ', 'คิว', 'เวลาส่งคำขอ', 'ID']
        
        col_f1, col_f2, col_f3 = st.columns(3)
        filter_name = col_f1.selectbox("👤 ค้นหาตามชื่อ", ["ทั้งหมด"] + sorted(list(df_history['ผู้ขอ'].unique())))
        filter_month = col_f2.selectbox("📅 ค้นหาตามเดือน", ["ทั้งหมด"] + sorted(list(df_history['วันที่'].str[:7].unique()), reverse=True))
        filter_type = col_f3.selectbox("🏷️ ค้นหาตามประเภท", ["ทั้งหมด"] + sorted(list(df_history['ประเภท'].unique())))
        
        filtered_df = df_history.copy()
        if filter_name != "ทั้งหมด": filtered_df = filtered_df[filtered_df['ผู้ขอ'] == filter_name]
        if filter_month != "ทั้งหมด": filtered_df = filtered_df[filtered_df['วันที่'].str.startswith(filter_month)]
        if filter_type != "ทั้งหมด": filtered_df = filtered_df[filtered_df['ประเภท'] == filter_type]
        
        display_df = filtered_df.drop(columns=['ID'])
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        col_a1, col_a2 = st.columns(2)
        
        output_hist = io.BytesIO()
        with pd.ExcelWriter(output_hist, engine='openpyxl') as writer:
            display_df.to_excel(writer, index=False, sheet_name='History')
        excel_hist_data = output_hist.getvalue()
        
        col_a1.download_button("📥 ดาวน์โหลดประวัติ (Excel)", data=excel_hist_data, file_name=f"Leave_History_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        
        with col_a2.popover("🗑️ จัดการฐานข้อมูล (Admin Only)"):
            st.write("ลบข้อมูลที่เก่ากว่า 6 เดือน (ทำความสะอาดฐานข้อมูล)")
            if st.button("ยืนยันการลบข้อมูลเก่า", type="primary"):
                six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
                to_delete = [r['id'] for r in history_reqs if r['req_date'] < six_months_ago]
                for r_id in to_delete:
                    delete_request(r_id)
                st.toast(f"✅ ลบข้อมูลเก่าสำเร็จ {len(to_delete)} รายการ!")
                time.sleep(1)
                st.rerun()
    else:
        st.info("ไม่มีประวัติข้อมูล")

# ==================================================================
# หน้า 3: ⚙️ สร้างตารางทำงานประจำวัน
# ==================================================================
elif page == "📝 สร้างตารางทำงานประจำวัน":
    st.title("📝 สร้างตารางทำงานประจำวัน")
    
    col_t1, col_t2 = st.columns([7, 3])
    tz_bkk = timedelta(hours=7)
    tomorrow_date = (datetime.utcnow() + tz_bkk).date() + timedelta(days=1)
    
    with col_t1:
        target_date = st.date_input("เลือกวันที่ต้องการจัดตาราง", value=tomorrow_date, key="ai_target_date")
    target_date_str = target_date.strftime("%Y-%m-%d")
    
    target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    IS_MWF = target_dt.weekday() in [0, 2, 4]
    DAY_OF_WEEK = 'Wed_Fri' if target_dt.weekday() in [2, 4] else 'Normal'
    
    with col_t2:
        st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 ดึงข้อมูลล่าสุดจากปฏิทิน", use_container_width=True):
            force_sync_dashboard(target_date_str, fetch_requests())
            st.toast("ดึงข้อมูลล่าสุดเรียบร้อย! 🔄")
            st.rerun()
        
    all_requests = fetch_requests()
    approved_today = [r for r in all_requests if r["req_date"] == target_date_str and r["status"] == "✅ อนุมัติแล้ว"]
    pts_today = [pt for pt in st.session_state.pt_daily_db if pt["date"] == target_date_str]
    current_hash = len(all_requests) + len(pts_today)

    if 'dash_date' not in st.session_state or st.session_state.dash_date != target_date_str or st.session_state.get('dash_hash', -1) != current_hash:
        force_sync_dashboard(target_date_str, all_requests)

    st.markdown("---")
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("🏖️ ผู้ลางาน", f"{len(st.session_state.dash_leaves)} คน")
    col_m2.metric("🏃 พาร์ทไทม์", f"{len(st.session_state.dash_pts)} คน")
    col_m3.metric("🟠 ไปแทน", f"{len(st.session_state.dash_subs)} คน")
    no_disp_count = sum(1 for l in st.session_state.dash_locks if l['type'] == 'no_dispense')
    col_m4.metric("🚫 เว้นจ่ายยา", f"{no_disp_count} คน")
    
    tab_l, tab_pt, tab_t, tab_bo, tab_sh, tab_sub, tab_lock = st.tabs([
        "🏖️ ลา", "🏃 PT", "💼 พิเศษ", "💻 Back Office", "🌅 ดึก/เย็น", "🟠 ไปแทน", "🔒 ล็อก/เว้น"
    ])
    
    with tab_l:
        for idx, l in enumerate(st.session_state.dash_leaves):
            c1, c2 = st.columns([8, 2])
            l_str = f"({l['start']}-{l['end']} น.)" if isinstance(l['leave_type'], tuple) else ""
            c1.info(f"👤 {l['user_name']} -> {l['leave_type'] if isinstance(l['leave_type'], str) else 'ลาฉุกเฉิน'} {l_str}")
            if c2.button("❌ ลบ", key=f"d_l_{idx}"):
                st.session_state.dash_leaves.pop(idx)
                st.rerun()
        with st.expander("➕ เพิ่มการลาหน้างาน"):
            add_l_u = st.selectbox("เภสัชกร", base_pharmacist_list, key="al_u")
            add_l_t = st.selectbox("ประเภทการลา", ["เต็มวัน", "ครึ่งวันเช้า (08.30-13.00)", "ครึ่งวันบ่าย (12.00-16.30)", "ลาป่วยฉุกเฉิน"], key="al_t")
            add_l_s, add_l_e = "08.30", "16.30"
            if add_l_t == "ลาป่วยฉุกเฉิน":
                cl1, cl2 = st.columns(2)
                with cl1: add_l_s = st.selectbox("เริ่มลา", VALID_TIMES, index=0, key="al_s")
                with cl2: add_l_e = st.selectbox("สิ้นสุด", VALID_TIMES, index=len(VALID_TIMES)-1, key="al_e")
            if st.button("บันทึกเพิ่มการลา", type="primary"):
                l_code = "ทั้งวัน" if add_l_t == "เต็มวัน" else "เช้า" if "เช้า" in add_l_t else "บ่าย" if "บ่าย" in add_l_t else "ฉุกเฉิน"
                st.session_state.dash_leaves.append({"user_name": add_l_u, "leave_type": l_code, "start": add_l_s, "end": add_l_e})
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()

    with tab_pt:
        for idx, pt in enumerate(st.session_state.dash_pts):
            c1, c2 = st.columns([8, 2])
            c1.success(f"🏃 {pt['name']} ({pt['start']}-{pt['end']} น.) | {pt['break_type']} {f'({pt['break_time']})' if pt['break_time'] else ''}")
            if c2.button("❌ ลบ", key=f"d_p_{idx}"):
                st.session_state.dash_pts.pop(idx)
                st.rerun()
        with st.expander("➕ เพิ่มพาร์ทไทม์หน้างาน"):
            pt_name = st.text_input("ชื่อเล่น PT", key="ap_n")
            c1, c2 = st.columns(2)
            with c1: pt_start = st.selectbox("เริ่ม", VALID_TIMES, index=0, key="ap_s")
            with c2: pt_end = st.selectbox("ถึงเวลา", VALID_TIMES, index=len(VALID_TIMES)-1, key="ap_e")
            pt_b_type = st.radio("การพัก", ["พัก 1 ชั่วโมง", "พักครึ่งชั่วโมง", "ไม่พักเลย"], horizontal=True, key="ap_bt")
            pt_b_time = st.selectbox("เวลาเริ่มพัก", VALID_TIMES, key="ap_btime") if pt_b_type != "ไม่พักเลย" else None
            if st.button("บันทึกเพิ่ม PT", type="primary"):
                if pt_name:
                    st.session_state.dash_pts.append({"name": pt_name, "start": pt_start, "end": pt_end, "break_type": pt_b_type, "break_time": pt_b_time})
                    st.success("✅ บันทึกข้อมูลสำเร็จ!")
                    time.sleep(1)
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
            with c1: add_t_s = st.selectbox("เริ่ม", VALID_TIMES, index=0, key="at_s")
            with c2: add_t_e = st.selectbox("ถึงเวลา", VALID_TIMES, index=len(VALID_TIMES)-1, key="at_e")
            if st.button("บันทึกเพิ่มงานพิเศษ", type="primary") and add_t_n:
                st.session_state.dash_tasks.append({"user_name": add_t_u, "task_name": add_t_n, "start": add_t_s, "end": add_t_e})
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()

    with tab_bo:
        for idx, bo in enumerate(st.session_state.dash_bo):
            c1, c2, c3 = st.columns([3, 4, 3])
            c1.markdown("<span style='font-size:14px; color:#555;'>ผู้รับผิดชอบ</span>", unsafe_allow_html=True)
            bo['user_name'] = c1.selectbox("ผู้รับผิดชอบ", base_pharmacist_list, index=safe_idx(base_pharmacist_list, bo['user_name'], 0), key=f"bo_u_{idx}", label_visibility="collapsed")
            c2.markdown("<span style='font-size:14px; color:#555;'>ชื่องาน</span>", unsafe_allow_html=True)
            bo['task_name'] = c2.text_input("ชื่องาน", value=bo['task_name'], key=f"bo_t_{idx}", label_visibility="collapsed")
            
            sc1, sc2, sc3 = c3.columns([4,4,2])
            sc1.markdown("<span style='font-size:14px; color:#555;'>เวลาเริ่ม</span>", unsafe_allow_html=True)
            bo['start'] = sc1.selectbox("เริ่ม", VALID_TIMES, index=safe_idx(VALID_TIMES, bo['start'], 0), key=f"bo_s_{idx}", label_visibility="collapsed")
            sc2.markdown("<span style='font-size:14px; color:#555;'>สิ้นสุด</span>", unsafe_allow_html=True)
            bo['end'] = sc2.selectbox("ถึงเวลา", VALID_TIMES, index=safe_idx(VALID_TIMES, bo['end'], len(VALID_TIMES)-1), key=f"bo_e_{idx}", label_visibility="collapsed")
            sc3.markdown("<span style='font-size:14px'>&nbsp;</span>", unsafe_allow_html=True)
            if sc3.button("❌ ลบ", key=f"del_bo_{idx}"):
                st.session_state.dash_bo.pop(idx)
                st.rerun()
                
        with st.expander("➕ เพิ่มงาน Back Office สำหรับวันนี้"):
            bo_u = st.selectbox("เภสัชกร", base_pharmacist_list, key="nbo_u")
            bo_t = st.text_input("ชื่องาน Back Office", key="nbo_t")
            c1, c2 = st.columns(2)
            with c1: bo_s = st.selectbox("เริ่ม", VALID_TIMES, index=0, key="nbo_s")
            with c2: bo_e = st.selectbox("ถึงเวลา", VALID_TIMES, index=len(VALID_TIMES)-1, key="nbo_e")
            if st.button("บันทึกเพิ่ม Back Office", type="primary") and bo_t:
                st.session_state.dash_bo.append({"user_name": bo_u, "task_name": bo_t, "start": bo_s, "end": bo_e})
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()

    with tab_sh:
        for idx, sh in enumerate(st.session_state.dash_shifts):
            c1, c2, c3 = st.columns([4, 4, 2])
            if sh['shift_type'] == 'ออกเวรดึก':
                c1.error(f"🌅 {sh['user_name']} -> **ออกเวรดึก**")
                with c2:
                    sc1, sc2 = st.columns(2)
                    sh['start'] = sc1.selectbox("เริ่มพัก", VALID_TIMES, index=safe_idx(VALID_TIMES, sh.get('start', '08.30'), 0), key=f"d_sh_s_{idx}", label_visibility="collapsed")
                    sh['end'] = sc2.selectbox("ถึงเวลา", VALID_TIMES, index=safe_idx(VALID_TIMES, sh.get('end', '10.30'), 4), key=f"d_sh_e_{idx}", label_visibility="collapsed")
            else:
                c1.info(f"🌆 {sh['user_name']} -> **ออกเวรเย็น**")
                with c2:
                    sc1, sc2 = st.columns(2)
                    time_opts = ["15.00-15.30", "15.30-16.00", "16.00-16.30"]
                    sh['time_slot'] = sc1.selectbox("รอบพักทานข้าว", time_opts, index=safe_idx(time_opts, sh.get('time_slot', '15.00-15.30'), 0), key=f"d_sh_ts_{idx}", label_visibility="collapsed")
                    room_opts = ["ชั้น 1", "ตึกพระเทพ", "ตึกเก่า"]
                    sh['room'] = sc2.selectbox("เวรตึก", room_opts, index=safe_idx(room_opts, sh.get('room', 'ชั้น 1'), 0), key=f"d_sh_r_{idx}", label_visibility="collapsed")
                    
            if c3.button("❌ ลบ", key=f"d_sh_{idx}", use_container_width=True):
                st.session_state.dash_shifts.pop(idx)
                st.rerun()
                
        with st.expander("➕ เพิ่มการออกเวรหน้างาน"):
            add_sh_u = st.selectbox("เภสัชกร", base_pharmacist_list, key="ash_u")
            add_sh_t = st.radio("ประเภท", ["ออกเวรดึก", "ออกเวรเย็น"], horizontal=True, key="ash_t")
            add_sh_s, add_sh_e, add_sh_ts, add_sh_r = "08.30", "10.30", "15.00-15.30", "ชั้น 1"
            if add_sh_t == "ออกเวรดึก":
                sc1, sc2 = st.columns(2)
                with sc1: add_sh_s = st.selectbox("เริ่มพัก", VALID_TIMES, index=0)
                with sc2: add_sh_e = st.selectbox("ถึงเวลา", VALID_TIMES, index=4) 
            else:
                sc1, sc2 = st.columns(2)
                with sc1: add_sh_ts = st.selectbox("รอบพักทานข้าว", ["15.00-15.30", "15.30-16.00", "16.00-16.30"])
                with sc2: add_sh_r = st.selectbox("เวรตึก", ["ชั้น 1", "ตึกพระเทพ", "ตึกเก่า"])
            if st.button("บันทึกเพิ่มออกเวร", type="primary"):
                st.session_state.dash_shifts.append({"user_name": add_sh_u, "shift_type": add_sh_t, "room": add_sh_r, "start": add_sh_s, "end": add_sh_e, "time_slot": add_sh_ts})
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()

    with tab_sub:
        sys_reqs = [r for r in all_requests if r["req_date"] == target_date_str and r["user_name"] == "SYSTEM_REQ"]
        if sys_reqs:
            for r in sys_reqs: st.warning(f"🚨 แจ้งเตือน: {r['detail']}")
            st.write("---")
        if st.session_state.dash_subs:
            for idx, s in enumerate(st.session_state.dash_subs):
                c1, c2 = st.columns([8, 2])
                c1.info(f"✔️ ส่ง **{s['user_name']}** ไป {s['task_name']} ({s['start']}-{s['end']} น.)")
                if c2.button("❌ ลบ", key=f"d_s_{idx}"):
                    st.session_state.dash_subs.pop(idx)
                    st.rerun()
        with st.expander("➕ เพิ่มคนไปแทนห้องอื่น"):
            sub_u = st.selectbox("เภสัชกรที่จะส่งไป", base_pharmacist_list, key="sub_u")
            sub_loc = st.text_input("สถานที่ไปแทน", placeholder="เช่น OPD ชั้น 3", key="sub_loc")
            c1, c2 = st.columns(2)
            with c1: sub_s = st.selectbox("เริ่มเวลา", VALID_TIMES, index=0, key="sub_s")
            with c2: sub_e = st.selectbox("ถึงเวลา", VALID_TIMES, index=len(VALID_TIMES)-1, key="sub_e")
            if st.button("บันทึกส่งคนไปแทน", type="primary") and sub_loc:
                st.session_state.dash_subs.append({"user_name": sub_u, "task_name": f"แทน({sub_loc})", "start": sub_s, "end": sub_e})
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()

    with tab_lock:
        for idx, l in enumerate(st.session_state.dash_locks):
            c1, c2, c3 = st.columns([3, 4, 3])
            if l['type'] == 'task':
                c1.info(f"🔒 {l['user_name']}")
                c2.info(f"หน้าที่: {l['task_name']} ({l['start']}-{l['end']} น.)")
            elif l['type'] == 'break':
                c1.success(f"☕ {l['user_name']}")
                c2.success(f"เวลาพัก: ({l['start']}-{l['end']} น.)")
            elif l['type'] == 'no_dispense':
                c1.error(f"🚫 {l['user_name']}")
                c2.error("เว้นการจ่ายยา (ทั้งวัน)")
                
            if c3.button("❌ ลบ", key=f"del_l_{idx}"):
                st.session_state.dash_locks.pop(idx)
                st.rerun()
        with st.expander("➕ เพิ่มการล็อก/เว้น"):
            l_u = st.selectbox("เภสัชกร", base_pharmacist_list, key="l_u")
            l_t = st.radio("ประเภท", ["ล็อกภาระงานหลัก", "ล็อกเวลาพัก", "เว้นการจ่ายยา"], horizontal=True)
            if l_t == "ล็อกภาระงานหลัก":
                base_m_tasks = [f"จ่ายยา_{i}" for i in range(4, 12)] + [f"Ver_{i}" for i in range(1, 11)] + [f"PS_{i}" for i in range(1, 11)] + ["Match_C", "Match_C2", "Matching"]
                display_m_tasks = [t.replace('_', ' ') for t in base_m_tasks]
                l_task_display = st.selectbox("เลือกภาระงานหลัก", display_m_tasks, key="l_task")
                l_task = base_m_tasks[display_m_tasks.index(l_task_display)]
                
                c1, c2 = st.columns(2)
                l_s = c1.selectbox("เริ่ม", VALID_TIMES, index=0, key="l_s")
                l_e = c2.selectbox("ถึงเวลา", VALID_TIMES, index=2, key="l_e")
                if st.button("บันทึกการล็อก", type="primary"):
                    st.session_state.dash_locks.append({"user_name": l_u, "type": "task", "task_name": l_task, "start": l_s, "end": l_e})
                    st.success("✅ บันทึกข้อมูลสำเร็จ!")
                    time.sleep(1)
                    st.rerun()
            elif l_t == "ล็อกเวลาพัก":
                if DAY_OF_WEEK == 'Wed_Fri': b_opts = ["11.30", "12.30", "13.30"]
                else: b_opts = ["11.00", "12.00", "13.00"]
                c1, c2 = st.columns(2)
                l_s = c1.selectbox("เริ่มพัก", b_opts, key="lb_s")
                if st.button("บันทึกการล็อก", type="primary"):
                    e_idx = safe_idx(VALID_TIMES, l_s, 6) + 2
                    l_e = VALID_TIMES[e_idx] if e_idx < len(VALID_TIMES) else "16.30"
                    st.session_state.dash_locks.append({"user_name": l_u, "type": "break", "start": l_s, "end": l_e})
                    st.success("✅ บันทึกข้อมูลสำเร็จ!")
                    time.sleep(1)
                    st.rerun()
            elif l_t == "เว้นการจ่ายยา":
                if st.button("บันทึกการล็อก", type="primary"):
                    st.session_state.dash_locks.append({"user_name": l_u, "type": "no_dispense"})
                    st.success("✅ บันทึกข้อมูลสำเร็จ!")
                    time.sleep(1)
                    st.rerun()

    st.divider()
    
    if st.button("🚀 ประมวลผลสมองกล AI สร้างตาราง", type="primary", use_container_width=True):
        with st.spinner("🤖 AI กำลังคำนวณตำแหน่งและบล็อกเวลา ทะลุทะลวง 10,000 สมการ..."):
            
            custom_dict = {(t['user_name'], t['start'], t['end']): t['task_name'] for t in st.session_state.dash_tasks + st.session_state.dash_subs + st.session_state.dash_bo}
            for s in st.session_state.dash_shifts:
                if s['shift_type'] == 'ออกเวรดึก': custom_dict[(s['user_name'], s.get('start', '08.30'), s.get('end', '10.30'))] = "ออกเวรดึก"
                if s['shift_type'] == 'ออกเวรเย็น': custom_dict[(s['user_name'], s.get('time_slot', '15.00-15.30').split('-')[0], s.get('time_slot', '15.00-15.30').split('-')[1])] = "ออกเวรเย็น"
            
            mapped_pts = []
            for pt in st.session_state.dash_pts:
                has_b = True if pt['break_type'] != "ไม่พักเลย" else False
                mapped_pts.append({'name': pt['name'], 'start': pt['start'], 'end': pt['end'], 'has_break': has_b})

            leaves_dict = {}
            for l in st.session_state.dash_leaves:
                if isinstance(l['leave_type'], tuple):
                    leaves_dict[l['user_name']] = l['leave_type']
                elif l['leave_type'] == 'ฉุกเฉิน':
                    leaves_dict[l['user_name']] = (l['start'], l['end'])
                else:
                    leaves_dict[l['user_name']] = l['leave_type']

            df_schedule, status, msg = generate_schedule(
                DAY_OF_WEEK, 
                leaves_dict,
                custom_dict,
                mapped_pts,
                {l['user_name']: (0 if l['start'] in ['11.00','11.30'] else 1 if l['start'] in ['12.00','12.30'] else 2) for l in st.session_state.dash_locks if l['type'] == 'break'},
                {(l['user_name'], l['start'], l['end']): l['task_name'] for l in st.session_state.dash_locks if l['type'] == 'task'},
                [l['user_name'] for l in st.session_state.dash_locks if l['type'] == 'no_dispense'],
                IS_MWF
            )
            
            if df_schedule is not None:
                st.session_state.gen_df = df_schedule
                html_data = build_html_table(df_schedule, target_date_str, DAY_OF_WEEK)
                st.session_state.gen_html = html_data
                
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_schedule.to_excel(writer, index=False, sheet_name='ตารางเวร', startrow=2)
                    ws = writer.sheets['ตารางเวร']
                    ws.sheet_properties.pageSetUpPr.fitToPage = True
                    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
                    ws.page_setup.paperSize = ws.PAPERSIZE_A4
                    ws.page_setup.fitToWidth = 1 
                    ws.page_setup.fitToHeight = 1 
                    ws.print_options.horizontalCentered = True
                    ws.print_options.verticalCentered = True
                    cm_to_inch = 0.4 / 2.54
                    ws.page_margins = PageMargins(left=cm_to_inch, right=cm_to_inch, top=cm_to_inch, bottom=cm_to_inch, header=0, footer=0)
                    
                    thai_date_str = get_thai_date(target_dt)
                    ws['A1'] = "ตารางปฏิบัติงานเภสัชกร ห้องยาชั้น 1 อาคารสมเด็จพระเทพรัตน์"
                    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(df_schedule.columns))
                    ws['A1'].font = Font(name='TH Sarabun New', size=20, bold=True)
                    ws['A1'].alignment = Alignment(horizontal="center", vertical="center")
                    
                    ws['A2'] = f"ประจำ{thai_date_str}"
                    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(df_schedule.columns))
                    ws['A2'].font = Font(name='TH Sarabun New', size=18, bold=True)
                    ws['A2'].alignment = Alignment(horizontal="center", vertical="center")
                    
                    ws.row_dimensions[1].height = 35 
                    ws.row_dimensions[2].height = 25 
                    ws.row_dimensions[3].height = 40 
                    
                    center_aligned_text = Alignment(horizontal="center", vertical="center")
                    for col_idx in range(1, len(df_schedule.columns) + 1):
                        ws.column_dimensions[get_column_letter(col_idx)].width = 10.67 
                        
                        for row_idx in range(3, len(df_schedule) + 4): 
                            if row_idx > 3:
                                ws.row_dimensions[row_idx].height = 30 
                                
                            cell = ws.cell(row=row_idx, column=col_idx)
                            cell.alignment = center_aligned_text
                            cell.border = thin_border
                            val_str = str(cell.value) if cell.value is not None else ""
                            
                            if row_idx == 3 and col_idx >= 2:
                                c_name = get_header_color(col_idx - 2, DAY_OF_WEEK)
                                if c_name: cell.fill = header_color_map[c_name]
                                cell.font = Font(name='TH Sarabun New', size=16, bold=True)
                            elif row_idx > 3 and col_idx >= 2:
                                bg_hex = get_cell_bg_hex(val_str)
                                if bg_hex and bg_hex != "F5F5F5" and val_str != "ลา":
                                    cell.fill = PatternFill(start_color=bg_hex, end_color=bg_hex, fill_type='solid')
                                
                                if 'Match' in val_str and ('C' in val_str or 'C2' in val_str):
                                    cell.font = Font(name='TH Sarabun New', size=16, color='FF0000', bold=True)
                                else:
                                    cell.font = Font(name='TH Sarabun New', size=16, bold=False)
                            if col_idx == 1 or row_idx == len(df_schedule) + 3:
                                cell.font = Font(name='TH Sarabun New', size=16, bold=True)

                st.session_state.gen_excel = output.getvalue()
                st.session_state.show_balloons = True
                st.rerun() 
            else: st.error(f"⚠️ {msg}")

    if st.session_state.gen_df is not None:
        if st.session_state.show_balloons:
            st.balloons()
            st.success("🎉 AI คำนวณตารางเสร็จสมบูรณ์!")
            st.session_state.show_balloons = False
            
        st.markdown("### 📥 บันทึกผลลัพธ์")
        col_dl1, col_dl2 = st.columns(2)
        col_dl1.download_button(
            label="📊 ดาวน์โหลดไฟล์ Excel", 
            data=st.session_state.gen_excel, 
            file_name=f"Schedule_{target_date_str}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
            use_container_width=True
        )
        if col_dl2.button("💾 บันทึกตารางลง Database", use_container_width=True):
            if save_schedule_to_db(target_date_str, st.session_state.gen_html): 
                st.toast("บันทึกตารางสำเร็จ! ✅")
            else: 
                st.error("❌ บันทึกล้มเหลว")

        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;700&display=swap" rel="stylesheet">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
            <style>
                body {{ font-family: 'Sarabun', sans-serif; margin: 0; padding: 0; background: transparent; overflow-x: auto; }}
                .btn-container {{ display: flex; justify-content: flex-start; padding-bottom: 15px; margin-top: 5px; }}
                .btn-img {{ width: 100%; background-color: #ffffff; color: #31333F; padding: 0.5rem 1rem; border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: 500; font-family: 'Kanit', sans-serif; transition: all 0.2s ease; height: 42px; display: inline-flex; align-items: center; justify-content: center; }}
                .btn-img:hover {{ border-color: #ff4b4b; color: #ff4b4b; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
                #capture-area-wrapper {{ position: relative; width: max-content; padding-bottom: 20px; }}
            </style>
        </head>
        <body>
            <div class="btn-container">
                <button class="btn-img" onclick="takeShot()" id="dl-btn">🖼️ ดาวน์โหลดเป็นรูปภาพ (PNG)</button>
            </div>
            <div id="capture-area-wrapper">{st.session_state.gen_html}</div>
            <script>
                function takeShot() {{
                    const btn = document.getElementById('dl-btn');
                    btn.innerText = '⏳ กำลังสร้างรูปภาพ...';
                    const target = document.getElementById('capture-area');
                    html2canvas(target, {{ scale: 2, useCORS: true, backgroundColor: '#ffffff' }}).then(canvas => {{
                        let link = document.createElement('a');
                        link.download = 'Schedule_{target_date_str}.png';
                        link.href = canvas.toDataURL('image/png');
                        link.click();
                        btn.innerText = '🖼️ ดาวน์โหลดเป็นรูปภาพ (PNG)';
                    }});
                }}
            </script>
        </body>
        </html>
        """
        
        st.markdown("<hr style='margin: 10px 0px;'>", unsafe_allow_html=True)
        components.html(full_html, height=1000, scrolling=True)

# ==================================================================
# หน้า 4: 🏃 จัดการพาร์ทไทม์ (โฉมใหม่ มีประวัติและตัวกรอง)
# ==================================================================
elif page == "🏃 จัดการพาร์ทไทม์":
    st.title("🏃 จัดการข้อมูลบุคลากร Part-time")
    
    with st.expander("➕ เพิ่มเวรพาร์ทไทม์ใหม่", expanded=True):
        pt_date = st.date_input("วันที่ PT มาทำงาน", key="pt_db_date")
        pt_name = st.text_input("ชื่อ PT", placeholder="เช่น สมชาย")
        c1, c2 = st.columns(2)
        with c1: pt_start = st.selectbox("ตั้งแต่เวลา", VALID_TIMES, index=0)
        with c2: pt_end = st.selectbox("ถึงเวลา", VALID_TIMES, index=len(VALID_TIMES)-1)
        pt_break_type = st.radio("การพักเบรก", ["พัก 1 ชั่วโมง", "พักครึ่งชั่วโมง", "ไม่พักเลย"], horizontal=True)
        pt_break_time = st.selectbox("ระบุเวลาเริ่มพัก", VALID_TIMES) if pt_break_type != "ไม่พักเลย" else None
        if st.button("บันทึกพาร์ทไทม์ลงระบบ", type="primary", key="btn_pt_save_page"):
            if pt_name:
                st.session_state.pt_daily_db.append({"date": pt_date.strftime("%Y-%m-%d"), "name": pt_name, "start": pt_start, "end": pt_end, "break_type": pt_break_type, "break_time": pt_break_time})
                st.success("✅ บันทึกข้อมูลสำเร็จ!")
                time.sleep(1)
                st.rerun()
                
    st.divider()
    st.subheader("📋 ค้นหาและจัดการประวัติพาร์ทไทม์")
    
    pt_db = st.session_state.pt_daily_db
    for i, p in enumerate(pt_db):
        p['_idx'] = i
        
    all_pt_months = sorted(list(set([x['date'][:7] for x in pt_db])), reverse=True)
    all_pt_names = sorted(list(set([x['name'] for x in pt_db])))
    
    col_f1, col_f2 = st.columns(2)
    f_month = col_f1.selectbox("📅 ค้นหาตามเดือน", ["ทั้งหมด"] + all_pt_months)
    f_name = col_f2.selectbox("👤 ค้นหาตามชื่อ", ["ทั้งหมด"] + all_pt_names)
    
    filtered_pts = pt_db
    if f_month != "ทั้งหมด":
        filtered_pts = [x for x in filtered_pts if x['date'].startswith(f_month)]
    if f_name != "ทั้งหมด":
        filtered_pts = [x for x in filtered_pts if x['name'] == f_name]
        
    today_str = datetime.now().strftime("%Y-%m-%d")
    upcoming_pts = sorted([x for x in filtered_pts if x['date'] >= today_str], key=lambda x: x['date'])
    past_pts = sorted([x for x in filtered_pts if x['date'] < today_str], key=lambda x: x['date'], reverse=True)
    
    t1, t2 = st.tabs(["🟢 กำลังจะมาถึง (Upcoming)", "🗄️ ผ่านมาแล้ว (Past)"])
    
    with t1:
        if not upcoming_pts:
            st.info("ไม่มีรายการพาร์ทไทม์ที่กำลังจะมาถึง")
        else:
            for pt in upcoming_pts:
                with st.container(border=True):
                    c1, c2 = st.columns([8, 2])
                    b_text = f"{pt['break_type']} ({pt['break_time']})" if pt['break_time'] else "ไม่พัก"
                    c1.markdown(f"📅 **{pt['date']}** | 👤 **{pt['name']}** <br> ⏰ {pt['start']} - {pt['end']} น. | เบรก: {b_text}", unsafe_allow_html=True)
                    if c2.button("🗑️ ลบข้อมูล", key=f"del_pt_up_{pt['_idx']}", use_container_width=True):
                        st.session_state.pt_daily_db.pop(pt['_idx'])
                        st.rerun()
    with t2:
        if not past_pts:
            st.info("ไม่มีประวัติพาร์ทไทม์ในอดีต")
        else:
            for pt in past_pts:
                with st.container(border=True):
                    c1, c2 = st.columns([8, 2])
                    b_text = f"{pt['break_type']} ({pt['break_time']})" if pt['break_time'] else "ไม่พัก"
                    c1.markdown(f"📅 <span style='color:gray'>{pt['date']} | 👤 {pt['name']} <br> ⏰ {pt['start']} - {pt['end']} น. | เบรก: {b_text}</span>", unsafe_allow_html=True)
                    if c2.button("🗑️ ลบข้อมูล", key=f"del_pt_past_{pt['_idx']}", use_container_width=True):
                        st.session_state.pt_daily_db.pop(pt['_idx'])
                        st.rerun()

# ==================================================================
# หน้า 5: จัดการผู้ใช้งาน
# ==================================================================
elif page == "👥 จัดการผู้ใช้งาน":
    st.title("👥 จัดการรายชื่อและสิทธิ์แอปพลิเคชัน")
    
    st.markdown("**(📝 หมายเหตุสำหรับ Admin: โปรดกรอกข้อมูลให้ครบถ้วนเพื่อใช้ในระบบตารางและการกู้รหัสผ่าน)**")
    
    with st.form("add_user_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1: new_user = st.text_input("Username (ใช้ล็อกอิน)")
        with c2: new_pass = st.text_input("Password", type="password")
        with c3: new_name = st.text_input("ชื่อเล่น (แสดงในตาราง AI)")
        with c4: new_role = st.selectbox("สิทธิ์ (Role)", ["Staff", "Admin"])
        
        c5, c6, c7, c8 = st.columns(4)
        with c5: real_name = st.text_input("ชื่อจริง (Real Name)")
        with c6: surname = st.text_input("นามสกุล (Surname)")
        with c7: email = st.text_input("อีเมล (ใช้กู้รหัส)")
        with c8: position = st.text_input("ตำแหน่งงาน")
        
        if st.form_submit_button("บันทึกพนักงานใหม่", type="primary") and new_user and new_name:
            add_user_db(new_user, new_pass, new_name, new_role, real_name, surname, email, position)
            st.toast("✅ เพิ่มข้อมูลสำเร็จ!")
            time.sleep(1)
            st.rerun()
            
    st.divider()
    st.subheader("พนักงานในระบบ")
    for u in sorted(users_db.values(), key=lambda x: x['role']):
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([2, 2, 3, 2, 1])
            c1.markdown(f"**{u['username']}**<br><span style='color:gray; font-size:12px;'>ชื่อในตาราง: {u['full_name']}</span>", unsafe_allow_html=True)
            c2.markdown(f"{u.get('real_name', '-')} {u.get('surname', '')}<br><span style='color:gray; font-size:12px;'>{u.get('position', '-')}</span>", unsafe_allow_html=True)
            c3.write(f"📧 {u.get('email', '-')}")
            
            with c4:
                new_r = st.selectbox("สิทธิ์", ["Staff", "Admin"], index=0 if u['role']=='Staff' else 1, key=f"role_{u['username']}", label_visibility="collapsed")
                if new_r != u['role']:
                    update_user_role(u['username'], new_r)
                    st.rerun()
            with c5:
                if u['username'] != user_info['username']: 
                    if st.button("🗑️", key=f"del_u_{u['username']}"):
                        delete_user_db(u['username'])
                        st.toast("✅ ลบข้อมูลสำเร็จ!")
                        time.sleep(1)
                        st.rerun()
