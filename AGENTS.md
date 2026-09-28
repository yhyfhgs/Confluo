# Confluo

The project is owned by ActionMesh AI: `https://github.com/ActionMesh-AI/Confluo` (formerly Paper Crawler). Historical archive names and the local `.paper-crawler/` / `PAPER_CRAWLER_HOME` contract remain unchanged.

`AGENTS.md` is the shared instruction source. The repository is at the start of the v2 restart and has no implementation yet. `main` holds only current, condensed documents: the v2 plan, the source directory, a research summary and the interaction demo. Everything older lives in two archives; read them with `git show <ref>:<path>` or a separate worktree, and treat them as reference material, not as the current system:

- tag `v2-drafts`: the full v2 design-stage drafts (the design brief, long designs 00–09 with DDL, algorithms, task cards and acceptance criteria, the ADR full text, the survey with raw data, the design process record and session logs 011–013);
- branch `archive/v1` (tag `v1-final`): the complete v1 implementation and every v1 document (Python CLI, tests, VenueSpecs, configs, design documents, process rules and the full text of ADRs D-001…D-039), also a source of reusable adapters.

Read `README.md`, `docs/INDEX.md`, `docs/plan/progress.md` and `docs/plan/v2/README.md` first; `docs/archive.md` explains both archives.

## Ownership and ActionMesh workspace

- Primary owner: fhgs (`yhyfhgs`). Confluo is the owner's core active project and belongs to the default initialization and synchronization scope. Reuse this checkout; preserve local changes, untracked configuration and archive refs.
- Before workspace operations, read `../AGENTS.md`. For team collaboration, use `../team-hub/AI维护/README.md` to select the relevant current guide; repository scope is defined by `../team-hub/AI维护/工作区.json`, and project ownership by `../team-hub/开发/项目索引.md`. Standalone clones can read the [published guide index](https://github.com/ActionMesh-AI/team-hub/blob/main/AI维护/README.md).
- Git, PR and release operations follow the current [team collaboration rules](https://github.com/ActionMesh-AI/team-hub/blob/main/AI维护/协作规范.md): use a task branch and PR, preserve existing work, do not push directly to `main` or rewrite shared history, and validate the complete diff before merging. Archived v1 guidance permitting direct commits to `main` does not override the current workflow. Production releases require their own authorization.
- The `collab` branch and Obsidian plugin workflow apply to `team-hub`, not to this product repository. Product designs, source and detailed documentation remain here; team-hub holds shared rules and navigation. Product implementation still requires the applicable approved design.
- Synchronizing another repository does not confer maintenance authority. `dsh-whale` and `wechat-clawbot` are Alphainfix projects mirrored into the organization; `homework-grading` is maintained by `MistyHuang03`. Do not edit their files or submit changes as part of Confluo or routine workspace maintenance without explicit authorization for those projects.

## Layout and design authority

- `docs/plan/v2/` holds the v2 plan: the overview `README.md`, designs 01–08, the roadmap 09 and `demo/`. `docs/catalog/` holds the supported-source directory `source-directory.md`, the seven-class source taxonomy and status table `source-taxonomy.md`, unlisted research candidates `source-candidates.md`, the venue ranking systems `venue-rankings.md` and the per-discipline venue catalog `venues/`; `docs/survey/README.md` summarizes the research, and `docs/plan/decision-log.md` is the ADR log: an index of the v1 decisions plus the v2 proposals D-040 onward. Diagrams go in `docs/diagrams/`, session records in `docs/logs/` and milestone reports in `docs/reports/`.
- The condensed designs on `main` fold in the design brief's round-2 and round-3 rulings and become the design authority once the user approves them. The long drafts at `v2-drafts` hold the implementation detail; consult them for DDL, algorithms, task cards and acceptance criteria, and follow `main` wherever the two disagree.
- Code layout (backend, frontend, source registry, tests) is established by milestone V0 of `docs/plan/v2/09-roadmap-and-milestones.md`. Follow that plan, and record the resulting layout and commands in this file when V0 lands.
- Implement against approved designs. All v2 documents are currently draft and become implementation authority after user review. New documents start as draft; substantive changes to approved designs return to review or receive a reasoned ADR. Superseding an architectural decision requires a new ADR naming the old one.
- Keep `main` current and readable: move superseded documents to an archive ref and record them in `docs/archive.md` instead of leaving deprecated copies on `main`, and keep each document short enough to read in one sitting, with long detail in implementation plans or the archive.
- `docs/**/*.md` except INDEX/logs/reports requires title/status/owner/updated frontmatter. Status values are draft, review, approved, implemented and deprecated: draft → review → approved → implemented, and any status → deprecated. The v1 process documents (`docs/process/` on `archive/v1`) remain the workflow rules, summarized in this file; V0-T4's revision proposal brings their v2 versions back to `docs/process/`.
- Update the index for added/removed/renamed documents and `docs/GLOSSARY.md` for new shared terminology. Requirement-to-acceptance mappings live in §4 of the full roadmap draft at `v2-drafts` until V0 creates `docs/testing/acceptance-criteria.md`. Update progress at milestones; keep durable work evidence in the log/report structure and use instruction files for stable rules.
- Designs state function, approach, test method and acceptance criteria, or point to where that detail lives. Cite and date verified endpoint/rate-limit facts; label unverified claims. Label design pseudocode. Project documentation remains Chinese with English identifiers and kebab-case filenames.

## Acquisition and local-state constraints

- Acquire papers through legitimate sources and authorized user credentials, following robots.txt/ToS and conservative source-specific rates with an identifying user agent. Exclude paywall/CAPTCHA bypasses, impersonation, pirate sources and redistribution features.
- v2 is a multi-user platform. Auth-gated full text is retrieved on the user side with that user's own credentials, only on explicit request, and stays private to that user. Shared data holds only public metadata and content whose license permits redistribution, and anything derived from private content stays private. The compliance hard constraints HC-01 onward in `docs/plan/v2/08-compliance-security-privacy.md` are binding.
- Keep credentials, cookies, sessions and downloaded PDFs in ignored local storage. Local runtime config/state lives in ignored `.paper-crawler/`, selected through `PAPER_CRAWLER_HOME`.
- Protect `.paper-crawler` with `-e .paper-crawler` whenever an authorized cleanup uses `git clean -x`; this preserves credentials and databases even when Git ignore rules are bypassed.

## Commands and validation

No build or test toolchain exists on `main` yet; V0 establishes it (Python 3.12+ backend, TypeScript PWA, PostgreSQL 18). Until then, validate documentation changes: frontmatter is present, relative links resolve, and `docs/INDEX.md` is updated. The v1 commands (`make check`, `uv run crawler`) apply only on `archive/v1`.

Write Conventional Commits (`<type>(<scope>): <subject>` with an English lowercase imperative subject of at most 72 characters; the body may be Chinese) as defined in `docs/process/git-workflow.md` on `archive/v1`. Report the checks actually run. Delegate bounded research with explicit output paths; the primary agent reviews evidence and owns final architecture/design decisions; select models according to the task.

Task entry points: overview → `docs/plan/v2/README.md`; sources and connectors → `docs/plan/v2/03-sources-and-corpus-pipeline.md` and `docs/catalog/source-directory.md`; source classes, venues and rankings → `docs/catalog/source-taxonomy.md`, `docs/catalog/venues/README.md` and `docs/catalog/venue-rankings.md`; retrieval and routing → `04`; data platform → `05`; recommendation and matching → `06`; frontend → `07` and `demo/`; compliance → `08`; milestones → `09` (task cards are in the full draft at `v2-drafts`).
