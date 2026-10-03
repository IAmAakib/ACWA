# ACWA (Auto Contact WhatsApp)

> **⚠️ DISCLAIMER: PROJECT DISCONTINUED & INCOMPLETE**
> This project is incomplete and no longer maintained. While it includes "anti-ban" measures (like randomized delays and UI automation), **ban prevention is NOT guaranteed**. WhatsApp may still flag or ban accounts using this software. Use at your own risk.

*Note: This project was built with the help of AI agents.*

ACWA is an automated, AI-driven WhatsApp outreach and negotiation system. It leverages Waydroid and ADB to control a WhatsApp Business instance, automatically reaching out to leads from a CSV file, handling inbound replies via an LLM, and providing a web dashboard for monitoring.

## Key Features

- **Automated Outbound Outreach**: Reads pending leads from a CSV, generates a natural, custom AI greeting, and sends it via ADB to the WhatsApp Business app.
- **Inbound LLM Negotiation**: Listens to Android notifications to detect replies, passes them through LiteLLM for natural conversation, and continues negotiation automatically.
- **Human Handover**: Automatically detects if a prospect requires human assistance or complex answers, pausing the bot and notifying the user.
- **FastAPI Web Dashboard**: A built-in web dashboard to view live statistics, lead statuses, and chat history.
- **Anti-Ban Mechanisms**: Configurable randomized delays between messages to mimic human behavior and avoid WhatsApp spam flags.

---

## Tech Stack

- **Language**: Python 3
- **Automation**: ADB (Android Debug Bridge) + Waydroid
- **AI/LLM**: LiteLLM (Supports Ollama, OpenAI, Anthropic, etc.)
- **Web Dashboard**: FastAPI + Uvicorn
- **Data Storage**: CSV (Leads) + JSON (Chat History)

---

## Prerequisites

Before setting up ACWA, ensure you have the following installed and running:

- **Python 3.10+**
- **Waydroid** (or an active Android Emulator / Physical device with ADB enabled)
- **WhatsApp Business** installed inside Waydroid/Emulator and logged into an account.
- **ADB (Android Platform Tools)** installed on your host machine.
- An active LLM API or local Ollama instance running.

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/user/acwa.git
cd acwa
```

### 2. Set Up Python Environment

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt
```

### 3. Connect to Waydroid via ADB

Ensure Waydroid is running and the UI is active. Connect ADB to the Waydroid container:

```bash
# Check Waydroid IP
waydroid status

# Connect ADB (Replace with your Waydroid IP)
adb connect 192.168.240.112:5555
```

Verify the device is connected:

```bash
adb devices
```

### 4. Configure the Project

Edit `src/config.py` to match your environment. Specifically, update `ADB_TARGET_IP` to match the IP you found in the previous step, and set your desired `LITELLM_MODEL`.

### 5. Prepare the Data

Place your leads in `data/WhatsApp_Outreach_Pipeline_Api_Filtered.csv`.
The CSV must have the following headers:
`Phone Number`, `Business Name`, `Scraped Flaw/Detail`, `Status`, `Minimum Price Floor`, `Cold Opener Timestamp`, `Last Reply Received`, `AI Assigned Persona/Role`, `Bot Last Message`

Make sure the phone numbers contain only digits and include the country code (e.g., `919876543210`). Set the `Status` to `Pending` for new leads.

### 6. Start the Bot

Run the main CRM bot script:

```bash
cd src
../venv/bin/python crm_bot.py
```

Depending on your `config.py` settings, this will start the outbound outreach, inbound listeners, and the web dashboard concurrently.

---

## Architecture

### Directory Structure

```text
acwa/
├── data/
│   ├── WhatsApp_Outreach_Pipeline_Api_Filtered.csv  # Main leads database
│   ├── seen_messages.json                           # Tracks processed notifications
│   ├── reset_cooldown.flag                          # (Optional) Break sleep loop
│   └── chats/                                       # Individual JSON chat histories
├── src/
│   ├── config.py         # Global configuration and feature toggles
│   ├── crm_bot.py        # Main asyncio entrypoint (workers and listeners)
│   ├── device.py         # ADB wrapper for WhatsApp UI automation
│   ├── mock_agent.py     # LiteLLM integration for prompt generation
│   ├── storage.py        # CSV/JSON file I/O operations
│   └── web.py            # FastAPI dashboard application
├── requirements.txt      # Python dependencies
└── README.md             # This documentation
```

