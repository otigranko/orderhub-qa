import argparse
from concurrent.futures import ThreadPoolExecutor

from harness import corpus
from harness.builders import (partner_items, partner_order_number, partner_response, survey_csv,
                              survey_row, webhook_order)
from harness.client import MockPartnerClient, OrderHubClient

# Sends orders into the OrderHub started with `make run`. Run from the repo root:
#   python -m tools.inject webhook --count 50
#   python -m tools.inject partner --status cancelled
#   python -m tools.inject csv --rows 10
#   python -m tools.inject file webhook/truncated.json
#   python -m tools.inject reset-mock

ORDERHUB = "http://localhost:8080"
MOCK = "http://localhost:8090"


def show(r):
    print(r.status_code, r.text.strip())


# All at the same moment, like a burst from the platforms.
def send_webhook(args):
    with ThreadPoolExecutor(max_workers=args.count) as pool:
        for r in pool.map(lambda _: OrderHubClient(ORDERHUB).post_webhook(webhook_order()), range(args.count)):
            show(r)


# All orders in one partner response. OrderHub picks it up on its next poll.
def send_partner(args):
    items = {}
    for _ in range(args.count):
        number = partner_order_number()
        items.update(partner_items(number, *args.items, status=args.status))
        print("partner order", number)
    show(MockPartnerClient(MOCK).enqueue(partner_response(items)))


def send_csv(args):
    rows = [survey_row(first_name=f"Guest{i}") for i in range(args.rows)]
    show(OrderHubClient(ORDERHUB).upload_csv(survey_csv(rows)))


# A file from data/corpus/. The folder says which pipeline it goes to.
def send_file(args):
    body, _ = corpus.load(args.name)
    hub = OrderHubClient(ORDERHUB)
    show(hub.post_webhook_raw(body) if args.name.startswith("webhook/") else hub.upload_csv_raw(body))


def reset_mock(args):
    show(MockPartnerClient(MOCK).reset())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send orders into OrderHub (make run).")
    commands = parser.add_subparsers(required=True)

    p = commands.add_parser("webhook")
    p.add_argument("--count", type=int, default=1)
    p.set_defaults(run=send_webhook)

    p = commands.add_parser("partner")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--items", nargs="+", default=["Cold brew", "Blueberry pancakes"])
    p.add_argument("--status", default="ordered")
    p.set_defaults(run=send_partner)

    p = commands.add_parser("csv")
    p.add_argument("--rows", type=int, default=1)
    p.set_defaults(run=send_csv)

    p = commands.add_parser("file")
    p.add_argument("name", help="a file in data/corpus/, for example webhook/truncated.json")
    p.set_defaults(run=send_file)

    p = commands.add_parser("reset-mock")
    p.set_defaults(run=reset_mock)

    args = parser.parse_args()
    args.run(args)
