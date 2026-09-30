import time

import pytest

from harness import config
from harness.builders import partner_items, partner_order_number, partner_response, webhook_order
from harness.checks import QUIET_SECONDS, assert_dispatched_once
from harness.client import wait_until

# OrderHub is stopped and started again for deploys, after crashes (L37-022) and for maintenance.
# The spec's rules have to hold across that too.
# These tests restart the OrderHub the test run started, so they can't run against your make run.
pytestmark = pytest.mark.skipif(config.EXTERNAL, reason="restarts OrderHub, which QA_EXTERNAL=1 can't do")

DOWN_SECONDS = 3


# "Nothing that happens upstream may be lost." The partner doesn't know OrderHub is down,
# so orders keep happening there.

@pytest.mark.xfail(strict=True, reason="L37-024: partner orders placed while OrderHub is down are never fetched")
def test_partner_order_placed_while_orderhub_is_down_arrives_after_restart(hub, partner, services):
    order_number = partner_order_number()

    services.stop_orderhub()
    partner.enqueue(partner_response(partner_items(order_number, "Cold brew")))
    time.sleep(DOWN_SECONDS)
    services.start_orderhub()

    wait_until(lambda: hub.find_by_external("api", order_number),
               message=f"partner order {order_number}, placed while OrderHub was down, never arrived")


# "Each order is dispatched to the robot exactly once." Orders still waiting for the robot
# when OrderHub stops must be sent after it starts again: not lost, not sent twice.

def test_orders_waiting_for_the_robot_are_sent_once_after_restart(hub, robot, services):
    robot.fail_next = 1000
    order_ids = [hub.post_webhook(webhook_order()).json()["id"] for _ in range(3)]
    time.sleep(QUIET_SECONDS)
    assert all(hub.get_order(i).json()["status"] == "queued" for i in order_ids)

    services.stop_orderhub()
    robot.behave()
    services.start_orderhub()

    for order_id in order_ids:
        assert_dispatched_once(robot, order_id)


# A crash can happen while the robot is accepting an order: the robot has it, but OrderHub
# never hears back. After the restart the order must not be built a second time.

@pytest.mark.xfail(strict=True, reason="L37-025: an order being sent when OrderHub crashes is sent again after restart")
def test_order_being_sent_during_a_crash_is_not_sent_again_after_restart(hub, robot, services):
    robot.delay = 3
    order_id = hub.post_webhook(webhook_order()).json()["id"]
    wait_until(lambda: robot.dispatches_for(order_id), message="order never reached the robot")

    services.stop_orderhub(crash=True)
    robot.behave()
    services.start_orderhub()

    time.sleep(QUIET_SECONDS)
    count = len(robot.dispatches_for(order_id))
    assert count == 1, f"the robot received the order {count} times"
