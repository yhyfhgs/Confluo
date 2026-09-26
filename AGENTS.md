# Paper Crawler

`AGENTS.md` is the shared instruction source. This repository contains the crawler implementation and its design knowledge base. Read `README.md`, the document registry `docs/INDEX.md`, and current `docs/plan/progress.md`; consult the relevant design and `docs/plan/decision-log.md` for the task. Establish current capability from the implementation and verification evidence.

## Layout and design authority

- `src/paper_crawler/` contains Python implementation; `tests/` contains unit/contract/integration tests; `venues/<field>/<venue_id>.yaml` contains VenueSpec declarations.
- `docs/design/` defines the system, `docs/design/adapters/` defines platform behavior, and `docs/catalog/` records venue/platform inventories. Plans/ADRs belong in `docs/plan/`; external research in `docs/research/`; diagrams in `docs/diagrams/`; testing evidence in `docs/testing/`; session/phase records in `docs/logs/` and `docs/reports/`.
- Implement against approved or implemented designs. New documents start as draft; substantive approved-design changes return to review or receive a reasoned ADR. Superseding an architectural decision requires a new ADR naming the old one. Deprecated docs remain with replacement links.
- `docs/**/*.md` except INDEX/logs/reports requires title/status/owner/updated frontmatter. Status values are draft, review, approved, implemented, deprecated; see `docs/process/status-workflow.md`.
- Update the index for added/removed/renamed documents, FR-to-AC mappings in `docs/testing/acceptance-criteria.md` for changed requirements, and `docs/GLOSSARY.md` for new shared terminology. Update progress at milestones; keep durable work evidence in the existing log/report structure and use instruction files for stable rules.
- Designs specify function, implementation, test method/type and acceptance criteria. Cite and date verified endpoint/rate-limit facts; label unverified claims. Label design pseudocode. Project documentation remains Chinese with English identifiers and kebab-case filenames.

## Acquisition and local-state constraints

- Acquire papers through legitimate sources and authorized user credentials, following robots.txt/ToS and conservative adapter-specific rates with an identifying user agent. Keep downloads scoped to local personal research. Exclude paywall/CAPTCHA bypasses, impersonation, pirate sources and redistribution features.
- Keep credentials, cookies, sessions and downloaded PDFs in ignored local storage. Runtime config/state lives in ignored `.paper-crawler/`, selected through `PAPER_CRAWLER_HOME` (D-032).
- Protect `.paper-crawler` with `-e .paper-crawler` whenever an authorized cleanup uses `git clean -x`; this preserves credentials and databases even when Git ignore rules are bypassed.
- Core dependencies stay separate from optional auth/browser dependencies; preserve lazy imports and the documented capability/entry-point contracts. Run default tests offline. Browser tests use their explicit `PC_BROWSER_TESTS` gate.

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

`make check` is the commit gate. `pytest` defaults to excluding `online`; changing `-m` overrides that default. Report actual checks and skipped external/browser validation. Follow `docs/process/git-workflow.md` for Conventional Commits. Delegate bounded research with explicit output paths; the primary agent reviews evidence and owns final architecture/design decisions; select models according to the task.

Task entry points: new venues → `docs/catalog/README.md`; adapters → `docs/design/adapters/README.md`; pipeline → `docs/design/05-pipeline.md`; data model → `docs/design/06-data-model.md` plus ADR/migration implications.
