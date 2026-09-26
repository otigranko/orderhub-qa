# OrderHub Test Strategy

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

Likelihood is my estimate of how easy it is to get the feature wrong. Retries,
concurrency, partial updates and time zones are where bugs usually are.

| ID | Risk | What the spec says | Likelihood | Impact |
| --- | --- | --- | --- | --- |
| R1 | The robot gets the same order twice | "dispatched to the robot exactly once" | Medium | High |
| R2 | A delivery platform retries a webhook and a duplicate order is created | "the same request may arrive more than once" | Medium | High |
| R3 | Two platforms use the same `order_id`, and one of the orders is dropped or overwritten | "Each platform assigns its own `order_id`s" | Medium | High |
| R4 | The partner API returns a 500 and the orders from that time are never picked up | "a retry of the same request succeeds. Nothing that happens upstream may be lost" | Medium | High |
| R5 | A partner API update only includes some of an order's items, and the other items are lost | "A response only contains the items that changed" | High | High |
| R6 | Partner API cancel is handled wrong: cancelling one item cancels the whole order, or cancelling all items does not cancel it | "An order whose items are all `cancelled` is cancelled" | Medium | High |
| R7 | Uploading the same CSV again creates duplicates, or a real repeat order is skipped as "already seen" | "later uploads repeat earlier rows" and "Each row becomes one order" | High | High |
| R8 | Survey orders are scheduled for the wrong time (time zone, `tomorrow`, meal hour) | Meal times are "in the kitchen's local time zone" | High | High |
| R9 | A cancelled order goes to the robot, or an order already sent to the robot gets marked cancelled | "A cancelled order is never dispatched" and a dispatched order "can no longer be cancelled" | Medium | High |
| R10 | Orders are lost when OrderHub restarts or crashes | "Nothing that happens upstream may be lost" | Medium | High |
| R11 | Bad input (broken JSON, broken CSV, unexpected values) crashes a pipeline or creates junk orders | The assignment asks for resilience to malformed input | High | Medium |
| R12 | The system can't keep up with 100,000 requests a day in bursts: slow responses, timeouts, lost requests | "must handle 100,000 requests per day, arriving in bursts" | Medium | High |
| R13 | An order's history is missing changes | "Every change to an order is recorded as an event" | Medium | Medium |
| R14 | The operator UI shows the wrong status or cancels the wrong orders | Operators use the UI to watch and cancel orders | Low | Medium |

### What to focus on first

1. Duplicates and lost orders (R1 to R4, R7). This matters most to the business, and it is hard
   to check by hand. It needs retries, concurrency and forced failures,
   which is what test tools are good at.
2. Correct orders and status (R5, R6, R8, R9). Each rule in the spec becomes a test with a clear
   expected result.
3. Bad data (R11) and load (R12). The assignment asks for both, and they are cheap to run once
   the tools to send orders exist.
4. Restart (R10), history (R13) and UI (R14). A few focused tests now, more in next steps.

## 3. Approach

- Black box testing, against the spec. Tests only use what a real user or system would
  use: the three ways orders come in, the API and UI to look at orders, and what goes out to
  the robot. When the system and the spec disagree, the spec is right and the test fails.
- Python, pytest and requests. Widely known, cheap to run, and easy for the team to add to.
- One tool per way orders come in: webhook, CSV upload, and the partner API (through the mock's
  `/enqueue`). Adding a new test case means adding data, not writing new plumbing.
- Catch what goes to the robot. OrderHub can send robot orders to any URL (`-robot-url`). We point
  it at a small server of our own that records every order it receives. It can also be told to
  answer slowly or fail. This is how we test "exactly once" without a real robot.
- Wait for results, don't sleep. OrderHub picks up partner orders and sends orders to the robot
  in the background. Tests keep checking for the expected result until a time limit, so they
  are fast and not flaky.
- Every test makes its own data with unique ids and names, so tests don't affect each other or
  old data.
