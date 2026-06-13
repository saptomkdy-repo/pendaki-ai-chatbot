"""
Pendaki AI
===========================================================

Fungsi      : Asisten AI untuk pendaki gunung di Indonesia.
Gaya bahasa : Santai.
Domain      : Info gunung populer Indonesia, perlengkapan, cuaca, keamanan, dll.

Tech stack dan Komponen:
- Streamlit         : antarmuka chat web
- LangChain Agent   : AI yang bisa memilih tools sendiri (tool-calling agent)
- RAG               : pencarian info detail gunung dari vector database (FAISS)
- Tools             : weather_check (OpenWeatherMap API), generate_packing_checklist, mountain_info (retriever RAG)
- Memory            : riwayat chat (session) dan profil user (sidebar)
"""

import os
import re
import uuid
import streamlit as st
from langchain.agents import create_agent
from langchain_core.messages import AIMessageChunk, HumanMessage, AIMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from tools import weather_check, generate_packing_checklist, build_retriever_tool
import db


# =========================================================
# 1. KONFIGURASI HALAMAN & API KEY
# =========================================================
st.set_page_config(page_title="Pendaki AI", page_icon="🏔️", layout="centered")

# API key bisa diisi via Streamlit secrets (untuk deployment) atau env var (lokal)
def get_secret(key: str) -> str:
    """Ambil API key dari st.secrets jika tersedia, jika tidak fallback ke
    environment variable. Aman dipanggil walau secrets.toml belum dibuat."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, "")


GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
OPENWEATHER_API_KEY = get_secret("OPENWEATHER_API_KEY")
SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_KEY = get_secret("SUPABASE_KEY")
SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)

if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
if OPENWEATHER_API_KEY:
    os.environ["OPENWEATHER_API_KEY"] = OPENWEATHER_API_KEY
if SUPABASE_URL:
    os.environ["SUPABASE_URL"] = SUPABASE_URL
if SUPABASE_KEY:
    os.environ["SUPABASE_KEY"] = SUPABASE_KEY

# =========================================================
# 1b. USER ID (untuk pemisahan riwayat chat per-browser)
# =========================================================
# Disimpan di URL query param supaya tetap sama walau halaman di-refresh,
# tapi akan berbeda untuk browser/device lain (incognito, dll).
if "uid" in st.query_params:
    USER_ID = st.query_params["uid"]
else:
    USER_ID = str(uuid.uuid4())
    st.query_params["uid"] = USER_ID

# =========================================================
# 2. SYSTEM PROMPT & PARAMETER
# =========================================================
SYSTEM_PROMPT = """
Kamu adalah "Pendaki AI", asisten AI untuk pendaki gunung di Indonesia.

GAYA BAHASA:
- Santai banget, hangat, dan akrab seperti senior pendaki berpengalaman ngobrol
  sama juniornya. Pakai bahasa gaul, lo / gue, tapi tetap sopan, hindari bahasa kaku/formal-korporat.

DOMAIN PENGETAHUAN:
- Info gunung-gunung populer di Indonesia: jalur, estimasi waktu tempuh,
  tingkat kesulitan, sumber air, titik camp.
- Perlengkapan mendaki sesuai durasi & kondisi cuaca.
- Pertolongan pertama dasar (P3K), terutama hipotermia dan AMS (mabuk
  ketinggian).
- Etika pendakian (Leave No Trace).

TOOLS YANG TERSEDIA:
- "mountain_info": untuk mencari detail jalur, sumber air, titik camp,
  dan tips dari knowledge base internal. GUNAKAN tool ini setiap kali user
  bertanya hal spesifik tentang gunung (jalur, estimasi waktu, dst), jangan
  hanya mengandalkan pengetahuan umum jika informasi spesifik dibutuhkan.
- "weather_check": untuk mengambil data cuaca real-time basecamp gunung
  (semeru, rinjani, gede, prau, merbabu, sindoro, slamet).
- "generate_packing_checklist": untuk membuat daftar perlengkapan
  berdasarkan gunung tujuan dan jumlah hari pendakian.

ATURAN PENTING:
1. SELALU ingatkan user untuk mengecek info terkini (status buka/tutup
   jalur, cuaca real-time, perizinan/SIMAKSI) ke pengelola resmi/BMKG
   sebelum berangkat.
2. Jika user menyebutkan kondisi berisiko (cuaca ekstrem, kondisi fisik
   tidak fit, gejala AMS/hipotermia), PRIORITASKAN saran keselamatan di
   atas topik lain.
3. Gunakan info profil user (level pengalaman & gunung yang sudah didaki,
   ada di bagian konteks) untuk memberi rekomendasi yang personal.
4. Untuk pertanyaan tentang gunung di luar 7 gunung di knowledge base,
   jawab dengan pengetahuan umummu, tapi tetap sampaikan keterbatasan
   info dan sarankan cek sumber resmi.
5. Output dari tool "mountain_info" diawali tag "[SUMBER: ...]" yang
   berisi nama file knowledge base yang dipakai. Tag ini HANYA untuk
   referensi internal. JANGAN tampilkan/sebutkan tag ini ke user dalam
   jawabanmu.
