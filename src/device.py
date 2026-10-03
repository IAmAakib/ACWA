import subprocess
import time
import urllib.parse
import re

class WhatsAppDevice:
    def __init__(self, target_ip: str):
        self.target_ip = target_ip

    def _adb_shell(self, cmd: str, check=True) -> str:
        args = ["adb", "-s", self.target_ip, "shell", cmd]
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            print("\n[!] ADB command timed out. Waydroid is probably frozen. Make sure 'waydroid show-full-ui' is open and visible!")
            return ""
            
        if check and result.returncode != 0:
            print(f"ADB error: {result.stderr.strip()}")
            raise subprocess.CalledProcessError(result.returncode, " ".join(args))
        return result.stdout.strip()

    def ensure_connection(self) -> bool:
        subprocess.run(["adb", "connect", self.target_ip], capture_output=True)
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True)
        return "device" in result.stdout.replace("devices", "")

    def go_home(self):
        # Back out of the chat (closes keyboard, then exits chat, then exits app)
        self._adb_shell("input keyevent 4")
        time.sleep(0.5)
        self._adb_shell("input keyevent 4")
        time.sleep(0.5)
        self._adb_shell("input keyevent 4")
        time.sleep(0.5)
        # Also send Home just in case
        self._adb_shell("input keyevent 3")

    def get_notifications(self) -> list:
        output = self._adb_shell("dumpsys notification --noredact", check=False)
        results = []
        for block in output.split("NotificationRecord"):
            if "com.whatsapp.w4b" not in block:
                continue
            title_match = re.search(r'android\.title=String \((.+?)\)', block)
            text_match = re.search(r'android\.text=String \((.+?)\)', block)
            if title_match and text_match:
                results.append({
                    "sender": title_match.group(1),
                    "text": text_match.group(1)
                })
        return results

    def send_message(self, phone: str, msg: str) -> bool:
        msg = " ".join(msg.replace("\n", " ").split())
        encoded = urllib.parse.quote(msg)
        intent_url = f'whatsapp://send?phone={phone}&text={encoded}'
        am_cmd = f'am start -a android.intent.action.VIEW -d "{intent_url}" -p com.whatsapp.w4b'
        
        self._adb_shell(am_cmd)
        time.sleep(8)
        
        # Check failsafe: if not in Conversation, number is probably invalid
        focus_check = self._adb_shell("dumpsys window | grep mCurrentFocus", check=False)
        if "com.whatsapp.Conversation" not in focus_check:
            print(f"\n[!] Failsafe triggered: {phone} is not on WhatsApp (Focus: {focus_check.splitlines()[0] if focus_check else 'None'})")
            return False
        
        self._adb_shell("input keyevent 66")
        time.sleep(2)
        return True
