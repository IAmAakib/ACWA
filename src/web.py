from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
import subprocess
import storage
import os
import time
import asyncio
from datetime import datetime, timezone
import crm_bot
import mock_agent

app = FastAPI()

@app.get("/api/chat/{phone}")
def get_full_chat_history(phone: str):
    import storage
    return {"history": storage.get_chat_history(phone)}


@app.post("/api/baileys/inbound")
async def baileys_inbound(payload: dict):
    start_time = time.time()
    
    sender = payload.get("phone")
    text = payload.get("text")
    if not sender or not text:
        return {"status": "error", "message": "Missing phone or text"}
        
    print(f"[Baileys] Inbound from {sender}: {text}")
    
    # 1. Opt-out check
    if text.lower().strip() in ["stop", "cancel", "not interested", "unsubscribe"]:
        storage.update_status(sender, "Opt-Out", "Last Reply Received", datetime.now(timezone.utc).isoformat())
        return {"reply_text": "Thank you. Opted out."}
    
    # 2. Ticket lookup/creation
    ticket = crm_bot.find_ticket_by_sender(sender)
    if not ticket:
        storage.add_ticket(sender, sender, "Negotiating", datetime.now(timezone.utc).isoformat())
        ticket = storage.get_contact_by_phone(sender)
    phone = ticket.get("Phone Number", sender)
        
    # 3. Evaluate Auto-Reply
    eval_result = mock_agent.evaluate_inbound(text)
    if eval_result == "AUTO_REPLY":
        storage.update_status(phone, "Auto-Reply")
        return {"status": "ignored", "reason": "auto_reply"}
        
    # 4. Save User Message
    storage.append_chat(phone, "user", text)
    
    # 5. Generate AI Reply
    reply = mock_agent.generate_reply(ticket)
    
    # 6. Handle Handover
    if "HANDOVER_REQUIRED" in reply:
        storage.update_status(phone, "Human Handover", "Last Reply Received", datetime.now(timezone.utc).isoformat())
        fallback_msg = "Let me get a human agent to answer that for you right away!"
        return {"reply_text": fallback_msg}
        
    # 7. Save and Return Bot Reply
    storage.append_chat(phone, "assistant", reply)
    storage.update_status(phone, "Negotiating", "Last Reply Received", datetime.now(timezone.utc).isoformat(), bot_msg=reply)
    
    print(f"[Baileys] Processed in {time.time()-start_time:.2f}s")
    return {"reply_text": reply}


@app.post("/api/log_error")
def log_client_error(payload: dict):
    with open("../data/client_error.log", "a") as f:
        f.write(f"{payload.get('msg')}\n{payload.get('stack')}\n---\n")
    return {"status": "ok"}


@app.post("/api/chat/send")
def send_direct_message(payload: dict):
    phone = payload.get("phone")
    text = payload.get("text")
    from device import WhatsAppDevice
    import config
    import storage
    
    device = WhatsAppDevice(config.ADB_TARGET_IP)
    device.ensure_connection()
    success = device.send_message(phone, text)
    device.go_home()
    
    if success:
        storage.append_chat(phone, "assistant", text)
        storage.update_status(phone, "Negotiating", bot_msg=text)
    return {"success": success}


@app.get("/api/auto_mode")
def get_auto_mode():
    mode = "ON"
    if os.path.exists("../data/auto_mode.txt"):
        mode = open("../data/auto_mode.txt").read().strip()
    return {"mode": mode}

@app.post("/api/auto_mode/toggle")
def toggle_auto_mode():
    mode = "ON"
    if os.path.exists("../data/auto_mode.txt"):
        mode = open("../data/auto_mode.txt").read().strip()
    new_mode = "OFF" if mode == "ON" else "ON"
    with open("../data/auto_mode.txt", "w") as f:
        f.write(new_mode)
    return {"mode": new_mode}
    
@app.post("/api/drafts/approve")
def approve_draft(payload: dict):
    phone = payload.get("phone")
    text = payload.get("text")
    from device import WhatsAppDevice
    import config
    import storage
    
    device = WhatsAppDevice(config.ADB_TARGET_IP)
    device.ensure_connection()
    success = device.send_message(phone, text)
    device.go_home()
    
    if success:
        ticket = storage.get_contact_by_phone(phone)
        if ticket:
            storage.append_chat(phone, "assistant", text)
            new_status = "Negotiating" if ticket.get("Cold Opener Timestamp") else "Sent"
            storage.update_status(phone, new_status, bot_msg=text)
    return {"success": success}


