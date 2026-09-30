import argparse
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

from harness import config
from harness.builders import (PARTNER_ERROR, partner_items, partner_order_number, partner_response,
                              survey_csv, survey_row, webhook_order)
from harness.client import MockPartnerClient, OrderHubClient
from harness.robot_sink import RobotSink
from harness.services import Services

# Bursty load against a fresh OrderHub, then counts lost and duplicated orders.

# Run from the repo root:
#   python -m tools.load                    # the peak hour of 100,000 orders a day, for 3 minutes
#   python -m tools.load --scale 5          # five times that
#   python -m tools.load --burst-every 10   # the same orders, in bigger bursts
#
# Traffic model (see LOAD_RESULTS.md for why):
#   - the peak hour carries 15% of the day's orders
#   - they arrive in bursts every 5 seconds, not evenly
#   - 80% webhook orders, 5% of them sent twice (platforms retry), 20% partner API orders
#   - the partner API fails with a 500 once a minute
#   - the survey export is uploaded every 30 seconds, each time with every row so far plus new ones
#   - the robot takes 30 ms to accept an order, like OrderHub's own simulated robot (15-40 ms)

PEAK_HOUR_SHARE = 0.15
BURST_EVERY = 5
WEBHOOK_SHARE = 0.8
RETRY_SHARE = 0.05
PARTNER_500_EVERY = 60
CSV_EVERY = 30
CSV_NEW_ROWS = 50
ROBOT_SECONDS = 0.03


def timed(send):
    start = time.monotonic()
    try:
        ok = send().status_code < 300
    except requests.RequestException:
        ok = False
    return ok, time.monotonic() - start


# p50: half the requests were faster than this. p95: 95 in 100 were faster.
def percentiles(seconds):
    seconds = sorted(seconds)
    ms = lambda s: f"{s * 1000:.0f} ms"
    return f"p50 {ms(seconds[len(seconds) // 2])}, p95 {ms(seconds[int(len(seconds) * 0.95)])}, max {ms(seconds[-1])}"


# Waits until OrderHub has stopped storing and dispatching, so the counts are final.
def wait_until_quiet(hub, robot):
    last = None
    while True:
        time.sleep(5)
        now = (len(hub.all_orders()), len(robot.received))
        if now == last:
            return
        last = now


