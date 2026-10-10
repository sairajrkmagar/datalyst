# The final gate: how to run it and how to read it

One command runs every layer of testing and writes a report you can send:

```
python final_gate.py            # standard: about 30 minutes, no AI needed
python final_gate.py quick      # about 10 minutes
python final_gate.py full       # several hours: real AI, bigger fuzzing, long robot runs, big mutation audit
```

Close other heavy apps first (the performance layer measures time). Keep Ollama OFF for `standard`
(the gate uses a stand-in AI); `full` needs Ollama running with both models.

## The layers

| Layer | What it does | Why it matters |
|---|---|---|
| static | every file compiles, no undefined names, project files up to date, packages consistent | catches a missing or broken file before a user does |
| suite | the whole existing test suite (1,300-question catalogue, simulated AI mistakes, dashboards, reports ...) | the correctness of every answer |
| security | hostile text through every display function, exports (Excel formulas, web page), malicious AI plans, code scan | nothing typed into a file can run as code |
| file fuzz | thousands of corrupted files and memory bombs | a damaged or hostile file gives a polite message, never a crash |
| metamorphic | shuffle, double, scale, rename the data: answers must change exactly as mathematics requires | catches wrong numbers without knowing the right answer |
| upload flow | a real browser uploads a file in the sidebar, presses Clean it for me, and checks the result stays on screen (skipped if `playwright` is not installed) | the bug found while recording the demo can never come back |
| cleaning | random messy tables: cleaning must obey its rules (never adds rows, twice = once ...) | the Clean page can be trusted |
| performance | time and memory budgets on 100,000 rows (500,000 in `full`) | stays fast on big files |
| robot | a robot clicks the real app at random, with hostile text, on many different files | no sequence of clicks can crash the app |
| mutation | deliberate bugs injected into the code: do the tests notice? | measures how strong the tests really are |

## Reading the report (`final_gate_report.txt`)

- Every line says PASS or FAIL with the numbers. At the bottom: **ALL LAYERS PASSED**, or the layers that need attention with the last lines of their output.
- The mutation audit lists "survivors": deliberate bugs the tests did not notice. Some are harmless (changing a limit by one byte changes nothing). A survivor that changes behaviour is a gap in the tests and becomes a new test.

## Honest limits

- A passing gate means these attacks found nothing. It does not prove nothing exists: real users will do things nobody imagined. The feedback buttons in the app are how those get found.
- `standard` uses a stand-in for the AI. Only `python run_all_tests.py full --fresh` (or `final_gate.py full`) tests your real AI.
