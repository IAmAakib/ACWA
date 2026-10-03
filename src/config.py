import os

ADB_TARGET_IP = os.getenv("ADB_TARGET_IP", "192.168.240.112:5555")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8000))
LITELLM_MODEL = os.getenv("LITELLM_MODEL", "ollama/huihui_ai/llama3.2-abliterate:latest")

UI_LATENCY_MIN = 90
UI_LATENCY_MAX = 240

# --- FEATURE FLAGS ---
ENABLE_OUTBOUND_OUTREACH = True
ENABLE_INBOUND_REPLIES = False      # Listen to notifications and AI reply
ENABLE_WEB_DASHBOARD = False        # Auto-start FastAPI dashboard on run
ENABLE_HUMAN_HANDOVER = True        # Stop bot if user asks for human

# --- BOT SETTINGS ---
ANTI_BAN_DELAY_MIN = 10             # Min seconds between messages
ANTI_BAN_DELAY_MAX = 49             # Max seconds between messages
MAX_LEADS_PER_DAY = 100             # Limit total outreach (0 for infinite)
