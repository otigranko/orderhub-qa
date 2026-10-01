# OrderHub QA

Test strategy, harness, and automated tests for OrderHub (order ingestion and dispatch).

Testing found 29 defects, 7 of them Critical: OrderHub loses orders, makes some orders twice,
and can be crashed by one survey upload. 

| The assignment asks for | Where it is |
| --- | --- |
| Test strategy: risks, test levels, merging and state, fault tolerance, the robot boundary, CI and release, trade-offs | [TEST_STRATEGY.md](TEST_STRATEGY.md) |
| Drivers for the three pipelines, fixtures and test data | `harness/` |
| Injecting orders on demand | `tools/inject.py`, see "Sending orders by hand" below |
| Load generator, bursty, at and above 100,000 a day | `tools/load.py` and `tools/csv_growth.py`, see "Load tests" below |
| Capturing what is sent to the robot | `harness/robot_sink.py` |
| Automated tests, one command | `tests/`, run with `python -m pytest` |
| Bad-data corpus | `data/corpus/` and `tests/test_bad_data.py` |
| Defect reports | `defects/defects.xlsx`, with screenshots in `defects/screenshots/`. A list of all defects is in [TEST_STRATEGY.md](TEST_STRATEGY.md), section 11, for reading on GitHub. |
| Load test results | [LOAD_RESULTS.md](LOAD_RESULTS.md) |
| Next steps and questions for the dev team | [TEST_STRATEGY.md](TEST_STRATEGY.md), section 13 |
| AI log | [AI_USAGE.md](AI_USAGE.md) |

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
tools/inject.py   sends orders into OrderHub by hand
tools/load.py     bursty load, then counts lost and duplicated orders
tools/csv_growth.py  how survey upload time grows as the export grows
defects/          defects.xlsx: every defect found, with steps, data and evidence
  screenshots/    what the UI showed, for the UI defects
data/corpus/      bad-data files, sent as raw bytes (see "Bad-data corpus" below)
results/          logs and database from the last run (not committed)
```

## Setup

Requires Python 3.9+.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # the browser for the UI tests, once
```

This repo expects the OrderHub checkout next to it (`../orderhub`). The tests run its built
binaries and read its example payloads. Build it once:

```sh
cd ../orderhub && make build
```

Point `ORDERHUB_DIR` elsewhere if your checkout lives somewhere else.

## Running

```sh
python -m pytest                   # everything
python -m pytest -m smoke          # just the smoke tests
python -m pytest -m "not ui"       # everything except the browser tests
python -m pytest -m ui --headed    # the UI tests, in a browser window you can watch
```

You don't need to start OrderHub yourself. Each test run starts its own OrderHub and mock partner API on a fresh 
database, with robot dispatches sent to a receiver inside the test run. Everything is stopped when the run ends. 
It uses different ports from `make run`, so you can keep your own instance running at the same time.

### UI tests

`tests/test_ui.py` checks what the operator sees in the OrderHub UI, in a real browser. It uses
Playwright through the `pytest-playwright` plugin, which is in `requirements.txt`. Each test
creates its orders through the API, then checks and clicks in the browser.

Install, once, after `pip install -r requirements.txt`:

```sh
playwright install chromium
```

This downloads the Chromium browser that Playwright drives. It doesn't touch your own Chrome.

Run:

```sh
python -m pytest -m ui                                     # all UI tests, no browser window
python -m pytest -m ui --headed --slowmo 500               # watch them in a browser window, slowed down
python -m pytest -m ui -k tick_stays --headed --runxfail   # one known bug, real failure, in a window
python -m pytest -m ui --screenshot only-on-failure --output results/ui   # screenshots of failures
```

The browser runs in the kitchen's time zone (`SITE_TZ`), as an operator at the site would see it.
The UI tests also work with `QA_EXTERNAL=1` (see "Running against `make run`" below), against
the UI of your own `make run`.

### Known defects in the test run

Tests that reproduce a known bug are marked `xfail` with the defect id from
`defects/defects.xlsx`, for example `L37-001`. They show up as `xfailed` instead of failing
the run, so the suite stays green while the bugs are open, and still tells you each bug is there:

```
29 passed, 38 xfailed
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
The restart tests (`tests/test_restart.py`) are skipped in this mode, because they stop and start
OrderHub, and they can't do that to yours.
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

### Sending orders by hand

`tools/inject.py` sends orders into the OrderHub you started with `make run` (ports 8080 and
8090), for exploring, demos, or checking a defect without long curl commands. Run it from this
repo:

```sh
python -m tools.inject webhook                      # one webhook order
python -m tools.inject webhook --count 50           # 50 at the same moment, like a burst
python -m tools.inject partner                      # one partner order, picked up on the next poll
python -m tools.inject partner --status cancelled   # a partner order that arrives already cancelled
python -m tools.inject csv --rows 10                # a survey upload with 10 rows
python -m tools.inject file webhook/truncated.json  # any file from data/corpus/
python -m tools.inject reset-mock                   # clear the mock partner API
```

It prints OrderHub's answer for each request, for example `202 {"id":5}`.

### Load tests

`tools/load.py` sends the peak hour of 100,000 orders a day in bursts, across all three
pipelines, then compares what was sent, what OrderHub stored, and what the robot received.
Like the tests, it starts its own OrderHub, so `make run` isn't touched.

```sh
python -m tools.load                    # 3 minutes at the expected peak
python -m tools.load --scale 5          # five times that
python -m tools.load --burst-every 10   # the same orders, in bigger bursts
python -m tools.csv_growth              # survey upload time as the export grows
```

The traffic model, results and what they mean are in [LOAD_RESULTS.md](LOAD_RESULTS.md).
`tools.csv_growth` stops at the first upload with no answer in 30 seconds and stops OrderHub,
because by then OrderHub is using more and more memory (L37-022).

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
