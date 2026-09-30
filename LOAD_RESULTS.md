# Load results

The question behind these runs is the same one as the rest of the testing: under realistic,
bursty traffic, does every order reach the robot exactly once, and is any order lost?

Short answer: at the expected peak of 100,000 orders a day every webhook order was made exactly
once, but OrderHub has no headroom. The same daily volume in slightly bigger bursts, or twice
the volume, makes the robot build orders twice, and at 5 to 10 times the load most orders are
built several times. Partner orders are lost at every load. And a single large survey upload
can crash OrderHub completely.

## How to run it

Both tools start their own OrderHub, mock partner API and robot receiver, like the tests, so
the counts are exact and your `make run` is not touched.

```sh
python -m tools.load                    # the peak hour of 100,000 orders a day, for 3 minutes
python -m tools.load --scale 5          # five times that
python -m tools.load --burst-every 10   # the same orders, in bigger bursts
python -m tools.csv_growth              # how survey upload time grows through the day
```

"Their own OrderHub" is the same two programs `make run` starts, `bin/orderhub` and
`bin/mockapi`, started a second time with different settings (see `harness/services.py`).
It's not a container, just ordinary processes that don't share ports or files with yours:

| | `make run` | Tests and load tools |
| --- | --- | --- |
| Programs | `bin/orderhub`, `bin/mockapi` | the same two files |
| OrderHub port | 8080 | 18080 |
| Mock partner API port | 8090 | 18090 |
| Database | `orderhub/data/orderhub.db` | `orderhub-qa/results/orderhub.db`, deleted at each start |
| Robot | writes to `data/robot_dispatch.jsonl` | posts to our robot receiver on 18181 (`-robot-url`) |
| Stopped by | you, with Ctrl-C | the script, when it finishes |

The code is identical, so a bug found in one is in the other. What they do share is the
machine's memory and CPU.

## Traffic model

Running a full day takes a day, and the risks are at the busiest moments, so the load test
runs the peak hour instead of the whole day.

| Assumption | Value | Why |
| --- | --- | --- |
| Share of the day in the peak hour | 15% | Food orders cluster around lunch and dinner. 100,000 a day gives about 4 orders a second at the peak. |
| How orders arrive | a burst every 5 seconds | The spec says traffic is bursty. `--burst-every` changes this. |
| Pipelines | 80% webhook, 20% partner API | Webhooks are the main live channel. The survey is separate (below). |
| Retries | 5% of webhook requests sent twice | "Platforms retry on failure, so the same request may arrive more than once." |
| Partner API failures | one 500 a minute | "The API sometimes fails with a 500." |
| Survey | whole export uploaded every 30 s, 50 new rows each time | "Each export contains every response so far." |
| Robot | 30 ms to accept each order | OrderHub's own simulated robot takes 15 to 40 ms, "similar to the real controller's ack time". |

Every order has a unique id, so a duplicate can only come from OrderHub itself. After the run
the tool waits until OrderHub has stopped storing and dispatching, then compares three lists:
what was sent, what OrderHub stored, and what the robot received.

## Results

Each run lasted 3 minutes, on a small test machine: 2 cores, 8 GB of memory, Linux. OrderHub was
built from the repository, with SQLite, and everything ran on the same machine. The x5 run and
the survey growth were repeated on a laptop four times its size (below).

| Run | Burst | Orders | Webhook response p50 / p95 / max | Lost (all partner) | Made more than once | Extra robot builds |
| --- | --- | --- | --- | --- | --- | --- |
| 100,000 a day | 21 every 5 s | 756 | 11 / 21 / 39 ms | 12 of 144 | 0 | 0 |
| 100,000 a day, bigger bursts | 42 every 10 s | 756 | 16 / 36 / 57 ms | 24 of 144 | 54 | 54 |
| x2 (200,000 a day) | 42 every 5 s | 1,512 | 20 / 42 / 72 ms | 24 of 288 | 108 | 108 |
| x5 (500,000 a day) | 104 every 5 s | 3,744 | 54 / 155 / 255 ms | 63 of 756 | 2,407 of 3,681 | 3,313 |
| x10 (1,000,000 a day) | 208 every 5 s | 7,488 | 276 / 1,014 / 1,405 ms | 126 of 1,512 | 7,315 of 7,362 | 50,221 |

In every run, every webhook request was accepted, no order was stored twice, and every stored
order reached the robot at least once. Survey rows were all stored once; they are scheduled for
tomorrow, so they are not part of the robot counts.

