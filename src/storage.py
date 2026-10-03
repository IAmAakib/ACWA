import csv
import fcntl
import os
from typing import Dict, Optional, List

CSV_FILE = "/home/iamaakib/Projects/ACWA/data/WhatsApp_Outreach_Pipeline_Api_Filtered.csv"
FIELDNAMES = [
    "Phone Number", "Business Name", "Scraped Flaw/Detail", 
    "Status", "Minimum Price Floor", "Cold Opener Timestamp", 
    "Last Reply Received", "AI Assigned Persona/Role", "Bot Last Message"
]

def _read_csv() -> List[Dict]:
    if not os.path.exists(CSV_FILE):
        return []
    with open(CSV_FILE, 'r', newline='') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            reader = csv.DictReader(f)
            return list(reader)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def _write_csv(data: List[Dict]):
    with open(CSV_FILE, 'w', newline='') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(data)
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def get_pending_ticket() -> Optional[Dict]:
    data = _read_csv()
    for row in data:
        if row.get("Status") == "Pending":
            return row
    return None

def update_status(phone: str, new_status: str, timestamp_field: Optional[str] = None, timestamp_val: Optional[str] = None, bot_msg: Optional[str] = None):
    data = _read_csv()
    updated = False
    for row in data:
        if row.get("Phone Number") == phone:
            row["Status"] = new_status
            if timestamp_field and timestamp_val:
                row[timestamp_field] = timestamp_val
            if bot_msg is not None:
                row["Bot Last Message"] = bot_msg
            updated = True
            break
    if updated:
        _write_csv(data)

def add_ticket(phone: str, business_name: str, status: str, timestamp_val: str):
    data = _read_csv()
    # Check if exists
    if any(r.get("Phone Number") == phone for r in data):
        return
    
    new_row = {
        "Phone Number": phone,
        "Business Name": business_name,
        "Scraped Flaw/Detail": "Inbound Lead",
        "Status": status,
        "Minimum Price Floor": "Unknown",
        "Cold Opener Timestamp": "",
        "Last Reply Received": timestamp_val,
        "AI Assigned Persona/Role": "Receptionist",
        "Bot Last Message": ""
    }
    data.append(new_row)
    _write_csv(data)

def get_contact_by_phone(phone: str) -> Optional[Dict]:
    data = _read_csv()
    for row in data:
        if row["Phone Number"] == phone:
            return row
    return None

import json

CHAT_DIR = "/home/iamaakib/Projects/ACWA/data/chats"

def append_chat(phone: str, role: str, content: str):
    os.makedirs(CHAT_DIR, exist_ok=True)
    file_path = os.path.join(CHAT_DIR, f"{phone}.json")
    
    history = []
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                history = json.load(f)
            except:
                pass
            
    history.append({"role": role, "content": content})
    
    with open(file_path, "w") as f:
        json.dump(history, f, indent=2)

def get_chat_history(phone: str) -> list:
    file_path = os.path.join(CHAT_DIR, f"{phone}.json")
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            try:
                return json.load(f)
            except:
                pass
    return []
