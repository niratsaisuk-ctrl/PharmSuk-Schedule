-- =====================================================================
-- PharmSuk — ขั้นที่ 3: เปิด Row Level Security + วางกฎสิทธิ์
-- =====================================================================
-- ⚠️ อ่านก่อนรัน ⚠️
--
-- ห้ามรันไฟล์นี้ จนกว่าจะทำ 2 อย่างนี้เสร็จแล้ว:
--   1) รัน 01_prepare.sql แล้ว
--   2) รัน migrate_to_supabase_auth.py แล้ว (ทุกคนต้องมี auth_id)
--
-- และต้องสลับ app.py ไปใช้ auth_client.py "ในคราวเดียวกัน"
-- เพราะหลังเปิด RLS แล้ว โค้ดเดิมที่ไม่ได้ล็อกอินผ่าน Supabase Auth
-- จะอ่านข้อมูลไม่เห็นเลยสักแถว (ไม่ error แต่ได้ข้อมูลว่าง)
--
-- ถ้าอะไรพัง -> รัน 99_rollback.sql ปิด RLS กลับได้ทันทีใน 5 วินาที
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. กันพลาด: ถ้ายังมีคนที่ไม่มี auth_id ให้หยุดก่อน
-- ---------------------------------------------------------------------
do $$
declare n int;
begin
  select count(*) into n
    from public.users
   where auth_id is null and coalesce(role, '') <> 'System';
  if n > 0 then
    raise exception 'ยังมีผู้ใช้ % คนที่ยังไม่ได้ย้ายเข้า Supabase Auth — กรุณารัน migrate_to_supabase_auth.py ให้เสร็จก่อน', n;
  end if;
end $$;


-- ---------------------------------------------------------------------
-- 1. เติมเจ้าของคำขอเดิมย้อนหลัง (จับคู่จากชื่อ-นามสกุลเต็ม)
-- ---------------------------------------------------------------------
update public.requests r
   set user_id = u.auth_id
  from public.users u
 where r.user_id is null
   and r.user_name = u.full_name
   and u.auth_id is not null;

-- คำขอของ SYSTEM_REQ จะไม่มีเจ้าของ (user_id เป็น null) ซึ่งถูกต้องแล้ว
-- เพราะเป็นประกาศของระบบ ไม่ใช่ของใครคนใดคนหนึ่ง


-- ---------------------------------------------------------------------
-- 2. เปิด RLS
-- ---------------------------------------------------------------------
-- ค่าเริ่มต้นของ RLS คือ "ปฏิเสธทุกอย่าง" แล้วเราค่อยเปิดเป็นข้อ ๆ
alter table public.users     enable row level security;
alter table public.requests  enable row level security;
alter table public.schedules enable row level security;


-- ---------------------------------------------------------------------
-- 3. ตาราง users
-- ---------------------------------------------------------------------
-- อ่าน: คนที่ล็อกอินแล้วอ่านได้ทุกแถว
--       (จำเป็น เพราะแอปต้องใช้รายชื่อทุกคนไปสร้างตารางเวร)
drop policy if exists users_select on public.users;
create policy users_select on public.users
  for select to authenticated
  using (true);

-- แก้ไข: แก้ของตัวเองได้ / Admin+Head แก้ของใครก็ได้
drop policy if exists users_update on public.users;
create policy users_update on public.users
  for update to authenticated
  using      (auth_id = auth.uid() or public.is_manager())
  with check (auth_id = auth.uid() or public.is_manager());

-- เพิ่ม/ลบผู้ใช้: เฉพาะ Admin + Head
drop policy if exists users_insert on public.users;
create policy users_insert on public.users
  for insert to authenticated
  with check (public.is_manager());

drop policy if exists users_delete on public.users;
create policy users_delete on public.users
  for delete to authenticated
  using (public.is_manager());

