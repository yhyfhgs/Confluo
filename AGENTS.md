# Paper Crawler

`AGENTS.md` is the shared instruction source. The repository is at the start of the v2 restart: `main` holds the v2 research, the v2 design and implementation plan, and the interaction demo, and has no implementation yet. The complete v1 implementation (Python CLI, tests, VenueSpecs, configs and all v1 design documents) is archived on branch `archive/v1` (tag `v1-final`); read it with `git show archive/v1:<path>` or a separate worktree, and treat it as reference material and a source of reusable adapters, not as the current system. Read `README.md`, the document registry `docs/INDEX.md`, current `docs/plan/progress.md` and `docs/plan/v2/README.md`; `docs/plan/v2/00-design-brief.md` holds the primary agent's architecture rulings, where §11 overrides §10 and §10 overrides earlier text and the design documents.

## Layout and design authority

- `docs/survey/` holds v2 external research, one document per topic with a same-name folder of raw-data attachments. `docs/plan/v2/` holds the v2 plan package: the brief, designs 01–08, the roadmap 09, ADR drafts, the design process record and `demo/`. `docs/catalog/source-directory.md` is the supported-source directory. `docs/plan/decision-log.md` is the ADR log: D-001…D-039 are v1 history and D-040 onward are v2 proposals. Diagrams go in `docs/diagrams/`, workflow rules in `docs/process/`, session records in `docs/logs/` and milestone reports in `docs/reports/`. `docs/archive-v1.md` maps every archived v1 path.
- Code layout (backend, frontend, source registry, tests) is established by milestone V0 of `docs/plan/v2/09-roadmap-and-milestones.md`. Follow that plan, and record the resulting layout and commands in this file when V0 lands.
- Implement against approved designs. All v2 documents are currently draft and become implementation authority after user review. New documents start as draft; substantive changes to approved designs return to review or receive a reasoned ADR. Superseding an architectural decision requires a new ADR naming the old one. Deprecated docs remain with replacement links.
- `docs/**/*.md` except INDEX/logs/reports requires title/status/owner/updated frontmatter. Status values are draft, review, approved, implemented, deprecated; see `docs/process/status-workflow.md`.
- Update the index for added/removed/renamed documents and `docs/GLOSSARY.md` for new shared terminology. Requirement-to-acceptance mappings live in `docs/plan/v2/09-roadmap-and-milestones.md` §4 until V0 creates `docs/testing/acceptance-criteria.md`. Update progress at milestones; keep durable work evidence in the log/report structure and use instruction files for stable rules.
- Designs specify function, implementation, test method/type and acceptance criteria. Cite and date verified endpoint/rate-limit facts; label unverified claims. Label design pseudocode. Project documentation remains Chinese with English identifiers and kebab-case filenames.

## Acquisition and local-state constraints

- Acquire papers through legitimate sources and authorized user credentials, following robots.txt/ToS and conservative source-specific rates with an identifying user agent. Exclude paywall/CAPTCHA bypasses, impersonation, pirate sources and redistribution features.
- v2 is a multi-user platform. Auth-gated full text is retrieved on the user side with that user's own credentials, only on explicit request, and stays private to that user. Shared data holds only public metadata and content whose license permits redistribution, and anything derived from private content stays private. The compliance hard constraints HC-01 onward in `docs/plan/v2/08-compliance-security-privacy.md` are binding.
- Keep credentials, cookies, sessions and downloaded PDFs in ignored local storage. Local runtime config/state lives in ignored `.paper-crawler/`, selected through `PAPER_CRAWLER_HOME`.
- Protect `.paper-crawler` with `-e .paper-crawler` whenever an authorized cleanup uses `git clean -x`; this preserves credentials and databases even when Git ignore rules are bypassed.

## Commands and validation

No build or test toolchain exists on `main` yet; V0 establishes it (Python 3.12+ backend, TypeScript PWA, PostgreSQL 18). Until then, validate documentation changes: frontmatter is present, relative links resolve, and `docs/INDEX.md` is updated. The v1 commands (`make check`, `uv run crawler`) apply only on `archive/v1`.

Follow `docs/process/git-workflow.md` for Conventional Commits. Report the checks actually run. Delegate bounded research with explicit output paths; the primary agent reviews evidence and owns final architecture/design decisions; select models according to the task.

Task entry points: sources and connectors → `docs/plan/v2/03-sources-and-corpus-pipeline.md` and `docs/catalog/source-directory.md`; retrieval and routing → `04`; data platform → `05`; recommendation and matching → `06`; frontend → `07` and `demo/`; compliance → `08`; milestones and task cards → `09`.
