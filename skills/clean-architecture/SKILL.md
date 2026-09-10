---
name: clean-architecture
description: Apply Clean Architecture boundaries when designing, structuring, refactoring, or reviewing the layout of application code — deciding which layer a class belongs in, whether to add an interface or repository, how data crosses a boundary, where a use case lives, or how to organise a new module or feature. Use when the user asks about architecture, layering, dependency direction, domain vs application vs infrastructure, DDD tactical patterns, vertical slices, CQRS structure, or whether an abstraction is worth adding. Includes a .NET/EF Core reference.
---

# Clean Architecture

Apply these as constraints, not suggestions. If a constraint blocks the task, say so and stop —
do not work around it.

## 1. The one rule

**Source dependencies point inward. Always.**

- An inner layer must never *name* a type, function, constant, or file from an outer layer.
- Control flow may go outward; compile-time dependency may not. Invert with an interface owned by the inner layer.
- If you need an exception, there is a modelling error. Report it. Do not add the reference.

## 2. Layer contract

| Layer | Owns | May reference | Banned | Tests |
|---|---|---|---|---|
| **Domain** | Entities, value objects, aggregates, invariants, domain events, domain errors | Language stdlib only | ORM attributes, DI, HTTP, JSON, logging, `DateTime.Now`, `Guid.NewGuid()`, config, any package | Pure unit tests, zero mocks |
| **Application** | Use cases, orchestration, port interfaces, authorization policy, transaction boundary | Domain | Controllers, HTTP types, concrete infrastructure classes | Unit tests with fakes |
| **Adapters** | Controllers, presenters, mappers, request/response DTOs, jobs, consumers | Application, Domain | Business rules of any kind | Thin; covered by integration tests |
| **Infrastructure** | ORM, HTTP clients, message bus, file system, clock, ID generation, secrets | Everything inward | Domain decisions | Integration tests against real dependencies |

**Naming test:** top-level folders name the business (`Invoicing/`, `Tenants/`, `Payroll/`), not the
framework (`Controllers/`, `Services/`, `Models/`).

## 3. Crossing boundaries

1. Only simple data crosses: primitives, records, DTOs. Never entities, ORM rows, or framework request objects.
2. The DTO is owned by the **inner** side. The outer side maps to it.
3. A DTO that mirrors an entity field-for-field with no transformation means the boundary is fake or the entity is anemic. Fix one.
4. Non-determinism is a port: time, randomness, environment, current user — injected, never called inline.
   ID generation is a port **when a test needs to control or assert on the value**. A surrogate key that
   nothing asserts on may be minted inline; injecting an `IIdGenerator` for it buys nothing and trips §4.2.
5. Expected failures are return values (`Result<T>`); exceptions are for genuinely exceptional states.
6. One transaction per use case. Never per repository call.

## 4. Pragmatism gates — when NOT to do this

Layering is a cost paid for changeability. Charge it only where change is expected.
Over-applied, it produces the same unmaintainable mess it was meant to prevent, with more files.

### 4.1 Skip the layers when
- The feature is CRUD with no invariants beyond "field is required".
- The module is under ~5 endpoints and owns no domain rule.

→ Use a **vertical slice**: one folder, one file per feature, endpoint → handler → data access.
Add boundaries when a real rule appears. Slices and layers coexist: layers define what may depend
on what, slices define where code lives.

### 4.2 Abstraction budget
An abstraction must earn its existence:

- **Interface with one implementation and no test-seam value → do not write it.** `IUserService`/`UserService` is the canonical slop signature.
- **Generic `IRepository<T>` over an ORM → do not write it.** `DbContext` is already Unit of Work + Repository. Use concrete, aggregate-shaped repositories only where an aggregate boundary must be protected.
- **"We might swap the database" is not a justification.** Name the actual second implementation or drop it.
- **A class that only forwards to the next layer → delete the layer, not the class.**

### 4.3 Duplication vs the wrong abstraction
Two similar pieces of code are not duplication until they must change together for the same
business reason. Wait for the third occurrence *and* a shared reason. Premature DRY across slices
couples features that should be independent.

## 5. .NET reference

**Projects:** `Domain` → `Application` → (`Infrastructure`, `Api`). `Domain` references nothing. `Api` composes.

- Enforce §1 mechanically with **NetArchTest** or **ArchUnitNET** as a failing test. See `arch-tests.md`.
- EF Core config lives in `Infrastructure` via `IEntityTypeConfiguration<T>`. No data annotations on domain entities.
- `DbContext` used directly in Application command/query handlers is acceptable and preferred over a generic repository.
- CQRS/MediatR is optional. Adopt it for the cross-cutting pipeline (validation, logging, transactions, authorization), not for fashion. Ten one-line pass-through handlers are a slop signal.
- `Result<T>` / `ErrorOr` for expected failures; exceptions for programmer errors and infrastructure faults. One global exception handler at the edge.
- Domain events raised in the aggregate, dispatched after `SaveChanges`, inside the write transaction when consistency requires it.
- `sealed` by default, `record` for DTOs and value objects, nullable reference types on, warnings as errors.
- Multi-tenancy: global query filters plus a scoped tenant accessor. Never per-query filtering by convention.
