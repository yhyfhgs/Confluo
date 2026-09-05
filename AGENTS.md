# Paper Crawler

`AGENTS.md` is the shared instruction source; `CLAUDE.md` imports it. This repository contains the crawler implementation and its design knowledge base. Read `README.md`, the document registry `docs/INDEX.md`, and current `docs/plan/progress.md`; consult the relevant design and `docs/plan/decision-log.md` for the task. Historical phase labels are not evidence of current capability.

## Layout and design authority

- `src/paper_crawler/` contains Python implementation; `tests/` contains unit/contract/integration tests; `venues/<field>/<venue_id>.yaml` contains VenueSpec declarations.
- `docs/design/` defines the system, `docs/design/adapters/` defines platform behavior, and `docs/catalog/` records venue/platform inventories. Plans/ADRs belong in `docs/plan/`; external research in `docs/research/`; diagrams in `docs/diagrams/`; testing evidence in `docs/testing/`; session/phase records in `docs/logs/` and `docs/reports/`.
- Implement against approved or implemented designs. New documents start as draft; substantive approved-design changes return to review or receive a reasoned ADR. Superseding an architectural decision requires a new ADR naming the old one. Deprecated docs remain with replacement links.
- `docs/**/*.md` except INDEX/logs/reports requires title/status/owner/updated frontmatter. Status values are draft, review, approved, implemented, deprecated; see `docs/process/status-workflow.md`.
- Update the index for added/removed/renamed documents, FR-to-AC mappings in `docs/testing/acceptance-criteria.md` for changed requirements, and `docs/GLOSSARY.md` for new shared terminology. Update progress at milestones; keep durable work evidence in the existing log/report structure rather than duplicating status in instruction files.
- Designs specify function, implementation, test method/type and acceptance criteria. Cite and date verified endpoint/rate-limit facts; label unverified claims. Label design pseudocode. Project documentation remains Chinese with English identifiers and kebab-case filenames.

## Acquisition and local-state constraints

- Use authorized user credentials. Do not add paywall/CAPTCHA bypasses, impersonation, pirate sources or redistribution features. Follow robots.txt/ToS and conservative adapter-specific rates with an identifying user agent; downloads are for local personal research.
- Credentials, cookies, sessions and downloaded PDFs never enter Git. Runtime config/state lives in ignored `.paper-crawler/`, selected through `PAPER_CRAWLER_HOME` (D-032).
- Never run bare `git clean -fdx`; a necessary clean must protect `.paper-crawler` with `-e .paper-crawler`, since `-x` ignores Git ignore rules.
- Core dependencies stay separate from optional auth/browser dependencies; preserve lazy imports and the documented capability/entry-point contracts. Default tests make no real network requests. Browser tests use their explicit `PC_BROWSER_TESTS` gate.

## Commands and validation

Python >=3.12; uv/hatchling, Ruff (100 columns), strict mypy. Use existing targets:

```bash
uv sync --extra auth
make check                 # sync-dev, lint/format-check, mypy, offline tests
make test                  # unit/contract/integration; 80% coverage gate
uv run crawler --help
# Explicit online validation only; requires PAPER_CRAWLER_CONTACT_EMAIL:
make smoke
```

`make check` is the commit gate. `pytest` defaults to excluding `online`; changing `-m` overrides that default. Report actual checks and skipped external/browser validation. Follow `docs/process/git-workflow.md` for Conventional Commits. Delegate bounded research with explicit output paths; the primary agent reviews evidence and owns final architecture/design decisions, without hardcoded model names.

Task entry points: new venues → `docs/catalog/README.md`; adapters → `docs/design/adapters/README.md`; pipeline → `docs/design/05-pipeline.md`; data model → `docs/design/06-data-model.md` plus ADR/migration implications.
