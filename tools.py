"""
Tools/Functions untuk Pendaki AI Agent
=====================================================
Berisi 3 jenis tools yang bisa dipanggil oleh AI Agent:
1. weather_check                : integrasi OpenWeather API
2. generate_packing_checklist   : rule-based, generate daftar perlengkapan
3. build_retriever_tool         : RAG tool berbasis vector database (FAISS)
"""

import os
import requests
from langchain_core.tools import tool
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.tools.retriever import create_retriever_tool

# =========================================================
# Koordinat basecamp gunung (untuk fitur cek cuaca)
# =========================================================
MOUNTAIN_COORDS = {
    "semeru": {"lat": -8.1077, "lon": 112.9220, "nama": "Gunung Semeru (Ranu Pani)"},
    "rinjani": {"lat": -8.4108, "lon": 116.4575, "nama": "Gunung Rinjani (Sembalun)"},
    "gede": {"lat": -6.7917, "lon": 106.9408, "nama": "Gunung Gede (Cibodas)"},
    "prau": {"lat": -7.1875, "lon": 109.9203, "nama": "Gunung Prau (Patak Banteng)"},
    "merbabu": {"lat": -7.4544, "lon": 110.4404, "nama": "Gunung Merbabu (Selo)"},
    "sindoro": {"lat": -7.3000, "lon": 109.9986, "nama": "Gunung Sindoro (Kledung)"},
    "slamet": {"lat": -7.2425, "lon": 109.2089, "nama": "Gunung Slamet (Bambangan)"},
}