Survey upload time, from `tools.csv_growth` (each upload is the whole export so far). "No
answer" means no response in 30 seconds, while OrderHub's memory grows until it is killed:

| Export size | Test machine | Laptop |
| --- | --- | --- |
| 500 rows | 0.7 s | 0.5 s |
| 1,000 rows | 2.6 s | 1.5 s |
| 1,500 rows | 5.7 s | 3.3 s |
| 2,000 rows | 10.2 s | 5.8 s |
| 2,500 rows | no answer | 9.6 s |
| 3,000 rows | | 13.8 s |
| 3,500 rows | | no answer |

### The same runs on a bigger machine

To check that the results aren't caused by the small test machine, the x5 run and the survey
growth were repeated on a laptop with an Intel Core i9-9980HK (8 cores, 16 threads) and 32 GB of
memory, running macOS.

| x5 run (500,000 orders a day) | Test machine (2 cores, 8 GB) | Laptop (16 threads, 32 GB) |
| --- | --- | --- |
| Orders made more than once | 2,407 of 3,681 | 2,652 of 3,681 |
| Extra robot builds | 3,313 | 3,950 |
| Partner orders lost | 63 of 756 | 63 of 756 |
| Webhook response p50 / p95 / max | 54 / 155 / 255 ms | 54 / 108 / 225 ms |
| Survey export with no answer | 2,500 rows | 3,500 rows |

With four times the cores and memory, the laptop made just as many duplicates (slightly more)
and lost exactly the same partner orders. What got better was the timings: faster responses,
faster uploads, and the survey crash moved from 2,500 to 3,500 rows. On both machines, doubling
the export made the upload about 4 times slower.

## What it means

1. Orders are built more than once as soon as about 34 orders are waiting at the same time
   (L37-010). With a 30 ms robot, 34 orders take more than a second to send, and the dispatcher
   starts again every second without waiting, so the next round sends the same orders again.
   At the expected peak this happens to stay just under the line, but the same 100,000 orders a
   day arriving in bursts every 10 seconds instead of every 5 already crosses it. Doubling the
   volume crosses it too. At 10 times the load almost every order was built about 8 times. This
   is the answer to "how do you know no order is duplicated": the counts above, per order, from
   the robot's side.

2. Partner orders are lost at every load (L37-005). One 500 a minute lost 1 in 12 partner orders,
   because every partner order in the poll window of the failed request is skipped for good.
   The number is high here because the bursts put many orders in one window; spread evenly it
   would be about 1 in 30. It never reaches zero while the partner API has any failures.

3. Taking orders in is not the bottleneck. Webhook responses stayed fast up to 5 times the
   load and only reached a second at 10 times. The problems are behind the API: dispatch and
   polling.

4. The survey is the biggest risk (L37-022, L37-023). Upload time grows much faster than the
   export: four times the rows took 15 times as long. Once an upload takes more than about 15
   seconds it never finishes: OrderHub's memory grows until it is killed, which stops every
   pipeline. Health checks pass until the end. That happens at about 2,500 survey rows on the
   test machine and 3,500 on the laptop, and exports only ever grow. The first sign was not
   in the survey counts at all: during an earlier run with large uploads, the mock partner API
   timed out because OrderHub was using all the memory and CPU.

## What these runs don't show

- A whole day. A long run at normal load (a soak test) would show slow growth: the database,
  memory, and survey uploads as the day goes on.
- Production hardware. Both machines are far below a production server. That changes the
  timings: response times, and the survey size at which uploads pass 15 seconds, would be better
  on real hardware. It doesn't change the findings, as the laptop run shows: duplicates depend on
  the robot's speed and the dispatcher's 1-second cycle, not on the machine, and in L37-022
  memory grows without limit, so more memory only means OrderHub takes longer to fail.
- Cancels under load. A cancel racing with dispatch is already known to be lost (L37-012); under
  load there are more races.
- Colliding order ids. Here every platform's ids are unique. Real platforms number their own
  orders, so the same id from two platforms (L37-001) would lose orders at any load.
- Restarts. What happens to partner orders while OrderHub is down, for example after the survey
  crash, is the next test (step 11).

## Next steps

- Run `tools.load` in CI on every change that touches ingest or dispatch, at x1 and x2, and fail
  the build if any order is lost or made more than once.
- Repeat the x1 and x5 runs after the L37-010 and L37-005 fixes. The target is zero lost and zero
  extra builds up to at least 5 times the expected peak.
- Add a soak run: 100,000 orders spread over a compressed day, with the survey growing to its
  real size.