def main():
    parser = argparse.ArgumentParser(description="Bursty load against OrderHub.")
    parser.add_argument("--per-day", type=int, default=100_000, help="orders per day")
    parser.add_argument("--scale", type=float, default=1, help="multiply the traffic, for example 5")
    parser.add_argument("--minutes", type=float, default=3)
    parser.add_argument("--burst-every", type=int, default=BURST_EVERY, help="seconds between bursts")
    args = parser.parse_args()

    per_second = args.per_day * args.scale * PEAK_HOUR_SHARE / 3600
    burst = max(1, round(per_second * args.burst_every))
    webhooks_per_burst = round(burst * WEBHOOK_SHARE)
    partner_per_burst = burst - webhooks_per_burst
    print(f"{args.per_day:,} orders/day x{args.scale:g}: a burst of {burst} orders every {args.burst_every} s "
          f"({webhooks_per_burst} webhook, {partner_per_burst} partner) for {args.minutes:g} minutes")

    robot = RobotSink(config.ROBOT_PORT)
    robot.delay = ROBOT_SECONDS
    robot.start()
    services = Services(robot.url)
    services.start()
    hub = OrderHubClient()
    partner = MockPartnerClient()

    webhooks = []           # every webhook order, once each
    webhook_results = []    # (order_id, ok, seconds) for each request
    partner_orders = []
    partner_500s = 0
    csv_rows = []
    csv_uploads = []        # (rows in the upload, ok, seconds)

    def send_webhook(order):
        ok, seconds = timed(lambda: OrderHubClient().post_webhook(order))
        webhook_results.append((order["order_id"], ok, seconds))

    def upload_csv(rows):
        ok, seconds = timed(lambda: OrderHubClient(timeout=30).upload_csv(survey_csv(rows)))
        csv_uploads.append((len(rows), ok, seconds))

    pool = ThreadPoolExecutor(max_workers=200)
    start = time.monotonic()
    tick = 0
    while time.monotonic() - start < args.minutes * 60:
        if tick % PARTNER_500_EVERY == 0:
            partner.enqueue(PARTNER_ERROR)
            partner_500s += 1

        if tick % args.burst_every == 0:
            for _ in range(webhooks_per_burst):
                order = webhook_order()
                webhooks.append(order)
                pool.submit(send_webhook, order)
                if len(webhooks) % round(1 / RETRY_SHARE) == 0:
                    pool.submit(send_webhook, order)

            items = {}
            for _ in range(partner_per_burst):
                number = partner_order_number()
                partner_orders.append(str(number))
                items.update(partner_items(number, "Cold brew"))
            if items:
                partner.enqueue(partner_response(items))

        if tick % CSV_EVERY == 0:
            csv_rows.extend(survey_row(first_name=f"Guest{len(csv_rows) + i}") for i in range(CSV_NEW_ROWS))
            pool.submit(upload_csv, list(csv_rows))

        tick += 1
        time.sleep(max(0, start + tick - time.monotonic()))

    pool.shutdown(wait=True)
    print("All sent. Waiting for OrderHub to finish storing and dispatching...")
    wait_until_quiet(hub, robot)

    stored = {source: Counter(o["external_id"] for o in hub.all_orders(source=source))
              for source in ("webhook", "api")}
    stored_csv = Counter(o["customer_last"] for o in hub.all_orders(source="csv"))
    built = Counter(p["external_ref"] for p in robot.received)
    services.stop()
    robot.stop()

    accepted = {order_id for order_id, ok, _ in webhook_results if ok}
    unique_webhooks = {o["order_id"] for o in webhooks}
    failed = unique_webhooks - accepted
    print()
    print(f"Webhook:  {len(unique_webhooks)} orders, {len(webhook_results)} requests "
          f"({len(webhook_results) - len(unique_webhooks)} retries), {len(failed)} orders never accepted")
    print(f"          response time {percentiles([s for _, _, s in webhook_results])}")
    print(f"Partner:  {len(partner_orders)} orders, {partner_500s} partner 500s")
    print(f"Survey:   {len(csv_rows)} rows in {len(csv_uploads)} uploads, "
          f"{sum(1 for _, ok, _ in csv_uploads if not ok)} failed")
    for rows, ok, seconds in sorted(csv_uploads):
        print(f"          upload of {rows} rows took {seconds:.1f} s")
    print()

    expected = {"webhook": accepted, "api": set(partner_orders)}
    total_lost = total_duplicated = total_never = total_extra_builds = 0
    for source, sent in expected.items():
        lost = sent - set(stored[source])
        duplicated = [k for k, n in stored[source].items() if n > 1]
        builds = [built[f"{source}:{k}"] for k in sent - lost]
        never = builds.count(0)
        twice = sum(1 for n in builds if n > 1)
        extra = sum(n - 1 for n in builds if n > 1)
        print(f"{source:8}  sent {len(sent)}, stored {len(sent) - len(lost)}, lost {len(lost)}, "
              f"stored twice {len(duplicated)} | robot: made once {builds.count(1)}, never {never}, "
              f"more than once {twice} ({extra} extra builds)")
        total_lost += len(lost)
        total_duplicated += len(duplicated)
        total_never += never
        total_extra_builds += extra

    csv_lost = [r["last_name"] for r in csv_rows if stored_csv[r["last_name"]] == 0]
    csv_twice = [r["last_name"] for r in csv_rows if stored_csv[r["last_name"]] > 1]
    print(f"{'csv':8}  rows {len(csv_rows)}, stored {len(csv_rows) - len(csv_lost)}, lost {len(csv_lost)}, "
          f"stored more than once {len(csv_twice)} (scheduled for tomorrow, so not dispatched in this run)")
    print()
    print(f"Lost {total_lost + len(csv_lost)}, stored twice {total_duplicated + len(csv_twice)}, "
          f"never made {total_never}, extra robot builds {total_extra_builds}")


if __name__ == "__main__":
    main()
