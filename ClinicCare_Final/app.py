import os

from backend.app import app, init_db


# Ensure schema/seed data exists for both local runs and WSGI startup.
init_db()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))
    print(f"ClinicCare Flask backend running on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
