import json

import pytest

from harness import corpus
from harness.checks import assert_dispatched_once

# Every test here sends a file from data/corpus/ byte for byte.


def csv_orders(hub, tag):
    return [o for o in hub.all_orders(source="csv") if tag in o["customer_last"]]


# Webhook

# Platforms retry on failure, so a body that can't be read must get a 400 (the platform sees the failure)
#  and must not create an order.

@pytest.mark.parametrize("name", ["truncated.json", "empty.json", "array.json",
                                  "total_as_text.json", "items_as_text.json"])
def test_webhook_that_cannot_be_read_is_rejected(hub, name):
    body, tag = corpus.load(f"webhook/{name}")

    r = hub.post_webhook_raw(body)

    assert r.status_code == 400, f"{name} was accepted: {r.status_code} {r.text}"
    assert hub.find_by_external("webhook", f"wh-{tag}") == []


# A key with a comma in it is just a key OrderHub doesn't know. It is ignored and the order is kept as it is.

def test_webhook_with_a_comma_in_an_extra_key_is_accepted(hub, robot):
    body, tag = corpus.load("webhook/comma_in_extra_key.json")

    r = hub.post_webhook_raw(body)

    assert r.status_code == 202
    order = hub.get_order(r.json()["id"]).json()
    assert order["external_id"] == f"wh-{tag}"
    assert [i["name"] for i in order["items"]] == ["Margherita pizza", "Garlic knots"]
    assert_dispatched_once(robot, order["id"])


# With a comma in "order_id," the order has no order_id at all, and neither does null.

@pytest.mark.xfail(strict=True, reason="L37-004: webhooks with missing fields are accepted")
@pytest.mark.parametrize("name", ["comma_in_order_id_key.json", "null.json"])
def test_webhook_without_an_order_id_is_rejected(hub, name):
    body, _ = corpus.load(f"webhook/{name}")

    r = hub.post_webhook_raw(body)

    assert r.status_code == 400, f"{name} was accepted: {r.status_code} {r.text}"


# order_source is Grubstub, DoorDrop or Overeats, total is dollars, items has one entry per item.

@pytest.mark.xfail(strict=True, reason="L37-017: webhooks with values outside the spec are accepted")
@pytest.mark.parametrize("name", ["unknown_platform.json", "negative_total.json", "no_items.json"])
def test_webhook_with_values_outside_the_spec_is_rejected(hub, name):
    body, _ = corpus.load(f"webhook/{name}")

    r = hub.post_webhook_raw(body)

    assert r.status_code == 400, f"{name} was accepted: {r.status_code} {r.text}"


# Accents, emoji, commas, quotes and new lines are normal in names, items and notes.
# The robot must get exactly what the platform sent.

def test_special_characters_reach_the_robot_unchanged(hub, robot):
    body, _ = corpus.load("webhook/special_characters.json")
    sent = json.loads(body)

    order_id = hub.post_webhook_raw(body).json()["id"]

    assert_dispatched_once(robot, order_id)
    payload = robot.dispatches_for(order_id)[0]
    assert [i["name"] for i in payload["items"]] == sent["items"]
    assert payload["notes"] == sent["notes"]
    assert payload["customer"] == f"{sent['first_name']} {sent['last_name']}"


# Survey CSV

# Quotes, commas and new lines inside a field are standard CSV. Every value must be read whole.

def test_quotes_commas_and_new_lines_inside_fields_are_read_correctly(hub):
    body, tag = corpus.load("csv/quotes_commas_newlines.csv")

    result = hub.upload_csv_raw(body).json()

    assert result["created"] == 2 and result["errors"] == []
    orders = {o["customer_first"]: o for o in csv_orders(hub, tag)}
    lena, marcus = orders["Lena"], orders["Marcus"]
    assert lena["customer_last"] == f"Cho-{tag}, Jr."
    assert [i["name"] for i in lena["items"]] == ['Bagel "everything"', "Orange juice"]
    assert lena["notes"] == 'Say "hi", then knock'
    assert [i["name"] for i in marcus["items"]] == ["Soup", "Bread"]
    assert marcus["notes"] == "Allergic to nuts\nExtra napkins"


# Files saved on Windows, or with the columns in another order, are still survey exports.

def test_file_with_windows_line_endings_is_read_correctly(hub):
    body, tag = corpus.load("csv/windows_line_endings.csv")

    result = hub.upload_csv_raw(body).json()

    assert result["created"] == 2 and result["errors"] == []
    orders = {o["customer_first"]: o for o in csv_orders(hub, tag)}
    assert [i["name"] for i in orders["Lena"]["items"]] == ["Bagel", "Orange juice"]
    assert [i["name"] for i in orders["Marcus"]["items"]] == ["Soup", "Bread"]


def test_columns_are_found_by_name_in_any_order(hub):
    body, tag = corpus.load("csv/columns_in_other_order.csv")

    hub.upload_csv_raw(body)

    order = csv_orders(hub, tag)[0]
    assert order["customer_first"] == "Lena"
    assert [i["name"] for i in order["items"]] == ["Soup"]


# Excel's "CSV UTF-8" format starts the file with a byte order mark (BOM).
# Lena and Mia are sisters who ordered the same lunch: two rows, two orders.

@pytest.mark.xfail(strict=True, reason="L37-021: a CSV with a byte order mark loses first names and merges orders")
def test_file_with_a_byte_order_mark_is_read_correctly(hub):
    body, tag = corpus.load("csv/utf8_bom.csv")

    hub.upload_csv_raw(body)

    assert sorted(o["customer_first"] for o in csv_orders(hub, tag)) == ["Lena", "Mia"]


# A row OrderHub can't read must not take other rows with it. Either every other row becomes an
# order and the bad line is listed in errors, or the whole file is rejected so it can be fixed
# and uploaded again. A row must never disappear without being reported.

@pytest.mark.parametrize("name", [
    "stray_quote.csv",
    "short_row.csv",
    pytest.param("unterminated_quote.csv", marks=pytest.mark.xfail(
        strict=True, reason="L37-019: an unterminated quote silently drops every row after it")),
])
def test_one_bad_row_does_not_lose_the_other_rows(hub, name):
    body, tag = corpus.load(f"csv/{name}")

    r = hub.upload_csv_raw(body)

    created = sorted(o["customer_first"] for o in csv_orders(hub, tag))
    if r.status_code == 400:
        assert created == []
    else:
        assert r.json()["errors"], "the bad row was not reported"
        assert created == ["Good1", "Good2", "Good3"], f"only {created} became orders: {r.json()}"


# A file without the survey columns isn't a survey export. It must be rejected, not turned
# into orders with empty values.

@pytest.mark.parametrize("name", [
    "empty.csv",
    pytest.param("semicolon_separated.csv", marks=pytest.mark.xfail(
        strict=True, reason="L37-020: a CSV without the survey columns is accepted")),
    pytest.param("missing_meal_column.csv", marks=pytest.mark.xfail(
        strict=True, reason="L37-020: a CSV without the survey columns is accepted")),
])
def test_file_without_the_survey_columns_is_rejected(hub, name):
    body, _ = corpus.load(f"csv/{name}")

    r = hub.upload_csv_raw(body)

    assert r.status_code == 400, f"{name} was accepted: {r.text}"
