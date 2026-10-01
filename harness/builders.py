import csv
import io
import random
import uuid


def unique_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


# A valid webhook order with a unique order_id. Pass fields to change them:
# webhook_order(order_source="DoorDrop", items=["Soup"])
def webhook_order(**changes):
    order = {
        "order_id": unique_id("wh"),
        "order_source": "Grubstub",
        "restaurant": "Just Pizza",
        "first_name": "Ada",
        "last_name": "Park",
        "total": 24.5,
        "items": ["Margherita pizza", "Garlic knots"],
        "notes": "",
    }
    order.update(changes)
    return order


# The cancel message a platform sends for an order it sent earlier.
def webhook_cancel(order):
    return {**order, "update": ["cancelled"]}


# Partner API: each key in "data" is an item id; items belong to an order by "order" number.
def partner_order_number():
    return random.randint(10_000_000, 99_999_999)


# Items for one partner order, each with a new item id: {item_id: item}
def partner_items(order_number, *names, status="ordered"):
    return {
        uuid.uuid4().hex: {"order": order_number, "name": name, "category": "Food", "price": 5.0, "status": status}
        for name in names
    }


def partner_response(items):
    return {"response": 200, "data": items}


PARTNER_ERROR = {"response": 500, "error": "Internal server error"}


# Survey CSV. last_name gets a unique suffix, so a test can find its own orders and repeated test runs don't look
# like re-uploads of the same rows.
SURVEY_COLUMNS = ["first_name", "last_name", "items", "notes", "tomorrow", "meal"]


def survey_row(**changes):
    row = {
        "first_name": "Lena",
        "last_name": unique_id("Cho"),
        "items": "Bagel with cream cheese, Orange juice",
        "notes": "",
        "tomorrow": "true",
        "meal": "lunch",
    }
    row.update(changes)

    return row


def survey_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=SURVEY_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)

    return out.getvalue()
