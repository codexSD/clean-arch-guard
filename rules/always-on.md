# Architecture rules (always on)

- Dependencies point inward only: Domain <- Application <- Adapters <- Infrastructure.
  Domain references nothing. Inner layers never name outer-layer types.
- Only DTOs and primitives cross boundaries. Never entities, ORM rows, or HTTP types.
- Time, randomness, current user are injected ports, never called inline. Same for ID generation
  *when a test asserts on the value*; a surrogate key nothing asserts on may be minted inline.
- Expected failures are Result values; exceptions are for exceptional states.
- Folders are named after the business, not the framework.

# Abstraction budget

- No interface with one implementation and no test-seam reason.
- No generic repository over the ORM. No pass-through layers.
- Duplicate until the third occurrence AND a shared reason to change.
- Small CRUD modules: vertical slice, no layers. Add boundaries when a real rule appears.

# Code shape

- Nesting depth 3 max, 2 preferred. Invert conditions and return early; guard clauses
  before the happy path. Extract, do not indent. Counts control flow only — declarative
  configuration (ORM mapping, DI registration, validation rules) nests by nature.
- Long if-else chains become lookup tables or polymorphism, not more branches.
- Static is only acceptable when the method holds no state of its own. Receiving a collaborator
  as an explicit parameter is fine and often clearer — doing IO *through* one is not the problem.
  The moment it reaches for time, IO, config, tenant context, or mutable state that the caller
  did not hand it, it becomes an injectable class. Within one slice, pick one shape and match it.
- No mutable static state. Ever.
- No Helper / Util / Manager class as a home for logic that had nowhere else to go.
  If it has no home, the model is wrong — say so.

# Anti-slop

- Search the repo before writing anything new; say what you found.
- Plan first: intent, files touched, what you are NOT doing. Wait for confirmation.
- Change one thing. No drive-by refactors, renames, or reformatting.
- No new dependency without approval and an existence check.
- No invented APIs. If unsure a method exists, say so.
- Delete dead code; never keep it "for compatibility".
- No placeholder stubs presented as finished work.
- Tests must fail if the business rule is inverted. No mock-call assertions.
- Match existing codebase patterns over your own defaults.
- Secrets never in client code, committed config, or logs. Authorization server-side.
  Parameterized queries only.

For the full layer contract, pragmatism gates, and .NET reference, use the `clean-architecture` skill.
Before commit or PR, run the `clean-arch-guard:slop-reviewer` subagent on the diff.