"""


# =========================================================
# 3. SETUP RESOURCES (CACHED - llm & tools, termasuk vector store RAG)
# =========================================================
@st.cache_resource(show_spinner="Menyiapkan Pendaki AI (membangun knowledge base)...")
def setup_resources():
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.1-flash-lite",
        temperature=0.7,
        top_p=0.9,
        max_output_tokens=1024,
    )

    retriever_tool = build_retriever_tool(kb_dir="knowledge_base")
    tools = [retriever_tool, weather_check, generate_packing_checklist]
    return llm, tools


def get_agent(profile_context: str):
    """Bangun agent dengan system prompt yang sudah disisipi konteks profil
    user terkini. Pembuatan agent (compile graph) ringan, jadi tidak masalah
    dibuat ulang setiap request, sedangkan LLLM & tools tetap memakai
    instance yang sudah di-cache."""
    llm, tools = setup_resources()
    full_system_prompt = (
        SYSTEM_PROMPT
        + "\n\nKONTEKS PROFIL USER SAAT INI:\n"
        + profile_context
    )
    return create_agent(model=llm, tools=tools, system_prompt=full_system_prompt)


def extract_text(content) -> str:
    """Ekstrak teks dari AIMessage.content. Gemini 2.5 kadang mengembalikan
    content sebagai list of blocks (text, thinking signature, dll), bukan
    string biasa - jadi perlu digabungkan hanya bagian type='text'."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)