-- กันคนตั้งสิทธิ์ให้ตัวเองเป็น Admin
-- (RLS policy เทียบค่า "ก่อนแก้" กับ "หลังแก้" พร้อมกันไม่ได้ ต้องใช้ trigger)
create or replace function public.guard_users_update()
returns trigger
language plpgsql security definer set search_path = public
as $$
begin
  if public.is_manager() then
    return new;
  end if;
  if new.role          is distinct from old.role
  or new.display_order is distinct from old.display_order
  or new.username      is distinct from old.username
  or new.auth_id       is distinct from old.auth_id
  or new.full_name     is distinct from old.full_name then
    raise exception 'ไม่มีสิทธิ์แก้ไข role / display_order / username / full_name ของตัวเอง';
  end if;
  return new;
end $$;

drop trigger if exists trg_guard_users_update on public.users;
create trigger trg_guard_users_update
  before update on public.users
  for each row execute function public.guard_users_update();


-- ---------------------------------------------------------------------
-- 4. ตาราง requests (ใบลา / งานพิเศษ / ออกเวร)
-- ---------------------------------------------------------------------
-- อ่าน: ทุกคนที่ล็อกอินแล้ว (ปฏิทินห้องยาต้องเห็นของทุกคน)
drop policy if exists requests_select on public.requests;
create policy requests_select on public.requests
  for select to authenticated
  using (true);

-- สร้าง: ลงได้เฉพาะในนามตัวเอง / Admin+Head ลงแทนคนอื่นและลง SYSTEM_REQ ได้
drop policy if exists requests_insert on public.requests;
create policy requests_insert on public.requests
  for insert to authenticated
  with check (
    public.is_manager()
    or (user_id = auth.uid() and user_name = public.my_full_name())
  );

-- แก้ไข: ของตัวเอง หรือ Admin+Head
drop policy if exists requests_update on public.requests;
create policy requests_update on public.requests
  for update to authenticated
  using      (public.is_manager() or user_id = auth.uid())
  with check (public.is_manager() or user_id = auth.uid());

-- ลบ: Admin+Head ลบได้เสมอ / เจ้าของลบได้เฉพาะตอนที่ยัง "รออนุมัติ"
drop policy if exists requests_delete on public.requests;
create policy requests_delete on public.requests
  for delete to authenticated
  using (
    public.is_manager()
    or (user_id = auth.uid() and status = '⏳ รออนุมัติ')
  );

-- กันคนกดอนุมัติใบลาตัวเอง และกันการโอนคำขอไปให้คนอื่น
create or replace function public.guard_requests_update()
returns trigger
language plpgsql security definer set search_path = public
as $$
begin
  if public.is_manager() then
    return new;
  end if;
  if new.status is distinct from old.status then
    raise exception 'เฉพาะ Admin หรือ Head เท่านั้นที่เปลี่ยนสถานะคำขอได้';
  end if;
  if new.user_id is distinct from old.user_id
  or new.user_name is distinct from old.user_name then
    raise exception 'ไม่มีสิทธิ์เปลี่ยนเจ้าของคำขอ';
  end if;
  return new;
end $$;

drop trigger if exists trg_guard_requests_update on public.requests;
create trigger trg_guard_requests_update
  before update on public.requests
  for each row execute function public.guard_requests_update();


-- ---------------------------------------------------------------------
-- 5. ตาราง schedules (ตารางเวรที่จัดเสร็จแล้ว)
-- ---------------------------------------------------------------------
-- อ่าน: ทุกคนที่ล็อกอินแล้ว
drop policy if exists schedules_select on public.schedules;
create policy schedules_select on public.schedules
  for select to authenticated
  using (true);

-- เขียน/แก้/ลบ: เฉพาะ Admin + Head
drop policy if exists schedules_write on public.schedules;
create policy schedules_write on public.schedules
  for all to authenticated
  using      (public.is_manager())
  with check (public.is_manager());


-- ---------------------------------------------------------------------
-- 6. ตรวจผล
-- ---------------------------------------------------------------------
select tablename,
       rowsecurity as "เปิด_RLS_แล้ว",
       (select count(*) from pg_policies p
         where p.schemaname = 'public' and p.tablename = t.tablename) as "จำนวนกฎ"
  from pg_tables t
 where schemaname = 'public'
   and tablename in ('users', 'requests', 'schedules')
 order by tablename;
