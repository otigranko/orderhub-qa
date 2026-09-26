import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# OrderHub service (UI + API) and the mock partner API it polls.
ORDERHUB_URL = os.environ.get("ORDERHUB_URL", "http://localhost:8080").rstrip("/")
MOCK_API_URL = os.environ.get("MOCK_API_URL", "http://localhost:8090").rstrip("/")

# Path to the OrderHub checkout. Used to read the provided example payloads
# (we reference them instead of copying them into this repo).
ORDERHUB_DIR = Path(os.environ.get("ORDERHUB_DIR", REPO_ROOT.parent / "orderhub")).resolve()
EXAMPLES_DIR = ORDERHUB_DIR / "data" / "examples"

# How long to wait for asynchronous work. The partner API is polled every 2s and the
# dispatcher runs every 1s by default, so a few poll cycles is plenty.
DEFAULT_TIMEOUT = float(os.environ.get("QA_TIMEOUT", "10"))
