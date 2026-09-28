# OrderHub QA

Test strategy, harness, and automated tests for OrderHub (order ingestion and dispatch).

The plan and the reasoning behind it are in [TEST_STRATEGY.md](TEST_STRATEGY.md).
How I used AI is in [AI_USAGE.md](AI_USAGE.md).

## Layout

```
harness/          reusable test tooling
  config.py       paths, ports and timeouts (env-var overridable)
  client.py       HTTP clients for OrderHub and the mock partner API, wait helper
  builders.py     valid orders with unique ids, easy to change per test
  checks.py       "reached the robot exactly once" and "never reached the robot"
  corpus.py       reads a bad-data file and gives it unique ids
  robot_sink.py   stands in for the robot: records every dispatch, can be made slow or reject orders
  services.py     starts OrderHub and the mock partner API for a test run
tests/            pytest suites
defects/          defects.xlsx: every defect found, with steps, data and evidence
data/corpus/      bad-data files, sent as raw bytes (see "Bad-data corpus" below)
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

### Known defects in the test run

Tests that reproduce a known bug are marked `xfail` with the defect id from
`defects/defects.xlsx`, for example `L37-001`. They show up as `xfailed` instead of failing
the run, so the suite stays green while the bugs are open, and still tells you each bug is there:

```
27 passed, 32 xfailed
```

They use `strict=True`: when a bug is fixed, its test starts passing, pytest reports it as a
failure, and that's the reminder to remove the marker and close the defect. To see the real
failure output for the known bugs:

```sh
python -m pytest --runxfail
```

### Running against `make run`

To run the tests against your own OrderHub instead, for example to watch orders appear in the
UI or to re-check a defect, start it so it sends robot dispatches to the test run's receiver:

```sh
cd ../orderhub
make reset
ORDERHUB_ROBOT_URL=http://127.0.0.1:18181/dispatch make run
```

Then, in this repo:

```sh
QA_EXTERNAL=1 python -m pytest                                   # everything
QA_EXTERNAL=1 python -m pytest --runxfail -k same_order_id       # one known bug, real failure output
```

In this mode the tests use OrderHub on 8080 and the mock on 8090, and only start the robot
receiver. Every test uses unique ids, so data already in your database doesn't get in the way.
When no test run is active, nothing listens on 18181, so orders you send by hand stay `queued`.
For the curl steps in `defects/defects.xlsx`, use plain `make run` instead.

After a normal run, `results/` holds OrderHub's log, the mock's log, and the database. Useful for
debugging a failure or attaching to a defect report.

### Bad-data corpus

`data/corpus/webhook/` and `data/corpus/csv/` hold one file per bad input: broken JSON, a
comma in a JSON key, CSV fields with quotes, commas and new lines, a byte order mark, and so on.
`tests/test_bad_data.py` sends each file byte for byte and says what OrderHub should do with it.
Where a file needs its own order id or name it has `UNIQUE`, which is replaced with a new value
each time, so the same file can be sent again. `.gitattributes` stops Git from changing the
files' line endings. To add a case, add a file and add its name to the matching test.

Partner API cases are built in `tests/test_partner_api.py` instead, because the mock partner API
only accepts valid JSON.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ORDERHUB_DIR` | `../orderhub` | OrderHub checkout (binaries and example payloads) |
| `QA_EXTERNAL` | not set | `1` runs against an OrderHub that is already running (see above) |
| `ORDERHUB_PORT` | `18080` (`8080` with `QA_EXTERNAL=1`) | OrderHub port |
| `MOCK_API_PORT` | `18090` (`8090` with `QA_EXTERNAL=1`) | Mock partner API port |
| `ROBOT_PORT` | `18181` | Port for the robot receiver |
| `SITE_TZ` | `America/New_York` | The kitchen's time zone; must match OrderHub's `-site-tz` |
| `QA_TIMEOUT` | `10` | Seconds to wait for async outcomes (polling, dispatch) |
