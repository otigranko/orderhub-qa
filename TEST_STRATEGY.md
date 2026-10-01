# OrderHub Test Strategy

Contents:
1. What we are protecting
2. Risk assessment
3. Approach
4. Test levels: what belongs where
5. Correctness of merging and state
6. Fault tolerance
7. The robot boundary
8. CI and release
9. Tooling, maintainability, cost and flakiness
10. Trade-offs
11. What we found
12. Release recommendation
13. Next steps

## 1. What we are protecting

OrderHub takes orders from customers and sends them to a robot that makes the food.
The worst things that can happen are:

- An order is lost. The customer paid and nothing gets made.
- An order is made twice. Food and robot time are wasted, and the kitchen falls behind.
- The wrong thing is made. A cancelled order gets made, items are missing or extra, or it is made at the wrong time.

From the spec, this gives two rules that most tests check:

1. No lost orders. Every order sent to OrderHub shows up exactly once.
2. Each order goes to the robot exactly once. A cancelled order never goes to the robot.

To check these rules, the test tools keep a list of every order they sent and what should
happen to it. After each test, that list is compared with:

- the orders OrderHub has (`GET /api/orders`)
- each order's history
- what the robot actually received

The load test uses the same check. So it tells us whether orders are still correct under
heavy traffic, not only how fast the system is.

## 2. Risk assessment

Impact:
- High: an order is lost, made twice, or the wrong food is made.
- Medium: wrong data or wrong status, but no wrong food.
- Low: cosmetic, or an inconvenience for operators.

| Risk | What the spec says | Impact | What we found |
| --- | --- | --- | --- | --- |
| The robot gets the same order twice | "dispatched to the robot exactly once" | High | L37-010, L37-025 |
| A delivery platform retries a webhook and a duplicate order is created | "the same request may arrive more than once" | High | Works, including 10 retries at once |
| Two platforms use the same `order_id`, and one of the orders is dropped or overwritten | "Each platform assigns its own `order_id`s" | High | L37-001, L37-002 |
| The partner API returns a 500 and the orders from that time are never picked up | "a retry of the same request succeeds. Nothing that happens upstream may be lost" | High | L37-005, L37-018 |
| A partner API update only includes some of an order's items, and the other items are lost | "A response only contains the items that changed" | High | L37-006 |
| Partner API cancel is handled wrong: cancelling one item cancels the whole order, or cancelling all items does not cancel it | "An order whose items are all `cancelled` is cancelled" | High | L37-007, L37-008, L37-009 |
| Uploading the same CSV again creates duplicates, or a real repeat order is skipped as "already seen" | "later uploads repeat earlier rows" and "Each row becomes one order" | High | L37-016, L37-021; re-uploads work |
| Survey orders are scheduled for the wrong time (time zone, `tomorrow`, meal hour) | Meal times are "in the kitchen's local time zone" | High | L37-013, L37-014, L37-015 |
| A cancelled order goes to the robot, or an order already sent to the robot gets marked cancelled | "A cancelled order is never dispatched" and a dispatched order "can no longer be cancelled" | High | L37-003, L37-011, L37-012 |
| Orders are lost when OrderHub restarts or crashes | "Nothing that happens upstream may be lost" | Medium | High | L37-024, L37-025 |
| Bad input (broken JSON, broken CSV, unexpected values) crashes a pipeline or creates junk orders | The assignment asks for resilience to malformed input | Medium | L37-004, L37-017 to L37-021, L37-022 |
| The system can't keep up with 100,000 requests a day in bursts: slow responses, timeouts, lost requests | "must handle 100,000 requests per day, arriving in bursts" | High | L37-010, L37-022, L37-023 |
| An order's history is missing changes | "Every change to an order is recorded as an event" | Medium | No separate tests; seen inside L37-001, L37-003, L37-012 |
| The operator UI shows the wrong status or cancels the wrong orders | Operators use the UI to watch and cancel orders | Medium | L37-026 to L37-029 |

### What to focus on first

1. Duplicates and lost orders. This matters most to the business, and it is hard to check by hand. It needs retries, 
   concurrency and forced failures, which is what test tools are good at.
2. Correct orders and status. Each rule in the spec becomes a test with a clear expected result.
3. Bad data and load. The assignment asks for both, and they are cheap to run once the tools to send orders exist.
4. Restart , history and UI.

## 3. Approach

- Black box testing, against the spec. Tests only use what a real user or system would
  use: the three ways orders come in, the API and UI to look at orders, and what goes out to
  the robot. When the system and the spec disagree, the spec is right and the test fails.
