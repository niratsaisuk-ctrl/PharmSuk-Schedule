-- =====================================================================
-- PharmSuk — ขั้นสุดท้าย: ลบคอลัมน์รหัสผ่านทิ้ง
-- =====================================================================
-- รันไฟล์นี้ "หลังจาก" ทุกคนล็อกอินด้วยระบบใหม่ได้เรียบร้อยแล้วอย่างน้อย 1 สัปดาห์
--
-- ตอนนี้รหัสผ่านตัวจริงถูกเก็บแบบเข้ารหัส (bcrypt) อยู่ใน auth.users ของ Supabase แล้ว
-- คอลัมน์ users.password ที่เป็นข้อความล้วนจึงไม่จำเป็นอีกต่อไป และเป็นความเสี่ยง
-- =====================================================================

-- 1. สำรองไว้ก่อน เผื่อต้องย้อนกลับ (ตารางนี้เข้าถึงได้เฉพาะ service_role)
create table if not exists public._users_password_backup as
  select username, password, now() as backed_up_at
    from public.users;

alter table public._users_password_backup enable row level security;
-- ไม่สร้าง policy ใด ๆ = ไม่มีใครอ่านได้ นอกจาก service_role

-- 2. ลบคอลัมน์จริง
alter table public.users drop column if exists password;

-- 3. ตรวจว่าหายจริง
select column_name
  from information_schema.columns
 where table_schema = 'public' and table_name = 'users'
 order by ordinal_position;

-- เมื่อมั่นใจแล้วว่าไม่ต้องย้อนกลับ ให้ลบตารางสำรองทิ้งด้วย:
--   drop table public._users_password_backup;
