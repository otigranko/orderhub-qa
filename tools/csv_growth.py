import time

import requests

from harness import config
from harness.builders import survey_csv, survey_row
from harness.client import OrderHubClient
from harness.robot_sink import RobotSink
from harness.services import Services

# How long a survey upload takes as the day goes on. Each export contains every response so
# far, so each upload is 500 rows bigger than the last. Starts its own OrderHub, like the tests.
# Stops at the first upload that gets no answer in 30 seconds (see L37-022), and stops OrderHub
# right away, because by then it is using more and more memory.
# Run from the repo root:
#   python -m tools.csv_growth
NEW_ROWS = 500
MAX_ROWS = 10_000
GIVE_UP_SECONDS = 30


def main():
    robot = RobotSink(config.ROBOT_PORT)
    robot.start()
    services = Services(robot.url)
    services.start()
    hub = OrderHubClient(timeout=GIVE_UP_SECONDS)

    rows = []
    while len(rows) < MAX_ROWS:
        rows.extend(survey_row(first_name=f"Guest{len(rows) + i}") for i in range(NEW_ROWS))
        start = time.monotonic()
        try:
            hub.upload_csv(survey_csv(rows))
        except requests.RequestException:
            print(f"export of {len(rows):5} rows: no answer after {GIVE_UP_SECONDS} s, stopping OrderHub")
            break
        print(f"export of {len(rows):5} rows: {time.monotonic() - start:5.1f} s")

    services.stop()
    robot.stop()


if __name__ == "__main__":
    main()
