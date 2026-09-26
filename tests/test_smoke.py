import csv
import io
import json
import random
import uuid

import pytest
import requests

from harness import config
from harness.client import wait_until

pytestmark = pytest.mark.smoke


def load_example(rel_path):
    path = config.EXAMPLES_DIR / rel_path
    if not path.exists():
        pytest.skip(f"example not found: {path} (set ORDERHUB_DIR)")
    return path.read_text()


def test_services_are_up():
    assert requests.get(f"{config.ORDERHUB_URL}/healthz", timeout=5).status_code == 200
    assert requests.get(f"{config.MOCK_API_URL}/status", timeout=5).status_code == 200


def test_webhook_example_creates_order_and_dispatches(hub):
    payload = json.loads(load_example("webhook/new_order.json"))
    payload["order_id"] = f"smoke-{uuid.uuid4().hex[:10]}"

    r = hub.post_webhook(payload)
    assert r.status_code == 202, r.text
    order_id = r.json()["id"]

    order = hub.get_order(order_id).json()
    assert order["source"] == "webhook"
    assert order["external_id"] == payload["order_id"]
    assert order["platform"] == payload["order_source"]
    assert [i["name"] for i in order["items"]] == payload["items"]

    # Live orders are ready immediately, so the dispatcher should pick it up within a tick or two.
    wait_until(lambda: hub.get_order(order_id).json()["status"] == "dispatched",
               message=f"order {order_id} was not dispatched")


def test_partner_api_example_is_polled_into_an_order(hub, partner):
    response = json.loads(load_example("partner_api/new_order.json"))
    order_num = random.randint(10_000_000, 99_999_999)
    # Item ids are the keys of `data`; make them unique too.
    response["data"] = {f"{uuid.uuid4().hex}": {**item, "order": order_num}
                        for item in response["data"].values()}

    assert partner.enqueue(response).status_code == 200

    found = wait_until(lambda: hub.find_by_external("api", order_num),
                       message=f"partner order {order_num} never appeared")
    assert len(found) == 1
    names = sorted(i["name"] for i in found[0]["items"])
    assert names == sorted(i["name"] for i in response["data"].values())


def test_csv_example_creates_one_order_per_row(hub):
    text = load_example("survey.csv")
    rows = list(csv.DictReader(io.StringIO(text)))
    # Rows are deduped on content, so tag each one to make this run's rows unique.
    tag = uuid.uuid4().hex[:8]
    for row in rows:
        row["last_name"] = f"{row['last_name']}-{tag}"
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

    r = hub.upload_csv(out.getvalue())
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["rows"] == len(rows)
    assert result["created"] == len(rows)
    assert result["errors"] == []

    mine = [o for o in hub.all_orders(source="csv") if o["customer_last"].endswith(tag)]
    assert len(mine) == len(rows)
