import time

import pytest

from harness.builders import PARTNER_ERROR, partner_items, partner_order_number, partner_response
from harness.checks import QUIET_SECONDS, assert_dispatched_once, assert_never_dispatched
from harness.client import wait_until

# OrderHub polls the partner API every 2 seconds. Waiting 3 poll cycles is enough to be sure
# an update was picked up.
POLL_WAIT = 6


def wait_for_partner_order(hub, order_number):
    orders = wait_until(lambda: hub.find_by_external("api", order_number),
                        message=f"partner order {order_number} never appeared")
    return orders[0]


def item_with_name(items, name):
    return next(item_id for item_id, item in items.items() if item["name"] == name)


# "The API sometimes fails with a 500, and a retry of the same request succeeds.
#  Nothing that happens upstream may be lost."

@pytest.mark.xfail(strict=True, reason="L37-005: orders in the same poll window as a partner API 500 are lost")
def test_order_in_the_same_window_as_a_500_is_not_lost(hub, partner):
    before = partner.status()
    order_number = partner_order_number()

    partner.enqueue(PARTNER_ERROR)
    partner.enqueue(partner_response(partner_items(order_number, "Cold brew")))

    # Prove both reached the mock, so a missing order is OrderHub's fault, not the harness's.
    after = partner.status()
    assert after["enqueued"] == before["enqueued"] + 2
    assert after["failures"] == before["failures"] + 1

    wait_for_partner_order(hub, order_number)


def test_polling_recovers_after_a_500(hub, partner):
    partner.enqueue(PARTNER_ERROR)
    time.sleep(POLL_WAIT)
    order_number = partner_order_number()

    partner.enqueue(partner_response(partner_items(order_number, "Cold brew")))

    wait_for_partner_order(hub, order_number)


# "A response only contains the items that changed."

def test_status_update_does_not_create_or_dispatch_a_second_order(hub, partner, robot):
    order_number = partner_order_number()
    items = partner_items(order_number, "Cold brew", "Blueberry pancakes")
    partner.enqueue(partner_response(items))
    order_id = wait_for_partner_order(hub, order_number)["id"]

    partner.enqueue(partner_response({k: {**v, "status": "processing"} for k, v in items.items()}))
    time.sleep(POLL_WAIT)

    assert len(hub.find_by_external("api", order_number)) == 1
    assert_dispatched_once(robot, order_id)


@pytest.mark.xfail(strict=True, reason="L37-006: a partner update for some items removes the order's other items")
def test_status_update_for_one_item_keeps_the_other_items(hub, partner):
    order_number = partner_order_number()
    items = partner_items(order_number, "Cold brew", "Blueberry pancakes")
    partner.enqueue(partner_response(items))
    order_id = wait_for_partner_order(hub, order_number)["id"]

    cold_brew = item_with_name(items, "Cold brew")
    partner.enqueue(partner_response({cold_brew: {**items[cold_brew], "status": "processing"}}))
    time.sleep(POLL_WAIT)

    order = hub.get_order(order_id).json()
    assert sorted(i["name"] for i in order["items"]) == ["Blueberry pancakes", "Cold brew"]
    assert order["total"] == 10.0


# "An order whose items are all cancelled is cancelled." So cancelling some items must not.

@pytest.mark.xfail(strict=True, reason="L37-007: cancelling one item cancels the whole partner order")
def test_cancelling_one_item_does_not_cancel_the_order(hub, partner):
    order_number = partner_order_number()
    items = partner_items(order_number, "Cold brew", "Blueberry pancakes")
    partner.enqueue(partner_response(items))
    order_id = wait_for_partner_order(hub, order_number)["id"]

    pancakes = item_with_name(items, "Blueberry pancakes")
    partner.enqueue(partner_response({pancakes: {**items[pancakes], "status": "cancelled"}}))
    time.sleep(POLL_WAIT)

    assert hub.get_order(order_id).json()["status"] != "cancelled"


@pytest.mark.xfail(strict=True, reason="L37-008: a partner order that arrives with every item cancelled is made")
def test_order_that_arrives_fully_cancelled_is_never_dispatched(hub, partner, robot):
    order_number = partner_order_number()

    partner.enqueue(partner_response(partner_items(order_number, "Cold brew", "Blueberry pancakes",
                                                   status="cancelled")))
    order_id = wait_for_partner_order(hub, order_number)["id"]

    assert_never_dispatched(robot, order_id)
    assert hub.get_order(order_id).json()["status"] == "cancelled"


# "A cancelled order is never dispatched." A cancelled item shouldn't be made either.

@pytest.mark.xfail(strict=True, reason="L37-009: cancelled items are sent to the robot")
def test_cancelled_item_is_not_sent_to_the_robot(hub, partner, robot):
    order_number = partner_order_number()
    items = partner_items(order_number, "Cold brew")
    items.update(partner_items(order_number, "Blueberry pancakes", status="cancelled"))

    partner.enqueue(partner_response(items))
    order_id = wait_for_partner_order(hub, order_number)["id"]

    wait_until(lambda: robot.dispatches_for(order_id), message="order never reached the robot")
    time.sleep(QUIET_SECONDS)
    sent = robot.dispatches_for(order_id)[0]
    assert [i["name"] for i in sent["items"]] == ["Cold brew"]
