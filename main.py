import os
import sys

# supaya bisa import file di folder be/
BASE_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(BASE_DIR, "be"))

from camera_server import app  # app = FastAPI() ada di camera_server.py
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
