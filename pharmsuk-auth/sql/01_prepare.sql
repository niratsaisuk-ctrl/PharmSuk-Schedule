-- =====================================================================
-- PharmSuk — ขั้นที่ 1: เตรียมโครงสร้าง (ยังไม่เปิด RLS)
-- =====================================================================
-- รันไฟล์นี้ได้เลยทันที แอปเดิมจะยังทำงานปกติ 100% ไม่มีอะไรพัง
-- เพราะขั้นนี้แค่ "เพิ่ม" คอลัมน์กับฟังก์ชัน ไม่ได้แตะข้อมูลเดิม
--
-- วิธีรัน: Supabase Dashboard -> SQL Editor -> วาง -> Run
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. เพิ่มคอลัมน์เชื่อมกับระบบ Auth ของ Supabase
-- ---------------------------------------------------------------------
-- users.auth_id  = ตัวเชื่อมระหว่างตาราง users เดิม กับ auth.users ของ Supabase
alter table public.users
  add column if not exists auth_id uuid unique references auth.users(id) on delete set null;

-- requests.user_id = เจ้าของคำขอ (ของเดิมเก็บเป็นชื่อ ซึ่งปลอมได้ง่าย)
alter table public.requests
  add column if not exists user_id uuid references auth.users(id) on delete set null;

create index if not exists idx_users_auth_id   on public.users(auth_id);
create index if not exists idx_requests_user_id on public.requests(user_id);


-- ---------------------------------------------------------------------
-- 2. ฟังก์ชันผู้ช่วย — ใช้ตอบคำถาม "คนที่กำลังใช้งานอยู่คือใคร มีสิทธิ์อะไร"
-- ---------------------------------------------------------------------
-- security definer = ฟังก์ชันนี้อ่านตาราง users ได้เสมอ
-- จำเป็น เพราะถ้าไม่ใส่ กฎ RLS จะเรียกตัวเองวนไม่รู้จบ (infinite recursion)

create or replace function public.my_role()
returns text
language sql stable security definer set search_path = public
as $$
  select role from public.users where auth_id = auth.uid() limit 1
$$;

create or replace function public.my_full_name()
returns text
language sql stable security definer set search_path = public
as $$
  select full_name from public.users where auth_id = auth.uid() limit 1
$$;

-- "ผู้จัดการ" = Admin หรือ Head (ตรงกับที่ app.py ใช้เช็คสิทธิ์อยู่แล้ว)
create or replace function public.is_manager()
returns boolean
language sql stable security definer set search_path = public
as $$
  select coalesce(
    (select role in ('Admin', 'Head') from public.users where auth_id = auth.uid() limit 1),
    false
  )
$$;

grant execute on function public.my_role()      to authenticated;
grant execute on function public.my_full_name() to authenticated;
grant execute on function public.is_manager()   to authenticated;


-- ---------------------------------------------------------------------
-- 3. ตัวแปลง "username หรือ email" -> "อีเมลสำหรับล็อกอิน"
-- ---------------------------------------------------------------------
-- Supabase Auth ใช้อีเมลเป็นตัวระบุตัวตนเสมอ แต่ผู้ใช้ของเราคุ้นกับ username
-- เราจึงกำหนดว่า อีเมลสำหรับล็อกอิน = <username>@pharmsuk.local
-- ส่วนอีเมลจริงของแต่ละคน ยังเก็บไว้ที่ users.email เหมือนเดิม (ใช้ติดต่อ)
--
-- ฟังก์ชันนี้ต้องเรียกได้ "ก่อน" ล็อกอิน จึงเปิดให้ anon เรียกได้
-- ผลข้างเคียง: คนนอกลองเดา username ได้ว่ามีอยู่จริงไหม
-- ซึ่งหน้าล็อกอินเดิมก็บอกอยู่แล้วผ่านข้อความ error จึงไม่ได้แย่ลงกว่าเดิม

create or replace function public.auth_email_for(identifier text)
returns text
language sql stable security definer set search_path = public
as $$
  select coalesce(
    -- ลองตีความว่าเป็น username ก่อน
    (select lower(u.username) || '@pharmsuk.local'
       from public.users u
      where lower(u.username) = lower(trim(identifier))
      limit 1),
    -- ถ้าไม่ใช่ ลองตีความว่าเป็นอีเมลจริงที่ลงทะเบียนไว้
    (select lower(u.username) || '@pharmsuk.local'
       from public.users u
      where trim(identifier) <> ''
        and lower(coalesce(u.email, '')) = lower(trim(identifier))
      limit 1)
  )
$$;

grant execute on function public.auth_email_for(text) to anon, authenticated;


-- ---------------------------------------------------------------------
-- 4. ตรวจผลลัพธ์
-- ---------------------------------------------------------------------
select
  (select count(*) from public.users)                          as ผู้ใช้ทั้งหมด,
  (select count(*) from public.users where auth_id is not null) as ย้ายเข้า_auth_แล้ว,
  (select count(*) from public.requests)                        as คำขอทั้งหมด;
-- ตอนนี้ "ย้ายเข้า_auth_แล้ว" ควรเป็น 0 — จะเพิ่มขึ้นหลังรัน migrate_to_supabase_auth.py
