"""
SISTEM ANTRIAN DIGITAL - PLUG & PLAY
Jalan di Android TV / TV Digital via browser
"""
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS
import qrcode
import socket
import json
import os
import asyncio
import tempfile
import edge_tts

app = Flask(__name__)
CORS(app)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
app.jinja_env.bytecode_cache = None

QUEUE_FILE = "queue_data.json"

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def load():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE) as f:
            return json.load(f)
    return {
        "counter": 0,
        "current": 0,
        "queue": [],
        "history": [],
    }

def save(data):
    with open(QUEUE_FILE, "w") as f:
        json.dump(data, f)

# ── Routes ──

@app.route("/")
def home():
    """Landing page — QR code + link"""
    data = load()
    ip = get_ip()
    return render_template("home.html", ip=ip, counter=data["counter"])

@app.route("/display")
def display():
    """TV Display — nomor antrian + daftar"""
    return render_template("display.html")

@app.route("/admin")
def admin():
    """Panel operator — baca langsung dari file biar gak kena cache"""
    with open(os.path.join(os.path.dirname(__file__), 'templates', 'admin.html'), 'r', encoding='utf-8') as f:
        return f.read()

@app.route("/debug")
def debug():
    import os
    path = os.path.join(os.path.dirname(__file__), 'templates', 'admin.html')
    size = os.path.getsize(path)
    with open(path, 'r') as f:
        has_recall = 'panggilUlang' in f.read()
    return f"File: {path}<br>Size: {size}<br>Has panggilUlang: {has_recall}"

@app.route("/ambil")
def ambil():
    """Halaman pasien ambil nomor"""
    return render_template("ambil.html")

# ── API ──

@app.route("/api/ambil", methods=["POST"])
def api_ambil():
    data = load()
    nama = request.json.get("nama", "Anonim").strip() or "Anonim"
    keperluan = request.json.get("keperluan", "Umum").strip() or "Umum"
    data["counter"] += 1
    nomor = f"A-{data['counter']:03d}"
    data["queue"].append({
        "nomor": nomor,
        "nama": nama,
        "keperluan": keperluan,
        "status": "menunggu",
    })
    save(data)
    return jsonify({"success": True, "nomor": nomor, "nama": nama})

@app.route("/api/status")
def api_status():
    data = load()
    return jsonify({
        "counter": data["counter"],
        "current": data["current"],
        "queue": data["queue"],
        "history": data["history"][-5:],
    })

@app.route("/api/panggil", methods=["POST"])
def api_panggil():
    data = load()
    idx = request.json.get("index", 0)
    if idx < len(data["queue"]):
        item = data["queue"][idx]
        item["status"] = "dipanggil"
        data["current"] = idx + 1
        data["history"].append(item)
        save(data)
        return jsonify({"success": True, "item": item})
    return jsonify({"success": False, "msg": "Antrian kosong"})

@app.route("/api/skip", methods=["POST"])
def api_skip():
    data = load()
    idx = request.json.get("index", 0)
    if idx < len(data["queue"]):
        item = data["queue"].pop(idx)
        item["status"] = "dilewati"
        data["history"].append(item)
        save(data)
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route("/api/selesai", methods=["POST"])
def api_selesai():
    data = load()
    idx = request.json.get("index", 0)
    if idx < len(data["queue"]):
        item = data["queue"].pop(idx)
        item["status"] = "selesai"
        data["history"].append(item)
        save(data)
        return jsonify({"success": True, "item": item})
    return jsonify({"success": False})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    save({"counter": 0, "current": 0, "queue": [], "history": []})
    return jsonify({"success": True})

import threading

@app.route("/api/sse")
def api_sse():
    """Server-Sent Events — push real-time updates ke display TV"""
    import time
    def generate():
        last_state = json.dumps({})
        while True:
            try:
                data = load()
                current_state = json.dumps({
                    "queue": data["queue"],
                    "counter": data["counter"],
                })
                if current_state != last_state:
                    yield f"data: {current_state}\n\n"
                    last_state = current_state
                    time.sleep(0.5)
                else:
                    time.sleep(1)
            except GeneratorExit:
                return
            except:
                yield f"data: {json.dumps({'error': True})}\n\n"
                time.sleep(5)
    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})

def generate_tts_sync(text, output_path):
    """Generate suara Indonesia pake Edge TTS (gratis, natural)"""
    async def _gen():
        voice = "id-ID-GadisNeural"
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
    asyncio.run(_gen())

@app.route("/api/suara")
def api_suara():
    """Hasilkan & kirim MP3 suara panggilan"""
    nomor = request.args.get('nomor', 'A-000')
    nama = request.args.get('nama', '')
    nomor_str = nomor.replace('-', ' - ').replace('A', 'A ')
    if nama:
        text = f"Nomor antrian, {nomor_str}, atas nama {nama}. Silahkan ke loket."
    else:
        text = f"Nomor antrian, {nomor_str}. Silahkan ke loket."
    
    cache_dir = os.path.join(os.path.dirname(__file__), 'cache_suara')
    os.makedirs(cache_dir, exist_ok=True)
    suffix = '_nama' if nama else ''
    mp3_path = os.path.join(cache_dir, f'{nomor}{suffix}.mp3')
    
    if not os.path.exists(mp3_path):
        generate_tts_sync(text, mp3_path)
    
    return send_file(mp3_path, mimetype='audio/mpeg')

@app.route("/api/replay", methods=["POST"])
def api_replay():
    """Trigger replay suara di display — increment replay counter"""
    data = load()
    idx = request.json.get("index", 0)
    if idx < len(data["queue"]):
        data["queue"][idx]["replay"] = data["queue"][idx].get("replay", 0) + 1
        save(data)
    return jsonify({"success": True})

@app.route("/api/clearcache", methods=["POST"])
def api_clearcache():
    import glob
    cache_dir = os.path.join(os.path.dirname(__file__), 'cache_suara')
    if os.path.exists(cache_dir):
        for f in glob.glob(os.path.join(cache_dir, '*.mp3')):
            os.remove(f)
    return jsonify({"success": True})

if __name__ == "__main__":
    ip = get_ip()
    print(f"""
╔══════════════════════════════════════════╗
║   SISTEM ANTRIAN DIGITAL - SIAP JALAN   ║
╠══════════════════════════════════════════╣
║  📺 TV Display:  http://{ip}:5000/display  ║
║  🎛️  Admin Panel: http://{ip}:5000/admin     ║
║  🏠 Home/QR:     http://{ip}:5000            ║
╚══════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=8080, debug=False)
