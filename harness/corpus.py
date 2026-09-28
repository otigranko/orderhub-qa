import uuid

from harness import config


# Reads a bad-data file from data/corpus/, for example load("webhook/truncated.json").
# Files write UNIQUE where a test needs its own value (an order_id, a last name).
# Each load replaces it with a new tag, so a file can be sent again without looking like a retry.
# Returns the bytes to send and the tag, so the test can find what it created.
def load(name):
    tag = uuid.uuid4().hex[:10]
    body = (config.CORPUS_DIR / name).read_bytes()

    return body.replace(b"UNIQUE", tag.encode()), tag
