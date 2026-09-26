# OrderHub QA

Test strategy, harness, and automated tests for OrderHub (order ingestion and dispatch).

## Layout

```
harness/        reusable test tooling
  config.py     where the system under test lives (env-var overridable)
  client.py     HTTP clients for OrderHub and the mock partner API, wait helper
tests/          pytest suites
data/corpus/    bad-data files, sent as raw bytes
data/scenarios/ named static scenarios
```

## Setup

Requires Python 3.10+.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This repo expects the OrderHub checkout next to it (`../orderhub`), which is where it reads
the provided example payloads from. Point `ORDERHUB_DIR` elsewhere if yours lives somewhere else.

## Running

Start OrderHub first (in the orderhub repo):

```sh
make run
```

Then, from this repo:

```sh
pytest                # everything
pytest -m smoke       # just the smoke tests
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ORDERHUB_URL` | `http://localhost:8080` | OrderHub API |
| `MOCK_API_URL` | `http://localhost:8090` | Mock partner API |
| `ORDERHUB_DIR` | `../orderhub` | OrderHub checkout (for example payloads) |
| `QA_TIMEOUT` | `10` | Seconds to wait for async outcomes (polling, dispatch) |
