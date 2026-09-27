# OrderHub QA

Test strategy, harness, and automated tests for OrderHub (order ingestion and dispatch).

The plan and the reasoning behind it are in [TEST_STRATEGY.md](TEST_STRATEGY.md).

## Layout

```
harness/          reusable test tooling
  config.py       paths, ports and timeouts (env-var overridable)
  client.py       HTTP clients for OrderHub and the mock partner API, wait helper
  robot_sink.py   stands in for the robot and records every dispatch it receives
  services.py     starts OrderHub and the mock partner API for a test run
tests/            pytest suites
data/corpus/      bad-data files, sent as raw bytes
data/scenarios/   named static scenarios
results/          logs and database from the last run (not committed)
```

## Setup

Requires Python 3.10+.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This repo expects the OrderHub checkout next to it (`../orderhub`). The tests run its built
binaries and read its example payloads. Build it once:

```sh
cd ../orderhub && make build
```

Point `ORDERHUB_DIR` elsewhere if your checkout lives somewhere else.

## Running

```sh
python -m pytest              # everything
python -m pytest -m smoke     # just the smoke tests
```

You don't need to start OrderHub yourself. Each test run starts its own OrderHub and mock
partner API on a fresh database, with robot dispatches sent to a receiver inside the test run.
Everything is stopped when the run ends. It uses different ports from `make run`, so you can
keep your own instance running at the same time.

After a run, `results/` holds OrderHub's log, the mock's log, and the database. Useful for
debugging a failure or attaching to a defect report.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ORDERHUB_DIR` | `../orderhub` | OrderHub checkout (binaries and example payloads) |
| `ORDERHUB_PORT` | `18080` | Port for the OrderHub the tests start |
| `MOCK_API_PORT` | `18090` | Port for the mock partner API the tests start |
| `ROBOT_PORT` | `18181` | Port for the robot receiver |
| `QA_TIMEOUT` | `10` | Seconds to wait for async outcomes (polling, dispatch) |
