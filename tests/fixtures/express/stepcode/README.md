# stepcode EXPRESS fixtures (provenance)

75 EXPRESS schemas copied from **STEPcode**
(https://github.com/stepcode/stepcode — formerly NIST's STEP Class
Library), 3-clause BSD (see COPYING + INTENT.md upstream). Path
components flattened with `__`. Copied 2026-10-06 from the clone at
`~/proj/third_party/stepcode` (upstream last pushed 2026-09-28).

## Why vendor these

- They are the upstream project's own parser edge-case corpus
  (`test/unitary_schemas/`, `test/buggy/` regression schemas, data
  trees) — decades of accumulated syntax torture.
- 8,617 `WHERE` rule occurrences across the set: the design corpus for
  stepper's future WHERE-rule evaluator (directions.md item 4). When
  the evaluator lands, these files become its acceptance corpus.
- All 75 parse clean with `stepper.express.load_express` (verified
  2026-10-06; if any regresses, that's a stepper bug, not a fixture
  problem).

`test/buggy/` schemas upstream are intentionally-ill-formed negative
cases — those parse "successfully" here only until stepper grows
negative-case awareness; do not treat their parse as an endorsement of
their content.