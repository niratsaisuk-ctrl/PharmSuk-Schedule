-- =====================================================================
-- PharmSuk — ปุ่มฉุกเฉิน: ปิด RLS กลับเป็นเหมือนเดิม
-- =====================================================================
-- ใช้เมื่อเปิด RLS แล้วแอปพัง และต้องการให้กลับมาใช้งานได้ทันที
-- ปลอดภัย: ไม่มีการลบข้อมูลใด ๆ แค่ปิดกฎสิทธิ์ชั่วคราว
--
-- หลังรันไฟล์นี้ ให้สลับ app.py กลับไปใช้ระบบล็อกอินเดิมด้วย
-- (คอลัมน์ users.password ยังอยู่ ถ้ายังไม่ได้รัน 03_drop_password.sql)
-- =====================================================================

alter table public.users     disable row level security;
alter table public.requests  disable row level security;
alter table public.schedules disable row level security;

drop trigger if exists trg_guard_users_update    on public.users;
drop trigger if exists trg_guard_requests_update on public.requests;

select tablename, rowsecurity as "เปิด_RLS_อยู่"
  from pg_tables
 where schemaname = 'public'
   and tablename in ('users', 'requests', 'schedules')
 order by tablename;
-- ควรได้ false ทั้งสามแถว
