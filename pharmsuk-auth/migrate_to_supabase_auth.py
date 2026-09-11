# -*- coding: utf-8 -*-
"""
PharmSuk — ขั้นที่ 2: ย้ายผู้ใช้เดิมเข้าระบบ Supabase Auth
==========================================================

สคริปต์นี้ทำอะไร
  อ่านทุกแถวจากตาราง users แล้วสร้างบัญชีใน Supabase Auth ให้ทีละคน
  โดยใช้ "รหัสผ่านเดิมของเขา" -> Supabase จะเข้ารหัส (bcrypt) ให้อัตโนมัติ
  แปลว่า ทุกคนยังล็อกอินด้วยรหัสเดิมได้ ไม่ต้องแจ้งใครให้ตั้งรหัสใหม่

  อีเมลสำหรับล็อกอิน = <username>@pharmsuk.local
  (อีเมลจริงของแต่ละคนยังอยู่ที่ users.email เหมือนเดิม ไม่ถูกแตะต้อง)

รันซ้ำได้ปลอดภัย — คนที่ย้ายแล้วจะถูกข้าม

วิธีใช้
  pip install supabase python-dotenv
  # ใส่ค่าในไฟล์ .env (ดู .env.example)
  python migrate_to_supabase_auth.py --dry-run    # ดูก่อนว่าจะทำอะไรบ้าง
  python migrate_to_supabase_auth.py              # ทำจริง

⚠️ ต้องใช้ service_role key ไม่ใช่ anon key
   หาได้ที่ Supabase Dashboard -> Project Settings -> API -> service_role
   คีย์นี้ข้ามกฎสิทธิ์ทั้งหมดได้ ห้ามใส่ในแอปมือถือหรือ commit ขึ้น GitHub เด็ดขาด
"""

import argparse
import os
import secrets
import string
import sys
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from supabase import create_client

LOGIN_DOMAIN = "pharmsuk.local"
MIN_PASSWORD_LEN = 6  # ข้อกำหนดขั้นต่ำของ Supabase Auth


def make_temp_password():
    alphabet = string.ascii_letters + string.digits
    return "Ph" + "".join(secrets.choice(alphabet) for _ in range(10))


def login_email(username):
    return f"{username.lower().strip()}@{LOGIN_DOMAIN}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="แสดงผลอย่างเดียว ไม่เขียนอะไรจริง")
    args = ap.parse_args()

    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not url or not key:
        sys.exit("❌ ไม่พบ SUPABASE_URL หรือ SUPABASE_SERVICE_ROLE_KEY — ตรวจไฟล์ .env")
    if len(key) < 100 or "service_role" not in key and key.count(".") != 2:
        print("⚠️  คีย์ดูสั้นผิดปกติ — ตรวจให้แน่ใจว่าใช้ service_role key ไม่ใช่ anon key\n")

    sb = create_client(url, key)

    users = sb.table("users").select("*").execute().data
    print(f"พบผู้ใช้ทั้งหมด {len(users)} คน")
    if args.dry_run:
        print("🔍 โหมดทดลอง — จะไม่มีการเขียนข้อมูลจริง\n")
    print("-" * 70)

    created, skipped, temp_passwords, failed = 0, 0, [], []

    for u in sorted(users, key=lambda r: str(r.get("username", ""))):
        username = str(u.get("username", "")).strip()
        role = u.get("role") or ""

        if not username:
            print(f"⏭️  ข้าม: แถวที่ไม่มี username ({u})")
            skipped += 1
            continue

        if role == "System":
            print(f"⏭️  ข้าม '{username}' (บัญชีระบบ ไม่ต้องล็อกอิน)")
            skipped += 1
            continue

        if u.get("auth_id"):
            print(f"✓  ข้าม '{username}' (ย้ายไปแล้ว)")
            skipped += 1
            continue

        password = str(u.get("password") or "")
        is_temp = False
        if len(password) < MIN_PASSWORD_LEN:
            password = make_temp_password()
            is_temp = True

        email = login_email(username)

        if args.dry_run:
            note = "  ⚠️ รหัสเดิมสั้นเกิน จะได้รหัสชั่วคราว" if is_temp else ""
            print(f"➕ จะสร้าง: {username:<20} -> {email}{note}")
            created += 1
            continue

        try:
            res = sb.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {
                    "username": username,
                    "full_name": u.get("full_name"),
                    "role": role,
                },
            })
            auth_id = res.user.id
            sb.table("users").update({"auth_id": auth_id}).eq("username", u["username"]).execute()
            print(f"✅ สร้างแล้ว: {username:<20} -> {email}")
            created += 1
            if is_temp:
                temp_passwords.append((username, u.get("full_name"), password))
        except Exception as e:
            msg = str(e)
            # ถ้าบัญชีมีอยู่แล้วใน Auth แต่ auth_id ในตารางยังว่าง ให้ไปหา id มาเติม
            if "already been registered" in msg or "already exists" in msg:
                try:
                    page = sb.auth.admin.list_users()
                    match = next((x for x in page if str(x.email).lower() == email), None)
                    if match:
                        sb.table("users").update({"auth_id": match.id}).eq("username", u["username"]).execute()
                        print(f"🔗 เชื่อมบัญชีเดิม: {username:<20} -> {email}")
                        created += 1
                        continue
                except Exception as e2:
                    msg = f"{msg} / {e2}"
            print(f"❌ ล้มเหลว: {username:<20} — {msg}")
            failed.append((username, msg))

    print("-" * 70)
    print(f"สร้าง/เชื่อมแล้ว {created} คน | ข้าม {skipped} คน | ล้มเหลว {len(failed)} คน")

    if temp_passwords:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"temp_passwords_{stamp}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write("รหัสผ่านชั่วคราว (รหัสเดิมสั้นกว่า 6 ตัวอักษร ใช้กับ Supabase ไม่ได้)\n")
            f.write("กรุณาแจ้งเจ้าตัวเป็นการส่วนตัว แล้วให้เปลี่ยนรหัสทันทีที่เข้าระบบได้\n")
            f.write("=" * 60 + "\n")
            for username, full_name, pw in temp_passwords:
                f.write(f"{username:<20} {full_name or '':<25} {pw}\n")
        print(f"\n⚠️  มี {len(temp_passwords)} คนที่ได้รหัสชั่วคราว — บันทึกไว้ที่ {fname}")
        print("    แจ้งเจ้าตัวแล้วให้ลบไฟล์นี้ทิ้ง อย่า commit ขึ้น GitHub")

    if failed:
        print("\nรายชื่อที่ล้มเหลว:")
        for username, msg in failed:
            print(f"  - {username}: {msg[:120]}")
        return 1

    if not args.dry_run:
        print("\n🎉 เสร็จเรียบร้อย — ขั้นถัดไปคือรัน sql/02_enable_rls.sql")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