# =========================================================
# TOOL 1: Cek Cuaca
# =========================================================
@tool
def weather_check(nama_gunung: str) -> str:
    """Mengambil info cuaca terkini (suhu, kondisi langit, angin, kelembapan)
    untuk lokasi basecamp gunung tertentu. Gunakan tool ini jika user
    bertanya tentang cuaca di gunung tertentu.

    Args:
        nama_gunung: nama gunung, contoh: "semeru", "rinjani", "prau".
            Harus salah satu dari: semeru, rinjani, gede, prau, merbabu,
            sindoro, slamet.
    """
    key = nama_gunung.strip().lower()
    if key not in MOUNTAIN_COORDS:
        daftar = ", ".join(MOUNTAIN_COORDS.keys())
        return (f"Data koordinat untuk '{nama_gunung}' belum tersedia. "
                f"Gunung yang didukung untuk cek cuaca: {daftar}.")

    api_key = os.environ.get("OPENWEATHER_API_KEY", "")
    if not api_key:
        return "Fitur cek cuaca belum aktif."

    info = MOUNTAIN_COORDS[key]
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {
        "lat": info["lat"],
        "lon": info["lon"],
        "appid": api_key,
        "units": "metric",
        "lang": "id",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cuaca = data["weather"][0]["description"]
        suhu = data["main"]["temp"]
        terasa = data["main"]["feels_like"]
        kelembapan = data["main"]["humidity"]
        angin = data["wind"]["speed"]

        return (
            f"Cuaca terkini di {info['nama']}: "
            f"kondisi {cuaca}, suhu {suhu}°C (terasa seperti {terasa}°C), "
            f"kelembapan {kelembapan}%, angin {angin} m/s. "
            f"(Data dari OpenWeatherMap, tapi tetap cek update terbaru sebelum berangkat)"
        )
    except Exception as e:
        return f"Gagal mengambil data cuaca: {e}"


# =========================================================
# TOOL 2: Generator Checklist Packing
# =========================================================
BASE_ITEMS = [
    "Tas carrier (sesuaikan ukuran dengan durasi)",
    "Sepatu/sandal gunung",
    "Jas hujan / rain cover tas",
    "Headlamp + baterai cadangan",
    "Botol/tempat air minum",
    "P3K pribadi (obat pribadi, plester, antiseptik)",
    "Sunblock & kacamata hitam",
    "Trash bag (bawa turun sampah sendiri)",
    "Kartu identitas (KTP) & surat sehat jika diperlukan",
]

CLOTHING_PER_DAY = [
    "Baju ganti (quick-dry, hindari bahan katun)",
    "Celana lapangan",
    "Kaos kaki cadangan",
]

SLEEP_GEAR = [
    "Tenda (dan flysheet)",
    "Sleeping bag",
    "Matras",
    "Jaket tebal/down jacket untuk malam",
    "Sarung tangan & kupluk/buff",
]

COOKING_GEAR = [
    "Kompor portable + gas/bahan bakar",
    "Nesting/peralatan masak ringan",
    "Makanan utama (sesuai jumlah hari + cadangan 1 hari)",
    "Snack berenergi tinggi (cokelat, energy bar, dll)",
]

EXTREME_MOUNTAINS = {"semeru", "rinjani", "slamet"}
EXTREME_EXTRA = [
    "Masker (debu vulkanik/gas kawah)",
    "Trekking pole (sangat membantu di jalur curam berpasir)",
    "Gaiter (pelindung sepatu dari pasir/kerikil)",
]


@tool
def generate_packing_checklist(nama_gunung: str, jumlah_hari: int) -> str:
    """Membuat daftar checklist perlengkapan pendakian berdasarkan nama
    gunung dan jumlah hari pendakian. Gunakan tool ini ketika user minta
    bantuan menyiapkan perlengkapan/packing list untuk pendakian.

    Args:
        nama_gunung: nama gunung tujuan, contoh "semeru" atau "prau".
        jumlah_hari: jumlah hari pendakian (termasuk malam menginap),
            misal 2 untuk pendakian "2D1N" atau pendakian 2 hari 1 malam
            atau yang lainnya.
    """
    jumlah_hari = max(1, int(jumlah_hari))
    items = list(BASE_ITEMS)

    # Pakaian disesuaikan jumlah hari
    for _ in range(jumlah_hari):
        items.extend(CLOTHING_PER_DAY)

    # Perlengkapan tidur hanya relevan jika ada minimal 1 malam
    if jumlah_hari >= 1:
        items.extend(SLEEP_GEAR)
        items.extend(COOKING_GEAR)

    # Tambahan khusus gunung dengan jalur ekstrem
    key = nama_gunung.strip().lower()
    if key in EXTREME_MOUNTAINS:
        items.extend(EXTREME_EXTRA)

    checklist_text = "\n".join(f"- {item}" for item in items)
    return (
        f"Checklist packing untuk {nama_gunung.title()} ({jumlah_hari} hari):\n"
        f"{checklist_text}"
    )


# =========================================================
# TOOL 3: RAG Retriever (Vector Database)
# =========================================================
def build_retriever_tool(kb_dir: str = "knowledge_base"):
    """Membangun vector store dari dokumen knowledge base gunung, lalu
    membungkusnya sebagai tool retriever untuk agent (RAG)."""

    loader = DirectoryLoader(kb_dir, glob="*.txt", loader_cls=TextLoader)
    docs = loader.load()

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(docs)

    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-2")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

    @tool
    def mountain_info(query: str) -> str:
        """Mencari informasi detail tentang jalur pendakian, estimasi waktu
        tempuh, tingkat kesulitan, sumber air, titik camp, dan tips untuk
        gunung-gunung yang ada di knowledge base (Semeru, Rinjani, Gede,
        Prau, Merbabu, Sindoro, Slamet).

        Args:
            query: pertanyaan atau topik yang ingin dicari, contoh:
                'jalur pendakian Semeru via Ranu Pani' atau
                'sumber air di Prau'.
        """
        retrieved_docs = retriever.invoke(query)

        sumber = []
        for d in retrieved_docs:
            nama_file = os.path.basename(d.metadata.get("source", "unknown"))
            if nama_file not in sumber:
                sumber.append(nama_file)

        isi = "\n\n---\n\n".join(d.page_content for d in retrieved_docs)
        header = f"[SUMBER: {', '.join(sumber)}]\n"
        return header + isi

    return mountain_info
