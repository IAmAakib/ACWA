# ACWA (Auto Contact WhatsApp)

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Status](https://img.shields.io/badge/status-discontinued-red)
![License](https://img.shields.io/badge/license-MIT-green)

An experimental, AI-driven WhatsApp outreach and negotiation system. ACWA uses Waydroid and ADB to control a WhatsApp Business instance, sends a first message to leads from a CSV file, answers inbound replies with an LLM, and exposes a web dashboard for monitoring.

> **Project status: discontinued and incomplete.**
> This project is no longer maintained. It was built as an experiment, with the help of AI agents, and is published for learning purposes only.

> **Responsible use**
> Automating a personal or Business WhatsApp account is **against WhatsApp's Terms of Service**, and accounts that do it can be restricted or permanently banned. The rate-limiting options in this project do not guarantee otherwise. Sending unsolicited bulk messages may also violate anti-spam and data-protection laws in your country (for example TCPA, GDPR, or India's TRAI rules). Only message people who have agreed to hear from you, and use this at your own risk.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Commands](#commands)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- **Outbound messaging**: reads `Pending` leads from a CSV, generates a short custom greeting with an LLM, and sends it through the WhatsApp Business app via ADB.
- **Inbound replies**: reads Android notifications to detect responses, passes them to an LLM through LiteLLM, and continues the conversation automatically.
- **Human handover**: pauses the bot and notifies you when a prospect asks for a person or needs a complex answer.
- **Web dashboard**: a FastAPI dashboard showing live stats, lead statuses, and chat history.
- **Rate limiting**: configurable random delays between outbound messages.

---

## Tech Stack

| Area | Tools |
|------|-------|
| Language | Python 3 |
| Device automation | ADB + Waydroid |
| LLM | LiteLLM (Ollama, OpenAI, Anthropic, and others) |
| Dashboard | FastAPI + Uvicorn |
| Storage | CSV (leads) and JSON (chat history) |

---

## Prerequisites

- Python 3.10+
- Waydroid, or an Android emulator or physical device with ADB enabled
- WhatsApp Business installed and logged in on that device
- ADB (Android Platform Tools) on the host machine
- An LLM API key or a running local Ollama instance

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/IAmAakib/ACWA.git
cd ACWA
```

### 2. Set up the Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Connect ADB to Waydroid

Make sure Waydroid is running with its UI active, then:

```bash
# Find the Waydroid IP
waydroid status

# Connect (replace with your IP)
adb connect 192.168.240.112:5555

# Verify
adb devices
```

### 4. Configure

Edit `src/config.py`:

- Set `ADB_TARGET_IP` to the IP from the previous step.
- Set `LITELLM_MODEL` to the model you want to use.

See the [Configuration](#configuration) table for all options.

### 5. Prepare your leads

Put your leads in `data/WhatsApp_Outreach_Pipeline_Api_Filtered.csv` with these headers:

```text
Phone Number, Business Name, Scraped Flaw/Detail, Status, Minimum Price Floor,
Cold Opener Timestamp, Last Reply Received, AI Assigned Persona/Role, Bot Last Message
```

- Phone numbers must be digits only and include the country code (for example `919876543210`), with no `+` or `00`.
- Set `Status` to `Pending` for new leads.

### 6. Run

```bash
cd src
../venv/bin/python crm_bot.py
```

Depending on your `config.py` toggles, this starts the outbound worker, the inbound listener, and the dashboard together.

---

## Architecture

### Directory structure

```text
ACWA/
├── data/
│   ├── WhatsApp_Outreach_Pipeline_Api_Filtered.csv  # Leads database
│   ├── seen_messages.json                           # Processed notifications
│   ├── reset_cooldown.flag                          # Optional: skips the current delay
│   └── chats/                                       # Per-lead JSON chat histories
├── src/
│   ├── config.py       # Global settings and feature toggles
│   ├── crm_bot.py      # Asyncio entrypoint (workers and listeners)
│   ├── device.py       # ADB wrapper for WhatsApp UI automation
│   ├── mock_agent.py   # LiteLLM integration and prompt generation
│   ├── storage.py      # CSV and JSON file I/O
│   └── web.py          # FastAPI dashboard
├── requirements.txt
└── README.md
```

### Outbound flow

1. `outbound_worker` in `crm_bot.py` picks a `Pending` lead from `storage.py`.
2. `mock_agent.generate_initial_message()` writes a casual greeting based on the business name.
3. `device.py` opens a WhatsApp intent (`whatsapp://send?phone=...`) over ADB.
4. A simulated Enter key press (keyevent 66) sends the message.
5. The lead's status is set to `Sent` in the CSV.

### Inbound flow

1. `notification_listener` polls `dumpsys notification` over ADB.
2. Notifications from `com.whatsapp.w4b` are parsed for sender and text, then queued for `inbound_worker`.
3. The worker checks whether the message is a human reply or an automated one (for example "Press 1 for...").
4. For valid replies, the chat history is loaded and the LLM generates a contextual response.
5. The reply is sent over ADB and the lead's status becomes `Negotiating`.

---

## Configuration

All settings live in `src/config.py`.

| Variable | Description | Default |
|----------|-------------|---------|
| `ADB_TARGET_IP` | IP and port of the Waydroid/ADB device | `192.168.240.112:5555` |
| `LITELLM_MODEL` | Model string passed to LiteLLM | `ollama/huihui_ai/llama3.2...` |
| `WEBHOOK_PORT` | Port for the web dashboard | `8000` |
| `ENABLE_OUTBOUND_OUTREACH` | Send to pending leads automatically | `True` |
| `ENABLE_INBOUND_REPLIES` | Read notifications and auto-reply | `False` |
| `ENABLE_WEB_DASHBOARD` | Start `web.py` together with `crm_bot.py` | `False` |
| `ENABLE_HUMAN_HANDOVER` | Stop the bot and notify you when a human is requested | `True` |
| `ANTI_BAN_DELAY_MIN` | Minimum seconds between outbound messages | `10` |
| `ANTI_BAN_DELAY_MAX` | Maximum seconds between outbound messages | `49` |

---

## Commands

| Command | Description |
|---------|-------------|
| `cd src && ../venv/bin/python crm_bot.py` | Start the automation loops based on `config.py` |
| `cd src && uvicorn web:app` | Start only the dashboard |

### Skipping the delay

To end the current delay early and continue immediately:

```bash
touch data/reset_cooldown.flag
```

The bot checks for this file every second, then deletes it and resumes.

---

## Troubleshooting

<details>
<summary><strong>Device fails to connect</strong> (<code>Failed to connect device</code> or ADB timeout)</summary>

1. Make sure Waydroid is running: `waydroid show-full-ui`.
2. Check the IP with `waydroid status`.
3. Update `ADB_TARGET_IP` in `src/config.py`.
4. Run `adb connect <YOUR_IP>:5555` manually so the host trusts the device.

</details>

<details>
<summary><strong>Wrong chat, or message fails to send</strong> (<code>Number is not on WhatsApp</code>)</summary>

Phone numbers must be digits only and include the country code (for example `91` for India), with no leading `+` or `00`. `device.py` relies on the WhatsApp URL scheme, which requires this format.

</details>

<details>
<summary><strong>Notifications are not being read</strong> (bot never replies)</summary>

1. Set `ENABLE_INBOUND_REPLIES = True` in `config.py`.
2. Enable WhatsApp Business notifications in Android settings and allow message previews on the lock screen and notification shade. `dumpsys notification` cannot read redacted notifications.

</details>

<details>
<summary><strong>ModuleNotFoundError</strong> (missing <code>litellm</code>, <code>fastapi</code>, and so on)</summary>

Run the scripts with the virtual environment's Python (`venv/bin/python`), or activate the environment first with `source venv/bin/activate`.

</details>

---

## License

Licensed under the MIT License. See [LICENSE](LICENSE) for details.
