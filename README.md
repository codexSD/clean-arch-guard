# clean-arch-guard

Clean Architecture boundaries, an anti-slop review gate, and a C# complexity guard, packaged as a
Claude Code plugin so it travels across projects and versions in one place.

## What's in it

| Component | Fires | Job |
|---|---|---|
| `rules/always-on.md` via `scripts/inject-rules.py` on SessionStart | Every session | Cheap, always-present constraints while code is being written |
| `skills/clean-architecture/` | On demand, when structuring code | Layer contract, pragmatism gates, .NET/EF Core reference |
| `agents/slop-reviewer.md` | On demand, after code is written | Reviews a diff in a fresh context for slop and boundary violations |
| `scripts/complexity-guard.py` via PostToolUse hook | Every `.cs` write or edit | Nesting, method size, params, impure statics, fake async |

The split is deliberate. Rules that must be present while writing have to be short or they eat the
context they are meant to protect. Review is a different job with a different context window — the
agent that wrote the code is the worst reviewer of it. And structural limits belong in a hook, not
a prompt: prompt rules degrade over a long session, a hook fires every time.

## Requirements

`python3` on `PATH` — both hooks run through it. There is no shell dependency, so the same plugin
works on Windows, macOS, Linux, and in cloud sessions. On a Windows box where only `python.exe`
exists, either install Python from python.org 3.13+ (it ships `python3.exe`) or drop a
`python3.bat` containing `@py -3 %*` somewhere on `PATH`.

## Install

Try it in one project first, without installing anything:

```bash
claude --plugin-dir /path/to/clean-arch-guard
```

This repo is its own marketplace — `.claude-plugin/marketplace.json` sits at the root. Register it
once per machine, then install:

```bash
claude plugin marketplace add codexSD/clean-arch-guard
claude plugin install clean-arch-guard@clean-arch-guard-local            # all your projects
claude plugin install clean-arch-guard@clean-arch-guard-local -s project # commit it for the team
```

`--scope user` (the default) enables it everywhere you work. `--scope project` writes to
`.claude/settings.json`, so everyone who clones that repo gets it.

### Cloud sessions

A cloud session starts from a fresh container and sees none of your local config, so user-scope
installs do not travel. Commit the marketplace and the enable flag into the target repo's
`.claude/settings.json` and the session bootstraps the plugin itself:

```json
{
  "extraKnownMarketplaces": {
    "clean-arch-guard-local": {
      "source": { "source": "github", "repo": "codexSD/clean-arch-guard" }
    }
  },
  "enabledPlugins": { "clean-arch-guard@clean-arch-guard-local": true }
}
```

Same file works for teammates on their laptops, so project scope is worth using even when you
already have it at user scope.

Verify:

```bash
claude plugin validate ./clean-arch-guard --strict   # before publishing
claude plugin list                                   # after installing
claude plugin details clean-arch-guard               # component inventory + token cost
claude --debug                                       # if something isn't loading
```

## Use

**Rules** apply on their own at session start. Nothing to invoke. Opt a repo out with an empty
`.no-arch-guard` file at its root.

**Skill** loads itself when you ask an architecture question. Force it with `/clean-architecture`.

**Reviewer** — before a commit or PR:

```
@clean-arch-guard:slop-reviewer review the staged diff
```

It reports and does not edit; `Write` and `Edit` are disallowed for it by design.

**Complexity guard** runs automatically on every `.cs` write. `PostToolUse` is an observe-only
event, so exit 2 does not undo the write — it surfaces the findings to Claude, which then has to
fix them before moving on. Defaults, overridable per project via environment variable:

| Variable | Default |
|---|---|
| `CAG_MAX_NESTING` | 3 |
| `CAG_MAX_METHOD_LINES` | 40 |
| `CAG_MAX_PARAMS` | 4 |
| `CAG_MAX_FILE_LINES` | 400 |
| `CAG_TEST_STRICT` | unset |

`CAG_MAX_PARAMS` counts **data** parameters only. Injected collaborators — an interface, a
`DbContext`, `CancellationToken`, `HttpContext`, anything marked `[FromServices]` — are the
dependency graph, not arguments a caller assembles, so a minimal-API handler with eight injected
parameters is not a finding. Nine query-string filters still is.

Test files (under `tests/`, or named `*Tests.cs`) are exempt from file length and the static-purity
checks: a long fixture and a static test-data holder that mints a `Guid` are correct in test code.
Set `CAG_TEST_STRICT=1` to check them like production code.

It skips `obj/`, `bin/`, `Migrations/`, `*.g.cs`, and `*.Designer.cs`, on both path separators.
Test it by hand:

```bash
echo '{"tool_name":"Write","tool_input":{"file_path":"src/Foo.cs"}}' \
  | python3 scripts/complexity-guard.py
```

The regression suite covers the parser's known traps — expression-bodied
members, anonymous objects in argument lists, generic methods, primary constructors, `await` inside
a string or comment:

```bash
python3 tests/test_complexity_guard.py
```

## Versioning

`plugin.json` pins an explicit `version`, so installs move only when you bump it and run
`claude plugin update clean-arch-guard`. If you would rather have every push land in every project
immediately, delete the `version` field — the version then resolves to the source commit SHA.

## Other agents

Claude Code reads `CLAUDE.md`, not `AGENTS.md`. For a repo shared with Cursor or Copilot, copy
`rules/always-on.md` into the repo as `AGENTS.md` and make `CLAUDE.md` one line:

```
@AGENTS.md
```

## Real enforcement

The hook covers the agent's own writes. It does not cover a teammate's hand-written code, and it
is not a build gate. Put the boundary rules in CI too —
`skills/clean-architecture/arch-tests.md` has a NetArchTest suite that fails the build on a
dependency-rule violation. Add `SonarAnalyzer.CSharp` with warnings-as-errors for cognitive
complexity across the whole solution, not just new files.

## Maintaining it

Add a rule only after a real mistake — scar tissue, not aspiration. Aspirational rules get ignored
and dilute the ones that matter. Delete rules the team stopped enforcing. Every line in
`rules/always-on.md` costs context in every session; if it isn't load-bearing, cut it.