def stream_agent_response(agent, messages, meta: dict):
    """Generator yang menghasilkan potongan teks jawaban secara streaming
    (token-per-token) dari agent. Hanya meneruskan teks dari AIMessageChunk
    (jawaban final), bukan dari tool-call chunks.

    Selain itu, menangkap nama file sumber dari tool "mountain_info"
    (lihat tag "[SUMBER: ...]" di tools.py) dan menyimpannya ke `meta`
    supaya bisa ditampilkan setelah streaming selesai.

    Jika terjadi error (rate limit, timeout, dll), tangkap dan tampilkan
    pesan ramah ke user daripada stack trace mentah."""
    meta["sources"] = []
    try:
        for mode, data in agent.stream(
            {"messages": messages},
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                chunk, _metadata = data
                if isinstance(chunk, AIMessageChunk):
                    text = extract_text(chunk.content)
                    if text:
                        yield text
            elif mode == "updates":
                for node_update in data.values():
                    if not isinstance(node_update, dict):
                        continue
                    for msg in node_update.get("messages", []):
                        if isinstance(msg, ToolMessage) and msg.name == "mountain_info":
                            content = extract_text(msg.content)
                            match = re.match(r"\[SUMBER: (.*?)\]", content)
                            if match:
                                for s in match.group(1).split(", "):
                                    s = s.strip()
                                    if s and s not in meta["sources"]:
                                        meta["sources"].append(s)

    except Exception as e:
        st.session_state["last_error"] = str(e)
        yield (
            "\n\nSorry ya guys, Pendaki AI lagi ada gangguan koneksi ke "
            "server AI nih. Coba lo kirim ulang "
            "pesannya nanti lagi ya."
        )

# =========================================================
# QUICK ACTIONS - contoh prompt untuk memudahkan demo
# =========================================================
QUICK_ACTIONS = [
    "Rekomendasi gunung buat pemula",
    "Cek cuaca Gunung Semeru",
    "Bikinin checklist packing 2D1N ke Prau",
    "Apa itu AMS dan cara mencegahnya?",
]

def load_session_into_state(session_id: str):
    """Muat seluruh pesan dari sebuah session Supabase ke session_state,
    supaya chat bisa dilanjutkan."""
    rows = db.load_messages(session_id)

    messages = []
    chat_history = []
    for row in rows:
        messages.append({"role": row["role"], "content": row["content"]})
        if row["role"] == "user":
            chat_history.append(HumanMessage(content=row["content"]))
        else:
            chat_history.append(AIMessage(content=row["content"]))

    st.session_state["messages"] = messages
    st.session_state["chat_history"] = chat_history
    st.session_state["current_session_id"] = session_id


# =========================================================
# 4. SIDEBAR - RIWAYAT CHAT (SUPABASE)
# =========================================================
with st.sidebar:
    st.header("💬 Riwayat Chat")

    if not SUPABASE_ENABLED:
        st.caption(
            "Fitur riwayat chat belum aktif."
        )
    else:
        if st.button("➕ Chat Baru", use_container_width=True):
            st.session_state["messages"] = []
            st.session_state["chat_history"] = []
            st.session_state["current_session_id"] = None
            st.rerun()

        search_query = st.text_input("🔍 Cari", placeholder="Cari kata kunci...")
        if search_query:
            try:
                results = db.search_messages(search_query, USER_ID)
            except Exception as e:
                results = []
                st.caption(f"Gagal mencari: {e}")

            if not results:
                st.caption("Tidak ada hasil.")
            else:
                st.caption(f"{len(results)} hasil ditemukan:")
                for r in results:
                    label = f"{r['session_title']} — {r['content'][:40]}..."
                    if st.button(label, key=f"search_{r['session_id']}_{r['created_at']}", use_container_width=True):
                        load_session_into_state(r["session_id"])
                        st.rerun()
        else:
            st.caption("Chat terbaru:")
            try:
                sessions = db.list_sessions(USER_ID)
            except Exception as e:
                sessions = []
                st.caption(f"Gagal memuat riwayat: {e}")

            for s in sessions:
                is_active = st.session_state.get("current_session_id") == s["id"]
                label = ("📌 " if is_active else "") + s["title"]
                if st.button(label, key=f"session_{s['id']}", use_container_width=True):
                    load_session_into_state(s["id"])
                    st.rerun()

    st.divider()


# =========================================================
# 5. SIDEBAR - PROFIL USER (MEMORY)
# =========================================================
with st.sidebar:
    st.header("🧭 Profil Pendaki")
    st.caption("Info ini akan dipakai Pendaki AI untuk personalisasi.")

    name = st.text_input("Siapa Nama lo?", value=st.session_state.get("nama", ""), placeholder="Contoh: Pria Solo")
    level = st.selectbox(
        "Apa level pengalaman lo?",
        ["", "Pemula", "Menengah", "Mahir"],
        index=["", "Pemula", "Menengah", "Mahir"].index(st.session_state.get("level", "")),
    )
    mountain_list = st.text_input(
        "Gunung yang pernah lo daki (pisahkan koma)",
        value=st.session_state.get("mountain_list", ""),
        placeholder="Contoh: Prau, Merbabu",
    )

    st.session_state["nama"] = name
    st.session_state["level"] = level
    st.session_state["mountain_list"] = mountain_list

    st.divider()
    st.caption(
        "Knowledge base RAG mencakup 7 gunung populer: Semeru, Rinjani, Gede, "
        "Prau, Merbabu, Sindoro, Slamet."
    )

    if not SUPABASE_ENABLED and st.button("🗑️ Reset Chat"):
        st.session_state["messages"] = []
        st.session_state["chat_history"] = []
        st.session_state["current_session_id"] = None
        st.rerun()


def ringkasan_profil() -> str:
    if not name and not level and not mountain_list:
        return "Belum ada info profil user."
    return (
        f"Nama: {name or '-'} | "
        f"Level pengalaman: {level or '-'} | "
        f"Gunung yang pernah didaki: {mountain_list or '-'}"
    )


# =========================================================
# 6. MAIN CHAT UI
# =========================================================
st.title("🏔️ Pendaki AI")
st.caption("Asisten AI untuk perencanaan pendakian gunung di Indonesia.")

if not GEMINI_API_KEY:
    st.warning(
        "Pendaki AI belum di-set. Coba lagi nanti ya guys, atau hubungi admin buat aktifin fitur ini."
    )
    st.stop()

if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "current_session_id" not in st.session_state:
    st.session_state["current_session_id"] = None

# Tampilkan riwayat chat
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Quick action buttons: hanya muncul kalau percakapan masih kosong.
if not st.session_state["messages"]:
    st.caption("Coba lo tanya:")
    cols = st.columns(2)
    for i, action in enumerate(QUICK_ACTIONS):
        if cols[i % 2].button(action, use_container_width=True, key=f"qa_{i}"):
            st.session_state["pending_input"] = action
            st.rerun()

# Input chat
user_input = st.chat_input("Tanyain gue apa saja soal pendakian...")
if not user_input and "pending_input" in st.session_state:
    user_input = st.session_state.pop("pending_input")

if user_input:
    st.session_state["messages"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        try:
            agent = get_agent(ringkasan_profil())
            messages = st.session_state["chat_history"] + [HumanMessage(content=user_input)]
            meta = {}
            answer = st.write_stream(stream_agent_response(agent, messages, meta))

            if meta.get("sources"):
                with st.expander("📄 Sumber referensi (knowledge base)"):
                    for src in meta["sources"]:
                        st.caption(f"- {src}")
        except Exception as e:
            answer = (
                "Sorry ya guys, Pendaki AI gagal memproses permintaan ini "
                f"(error: {e}). Coba lo kirim ulang lagi deh "
                "pesannya."
            )
            st.markdown(answer)

    st.session_state["messages"].append({"role": "assistant", "content": answer})
    st.session_state["chat_history"].append(HumanMessage(content=user_input))
    st.session_state["chat_history"].append(AIMessage(content=answer))

    # Simpan ke Supabase (jika dikonfigurasi)
    if SUPABASE_ENABLED:
        try:
            if st.session_state["current_session_id"] is None:
                st.session_state["current_session_id"] = db.create_session(user_input, USER_ID)
            db.save_message(st.session_state["current_session_id"], "user", user_input)
            db.save_message(st.session_state["current_session_id"], "assistant", answer)
        except Exception as e:
            st.caption(f"Gagal menyimpan riwayat: {e}")
