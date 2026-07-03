---
name: conventional-commit
description: Write and validate Conventional Commit messages for this HACS integration so release-drafter's autolabeler can pick the next semantic version. Use whenever committing — a non-conforming PR title means the wrong bump (or none).
---

# Conventional commit (release-drafter-aware)

release-drafter's autolabeler matches the **PR title** against Conventional
Commit prefixes to apply a label (`enhancement`, `fix`, `chore`), and the
version-resolver uses that label to pick the next **semantic version**. On
merge, a `sync-manifest-version` job writes the resolved version into
`custom_components/<domain>/manifest.json`. A title that doesn't match any
pattern falls back to a **patch** bump.

## Format

```
<type>(<scope>): <subject>
```

- **scope is optional.** This is a single integration, so scope does not route
  anything — use it only to name the area touched: `config-flow`, `sensor`,
  `coordinator`, `api`, `docs`, `ci`, `deps`.

## Types → release effect

| Type | Label | Effect |
|---|---|---|
| `feat` | `enhancement` | minor bump · "New Features" |
| `fix` / `perf` / `revert` | `fix` | patch bump · "Bug Fixes" |
| `chore` / `ci` / `docs` / `refactor` / `build` / `style` / `test` | `chore` | patch bump · "Maintenance" |
| no matching prefix | *(none)* | patch bump (version-resolver default) |

- There is no `major` tier configured — a breaking change still only bumps
  patch. Bump `major` by hand (edit the draft release's tag before
  publishing) if a change actually breaks something.

## Rules

- Imperative subject, ≤ ~72 chars, no trailing period.
- **Never** `--no-verify` / `--no-gpg-sign`; if a hook fails, fix the cause.
- **Don't hand-edit** `manifest.json` `version` in a feature commit — the
  `sync-manifest-version` CI job owns it.

## Output

- The proposed commit message in a code block.