### Request Lifecycle (Outbound)
1. `outbound_worker` in `crm_bot.py` polls `storage.py` for a `Pending` lead.
2. The lead is passed to `mock_agent.generate_initial_message()`.
3. The AI generates a customized, casual greeting based on the business name.
4. `device.py` constructs a WhatsApp intent (`whatsapp://send?phone=...`) and triggers it via ADB.
5. The device simulates a button press (Keyevent 66 / Enter) to send the message.
6. The lead's status is updated to `Sent` in the CSV.

### Request Lifecycle (Inbound)
1. `notification_listener` continuously polls `dumpsys notification` via ADB.
2. When a notification from `com.whatsapp.w4b` arrives, it extracts the sender and text.
3. The message is queued to `inbound_worker`.
4. The system evaluates if the message is a human reply or an Auto-Reply (e.g., "Press 1 for...").
5. If valid, the chat history is retrieved, and the AI generates a contextual reply.
6. The reply is sent via ADB, and the CSV status updates to `Negotiating`.

---

## Configuration Reference (`src/config.py`)

| Variable | Description | Default |
|----------|-------------|---------|
| `ADB_TARGET_IP` | The IP address and port of your Waydroid/ADB device. | `192.168.240.112:5555` |
| `LITELLM_MODEL` | The LLM model string for LiteLLM to use for generation. | `ollama/huihui_ai/llama3.2...` |
| `WEBHOOK_PORT` | Port for the FastAPI Web Dashboard. | `8000` |
| `ENABLE_OUTBOUND_OUTREACH` | Master switch for automated sending to pending leads. | `True` |
| `ENABLE_INBOUND_REPLIES` | Switch to enable reading notifications and auto-replying. | `False` |
| `ENABLE_WEB_DASHBOARD` | Auto-starts `web.py` when running `crm_bot.py`. | `False` |
| `ENABLE_HUMAN_HANDOVER` | Stops bot and notifies user if client asks for a human. | `True` |
| `ANTI_BAN_DELAY_MIN` | Minimum seconds to sleep between outbound messages. | `10` |
| `ANTI_BAN_DELAY_MAX` | Maximum seconds to sleep between outbound messages. | `49` |

---

## Available Scripts

| Command | Description |
|---------|-------------|
| `python src/crm_bot.py` | Starts the main automation loops based on `config.py`. |
| `uvicorn web:app` | Manually start the FastAPI dashboard from the `src/` directory. |

### Resetting the Cooldown
If the bot is currently in a long anti-ban sleep cycle and you want to force it to proceed immediately, create a flag file:
```bash
touch data/reset_cooldown.flag
```
The bot checks for this file every second, and will instantly break the sleep and delete the flag.

---

## Troubleshooting

### Device Fails to Connect
**Error:** `Failed to connect device.` or ADB timeout.
**Solution:**
1. Ensure Waydroid is running: `waydroid show-full-ui`.
2. Check the IP address via `waydroid status`.
3. Update `ADB_TARGET_IP` in `src/config.py` to match the exact IP.
4. Run `adb connect <YOUR_IP>:5555` manually to ensure your host trusts the device.

### Bot Sends to Wrong Chat or Fails to Send
**Error:** Failsafe triggered: Number is not on WhatsApp.
**Solution:**
Ensure the phone numbers in the CSV are strictly numeric and contain the country code (e.g., 91 for India) without a leading `+` or `00`. `device.py` relies on the WhatsApp URL scheme, which strictly requires this format.

### Notifications Not Being Read
**Error:** Bot doesn't reply to incoming messages.
**Solution:**
1. Ensure `ENABLE_INBOUND_REPLIES = True` in `config.py`.
2. Make sure WhatsApp Business notifications are **enabled** in Android settings, and message previews (content) are visible on the lock screen/notification shade. `dumpsys notification` cannot read redacted/hidden notifications.

### "ModuleNotFoundError"
**Error:** Missing `litellm`, `fastapi`, etc.
**Solution:**
Ensure you are running the scripts using the python executable inside your virtual environment (`venv/bin/python`), or that you have activated the virtual environment before running `python src/crm_bot.py`.
