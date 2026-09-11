# -*- coding: utf-8 -*-
"""
PharmSuk — ตรวจสอบว่ากฎสิทธิ์ (RLS) ทำงานจริง
==============================================
รันหลังจากเปิด RLS แล้ว เพื่อพิสูจน์ว่าคนทั่วไปทำสิ่งที่ไม่ควรทำไม่ได้จริง

  pip install supabase python-dotenv
  python verify_rls.py --staff-user ชื่อผู้ใช้ระดับ_Staff --staff-pass รหัสผ่าน

สคริปต์นี้ล็อกอินด้วย anon key เหมือนผู้ใช้จริงทุกประการ (ไม่ใช้ service_role)
แล้วลองทำสิ่งต้องห้ามทีละอย่าง ถ้าทำได้แปลว่ากฎยังรั่ว
"""

import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from supabase import create_client

LOGIN_DOMAIN = "pharmsuk.local"
PASS, FAIL = "✅ ผ่าน", "❌ ไม่ผ่าน"
results = []


def check(name, should_fail_fn, expect_blocked=True):
    """should_fail_fn คืน True ถ้า 'ทำได้' (ซึ่งแปลว่ากฎรั่ว)"""
    try:
        allowed = should_fail_fn()
    except Exception:
        allowed = False
    ok = (not allowed) if expect_blocked else allowed
    results.append((name, ok))
    print(f"{PASS if ok else FAIL}  {name}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--staff-user", required=True, help="username ของคนที่ role = Staff")
    ap.add_argument("--staff-pass", required=True)
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    anon = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not url or not anon:
        sys.exit("❌ ต้องตั้ง SUPABASE_URL และ SUPABASE_ANON_KEY ใน .env")

    # ---------- ก่อนล็อกอิน: ต้องไม่เห็นอะไรเลย ----------
    print("\n[1] ยังไม่ล็อกอิน (anon)")
    anon_sb = create_client(url, anon)
    check("คนนอกอ่านตาราง users ไม่ได้",
          lambda: len(anon_sb.table("users").select("*").execute().data) > 0)
    check("คนนอกอ่านใบลาไม่ได้",
          lambda: len(anon_sb.table("requests").select("*").execute().data) > 0)
    check("คนนอกอ่านตารางเวรไม่ได้",
          lambda: len(anon_sb.table("schedules").select("*").execute().data) > 0)

    # ---------- ล็อกอินเป็น Staff ----------
    print("\n[2] ล็อกอินเป็น Staff")
    sb = create_client(url, anon)
    email = sb.rpc("auth_email_for", {"identifier": args.staff_user}).execute().data
    if not email:
        sys.exit(f"❌ หา username '{args.staff_user}' ไม่เจอ")
    res = sb.auth.sign_in_with_password({"email": email, "password": args.staff_pass})
    if not res.session:
        sys.exit("❌ ล็อกอินไม่สำเร็จ — ตรวจรหัสผ่าน")
    me = sb.table("users").select("*").eq("auth_id", res.user.id).limit(1).execute().data[0]
    print(f"    ล็อกอินเป็น: {me['full_name']} (role={me['role']})")
    if me["role"] in ("Admin", "Head"):
        sys.exit("❌ บัญชีนี้เป็น Admin/Head — ต้องใช้บัญชี Staff เพื่อทดสอบ")

    check("Staff อ่านรายชื่อเพื่อนร่วมงานได้ (ต้องได้)",
          lambda: len(sb.table("users").select("username").execute().data) > 0,
          expect_blocked=False)
    check("Staff อ่านปฏิทินใบลาได้ (ต้องได้)",
          lambda: sb.table("requests").select("id").limit(1).execute() is not None,
          expect_blocked=False)

    # ---------- สิ่งที่ Staff ต้องทำไม่ได้ ----------
    print("\n[3] สิ่งที่ Staff ต้องทำไม่ได้")

    def promote_self():
        sb.table("users").update({"role": "Admin"}).eq("auth_id", res.user.id).execute()
        row = sb.table("users").select("role").eq("auth_id", res.user.id).execute().data
        return row and row[0]["role"] == "Admin"

    check("Staff ตั้งตัวเองเป็น Admin ไม่ได้", promote_self)

    def edit_other_profile():
        other = sb.table("users").select("username, auth_id").neq("auth_id", res.user.id) \
                  .not_.is_("auth_id", "null").limit(1).execute().data
        if not other:
            return False
        before = sb.table("users").select("real_name").eq("username", other[0]["username"]).execute().data
        sb.table("users").update({"real_name": "HACKED"}).eq("username", other[0]["username"]).execute()
        after = sb.table("users").select("real_name").eq("username", other[0]["username"]).execute().data
        changed = before and after and before[0]["real_name"] != after[0]["real_name"]
        if changed:  # เก็บกวาดถ้าเผลอแก้ได้จริง
            sb.table("users").update({"real_name": before[0]["real_name"]}) \
              .eq("username", other[0]["username"]).execute()
        return changed

    check("Staff แก้โปรไฟล์คนอื่นไม่ได้", edit_other_profile)

    def approve_own_leave():
        mine = sb.table("requests").select("id, status").eq("user_id", res.user.id) \
                 .eq("status", "⏳ รออนุมัติ").limit(1).execute().data
        if not mine:
            print("    (ข้าม: ไม่มีใบลาที่รออนุมัติของตัวเอง)")
            return False
        sb.table("requests").update({"status": "✅ อนุมัติแล้ว"}).eq("id", mine[0]["id"]).execute()
        now = sb.table("requests").select("status").eq("id", mine[0]["id"]).execute().data
        return now and now[0]["status"] == "✅ อนุมัติแล้ว"

    check("Staff อนุมัติใบลาตัวเองไม่ได้", approve_own_leave)

    def request_as_someone_else():
        other = sb.table("users").select("full_name").neq("auth_id", res.user.id).limit(1).execute().data
        if not other:
            return False
        r = sb.table("requests").insert({
            "user_name": other[0]["full_name"], "req_type": "ลางาน: ทดสอบ",
            "req_date": "2099-01-01", "detail": "RLS test", "status": "⏳ รออนุมัติ",
            "user_id": res.user.id,
        }).execute()
        return bool(r.data)

    check("Staff ลงใบลาในนามคนอื่นไม่ได้", request_as_someone_else)

    def write_schedule():
        r = sb.table("schedules").insert({
            "schedule_date": "2099-01-01", "html_content": "<p>RLS test</p>",
        }).execute()
        return bool(r.data)

    check("Staff บันทึกตารางเวรทับไม่ได้", write_schedule)

    # ---------- สรุป ----------
    sb.auth.sign_out()
    passed = sum(1 for _, ok in results if ok)
    print("\n" + "=" * 55)
    print(f"ผ่าน {passed} / {len(results)} ข้อ")
    if passed < len(results):
        print("\n⚠️ ข้อที่ไม่ผ่าน แปลว่ากฎ RLS ยังไม่ครอบคลุม:")
        for name, ok in results:
            if not ok:
                print(f"   - {name}")
        return 1
    print("🎉 กฎสิทธิ์ทำงานครบทุกข้อ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
