"""
Script debug untuk cek streaming agent & tool calls
=========================================================================
Tujuan: untuk cek apakah tool "mountain_info" benar-benar terpanggil, dan
lihat struktur data yang dihasilkan stream_mode=["messages","updates"].
"""

import os
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from tools import weather_check, generate_packing_checklist, build_retriever_tool, weather_check

# Setup API key (sesuaikan jika perlu)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    # Coba baca dari .streamlit/secrets.toml secara manual
    try:
        import toml
        secrets = toml.load(".streamlit/secrets.toml")
        GEMINI_API_KEY = secrets.get("GEMINI_API_KEY", "")
    except Exception:
        pass

if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
else:
    raise RuntimeError("GEMINI_API_KEY tidak ditemukan!")


llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.7)
retriever_tool = build_retriever_tool(kb_dir="knowledge_base")
tools = [retriever_tool, weather_check, generate_packing_checklist]

SYSTEM_PROMPT = (
    "Kamu adalah Trail Buddy. GUNAKAN tool 'mountain_info' setiap kali "
    "user bertanya hal spesifik tentang jalur/sumber air/titik camp gunung "
    "(Semeru, Rinjani, Gede, Prau, Merbabu, Sindoro, Slamet)."
)

agent = create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)

# Ganti query ini sesuai yang kamu test di app
query = "Berapa estimasi waktu dari Ranu Pani ke Ranu Kumbolo di Semeru?"

print(f"QUERY: {query}\n")
print("=" * 70)

messages = [HumanMessage(content=query)]

for mode, data in agent.stream({"messages": messages}, stream_mode=["messages", "updates"]):
    if mode == "messages":
        chunk, metadata = data
        if isinstance(chunk, AIMessageChunk):
            content = chunk.content
            if content:
                print(f"[messages] AIMessageChunk.content = {content!r}")

    elif mode == "updates":
        print(f"[updates] keys = {list(data.keys())}")
        for node_name, node_update in data.items():
            print(f"  node: {node_name}")
            if isinstance(node_update, dict):
                for msg in node_update.get("messages", []):
                    print(f"    message type: {type(msg).__name__}")
                    if isinstance(msg, ToolMessage):
                        print(f"      ToolMessage.name = {msg.name!r}")
                        print(f"      ToolMessage.content[:200] = {str(msg.content)[:200]!r}")
                    elif hasattr(msg, "tool_calls") and msg.tool_calls:
                        print(f"      tool_calls = {msg.tool_calls}")

print("=" * 70)
print("Selesai.")
