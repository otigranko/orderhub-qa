import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Path to the OrderHub checkout. We run its built binaries (`make build`) and read
# the provided example payloads from it.
ORDERHUB_DIR = Path(os.environ.get("ORDERHUB_DIR", REPO_ROOT.parent / "orderhub")).resolve()
EXAMPLES_DIR = ORDERHUB_DIR / "data" / "examples"
ORDERHUB_BIN = ORDERHUB_DIR / "bin" / "orderhub"
MOCK_API_BIN = ORDERHUB_DIR / "bin" / "mockapi"
FRONTEND_DIR = ORDERHUB_DIR / "frontend" / "dist"

# QA_EXTERNAL=1 runs the tests against an OrderHub that is already running (for example
# `make run`) instead of starting one. See "Running against make run" in the README.
EXTERNAL = os.environ.get("QA_EXTERNAL") == "1"

# By default the tests start their own OrderHub and mock partner API on ports different from
# `make run` (8080/8090), so both can run at the same time. In external mode they use 8080/8090.
ORDERHUB_PORT = int(os.environ.get("ORDERHUB_PORT", "8080" if EXTERNAL else "18080"))
MOCK_API_PORT = int(os.environ.get("MOCK_API_PORT", "8090" if EXTERNAL else "18090"))
ROBOT_PORT = int(os.environ.get("ROBOT_PORT", "18181"))

ORDERHUB_URL = f"http://127.0.0.1:{ORDERHUB_PORT}"
MOCK_API_URL = f"http://127.0.0.1:{MOCK_API_PORT}"

# Where OrderHub's logs and database for a test run go. Kept after the run for debugging.
RESULTS_DIR = REPO_ROOT / "results"

# How long to wait for asynchronous work. The partner API is polled every 2s and the
# dispatcher runs every 1s by default, so a few cycles is plenty.
DEFAULT_TIMEOUT = float(os.environ.get("QA_TIMEOUT", "10"))
