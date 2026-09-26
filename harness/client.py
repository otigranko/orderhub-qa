import time
import requests
from harness import config


class OrderHubClient:
    def __init__(self, base_url=config.ORDERHUB_URL, timeout=10):
        self.base = base_url
        self.http = requests.Session()
        self.timeout = timeout

    # ingest
    def post_webhook(self, payload):
        return self.http.post(f"{self.base}/webhooks/orders", json=payload, timeout=self.timeout)

    def upload_csv(self, csv_text):
        return self.http.post(f"{self.base}/uploads/csv", data=csv_text.encode("utf-8"),
                              headers={"Content-Type": "text/csv"}, timeout=self.timeout)

    # read
    def list_orders(self, **params):
        r = self.http.get(f"{self.base}/api/orders", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["orders"]

    def all_orders(self, page_size=500, **params):
        orders = []
        offset = 0
        while True:
            page = self.list_orders(limit=page_size, offset=offset, **params)
            if not page:
                return orders
            orders.extend(page)
            offset += len(page)

    def get_order(self, order_id):
        return self.http.get(f"{self.base}/api/orders/{order_id}", timeout=self.timeout)

    def find_by_external(self, source, external_id):
        return [o for o in self.all_orders(source=source) if o["external_id"] == str(external_id)]


class MockPartnerClient:
    def __init__(self, base_url=config.MOCK_API_URL, timeout=10):
        self.base = base_url
        self.http = requests.Session()
        self.timeout = timeout

    def enqueue(self, response):
        return self.http.post(f"{self.base}/enqueue", json=response, timeout=self.timeout)


def wait_until(check, timeout=config.DEFAULT_TIMEOUT, interval=0.25, message="condition not met"):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = check()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"Timed out after {timeout}s: {message} (last value: {last!r})")
