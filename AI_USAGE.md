# How I used AI

I used Claude (Anthropic) throughout this assignment, in the Claude desktop app connected to
my project folder.

I haven't included the full session transcript. This page summarizes how I used AI and what I
decided, and I'm happy to walk through the session in the interview.

## Start

- Present tech stack: Python, Pytest, requests + UI tests

## What Claude did

- Read QA_HOMEWORK.md, the OrderHub README and the job description, and proposed a first
  strategy built around two rules: no lost orders, and every order reaches the robot exactly once.
- Wrote the first drafts of the harness, the tests, TEST_STRATEGY.md and the defect reports.
- Read the OrderHub source code (Go) and listed suspected bugs. I don't work in Go, so
  these were only leads to test.
- Reproduced suspected bugs through the API and captured the evidence: HTTP responses,
  order history, robot dispatches and OrderHub logs.

## What I decided

- The spec is the source of truth. Where the implementation behaves differently, the
  implementation is wrong. For example, the spec only promises that the order list returns
  50 orders by default, so the harness pages through all orders instead of relying on one
  request with a very large `limit`.
- Reading the source only produces leads. A bug is reported only after it reproduces through
  the API or UI, with steps a developer can run using nothing but `curl`.
- The code stays small enough for me to explain every line. I removed type hints,
  docstrings, and any helper or method that no test used yet. Each step adds only what its
  tests need.
- A system handed over for testing has bugs, so the focus moved early from building tools to
  finding them.
- I questioned whether the robot receiver was needed. I kept it because the assignment asks for
  a way to capture what is sent to the robot, and a file can't simulate a slow or failing robot.
- The defect format: one spreadsheet, `defects/defects.xlsx`, with IDs `L37-001` and up, and
  the columns I chose.
- Suggested ability to tests (failed tests specifically) to run against localhost:8080 (make run). 
  This way don't have to curl but can run tests against local and watch queue

## Suggestions from Claude that I kept

- Tests for known bugs stay in the suite, marked `xfail(strict=True)` with the defect ID. The
  run stays green while bugs are open, and a fixed bug shows up automatically.
- Each test run starts its own OrderHub on a fresh database, on separate ports, so results
  don't depend on old data.
- Tests wait for a result with a time limit instead of sleeping a fixed time.

## How I checked the AI's work

- Ran each step's tests on my own machine before committing.
- Asked for an explanation of every piece of code I didn't understand, and removed what I
  couldn't justify.
- Checked that each defect's steps reproduce against `make run`.

## Log by step

| Step | What | Commit |
| --- | --- | --- |
| 1 | Harness skeleton, API clients, smoke test per pipeline | Initial commit, smoke tests + config |
| 2 | Test strategy draft: what we protect, risks R1 to R14, approach | Add test strategy |
| 3 | Tests start their own OrderHub; robot receiver checks exactly-once dispatch | Add server to run with tests |
| 4 | Webhook tests; defects L37-001 to L37-004 | Add defects, add test |
| 5 | Partner API tests; defects L37-005 to L37-009 | Partner API tests and defects L37-005 to L37-009 |
| 6 | Dispatch tests with a slow or failing robot; defects L37-010 to L37-012 | Dispatch tests and defects L37-010 to L37-012 |
