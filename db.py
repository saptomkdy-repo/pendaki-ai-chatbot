"""
Koneksi Supabase untuk riwayat chat Pendaki AI
==========================================================
Menyediakan fungsi-fungsi untuk:
- Membuat session percakapan baru
- Menyimpan pesan (user/assistant) ke session tertentu
- Mengambil daftar session terbaru
- Memuat seluruh pesan dari satu session
- Mencari pesan berdasarkan kata kunci (search riwayat chat)
"""

import streamlit as st
from supabase import create_client, Client


@st.cache_resource(show_spinner=False)
def get_client() -> Client:
    url = st.secrets.get("SUPABASE_URL") if _has_secret("SUPABASE_URL") else None
    key = st.secrets.get("SUPABASE_KEY") if _has_secret("SUPABASE_KEY") else None

    if not url or not key:
        import os
        url = url or os.environ.get("SUPABASE_URL")
        key = key or os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Database belum di-set."
        )
    return create_client(url, key)


def _has_secret(key: str) -> bool:
    try:
        return key in st.secrets
    except Exception:
        return False


def create_session(title: str, user_id: str) -> str:
    """Buat session percakapan baru, kembalikan session_id (uuid string)."""
    client = get_client()
    title = (title or "Chat Baru").strip()
    if len(title) > 60:
        title = title[:57] + "..."

    resp = client.table("chat_sessions").insert({
        "title": title,
        "user_id": user_id,
    }).execute()
    return resp.data[0]["id"]


def save_message(session_id: str, role: str, content: str) -> None:
    """Simpan satu pesan (user/assistant) ke session tertentu."""
    client = get_client()
    client.table("chat_messages").insert({
        "session_id": session_id,
        "role": role,
        "content": content,
    }).execute()


def list_sessions(user_id: str, limit: int = 20):
    """Ambil daftar session terbaru milik user_id tertentu, urut dari yang
    paling baru."""
    client = get_client()
    resp = (
        client.table("chat_sessions")
        .select("id, title, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return resp.data


def load_messages(session_id: str):
    """Ambil semua pesan dari satu session, urut dari yang paling lama."""
    client = get_client()
    resp = (
        client.table("chat_messages")
        .select("role, content, created_at")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    return resp.data


def search_messages(query: str, user_id: str, limit: int = 15):
    """Cari pesan milik user_id tertentu yang mengandung kata kunci
    (case-insensitive). Mengembalikan list pesan beserta judul session-nya."""
    client = get_client()
    resp = (
        client.table("chat_messages")
        .select("session_id, role, content, created_at, chat_sessions!inner(title, user_id)")
        .eq("chat_sessions.user_id", user_id)
        .ilike("content", f"%{query}%")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    results = []
    for row in resp.data:
        session_info = row.get("chat_sessions") or {}
        results.append({
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
            "session_title": session_info.get("title", "Percakapan"),
        })
    return results
