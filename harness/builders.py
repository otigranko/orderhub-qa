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
