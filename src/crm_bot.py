import asyncio
import time
import json
import os
from datetime import datetime, timezone

import config
import storage
import mock_agent
from device import WhatsAppDevice
import re

SEEN_MESSAGES_FILE = "../data/seen_messages.json"

def load_seen_messages():
    if os.path.exists(SEEN_MESSAGES_FILE):
        try:
            with open(SEEN_MESSAGES_FILE, "r") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_seen_message(msg_key: str):
    seen = load_seen_messages()
    seen.add(msg_key)
    with open(SEEN_MESSAGES_FILE, "w") as f:
        json.dump(list(seen), f)

def find_ticket_by_sender(sender: str):
    data = storage._read_csv()
    sender_lower = sender.lower()
    for row in data:
        bn = row.get("Business Name", "").lower()
        pn = row.get("Phone Number", "")
        if pn == sender or bn == sender_lower or (bn and bn in sender_lower) or (sender_lower and sender_lower in bn):
            return row
    norm_sender = re.sub(r'[^\d+]', '', sender)
    if norm_sender:
        for row in data:
            norm_row = re.sub(r'[^\d+]', '', row.get("Phone Number", ""))
            if norm_row and norm_sender.endswith(norm_row[-10:]):
                return row
    return None

def handle_inbound_sync(sender: str, text: str, device) -> str:
    ticket = find_ticket_by_sender(sender)
    
    # 1. Evaluate Auto-Reply
    eval_result = mock_agent.evaluate_inbound(text)
    if eval_result == "AUTO_REPLY":
        if ticket:
            storage.update_status(ticket["Phone Number"], "Auto-Reply")
        else:
            storage.add_ticket(sender, sender, "Auto-Reply", datetime.now(timezone.utc).isoformat())
        return f"Ignored Auto-Reply from {sender}"
        
    # 2. Handle New Lead
    if not ticket:
        storage.add_ticket(sender, sender, "Negotiating", datetime.now(timezone.utc).isoformat())
        ticket = find_ticket_by_sender(sender)
        
    phone = ticket["Phone Number"]
    
    # 3. Handle Opt-out
    if text.lower().strip() in ["stop", "cancel", "not interested"]:
        reply = "Thank you. Opted out."
        storage.update_status(phone, "Opt-Out", "Last Reply Received", datetime.now(timezone.utc).isoformat())
        device.send_message(phone, reply)
        device.go_home()
        return f"Opted-out {phone}"
        
    # 4. Normal Reply
    storage.append_chat(phone, "user", text)
    reply = mock_agent.generate_reply(ticket)
    
    if "HANDOVER_REQUIRED" in reply:
        if config.ENABLE_HUMAN_HANDOVER:
            storage.update_status(phone, "Human Handover", "Last Reply Received", datetime.now(timezone.utc).isoformat())
            fallback_msg = "Let me get a human agent to answer that for you right away!"
            device.send_message(phone, fallback_msg)
            device.go_home()
            return f"Triggered Human Handover for {phone}"
        else:
            reply = "I'm just an automated assistant, but I'll make sure someone gets back to you soon!"
        
    import os
    auto_mode = "ON"
    if os.path.exists("../data/auto_mode.txt"):
        auto_mode = open("../data/auto_mode.txt").read().strip()
        
    storage.append_chat(phone, "assistant", reply)
    storage.update_status(phone, "Negotiating", "Last Reply Received", datetime.now(timezone.utc).isoformat(), bot_msg=reply)
    device.send_message(phone, reply)
    device.go_home()
    return f"Replied to {phone}"

