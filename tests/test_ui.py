import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import expect

from harness import config
from harness.builders import survey_csv, survey_row, webhook_order
from harness.client import wait_until

# What the operator sees in the OrderHub UI. Orders are created through the API, then checked
# and acted on in the browser (the `page` fixture comes from pytest-playwright).
# The UI refreshes its order list every 3 seconds, so waits here allow 10.
pytestmark = pytest.mark.ui
REFRESH_WAIT = 10_000


# Run the browser in the kitchen's time zone, as an operator at the site would.
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "timezone_id": config.SITE_TZ, "locale": "en-US"}


# A survey order for tomorrow: it stays "scheduled", so it can be selected and cancelled.
def scheduled_order(hub):
    row = survey_row()
    hub.upload_csv(survey_csv([row]))
    return next(o["id"] for o in hub.all_orders(source="csv") if o["customer_last"] == row["last_name"])


def cancel_button(page):
    return page.get_by_role("button", name=re.compile("Cancel selected"))


# "Once an order is dispatched, the robot is already building it, so it can no longer be cancelled."

def test_dispatched_order_cannot_be_selected_for_cancel(hub, page):
    order_id = hub.post_webhook(webhook_order()).json()["id"]
    wait_until(lambda: hub.get_order(order_id).json()["status"] == "dispatched", message="order was not dispatched")

    page.goto(config.ORDERHUB_URL)

    expect(page.get_by_label(f"Select order {order_id}")).to_be_disabled(timeout=REFRESH_WAIT)


# The operator ticks orders, and the button says how many will be cancelled.

@pytest.mark.xfail(strict=True, reason="L37-026: the Cancel selected button always shows (0)")
def test_cancel_button_counts_the_ticked_orders(hub, page):
    order_id = scheduled_order(hub)
    page.goto(config.ORDERHUB_URL)

    page.get_by_label(f"Select order {order_id}").check()

    expect(cancel_button(page)).to_have_text("Cancel selected (1)")


# New orders keep arriving at the top of the list. A tick must stay on the order the operator
# ticked, because that is the order Cancel selected will cancel.

@pytest.mark.xfail(strict=True, reason="L37-027: when a new order arrives, the tick moves to a different order")
def test_tick_stays_on_the_same_order_when_a_new_order_arrives(hub, page):
    ticked = scheduled_order(hub)
    page.goto(config.ORDERHUB_URL)
    page.get_by_label(f"Select order {ticked}").check()

    newer = scheduled_order(hub)
    expect(page.get_by_label(f"Select order {newer}")).to_be_visible(timeout=REFRESH_WAIT)

    expect(page.get_by_label(f"Select order {ticked}")).to_be_checked()


# The status tabs show how many orders are in each status.

@pytest.mark.xfail(strict=True, reason="L37-028: the status tab counts never change after the page loads")
def test_status_tab_counts_update_when_orders_arrive(hub, page):
    page.goto(config.ORDERHUB_URL)
    all_count = page.locator("nav.rail button.tab").first.locator(".tab-count")
    expect(all_count).not_to_have_text("0", timeout=REFRESH_WAIT)
    before = int(all_count.inner_text())

    scheduled_order(hub)

    expect(all_count).to_have_text(str(before + 1), timeout=REFRESH_WAIT)


# "Make at" is when the order is made. OrderHub's API gives the time in UTC, so the UI has to
# show it in the operator's own time zone.

@pytest.mark.xfail(strict=True, reason="L37-029: Make at shows the UTC time as if it were local time")
def test_make_at_is_shown_in_local_time(hub, page):
    order_id = hub.post_webhook(webhook_order()).json()["id"]
    ready_at = hub.get_order(order_id).json()["ready_at"]
    local = datetime.strptime(ready_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(ZoneInfo(config.SITE_TZ))
    expected = f"{local:%b} {local.day}, {local.hour % 12 or 12}:{local:%M} {local:%p}"

    page.goto(config.ORDERHUB_URL)

    row = page.locator("tr", has=page.locator(f"a[href='#/orders/{order_id}']"))
    expect(row).to_contain_text(expected, timeout=REFRESH_WAIT)
