# Server ini pake waitress (production WSGI server)
# Kalau hosting support gunicorn, ganti jadi gunicorn app:app

from app import app

if __name__ == "__main__":
    from waitress import serve
    print("Server jalan di http://0.0.0.0:8080")
    serve(app, host="0.0.0.0", port=8080)
