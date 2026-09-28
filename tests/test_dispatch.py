import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from harness.builders import webhook_order
from harness.checks import QUIET_SECONDS, assert_dispatched_once
from harness.client import OrderHubClient, wait_until

# OrderHub's own simulated robot takes 15-40 ms to accept an order, "similar to the real
# controller's ack time". We use 30 ms as a normal robot.
NORMAL_ROBOT_SECONDS = 0.03


def send_orders_at_once(count):
    with ThreadPoolExecutor(max_workers=20) as pool:
        return list(pool.map(lambda _: OrderHubClient().post_webhook(webhook_order()).json()["id"], range(count)))


def times_made(robot, order_ids):
    return {order_id: len(robot.dispatches_for(order_id)) for order_id in order_ids}


# "Each order is dispatched to the robot exactly once."
# "Traffic is bursty."

@pytest.mark.usefixtures("services")
@pytest.mark.xfail(strict=True, reason="L37-010: orders are sent to the robot more than once when a batch takes over 1 second")
def test_burst_at_normal_robot_speed_makes_each_order_once(robot):
    robot.delay = NORMAL_ROBOT_SECONDS

    order_ids = send_orders_at_once(60)
    wait_until(lambda: all(robot.dispatches_for(i) for i in order_ids), timeout=30,
               message="not every order reached the robot")
    time.sleep(QUIET_SECONDS)

    made = times_made(robot, order_ids)
    extra = {i: n for i, n in made.items() if n > 1}
    assert not extra, f"{len(extra)} of {len(order_ids)} orders were made more than once: {extra}"


@pytest.mark.xfail(strict=True, reason="L37-010: orders are sent to the robot more than once when a batch takes over 1 second")
def test_slow_robot_makes_each_order_once(hub, robot):
    robot.delay = 1.5

    order_ids = [hub.post_webhook(webhook_order()).json()["id"] for _ in range(3)]
    wait_until(lambda: all(robot.dispatches_for(i) for i in order_ids), timeout=20,
               message="not every order reached the robot")
    time.sleep(QUIET_SECONDS)

    assert times_made(robot, order_ids) == {i: 1 for i in order_ids}


def test_order_is_sent_again_after_the_robot_rejects_it(hub, robot):
    robot.fail_next = 1

    order_id = hub.post_webhook(webhook_order()).json()["id"]

    assert_dispatched_once(robot, order_id)
    assert hub.get_order(order_id).json()["status"] == "dispatched"


# "Once an order is dispatched, the robot is already building it, so it can no longer be cancelled."

@pytest.mark.xfail(strict=True, reason="L37-011: an order the robot already has can be cancelled")
def test_dispatched_order_cannot_be_cancelled(hub, robot):
    order_id = hub.post_webhook(webhook_order()).json()["id"]
    assert_dispatched_once(robot, order_id)

    r = hub.cancel(order_id)

    assert r.status_code != 200, "cancel of a dispatched order was accepted"
    assert hub.get_order(order_id).json()["status"] == "dispatched"


@pytest.mark.xfail(strict=True, reason="L37-012: a cancel during dispatch is accepted, then silently undone")
def test_cancel_while_the_robot_is_receiving_the_order_is_refused(hub, robot):
    robot.delay = 0.8
    order_id = hub.post_webhook(webhook_order()).json()["id"]
    wait_until(lambda: robot.dispatches_for(order_id), interval=0.02, message="order never reached the robot")

    r = hub.cancel(order_id)
    time.sleep(QUIET_SECONDS)

    assert hub.get_order(order_id).json()["status"] == "dispatched"
    assert r.status_code != 200, "OrderHub said the order was cancelled, but the robot is building it"