- Python, pytest and requests. Playwright for the few UI tests.
- One tool per way orders come in: webhook, CSV upload, and the partner API (through the mock's `/enqueue` and `/reset`). 
- Catch what goes to the robot. OrderHub can send robot orders to any URL (`-robot-url`). We point
  it at a small server of our own that records every order it receives. It can also be told to
  answer slowly or fail. This is how we test "exactly once" without a real robot.
- Wait for results, don't sleep. OrderHub picks up partner orders and sends orders to the robot
  in the background. Tests keep checking for the expected result until a time limit, so they
  are fast and not flaky.
- Every test makes its own data with unique ids and names, so tests don't affect each other or old data.

## 4. Test levels: what belongs where

| Level | What it's for here | Who and where |
| --- | --- | --- |
| Unit | Small rules with many cases: meal time in a time zone, splitting survey items, recognising a repeated survey row, merging partner item updates, allowed status changes. Many of the defects are one of these rules getting one case wrong. | The dev team, in Go, next to the code. I'd pair on the cases: the defect reports are a ready list. |
| Integration (API) | Most of our suite. A real OrderHub with its database, the mock partner API and our robot receiver. Each spec rule is a test: send something in, check what OrderHub stored and what the robot got. | `tests/test_webhook.py`, `test_partner_api.py`, `test_csv.py`, `test_dispatch.py`, `test_bad_data.py` |
| Contract | The two formats OrderHub doesn't own: what the partner API sends, and what the robot's cell controller expects. The mock and our robot receiver stand in for both, so the tests are only as right as they are. | Today: the mock (given) and the payload checks in the tests. Next: a written contract with both teams (section 7). |
| End to end | One order through each pipeline all the way to the robot, and the operator's view in the browser. | `tests/test_smoke.py` (one per pipeline), `tests/test_ui.py` (5 Playwright tests) |
| Performance and load | Bursty traffic at 1 to 10 times the expected peak, counting lost and duplicated orders, not just response times. Survey upload time as the export grows. | `tools/load.py`, `tools/csv_growth.py`, results in LOAD_RESULTS.md |
| Resilience | Things going wrong: partner 500s, a slow or failing robot, OrderHub stopped or crashed with work in progress, bad input. | `tests/test_restart.py`, plus the failure tests in the other files |

## 5. Correctness of merging and state

How we know the orders OrderHub ends up with are the right ones:

- Every test knows what it sent and checks three places: what OrderHub stored, the order's  history, and what the robot 
  received. An order is right only if all three agree with what was sent.
- Each pipeline has its own idea of "the same order", and most defects are there. A webhook order is the same order when 
  platform and `order_id` match (L37-001 and L37-002 show OrderHub ignores the platform). A partner order is 
  identified by its order number, and its items by item id (L37-006 shows an update replaces the items instead 
  of merging). A survey order has no id at all, only the row's content (L37-016 and L37-021 show where that goes wrong). 
  The tests for each pipeline send the cases where "same" and "different" are easy to confuse: retries,
  same id from two platforms, partial updates, re-uploads, near-identical rows.
- Status follows the spec's lifecycle: received, then scheduled or queued, then dispatched or cancelled, and nothing 
  after dispatched. Tests check the moves that must not happen: cancelled to dispatched (L37-012), dispatched to 
  cancelled (L37-007, L37-011), and a cancel that never lands (L37-003).
- Under load the same reconciliation runs for every order: `tools/load.py` compares the sent
  list, the stored orders and the robot's list order by order, and reports lost, stored twice,
  never made, and made more than once.

## 6. Fault tolerance

What happens when something goes wrong:

| Where | What goes wrong | Result |
| --- | --- | --- |
| Delivery platforms | The same webhook arrives twice, or 10 times at once | Correct: one order |
| Delivery platforms | A cancel arrives before its order | Cancel lost, order made (L37-003) |
| Partner API | A 500, which the spec says happens and succeeds on retry | Orders in that window lost (L37-005) |
| Partner API | One item OrderHub can't read | The whole response lost (L37-018) |
| Survey | Broken or unexpected files | Mostly handled; some rows or whole files silently lost (L37-019, L37-020, L37-021) |
| Survey | A slow or large upload | OrderHub crashes (L37-022) |
| Robot | Slow to accept orders | Orders built twice once a batch takes over a second (L37-010) |
| Robot | Rejects orders | Correct: retried until accepted |
| Robot | Unreachable, then OrderHub restarts | Correct: each waiting order sent once afterwards |
| OrderHub | Stopped for a deploy | Partner orders from the downtime lost (L37-024) |
| OrderHub | Crashes while sending to the robot | That order built twice (L37-025) |

Not tested: the database being full or locked, disk errors, the clock jumping (for example daylight saving), 
and a network that drops part of a request.

## 7. The robot boundary

The real robot isn't available, so OrderHub is pointed at our robot receiver instead
(`-robot-url`), which records every dispatch. That is where "exactly once" is checked. The
receiver can also be slow or reject orders, which is how L37-010 and L37-025 were found.

What the tests check about what the robot gets:

- Each order exactly once, and never a cancelled order.
- The right content: the items (with cancelled items left out, L37-009), names, notes, and special characters 
  (accents, emoji, quotes, commas, new lines) exactly as sent.
- The right time: survey orders only at their meal time (L37-013).
- Nothing for junk input: no empty orders (L37-004, L37-020 show they do reach the robot).
 
## 8. CI and release

In CI:

| When | What | Time |
| --- | --- | --- |
| Every pull request | `python -m pytest` (all 67 tests, including the UI tests) | About 3 minutes |
| Nightly | `python -m tools.load` at x1 and x2, `python -m tools.csv_growth`, fail if any order is lost or made twice | About 10 minutes |
| Before a release | `python -m tools.load --scale 5`, and a soak run once it exists | About 30 minutes |

The suite needs nothing outside the repository and the OrderHub build: each run starts its own
OrderHub, mock and robot receiver on a fresh database, and stops them at the end.

Known bugs don't turn CI red. Their tests are marked `xfail(strict=True)` with the defect id, so
the run stays green while the defect is open. When a fix makes a test pass, pytest reports it as
a failure (XPASS), and that's the reminder to remove the marker and close the defect.

## 9. Tooling, maintainability, cost and flakiness

- Language and tools: Python, pytest, requests and Playwright. They are common, so the team can read and extend the 
  tests without learning a framework, and they need no services beyond the OrderHub build.
- Maintainability: all the plumbing is in `harness/` (clients, order builders, robot receiver, starting OrderHub), 
  so tests read as the spec rule they check. New bad-data cases are new files in `data/corpus/`. 
  The code is kept small on purpose: nothing is added until a test uses it.
- Cost: the whole suite runs in about 3 minutes on a laptop. The slowest tests are the ones that have to wait for 
  OrderHub's own timers (the 2-second partner poll and the 1-second dispatcher).
- Flakiness: tests wait for a result up to a limit instead of sleeping. Proving that something did not happen 
  (no second dispatch) uses a short fixed quiet period of 3 dispatcher cycles. Every test uses its own ids, and every 
  run a fresh database. Timing-sensitive tests were run many times before being accepted (the concurrent upload test 
  reproduces 8 times in 8).
- Running against a real instance: with `QA_EXTERNAL=1` the tests run against your own `make run`, so a developer can 
  watch a failing test in the UI.

## 10. Trade-offs

- Depth over breadth. The pipelines that can lose or duplicate orders got most of the time; the UI got five tests, 
  history got none of its own.
- The load test runs the peak hour, not a whole day, on one machine. It answers "does it lose or duplicate orders at 
  and above the peak?", not "how does it behave after a week".
- The mock partner API only accepts valid JSON, so a partner sending broken JSON wasn't tested.
  A mock of our own would allow it; I kept the given one.
- A few defects need the harness to reproduce (L37-025 needs a crash at a precise moment), so their steps use a pytest 
  command instead of curl.

## 11. What found

29 defects: 7 Critical, 16 High, 6 Medium. The full reports, with steps, expected and actual results, evidence and 
severity, are in `defects/defects.xlsx`. The four UI defects also have screenshots in `defects/screenshots/`. 
27 defects have an automated test that fails while they are open. The other two, L37-022 and L37-023, are shown by 
`tools/csv_growth.py` instead, because a test for them would crash the OrderHub the other tests share.

They fall into six groups:

1. The wrong idea of "the same order": L37-001, L37-002, L37-006, L37-016, L37-021.
2. Skipped time windows in partner polling: L37-005, L37-018, L37-024.
3. Dispatch timing: L37-010, L37-012, L37-025.
4. Cancellation rules: L37-003, L37-007, L37-008, L37-009, L37-011.
5. The survey pipeline: scheduling (L37-013, L37-015), validation (L37-014, L37-019, L37-020),
   and performance (L37-022, L37-023).
6. The operator UI: L37-026 to L37-029.

| ID | Severity | Title |
| --- | --- | --- |
| L37-001 | Critical | Orders from two platforms with the same order_id become one order; the second order is lost |
| L37-005 | Critical | Orders in the same poll window as a partner API 500 are lost |
| L37-010 | Critical | Orders are sent to the robot more than once during a burst (100 orders became 194 builds) |
| L37-016 | Critical | The same survey export uploaded twice at the same time creates duplicate orders |
| L37-018 | Critical | One malformed item in a partner API response loses every order in that response |
| L37-022 | Critical | A survey upload that takes longer than 15 seconds makes OrderHub use all memory and crash |
| L37-024 | Critical | Partner orders placed while OrderHub is down are never fetched after it starts again |
| L37-002 | High | A cancel from one platform cancels another platform's order |
| L37-003 | High | A cancel that arrives before its order is dropped, and the order is made anyway |
| L37-004 | High | Webhooks with missing fields are accepted: an empty order reaches the robot and real orders are lost |
| L37-006 | High | A partner API update for some of an order's items removes the other items |
| L37-007 | High | Cancelling one item of a partner order cancels the whole order, even after it was made |
| L37-008 | High | A partner order that arrives with every item cancelled is made |
| L37-009 | High | Cancelled items of a partner order are sent to the robot |
| L37-011 | High | An order the robot is already building can be cancelled through the API |
| L37-012 | High | A cancel accepted while an order is waiting to be sent is undone, and the order is made |
| L37-013 | High | Survey meals are scheduled in UTC instead of the kitchen's time zone; -site-tz is ignored |
| L37-015 | High | Survey column tomorrow: TRUE, yes or an empty value are silently treated as today |
| L37-019 | High | An unterminated quote in a survey CSV silently drops every row after it |
| L37-020 | High | A survey CSV without the survey columns is accepted: an empty order is sent to the robot and the real orders are lost |
| L37-021 | High | A survey CSV with a byte order mark (Excel "CSV UTF-8") loses first names, and people with the same last name and order are merged |
| L37-023 | High | Survey upload time grows with every row ever uploaded: each doubling of the export makes it about 4 times slower |
| L37-027 | High | When a new order arrives, the tick moves to a different order, and Cancel selected cancels one that isn't ticked on screen |
| L37-014 | Medium | A survey row with an unknown meal is accepted and the order is made immediately |
| L37-017 | Medium | Webhooks with values outside the spec are accepted: unknown platform, negative total, no items |
| L37-025 | Medium | An order being sent to the robot when OrderHub crashes is sent again after it starts, so it is built twice |
| L37-026 | Medium | The Cancel selected button always shows (0), but still cancels the ticked orders |
| L37-028 | Medium | The status tab counts never change after the page loads |
| L37-029 | Medium | Make at shows the UTC time as if it were local time |

What works well, and is covered by passing tests: webhook retries, including 10 at once;
re-uploading the same survey export; quotes, commas and new lines in CSV fields; special
characters reaching the robot unchanged; rejecting broken JSON; a failing robot being retried;
orders waiting for the robot surviving a restart; and response times, which stay fast up to 5
times the expected load.

## 13. Next steps

With another day:

- A soak run: 100,000 orders spread over a compressed day, with the survey growing to its real
  size, watching memory and upload times.
- Cancels under load: cancels racing with dispatch at 5 times the peak (L37-012 suggests more).
- History checks: every change in the spec produces exactly one event, on the right order.
- Daylight saving: survey scheduling across the November change, once L37-013 is fixed.

With another week:

- The robot contract (section 7) as a schema checked on every dispatch, and a replay of recorded
  payloads against the controller's simulator.
- A mock partner API of our own that can send broken JSON, slow responses and timeouts, and a
  realistic id scheme for platforms (sequential ids per platform, which would show L37-001 at
  scale).
- Unit tests with the dev team for the rules behind the defects: time zones, survey row identity,
  partner item merging, status changes.
- CI as in section 8, with the load results tracked over time.
- UI tests for the order page and the survey upload button; a second browser.

What I'd ask the development team:

- Two identical survey rows in one export: one order or two? The spec says "each row becomes one
  order", but rows have no id, and re-uploads repeat rows on purpose.
- A cancel for an order OrderHub hasn't seen yet: should it be remembered, or answered with an
  error so the platform retries (L37-003)?
- Does the robot's cell controller ignore an `order_id` it has already built (L37-025)?
- Is there meant to be authentication on the webhook, the upload and the cancel API?
- Is an order with a total of 0 valid, for example a free replacement order?
- What is the largest survey export you expect, and how long should its upload take (L37-023)?
- Order ids skip numbers when a duplicate is sent (the duplicate uses up an id). Harmless, but
  worth knowing if anyone reads gaps in the ids as lost orders.
- Should the API give times with a time zone (L37-029)?
