import time

from harness.client import wait_until

# The dispatcher runs every second. To prove something did NOT happen (no duplicate,
# no dispatch), give it this many seconds of dispatcher cycles, then count.
QUIET_SECONDS = 3


def assert_dispatched_once(robot, order_id):
    wait_until(lambda: robot.dispatches_for(order_id), message=f"order {order_id} never reached the robot")
    time.sleep(QUIET_SECONDS)
    count = len(robot.dispatches_for(order_id))

    assert count == 1, f"order {order_id} reached the robot {count} times, expected exactly once"


def assert_never_dispatched(robot, order_id):
    time.sleep(QUIET_SECONDS)
    count = len(robot.dispatches_for(order_id))

    assert count == 0, f"order {order_id} reached the robot {count} times, expected never"
