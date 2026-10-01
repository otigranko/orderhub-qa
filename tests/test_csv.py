from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from harness import config
from harness.builders import survey_csv, survey_row
from harness.client import OrderHubClient

MEAL_HOURS = {"breakfast": 8, "lunch": 12, "dinner": 18}


def orders_for(hub, last_name):
    return [o for o in hub.all_orders(source="csv") if o["customer_last"] == last_name]


# When a meal should be made, in the UTC format OrderHub stores: "2026-09-29 16:00:00".
def expected_ready_at(meal, tomorrow):
    site = ZoneInfo(config.SITE_TZ)
    day = datetime.now(site).date() + timedelta(days=1 if tomorrow else 0)
    local = datetime.combine(day, time(MEAL_HOURS[meal]), site)

    return local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")


# "Each export contains every response so far, so later uploads repeat earlier rows.
#  Each row becomes one order."

def test_uploading_the_same_export_again_creates_no_new_orders(hub):
    rows = [survey_row(first_name=f"Guest{i}") for i in range(5)]

    first = hub.upload_csv(survey_csv(rows)).json()
    again = hub.upload_csv(survey_csv(rows)).json()

    assert first["created"] == 5
    assert again["created"] == 0 and again["skipped"] == 5
    for row in rows:
        assert len(orders_for(hub, row["last_name"])) == 1


def test_later_export_creates_only_the_new_rows(hub):
    rows = [survey_row(first_name=f"Guest{i}") for i in range(5)]
    hub.upload_csv(survey_csv(rows))

    new_row = survey_row(first_name="Latecomer")
    result = hub.upload_csv(survey_csv(rows + [new_row])).json()

    assert result["created"] == 1 and result["skipped"] == 5
    assert len(orders_for(hub, new_row["last_name"])) == 1


# "The items column lists one item per line or separates items with commas."

@pytest.mark.parametrize("items", ["Veggie burrito, Chips and salsa", "Veggie burrito\nChips and salsa"],
                         ids=["commas", "new-lines"])
def test_items_are_split_into_separate_items(hub, items):
    row = survey_row(items=items)

    hub.upload_csv(survey_csv([row]))

    order = orders_for(hub, row["last_name"])[0]
    assert [i["name"] for i in order["items"]] == ["Veggie burrito", "Chips and salsa"]


# "meal is breakfast (made at 8:00), lunch (12:00), or dinner (18:00), in the kitchen's
#  local time zone (-site-tz, default America/New_York)."

@pytest.mark.xfail(strict=True, reason="L37-013: survey meals are scheduled in UTC, not the kitchen's time zone")
@pytest.mark.parametrize("meal", ["breakfast", "lunch", "dinner"])
def test_meal_is_scheduled_at_kitchen_local_time(hub, meal):
    row = survey_row(meal=meal, tomorrow="true")

    hub.upload_csv(survey_csv([row]))

    order = orders_for(hub, row["last_name"])[0]
    assert order["ready_at"] == expected_ready_at(meal, tomorrow=True)
    assert order["status"] == "scheduled"


# meal must be breakfast, lunch or dinner. Anything else can't be scheduled.

@pytest.mark.xfail(strict=True, reason="L37-014: an unknown meal is accepted and the order is made immediately")
def test_row_with_unknown_meal_is_rejected(hub):
    row = survey_row(meal="brunch")

    result = hub.upload_csv(survey_csv([row])).json()

    assert result["created"] == 0 and result["errors"], f"row with meal=brunch was accepted: {result}"
    assert orders_for(hub, row["last_name"]) == []


# "tomorrow (true or false)". Spreadsheet tools write TRUE/FALSE; meal is already
# read case-insensitively, so tomorrow should be too. Anything else is not a valid value.

@pytest.mark.xfail(strict=True, reason="L37-015: tomorrow=TRUE and other values are silently treated as today")
def test_tomorrow_in_capitals_means_tomorrow(hub):
    lower = survey_row(meal="dinner", tomorrow="true")
    upper = survey_row(meal="dinner", tomorrow="TRUE")

    hub.upload_csv(survey_csv([lower, upper]))

    # Compared with "true", not with a date, so the result doesn't depend on the time of day (L37-013).
    assert orders_for(hub, upper["last_name"])[0]["ready_at"] == orders_for(hub, lower["last_name"])[0]["ready_at"]


@pytest.mark.xfail(strict=True, reason="L37-015: tomorrow=TRUE and other values are silently treated as today")
@pytest.mark.parametrize("value", ["yes", ""], ids=["yes", "empty"])
def test_row_with_invalid_tomorrow_value_is_rejected(hub, value):
    row = survey_row(meal="dinner", tomorrow=value)

    result = hub.upload_csv(survey_csv([row])).json()

    assert result["created"] == 0 and result["errors"], f"row with tomorrow={value!r} was accepted: {result}"


# An upload can be sent twice at once: a double-click, or a retry after a slow upload timed out.
# Uploads get slower as more survey rows are stored, which widens the window, so store an
# earlier export first, as on a busy day.

@pytest.mark.xfail(strict=True, reason="L37-016: the same export uploaded twice at the same time creates duplicate orders")
def test_same_export_uploaded_twice_at_once_creates_each_order_once(hub):
    hub.upload_csv(survey_csv([survey_row(first_name=f"Earlier{i}") for i in range(300)]))

    rows = [survey_row(first_name=f"Guest{i}") for i in range(100)]
    body = survey_csv(rows)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: OrderHubClient().upload_csv(body), range(2)))

    # how many orders each last name has in one pass
    orders_per_row = Counter(o["customer_last"] for o in hub.all_orders(source="csv"))

    duplicated = [r["last_name"] for r in rows if orders_per_row[r["last_name"]] > 1]
    assert not duplicated, f"{len(duplicated)} of {len(rows)} rows became more than one order"
