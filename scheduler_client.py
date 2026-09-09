# -*- coding: utf-8 -*-
"""
ตัวเชื่อม Streamlit -> Scheduler API
====================================
คัดลอกไฟล์นี้ไปวางไว้ข้าง ๆ app.py ใน repo PharmSuk-Schedule

วิธีใช้ (แก้ app.py แค่ 2 จุด):

  จุดที่ 1 — เพิ่มบรรทัดนี้ไว้บนสุดของไฟล์ ใกล้ ๆ import อื่น:

      from scheduler_client import generate_schedule_remote

  จุดที่ 2 — ที่บรรทัด ~1550 เปลี่ยนจาก

      df_schedule, status, msg = generate_schedule(
          DAY_OF_WEEK, leaves_dict, custom_dict, mapped_pts, ...

    เป็น

      df_schedule, status, msg = generate_schedule_remote(
          base_pharmacist_list, DAY_OF_WEEK, leaves_dict, custom_dict, mapped_pts, ...

  (เพิ่มแค่ base_pharmacist_list ไว้ข้างหน้า และเติม _remote ต่อท้ายชื่อฟังก์ชัน
   ที่เหลือเหมือนเดิมทุกตัว)

ตั้งค่าใน .streamlit/secrets.toml:

      [scheduler]
      url = "https://xxxx.run.app"
      api_key = "คีย์ที่ตั้งไว้ใน API"

ฟังก์ชันนี้คืนค่าเหมือนของเดิมทุกอย่าง: (DataFrame, status, message)
โค้ดส่วน build_html_table / Excel / บันทึกลง Supabase ไม่ต้องแก้เลย
"""

import pandas as pd
import requests
import streamlit as st

DEFAULT_TIMEOUT = 90  # วินาที — ต้องมากกว่าเวลาที่ solver ใช้คิด


def _config():
    """อ่าน url + api_key จาก secrets ถ้าไม่มีให้ใช้เครื่องตัวเอง"""
    try:
        cfg = st.secrets["scheduler"]
        return str(cfg["url"]).rstrip("/"), str(cfg.get("api_key", ""))
    except Exception:
        return "http://localhost:8000", ""


def _leaves_to_json(LEAVES):
    out = []
    for name, l_type in LEAVES.items():
        if isinstance(l_type, (tuple, list)):
            out.append({"name": name, "type": "ช่วงเวลา", "start": l_type[0], "end": l_type[1]})
        else:
            out.append({"name": name, "type": l_type})
    return out


def _timed_to_json(d):
    return [
        {"name": name, "start": start, "end": end, "task": task}
        for (name, start, end), task in d.items()
    ]


def _part_time_to_json(PART_TIME):
    out = []
    for pt in PART_TIME:
        item = {
            "name": pt["name"],
            "start": pt["start"],
            "end": pt["end"],
            "break_type": pt.get("break_type", "ไม่พักเลย"),
            "break_time": pt.get("break_time"),
        }
        # เผื่อกรณีที่ส่งมาแค่ has_break=True แต่ไม่ได้บอกชนิด/เวลาพัก
        if item["break_type"] == "ไม่พักเลย" and pt.get("has_break"):
            item["break_type"] = "พัก 1 ชั่วโมง"
            item["break_time"] = item["break_time"] or "12.00"
        out.append(item)
    return out


def generate_schedule_remote(
    PHARMACISTS,
    DAY_OF_WEEK,
    LEAVES,
    CUSTOM_TASKS,
    PART_TIME,
    FIX_BREAKS,
    FIXED_MAIN_TASKS,
    SICK_PEOPLE,
    IS_MWF,
    HEAD_PHARMACISTS,
    ALLOW_HEAD_ASSIST=False,
    timeout=DEFAULT_TIMEOUT,
):
    url, api_key = _config()

    payload = {
        "pharmacists": list(PHARMACISTS),
        "day_of_week": DAY_OF_WEEK,
        "is_mwf": bool(IS_MWF),
        "head_pharmacists": list(HEAD_PHARMACISTS or []),
        "sick_people": list(SICK_PEOPLE or []),
        "allow_head_assist": bool(ALLOW_HEAD_ASSIST),
        "leaves": _leaves_to_json(LEAVES or {}),
        "custom_tasks": _timed_to_json(CUSTOM_TASKS or {}),
        "fixed_main_tasks": _timed_to_json(FIXED_MAIN_TASKS or {}),
        "part_time": _part_time_to_json(PART_TIME or []),
        "fix_breaks": [{"name": n, "group": int(g)} for n, g in (FIX_BREAKS or {}).items()],
        "max_solve_seconds": 20,
    }

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        res = requests.post(f"{url}/generate", json=payload, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout:
        return None, "Error", "⏱️ เซิร์ฟเวอร์จัดตารางใช้เวลานานเกินไป กรุณาลองใหม่อีกครั้ง"
    except requests.exceptions.RequestException as e:
        return None, "Error", f"🌐 ติดต่อเซิร์ฟเวอร์จัดตารางไม่ได้: {e}"

    if res.status_code == 401:
        return None, "Error", "🔑 API key ไม่ถูกต้อง — ตรวจสอบใน .streamlit/secrets.toml"
    if res.status_code != 200:
        return None, "Error", f"❌ เซิร์ฟเวอร์ตอบกลับผิดพลาด ({res.status_code}): {res.text[:200]}"

    body = res.json()
    if body["status"] != "Success":
        return None, body["status"], body["message"]

    df = pd.DataFrame(body["rows"])
    # เรียงคอลัมน์ให้เหมือนเดิมเป๊ะ ๆ (ชื่อ/เวลา ก่อน แล้วตามด้วย 16 ช่วงเวลา)
    df = df[body["columns"]]
    return df, "Success", ""
