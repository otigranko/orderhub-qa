import subprocess

import requests

from harness import config
from harness.client import wait_until


def is_up(url):
    try:
        return requests.get(url, timeout=1).status_code == 200
    except requests.ConnectionError:
        return False


# Starts the mock partner API and OrderHub for a test run:
# - a fresh database every run, so old data can't affect results
# - robot dispatches go to our RobotSink instead of a file
# Logs and the database stay in results/ after the run, for debugging and defect reports.
class Services:
    def __init__(self, robot_url):
        self.robot_url = robot_url
        self.processes = []
        self.logs = []

    def start(self):
        for path in (config.ORDERHUB_BIN, config.MOCK_API_BIN):
            if not path.exists():
                raise RuntimeError(f"{path} not found. Run `make build` in {config.ORDERHUB_DIR}.")

        config.RESULTS_DIR.mkdir(exist_ok=True)
        for old in [*config.RESULTS_DIR.glob("orderhub.db*"), *config.RESULTS_DIR.glob("*.log")]:
            old.unlink()

        self.run(config.MOCK_API_BIN, "mockapi.log",
                 "-addr", f"127.0.0.1:{config.MOCK_API_PORT}")
        wait_until(lambda: is_up(f"{config.MOCK_API_URL}/status"), message="mock partner API did not start")
        self.start_orderhub()

    # Starts OrderHub on this run's database. Also used to start it again after stop_orderhub().
    def start_orderhub(self):
        self.orderhub = self.run(config.ORDERHUB_BIN, "orderhub.log",
                                 "-addr", f"127.0.0.1:{config.ORDERHUB_PORT}",
                                 "-db", str(config.RESULTS_DIR / "orderhub.db"),
                                 "-api-url", config.MOCK_API_URL,
                                 "-robot-url", self.robot_url,
                                 "-frontend", str(config.FRONTEND_DIR))
        wait_until(lambda: is_up(f"{config.ORDERHUB_URL}/healthz"),
                   message=f"OrderHub did not start, see {config.RESULTS_DIR / 'orderhub.log'}")

    # Stops OrderHub the way a deploy does. With crash=True, the way a crash does: no time to
    # finish what it was doing. The database and the mock partner API stay, like in production.
    def stop_orderhub(self, crash=False):
        if crash:
            self.orderhub.kill()
        else:
            self.orderhub.terminate()
        self.orderhub.wait(timeout=5)

    # Logs are added to, not replaced, so a restart keeps OrderHub's earlier lines.
    def run(self, binary, log_name, *args):
        log = open(config.RESULTS_DIR / log_name, "a")
        self.logs.append(log)
        process = subprocess.Popen([str(binary), *args], stdout=log, stderr=subprocess.STDOUT)
        self.processes.append(process)
        return process

    def stop(self):
        for p in self.processes:
            p.terminate()
        for p in self.processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        for log in self.logs:
            log.close()
