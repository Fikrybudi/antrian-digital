# Server ini pake waitress (production WSGI server)
# Kalau hosting support gunicorn, ganti jadi gunicorn app:app

from app import app
import os

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 8080))
    print(f"Server jalan di http://0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port)