LOG_FILE = "../data/bot.log"

@app.get("/api/logs")
def get_logs():
    if not os.path.exists(LOG_FILE):
        return {"logs": "No logs yet."}
    with open(LOG_FILE, "r") as f:
        lines = f.readlines()
        return {"logs": "".join(lines[-100:])}


BOT_PROCESS = None

def generate_frames():
    while True:
        try:
            # Grab screenshot directly from Android
            result = subprocess.run(["adb", "-s", "192.168.240.112:5555", "exec-out", "screencap", "-p"], capture_output=True)
            frame = result.stdout
            if frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/png\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.5)
        except Exception as e:
            time.sleep(2)

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en" class="antialiased">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ACWA - Automated CRM</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    
        <script>
            window.onerror = function(message, source, lineno, colno, error) {
                fetch('/api/log_error', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({msg: message, stack: error ? error.stack : ''})
                });
            };
        </script>
        <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>

    <script src="https://unpkg.com/lucide@latest"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        brand: { 50: '#f0fdfa', 500: '#14b8a6', 600: '#0d9488', 900: '#134e4a' },
                        surface: { 50: '#f8fafc', 100: '#f1f5f9', 800: '#1e293b', 900: '#0f172a' }
                    }
                }
            }
        }
    </script>
    <style>
        body { background-color: #0f172a; color: #f8fafc; }
        .glass-panel { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.1); }
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel">
        const { useState, useEffect } = React;

        const StatCard = ({ title, value, icon, colorClass }) => (
            <div class="glass-panel p-6 rounded-xl flex items-center space-x-4 transition-transform hover:scale-[1.02]">
                <div class={`p-3 rounded-lg ${colorClass} bg-opacity-20`}>
                    <i data-lucide={icon} class={`w-6 h-6 ${colorClass.replace('bg-', 'text-')}`}></i>
                </div>
                <div>
                    <p class="text-sm font-medium text-slate-400 uppercase tracking-wider">{title}</p>
                    <p class="text-3xl font-bold text-white mt-1">{value}</p>
                </div>
            </div>
        );

        const StatusBadge = ({ status }) => {
            const styles = {
                'Pending': 'bg-slate-700 text-slate-300 border-slate-600',
                'Sent': 'bg-blue-900/50 text-blue-300 border-blue-700/50',
                'Negotiating': 'bg-amber-900/50 text-amber-300 border-amber-700/50',
                'Opt-Out': 'bg-rose-900/50 text-rose-300 border-rose-700/50',
                'Invalid Number': 'bg-red-900/80 text-red-200 border-red-700',
                'Avoided': 'bg-zinc-800 text-zinc-400 border-zinc-700 line-through',
                'Human Handover': 'bg-fuchsia-900/50 text-fuchsia-300 border-fuchsia-700/50 shadow-[0_0_8px_rgba(217,70,239,0.4)]',
                'Draft Approval Needed': 'bg-yellow-900/50 text-yellow-300 border-yellow-700/50 shadow-[0_0_8px_rgba(234,179,8,0.4)]'
            };
            const defaultStyle = 'bg-slate-800 text-slate-300 border-slate-700';
            return (
                <span class={`px-3 py-1 text-xs font-semibold rounded-full border ${styles[status] || defaultStyle}`}>
                    {status}
                </span>
            );
        };

        function Dashboard() {
            const [stats, setStats] = useState({ Pending: 0, Sent: 0, Negotiating: 0, 'Opt-Out': 0 });
            const [botRunning, setBotRunning] = useState(false);
                                                const [tickets, setTickets] = useState([]);
            const [isLoading, setIsLoading] = useState(true);
            const [activeTab, setActiveTab] = useState('pipeline');
            const [selectedChat, setSelectedChat] = useState(null);
            const [chatInput, setChatInput] = useState('');
            const [chatHistory, setChatHistory] = useState([]);
            const [kbText, setKbText] = useState("");
            const [savingKb, setSavingKb] = useState(false);
            const [logs, setLogs] = useState('');

            const fetchData = async () => {
                try {
                    const res = await fetch('/api/data');
                    const data = await res.json();
                    setStats({ Pending: 0, Sent: 0, Negotiating: 0, 'Opt-Out': 0, ...data.stats });
                    setTickets(data.tickets);
                    setBotRunning(data.bot_running);
                    setIsLoading(false);
                } catch (e) {
                    console.error("Failed to fetch data", e);
                }
            };

            const fetchKb = async () => {
                const res = await fetch('/api/kb');
                const data = await res.json();
                setKbText(data.content);
            };
            const fetchAutoMode = async () => {
                const res = await fetch('/api/auto_mode');
                const data = await res.json();
                            };
            const fetchLogs = async () => {
                if (activeTab === 'logs') {
                    const res = await fetch('/api/logs');
                    const data = await res.json();
                    setLogs(data.logs);
                }
            };

            useEffect(() => {
                fetchData();
                fetchKb();
                const interval = setInterval(() => { fetchData(); fetchLogs(); fetchAutoMode(); }, 2000);
                return () => clearInterval(interval);
            }, []);

            useEffect(() => {
                lucide.createIcons();
            });

            const toggleBot = async () => {
                await fetch('/api/bot/toggle', { method: 'POST' });
                fetchData();
            };

            const testOnce = async () => {
                alert("Triggering 1 Test Lead...");
                await fetch('/api/bot/test_once', { method: 'POST' });
                fetchData();
            };

            const resetLead = async (phone) => {
                await fetch('/api/reset', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone })
                });
                fetchData();
            };

            const avoidLead = async (phone) => {
                await fetch('/api/avoid', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone })
                });
                fetchData();
            };

            const saveKb = async () => {
                setSavingKb(true);
                await fetch('/api/kb', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content: kbText })
                });
                setSavingKb(false);
                alert("Knowledgebase saved!");
            };

            return (
                <div class="flex flex-col md:flex-row h-screen overflow-hidden">
                    <aside class="w-full md:w-64 glass-panel border-b md:border-b-0 md:border-r border-slate-800 flex flex-col flex-shrink-0">
                        <div class="p-4 md:p-6 flex justify-between items-center">
                            <div class="flex items-center space-x-3">
                                <div class="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center shrink-0">
                                    <i data-lucide="bot" class="w-5 h-5 text-white"></i>
                                </div>
                                <span class="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">ACWA</span>
                            </div>
                            <div class="flex md:hidden items-center space-x-2">
                                <div class={`w-2.5 h-2.5 rounded-full ${botRunning ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]' : 'bg-slate-600'}`}></div>
                                <span class="text-xs text-slate-400">{botRunning ? 'Active' : 'Offline'}</span>
                            </div>
                        </div>
                        <nav class="px-2 md:px-4 py-2 md:py-4 flex flex-row md:flex-col overflow-x-auto gap-2 md:space-y-2 md:flex-1">
                            <button onClick={() => setActiveTab('pipeline')} class={`shrink-0 flex items-center space-x-2 md:space-x-3 px-3 py-2 md:px-4 md:py-3 rounded-lg font-medium transition-colors ${activeTab === 'pipeline' ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
                                <i data-lucide="layout-dashboard" class="w-4 h-4 md:w-5 md:h-5"></i>
                                <span class="text-sm md:text-base">Pipeline</span>
                            </button>
                            <button onClick={() => setActiveTab('live')} class={`shrink-0 flex items-center space-x-2 md:space-x-3 px-3 py-2 md:px-4 md:py-3 rounded-lg font-medium transition-colors ${activeTab === 'live' ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
                                <i data-lucide="monitor-play" class="w-4 h-4 md:w-5 md:h-5"></i>
                                <span class="text-sm md:text-base">Live Feed</span>
                            </button>
                            <button onClick={() => setActiveTab('chats')} class={`shrink-0 flex items-center space-x-2 md:space-x-3 px-3 py-2 md:px-4 md:py-3 rounded-lg font-medium transition-colors ${activeTab === 'chats' ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
                                <i data-lucide="message-circle" class="w-4 h-4 md:w-5 md:h-5"></i>
                                <span class="text-sm md:text-base">Chats</span>
                            </button>
                            <button onClick={() => setActiveTab('settings')} class={`shrink-0 flex items-center space-x-2 md:space-x-3 px-3 py-2 md:px-4 md:py-3 rounded-lg font-medium transition-colors ${activeTab === 'settings' ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
                                <i data-lucide="settings" class="w-4 h-4 md:w-5 md:h-5"></i>
                                <span class="text-sm md:text-base">Settings</span>
                            </button>
                            <button onClick={() => {setActiveTab('logs'); fetchLogs();}} class={`shrink-0 flex items-center space-x-2 md:space-x-3 px-3 py-2 md:px-4 md:py-3 rounded-lg font-medium transition-colors ${activeTab === 'logs' ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}>
                                <i data-lucide="terminal" class="w-4 h-4 md:w-5 md:h-5"></i>
                                <span class="text-sm md:text-base">Terminal Logs</span>
                            </button>
                        </nav>
                        <div class="hidden md:block p-4 border-t border-slate-800">
                            <div class="flex items-center space-x-3 px-4 py-2">
                                <div class={`w-2.5 h-2.5 rounded-full ${botRunning ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]' : 'bg-slate-600'}`}></div>
                                <span class="text-sm text-slate-400">System {botRunning ? 'Active' : 'Offline'}</span>
                            </div>
                        </div>
                    </aside>

                    <main class="flex-1 flex flex-col h-full overflow-y-auto">
                        <header class="px-4 md:px-8 py-4 md:py-6 flex flex-col md:flex-row justify-between items-start md:items-center sticky top-0 bg-surface-900/80 backdrop-blur-md z-10 border-b border-slate-800/50 gap-4">
                            <div>
                                <h1 class="text-xl md:text-2xl font-semibold">
                                    {activeTab === 'pipeline' ? 'Overview' : activeTab === 'live' ? 'Live Device Monitor' : activeTab === 'chats' ? 'Direct Chats' : 'Settings & AI Prompts'}
                                </h1>
                                <p class="text-xs md:text-sm text-slate-400 mt-1">
                                    {activeTab === 'pipeline' ? 'Monitor your automated outreach pipeline' : activeTab === 'live' ? 'Watch the bot control WhatsApp in real-time' : activeTab === 'chats' ? 'Directly interact with leads' : 'Configure knowledgebase and controls'}
                                </p>
                            </div>
                            <div class="flex space-x-2 md:space-x-4 w-full md:w-auto">
                                <button 
                                    onClick={testOnce} 
                                    class="flex-1 md:flex-none flex items-center justify-center space-x-1 md:space-x-2 px-3 md:px-6 py-2 md:py-2.5 rounded-lg font-medium transition-all shadow-lg bg-slate-700 text-white hover:bg-slate-600 text-sm md:text-base"
                                >
                                    <span><i data-lucide="send" class="w-4 h-4"></i></span>
                                    <span>Test 1 Lead</span>
                                </button>
                                <button 
                                    onClick={toggleBot} 
                                    class={`flex-1 md:flex-none flex items-center justify-center space-x-1 md:space-x-2 px-3 md:px-6 py-2 md:py-2.5 rounded-lg font-medium transition-all shadow-lg text-sm md:text-base ${
                                        botRunning 
                                        ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:bg-rose-500/20' 
                                        : 'bg-brand-500 text-white shadow-brand-500/25 hover:bg-brand-600 hover:-translate-y-0.5'
                                    }`}
                                >
                                    <i data-lucide={botRunning ? "square" : "play"} class="w-4 h-4 fill-current"></i>
                                    <span>{botRunning ? 'Stop Bot' : 'Start Bot'}</span>
                                </button>
                            </div>
                        </header>

                        <div class="p-4 md:p-8 space-y-4 md:space-y-8 max-w-7xl mx-auto w-full">
                            {activeTab === 'pipeline' && (
                                <>
                                    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                                        <StatCard title="Pending Leads" value={stats.Pending} icon="hourglass" colorClass="bg-slate-400" />
                                        <StatCard title="Messages Sent" value={stats.Sent} icon="send" colorClass="bg-blue-400" />
                                        <StatCard title="Negotiating" value={stats.Negotiating} icon="message-circle" colorClass="bg-amber-400" />
                                        <StatCard title="Opt-Outs" value={stats['Opt-Out']} icon="user-x" colorClass="bg-rose-400" />
                                    </div>

                                    <section class="glass-panel rounded-xl overflow-hidden shadow-xl">
                                        <div class="px-6 py-5 border-b border-slate-800 flex justify-between items-center">
                                            <h2 class="text-lg font-semibold flex items-center">
                                                <i data-lucide="list" class="w-5 h-5 mr-2 text-slate-400"></i>
                                                Active Pipeline
                                            </h2>
                                        </div>
                                        <div class="overflow-x-auto">
                                            <table class="w-full text-left text-sm">
                                                <thead class="bg-slate-800/50 text-slate-400 font-medium">
                                                    <tr>
                                                        <th class="px-6 py-4 rounded-tl-lg">Phone Number</th>
                                                        <th class="px-6 py-4">Business Name</th>
                                                        <th class="px-6 py-4">Status</th>
                                                        <th class="px-6 py-4 text-right">Actions</th>
                                                    </tr>
                                                </thead>
                                                <tbody class="divide-y divide-slate-800/50">
                                                    {isLoading ? (
                                                        <tr><td colSpan="4" class="px-6 py-12 text-center text-slate-500">Loading pipeline data...</td></tr>
                                                    ) : tickets.length === 0 ? (
                                                        <tr><td colSpan="4" class="px-6 py-12 text-center text-slate-500">No leads found in pipeline.</td></tr>
                                                    ) : (
                                                        tickets.map((t, i) => (
                                                            <tr key={i} class="hover:bg-slate-800/30 transition-colors group">
                                                                <td class="px-6 py-4 font-mono text-slate-300">{t['Phone Number']}</td>
                                                                <td class="px-6 py-4 font-medium">{t['Business Name']}</td>
                                                                <td class="px-6 py-4"><StatusBadge status={t.Status} /></td>
                                                                <td class="px-6 py-4 text-right space-x-2">
                                                                    {t.Status === 'Pending' && (
                                                                        <button onClick={() => avoidLead(t['Phone Number'])} class="text-slate-400 hover:text-rose-400 px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs transition-colors" title="Avoid this contact">
                                                                            Skip
                                                                        </button>
                                                                    )}
                                                                    {t.Status !== 'Pending' && (
                                                                        <button onClick={() => resetLead(t['Phone Number'])} class="text-slate-400 hover:text-white px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs transition-colors">
                                                                            Reset
                                                                        </button>
                                                                    )}
                                                                </td>
                                                            </tr>
                                                        ))
                                                    )}
                                                </tbody>
                                            </table>
                                        </div>
                                    </section>
                                </>
                            )}
                            
                                                        {activeTab === 'chats' && (
                                <div class="flex flex-col md:flex-row h-[70vh] gap-4">
                                    <div class="w-full md:w-1/3 glass-panel rounded-xl shadow-xl overflow-y-auto border border-slate-800 flex flex-col">
                                        <div class="p-4 border-b border-slate-800 bg-slate-900/50 sticky top-0 z-10">
                                            <h2 class="font-semibold text-slate-200">Conversations</h2>
                                        </div>
                                        <div class="p-2 space-y-1">
                                            {tickets.filter(r => r.Status !== 'Pending').map(row => (
                                                <button 
                                                    key={row['Phone Number']}
                                                    onClick={async () => {
                                                        setSelectedChat(row);
                                                        const res = await fetch('/api/chat/' + row['Phone Number']);
                                                        const data = await res.json();
                                                        setChatHistory(data.history || []);
                                                        setTimeout(() => {
                                                            const sc = document.getElementById('chatScroll');
                                                            if(sc) sc.scrollTop = sc.scrollHeight;
                                                        }, 100);
                                                    }}
                                                    class={`w-full text-left p-3 rounded-lg transition-colors ${selectedChat && selectedChat['Phone Number'] === row['Phone Number'] ? 'bg-brand-500/20 border border-brand-500/30' : 'hover:bg-slate-800/80'}`}
                                                >
                                                    <div class="font-medium text-white text-sm truncate">{row['Business Name']}</div>
                                                    <div class="text-xs text-slate-400 mt-1 flex justify-between">
                                                        <span>{row['Status']}</span>
                                                        <span class="truncate ml-2">{row['Phone Number']}</span>
                                                    </div>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                    
                                    <div class="w-full md:w-2/3 glass-panel rounded-xl shadow-xl border border-slate-800 flex flex-col">
                                        {selectedChat ? (
                                            <>
                                                <div class="p-4 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
                                                    <div>
                                                        <h2 class="font-semibold text-white">{selectedChat['Business Name']}</h2>
                                                        <p class="text-xs text-slate-400">{selectedChat['Phone Number']}</p>
                                                    </div>
                                                    <span class="px-2 py-1 text-xs rounded bg-slate-800 text-slate-300">{selectedChat['Status']}</span>
                                                </div>
                                                <div class="flex-1 p-4 overflow-y-auto space-y-4 flex flex-col" id="chatScroll">
                                                    {chatHistory.length === 0 ? (
                                                        <div class="flex-1 flex items-center justify-center text-slate-500 text-sm">No chat history available.</div>
                                                    ) : (
                                                        chatHistory.map((msg, i) => (
                                                            <div key={i} class={`flex flex-col space-y-1 max-w-[85%] ${msg.role === 'assistant' ? 'self-end items-end' : 'self-start items-start'}`}>
                                                                <span class="text-[10px] text-slate-500 mx-1">{msg.role === 'assistant' ? 'Bot' : 'Lead'}</span>
                                                                <div class={`p-3 rounded-2xl text-sm ${msg.role === 'assistant' ? 'bg-brand-600 text-white rounded-tr-sm' : 'bg-slate-700 text-white rounded-tl-sm'}`}>
                                                                    {msg.content}
                                                                </div>
                                                            </div>
                                                        ))
                                                    )}
                                                </div>
                                                <div class="p-4 border-t border-slate-800 bg-slate-900/50">
                                                    <div class="flex space-x-2">
                                                        <input 
                                                            type="text" 
                                                            class="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-brand-500"
                                                            placeholder="Type a direct message..."
                                                            value={chatInput}
                                                            onChange={(e) => setChatInput(e.target.value)}
                                                            onKeyPress={(e) => {
                                                                if(e.key === 'Enter') {
                                                                    document.getElementById('sendChatBtn').click();
                                                                }
                                                            }}
                                                        />
                                                        <button 
                                                            id="sendChatBtn"
                                                            onClick={async () => {
                                                                if(!chatInput.trim()) return;
                                                                await fetch('/api/chat/send', {
                                                                    method: 'POST',
                                                                    headers: {'Content-Type': 'application/json'},
                                                                    body: JSON.stringify({phone: selectedChat['Phone Number'], text: chatInput})
                                                                });
                                                                setChatInput('');
                                                                fetchData();
                                                                const res2 = await fetch('/api/chat/' + selectedChat['Phone Number']);
                                                                const data2 = await res2.json();
                                                                setChatHistory(data2.history || []);
                                                                setTimeout(() => {
                                                                    const sc = document.getElementById('chatScroll');
                                                                    if(sc) sc.scrollTop = sc.scrollHeight;
                                                                }, 100);
                                                            }}
                                                            class="px-4 py-2 bg-brand-500 text-white rounded-lg hover:bg-brand-600 transition-colors flex items-center justify-center"
                                                        >
                                                            <span><i data-lucide="send" class="w-4 h-4"></i></span>
                                                        </button>
                                                    </div>
                                                </div>
                                            </>
                                        ) : (
                                            <div class="flex-1 flex flex-col items-center justify-center text-slate-500">
                                                <span><i data-lucide="message-square" class="w-12 h-12 mb-2 opacity-50"></i></span>
                                                <p>Select a conversation to view details</p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                            
                            {activeTab === 'live' && (
                                <section class="glass-panel rounded-xl shadow-xl p-8 flex flex-col items-center">
                                    <h2 class="text-xl font-semibold mb-6 flex items-center">
                                        <div class="w-3 h-3 bg-red-500 rounded-full animate-pulse mr-3"></div>
                                        Live Waydroid Feed
                                    </h2>
                                    <div class="border-4 border-slate-800 rounded-2xl overflow-hidden bg-black shadow-2xl" style={{ maxWidth: '400px' }}>
                                        <img src="/api/feed" alt="Live Screen Feed" class="w-full h-auto" />
                                    </div>
                                    <p class="text-slate-400 text-sm mt-6 text-center max-w-md">
                                        This feed mirrors the Waydroid container at 2-3 FPS using MJPEG streaming. 
                                        Watch the bot navigate WhatsApp automatically.
                                    </p>
                                </section>
                            )}

                            {activeTab === 'logs' && (
                                <section class="glass-panel rounded-xl shadow-xl p-8">
                                    <h2 class="text-xl font-semibold mb-6 flex items-center">
                                        <i data-lucide="terminal" class="w-5 h-5 mr-3 text-brand-400"></i>
                                        Live Terminal Logs
                                    </h2>
                                    <div class="bg-black rounded-lg p-4 h-96 overflow-y-auto border border-slate-700">
                                        <pre class="text-xs text-green-400 font-mono whitespace-pre-wrap font-medium">{logs || "Waiting for logs..."}</pre>
                                    </div>
                                    <div class="mt-4 flex justify-between items-center text-sm text-slate-400">
                                        <span>Showing last 100 lines</span>
                                        <button onClick={() => fetch('/api/logs/clear', {method: 'POST'})} class="text-rose-400 hover:text-rose-300 transition-colors">Clear Logs</button>
                                    </div>
                                </section>
                            )}
                            
                            {activeTab === 'settings' && (
                                <section class="glass-panel rounded-xl shadow-xl p-8">
                                    <h2 class="text-2xl font-semibold mb-2">AI Knowledgebase</h2>
                                    <p class="text-slate-400 mb-6">Edit the core instructions and features the LLM will use to generate outreach and replies.</p>
                                    
                                    <textarea 
                                        class="w-full h-96 bg-slate-900 border border-slate-700 rounded-lg p-4 text-slate-300 font-mono text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 outline-none"
                                        value={kbText}
                                        onChange={(e) => setKbText(e.target.value)}
                                    ></textarea>
                                    
                                    <div class="mt-6 flex justify-end">
                                        <button 
                                            onClick={saveKb} 
                                            disabled={savingKb}
                                            class="bg-brand-600 hover:bg-brand-500 text-white px-8 py-3 rounded-lg font-bold shadow-lg transition-all"
                                        >
                                            {savingKb ? 'Saving...' : 'Save Knowledgebase'}
                                        </button>
                                    </div>
                                </section>
                            )}
                        </div>
                    </main>
                </div>
            );
        }

        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(<Dashboard />);
    </script>
</body>
</html>
"""

@app.get("/")
def home():
    return HTMLResponse(HTML_DASHBOARD)

@app.get("/api/data")
def get_data():
    tickets = storage._read_csv()
    stats = {}
    for t in tickets:
        st = t.get("Status", "Unknown")
        stats[st] = stats.get(st, 0) + 1
        
    return {
        "bot_running": BOT_PROCESS is not None and BOT_PROCESS.poll() is None,
        "stats": stats,
        "tickets": tickets
    }

@app.post("/api/bot/toggle")
def toggle_bot():
    global BOT_PROCESS
    if BOT_PROCESS is not None and BOT_PROCESS.poll() is None:
        BOT_PROCESS.terminate()
        BOT_PROCESS = None
        return {"status": "stopped"}
    else:
        env = os.environ.copy()
        BOT_PROCESS = subprocess.Popen(["../venv/bin/python", "-u", "crm_bot.py", "--headless"], env=env)
        return {"status": "started"}

@app.post("/api/bot/test_once")
def test_once():
    # Run test_once.py sequentially
    subprocess.Popen(["../venv/bin/python", "test_once.py"])
    return {"status": "triggered"}

@app.get("/api/kb")
def get_kb():
    try:
        content = open("../data/knowledgebase.txt").read()
    except FileNotFoundError:
        content = ""
    return {"content": content}

@app.post("/api/kb")
async def save_kb(request: Request):
    data = await request.json()
    with open("../data/knowledgebase.txt", "w") as f:
        f.write(data.get("content", ""))
    return {"status": "saved"}

@app.post("/api/reset")
async def reset_lead(request: Request):
    data = await request.json()
    phone = data.get("phone")
    if phone:
        storage.update_status(phone, "Pending")
    return {"status": "reset"}

@app.post("/api/avoid")
async def avoid_lead(request: Request):
    data = await request.json()
    phone = data.get("phone")
    if phone:
        storage.update_status(phone, "Avoided")
    return {"status": "avoided"}

@app.get("/api/feed")
def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/logs/clear")
def clear_logs():
    if os.path.exists(LOG_FILE):
        open(LOG_FILE, 'w').close()
    return {"status": "cleared"}
