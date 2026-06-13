-- Dijalankan di Supabase SQL Editor
create table if not exists chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id text not null default 'anon',
  title text not null default 'Percakapan baru',
  created_at timestamptz not null default now()
);

create table if not exists chat_messages (
  id bigserial primary key,
  session_id uuid not null references chat_sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_chat_sessions_user
  on chat_sessions (user_id);

create index if not exists idx_chat_messages_session
  on chat_messages (session_id);

create index if not exists idx_chat_messages_content
  on chat_messages using gin (to_tsvector('indonesian', content));

-- Catatan:
-- Index gin di atas untuk full-text search bahasa Indonesia.
-- Tapi, pencarian sederhana memakai ILIKE (tidak butuh index ini, tapi index ini membantu performa kalau data sudah banyak).

-- =========================================================
-- CATATAN ROW LEVEL SECURITY (RLS)
-- =========================================================
-- Di project ini, awalnya RLS diaktifkan tanpa policy apapun.
-- Artinya, semua akses dari anon key akan DITOLAK.
-- Policy di bawah membuka akses penuh (read/write) untuk anon key.
-- Karena tidak ada Supabase Authentication,
-- pemisahan data antar "user" HANYA berdasarkan kolom `user_id` yang difilter di sisi aplikasi (lihat db.py)
-- dan bukan oleh RLS.
-- Sehingga, ini BUKAN termasuk isolasi data yang aman secara production-grade.

alter table chat_sessions enable row level security;
alter table chat_messages enable row level security;

create policy "Allow all access to chat_sessions"
  on chat_sessions for all
  using (true)
  with check (true);

create policy "Allow all access to chat_messages"
  on chat_messages for all
  using (true)
  with check (true);

