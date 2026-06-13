# Pendaki AI 🏔️

Chatbot AI asisten pendakian gunung di Indonesia, dibangun dengan:

- **Streamlit**: user-interface chat web
- **LangChain (`create_agent`)**: AI Agent yang bisa memilih tools sendiri
- **RAG + Vector Database (FAISS)**: knowledge base 7 gunung populer Indonesia
- **Tool/Function Calling**:
  - `mountain_info`: retriever RAG (jalur, sumber air, titik camp, tips, dll)
  - `weather_check`: integrasi OpenWeatherMap API
  - `generate_packing_checklist`: generator checklist perlengkapan
- **Memory**: profil user (level, gunung yang sudah didaki) via sidebar +
  riwayat chat persisten (Supabase) yang bisa di-search
- **UX tambahan**:
  - Quick action buttons (contoh prompt) saat percakapan masih kosong/baru dimulai
  - Jawaban di-stream token-per-token
  - Error handling ramah jika Gemini API kena rate limit/timeout

## Struktur Project

```
pendaki-ai/
├── app.py                  # Streamlit app + agent
├── tools.py                # Definisi tools (cuaca, checklist, RAG retriever)
├── db.py                   # Koneksi Supabase (riwayat chat & search)
├── debug_stream.py         # Cek apakah tool berfungsi
├── supabase_schema.sql     # SQL schema untuk tabel riwayat chat
├── knowledge_base/         # Dokumen sumber RAG (7 gunung populer di Indonesia)
│   ├── semeru.txt
│   ├── rinjani.txt
│   ├── gede.txt
│   ├── prau.txt
│   ├── merbabu.txt
│   ├── sindoro.txt
│   └── slamet.txt
├── requirements.txt
└── secrets.toml.example
```

## Setup & Jalankan Lokal

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Siapkan API key:
   - Buat folder `.streamlit/` dan file `.streamlit/secrets.toml`
   - Isi seperti contoh di `secrets.toml.example`:

     ```toml
     GEMINI_API_KEY = "API KEY GEMINI ANDA"
     OPENWEATHER_API_KEY = "API KEY OPENWEATHERMAP ANDA"

     SUPABASE_URL = "URL SUPABASE ANDA"
     SUPABASE_KEY = "PUBLISHABLE (ATAU ANON) API KEY SUPABASE ANDA"
     ```

   - Atau alternatif: set environment variable `GEMINI_API_KEY`,
     `OPENWEATHER_API_KEY`, `SUPABASE_URL`, dan `SUPABASE_KEY` manual di app.py sebelum menjalankan app.

3. Jalankan:

   ```bash
   streamlit run app.py
   ```

   Saat pertama kali dijalankan, app akan membangun vector store dari
   dokumen di `knowledge_base/` (proses ini menggunakan Google Embedding
   API (Embedding 2), butuh `GEMINI_API_KEY` valid dan koneksi internet). Proses ini
   di-cache (`@st.cache_resource`) sehingga hanya terjadi sekali per sesi
   server.

## API Key

- **Gemini API key**: [Google AI Studio](https://aistudio.google.com/)
  - Dipakai untuk LLM (`gemini-3.1-flash-lite`) dan embedding (`gemini-embedding-2`)
- **OpenWeather API key**: [Open Weather Map](https://openweathermap.org/api)
  (tier gratis)
  - Jika key ini tidak diisi, fitur cek cuaca akan mengembalikan pesan
    "Fitur cek cuaca belum aktif" tanpa membuat app crash.
- **Supabase**: [supabase.com](https://supabase.com/)
  - Dipakai untuk menyimpan riwayat chat dan mencari sesi chat user.
  1. Buat project baru (tier gratis).
  2. Buka **SQL Editor**, jalankan isi file `supabase_schema.sql` untuk
     membuat tabel `chat_sessions` dan `chat_messages` beserta RLS policy
     "allow all" (perlu untuk anon key bisa baca/tulis).
  3. Ambil `Project URL` dan `Publishable API key` dari
     **Project Settings -> API**, isi sebagai `SUPABASE_URL` dan
     `SUPABASE_KEY`.
  - Jika tidak diisi, fitur riwayat chat & search akan nonaktif (sidebar
    akan menampilkan pesan info), tapi chat tetap berfungsi normal dalam
    1 sesi.

### Catatan soal pemisahan riwayat antar user

App ini **tidak punya sistem login**. Pemisahan riwayat dilakukan dengan
cara sederhana: setiap browser mendapat `user_id` acak (UUID) yang
disimpan di URL (`?uid=...`), lalu setiap session/pesan disimpan dengan
`user_id` ini. Riwayat hanya ditampilkan untuk `user_id` yang cocok.

Implikasinya:

- Jika buka di browser/incognito/device lain, `user_id` baru dan riwayat
  kosong (terpisah).
- Jika refresh halaman dengan URL yang sama, `user_id` tetap sama dan riwayat
  tetap muncul.
- Ini BUKAN keamanan tingkat PRODUCTION (TIDAK DISARANKAN untuk PRODUCTION, hanya untuk keperluan TUGAS/DEMO saja). RLS di Supabase diset "allow all" agar anon key bisa baca/tulis tanpa Supabase Auth, sehingga pemisahan `user_id` hanya dilakukan oleh aplikasi, bukan oleh database.

## Deployment (Streamlit Community Cloud)

1. Push project ini ke repo GitHub (`secrets.toml` asli tidak di-commit (ditambahkan di .gitignore),
   tetapi sudah ada `secrets.toml.example` sebagai panduan).
2. Buka [share.streamlit.io](https://share.streamlit.io), connect ke repo,
   pilih `app.py` sebagai entry point.
3. Di dashboard Streamlit Cloud, masuk ke **Settings -> Secrets**, lalu
   tempel isi `secrets.toml` (GEMINI_API_KEY dan OPENWEATHER_API_KEY).
4. Lalu, deploy. App ini akan jalan 24/7 selama dalam batas free tier Streamlit Cloud.

> Catatan: project ini TIDAK di-deploy ke Vercel karena Streamlit
> membutuhkan server Python yang berjalan terus-menerus, bukan model
> serverless/function seperti yang digunakan Vercel.

## Menambah Gunung ke Knowledge Base

1. Tambahkan file `.txt` baru di folder `knowledge_base/` dengan format
   serupa file yang sudah ada (jalur, estimasi waktu, sumber air, titik
   camp, tips, dll).
2. Jika ingin gunung tersebut juga didukung fitur cek cuaca, tambahkan
   koordinatnya ke `MOUNTAIN_COORDS` di `tools.py`.
3. Restart app (atau clear cache `st.cache_resource`) agar vector store
   dibangun ulang dengan dokumen baru.

## Konfigurasi Parameter (untuk dokumentasi laporan)

- **Model**: `gemini-3.1-flash-lite`
- **Temperature**: `0.7` - cukup variatif untuk percakapan natural, tapi
  tetap konsisten untuk info safety pendakian gunung.
- **Gaya bahasa**: santai, hangat, gaul, dan tampak seperti senior pendaki berpengalaman.
- **Domain pengetahuan**: gunung-gunung populer Indonesia, perlengkapan,
  P3K dasar (AMS/hipotermia), etika pendakian (Leave No Trace).