async def notification_listener(device, queue: asyncio.Queue):
    print("Notification listener started...")
    seen = load_seen_messages()
    
    # Pre-warm without processing if there are many unread
    init_notifs = await asyncio.to_thread(device.get_notifications)
    for notif in init_notifs:
        key = f"{notif['sender']}:{notif['text']}"
        if key not in seen:
            save_seen_message(key)
            seen.add(key)
            
    while True:
        try:
            notifs = await asyncio.to_thread(device.get_notifications)
            for notif in notifs:
                key = f"{notif['sender']}:{notif['text']}"
                if key not in seen:
                    save_seen_message(key)
                    seen.add(key)
                    await queue.put((notif["sender"], notif["text"]))
        except Exception as e:
            print(f"Error reading notifications: {e}")
        await asyncio.sleep(2)

async def inbound_worker(device, queue: asyncio.Queue, ui_lock: asyncio.Lock):
    print("Inbound worker started...")
    while True:
        sender, text = await queue.get()
        t = datetime.now().strftime("%H:%M:%S")
        print(f"[{t}] Inbound MSG from {sender}")
        
        # We run the synchronous blocking function in a separate thread so it doesn't freeze the listener!
        async with ui_lock:
            action_log = await asyncio.to_thread(handle_inbound_sync, sender, text, device)
        print(f"[{t}] {action_log}")
        
        queue.task_done()

async def outbound_worker(device, ui_lock: asyncio.Lock):
    print("Outbound worker started...")
    while True:
        ticket = await asyncio.to_thread(storage.get_pending_ticket)
        if ticket:
            phone = ticket["Phone Number"]
            t = datetime.now().strftime("%H:%M:%S")
            print(f"[{t}] Outreach: {phone}")
            
            msg = await asyncio.to_thread(mock_agent.generate_initial_message, ticket)
            
            auto_mode = "ON"
            if os.path.exists("../data/auto_mode.txt"):
                auto_mode = open("../data/auto_mode.txt").read().strip()
                
            if auto_mode == "OFF":
                print(f"[{t}] Drafted outreach for {phone} (Approval Needed)")
                await asyncio.to_thread(storage.update_status, phone, "Draft Approval Needed", bot_msg=msg)
            else:
                async with ui_lock:
                    success = await asyncio.to_thread(device.send_message, phone, msg)
                    
                    if success:
                        await asyncio.to_thread(storage.update_status, phone, "Sent", "Cold Opener Timestamp", datetime.now(timezone.utc).isoformat(), bot_msg=msg)
                    else:
                        await asyncio.to_thread(storage.update_status, phone, "Invalid Number")
                        
                    await asyncio.to_thread(device.go_home)
            
            import random
            delay = random.randint(config.ANTI_BAN_DELAY_MIN, config.ANTI_BAN_DELAY_MAX)
            print(f"Anti-ban: Waiting {delay}s before next outreach...")
            for _ in range(delay):
                if os.path.exists("../data/reset_cooldown.flag"):
                    try:
                        os.remove("../data/reset_cooldown.flag")
                    except:
                        pass
                    print("Cooldown manually reset!")
                    break
                await asyncio.sleep(1)
        else:
            await asyncio.sleep(30)

async def run_headless_async():
    device = WhatsAppDevice(config.ADB_TARGET_IP)
    if not device.ensure_connection():
        print("Failed to connect device.")
        return
    device.go_home()
    
    queue = asyncio.Queue()
    ui_lock = asyncio.Lock()
    tasks = []
    
    if config.ENABLE_INBOUND_REPLIES:
        tasks.append(notification_listener(device, queue))
        tasks.append(inbound_worker(device, queue, ui_lock))
        
    if config.ENABLE_OUTBOUND_OUTREACH:
        tasks.append(outbound_worker(device, ui_lock))
        
    if config.ENABLE_WEB_DASHBOARD:
        print("Starting FastAPI Web Dashboard on port 8000...")
        import subprocess
        subprocess.Popen(["../venv/bin/uvicorn", "web:app", "--host", "0.0.0.0", "--port", "8000"])

    if not tasks:
        print("All bot features disabled in config. Exiting.")
        return
        
    await asyncio.gather(*tasks)

def run_headless():
    asyncio.run(run_headless_async())

if __name__ == "__main__":
    run_headless()
