from concurrent.futures import ThreadPoolExecutor

import pytest

from harness.builders import webhook_cancel, webhook_order
from harness.checks import assert_dispatched_once, assert_never_dispatched
from harness.client import OrderHubClient


# "Platforms retry on failure, so the same request may arrive more than once."

def test_retried_webhook_creates_one_order(hub, robot):
    order = webhook_order()

    first = hub.post_webhook(order)
    retry = hub.post_webhook(order)

    assert first.status_code == 202 and retry.status_code == 202
    assert first.json()["id"] == retry.json()["id"]
    assert len(hub.find_by_external("webhook", order["order_id"])) == 1
    assert_dispatched_once(robot, first.json()["id"])


def test_retries_arriving_at_the_same_time_create_one_order(hub, robot):
    order = webhook_order()

    # 10 copies of the same request at the same moment, like a platform retrying during a burst.
    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda _: OrderHubClient().post_webhook(order), range(10)))

    assert all(r.status_code == 202 for r in responses)
    ids = {r.json()["id"] for r in responses}
    assert len(ids) == 1, f"retries created {len(ids)} different orders: {ids}"
    assert len(hub.find_by_external("webhook", order["order_id"])) == 1
    assert_dispatched_once(robot, ids.pop())


# "Each platform assigns its own order_ids."

@pytest.mark.xfail(strict=True, reason="L37-001: same order_id from two platforms becomes one order")
def test_same_order_id_on_two_platforms_creates_two_orders(hub):
    grubstub = webhook_order(order_source="Grubstub", first_name="Gina")
    doordrop = webhook_order(order_id=grubstub["order_id"], order_source="DoorDrop", first_name="Dora")

    hub.post_webhook(grubstub)
    hub.post_webhook(doordrop)

    orders = hub.find_by_external("webhook", grubstub["order_id"])
    assert sorted(o["platform"] for o in orders) == ["DoorDrop", "Grubstub"]


# '"update": ["cancelled"] cancels an order that platform sent earlier.'

@pytest.mark.xfail(strict=True, reason="L37-002: a cancel from one platform cancels another platform's order")
def test_cancel_from_another_platform_does_not_cancel_the_order(hub):
    grubstub = webhook_order(order_source="Grubstub")
    order_id = hub.post_webhook(grubstub).json()["id"]

    hub.post_webhook(webhook_cancel({**grubstub, "order_source": "DoorDrop"}))

    assert hub.get_order(order_id).json()["status"] != "cancelled"


# "A cancelled order is never dispatched." Retries mean a cancel can arrive before its order.

@pytest.mark.xfail(strict=True, reason="L37-003: a cancel that arrives before its order is lost; the order is made")
def test_cancel_that_arrives_first_still_cancels_the_order(hub, robot):
    order = webhook_order()

    hub.post_webhook(webhook_cancel(order))
    order_id = hub.post_webhook(order).json()["id"]

    assert_never_dispatched(robot, order_id)
    assert hub.get_order(order_id).json()["status"] == "cancelled"


# every webhook order has an order_id, an order_source and items.
# Without them an order can't be made or tracked.

@pytest.mark.xfail(strict=True, reason="L37-004: webhooks with missing fields are accepted")
@pytest.mark.parametrize("body", [
    {},
    {"order_source": "Grubstub", "first_name": "Ann", "items": ["Soup"]},
], ids=["empty", "no-order-id"])
def test_webhook_with_missing_fields_is_rejected(hub, body):
    r = hub.post_webhook(body)

    assert r.status_code == 400
