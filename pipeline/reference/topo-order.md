# Reference — dependency ordering

> Single source of truth for the order in which `analyze-sprint` and `execute-sprint` walk a
> sprint's stories. Both skills cite this file; neither restates the algorithm.

Within a sprint, process stories **dependency-first**: topologically sort by the
`dependencies:` graph so a story is reached only after every story it depends on. Break ties by
**topic, then sequence number** (i.e. INDEX order).

## Cycle handling differs by stage

- **analyze-sprint** (read-mostly): a within-sprint dependency **cycle** → report it, suggest
  `/manage-stories lint`, and **fall back to INDEX order**. Analysis tolerates an imperfect
  order because it doesn't build on prior output.
- **execute-sprint** (builds on prior output): a within-sprint dependency **cycle is a hard
  blocker → halt**. Never fall back to INDEX order at build time — building in an order that
  violates declared dependencies (a story before the foundation it needs) defeats the purpose
  of the dispatch loop. Route to `/manage-stories lint` to break the cycle first.

## Cross-sprint dependencies

A dependency that lives in an **earlier sprint and isn't `done`** is a hard blocker for the
dependent story — you can't build on a foundation that isn't there. `execute-sprint` catches
this before dispatch (build the earlier sprint first).
