# MAXIV-EXACT — Development Instructions

## 1. Project overview

MAXIV-EXACT (Exploration of X-ray Absorption: Characterization and Treatment) is an established scientific Python application for XAS/NEXAFS data processing and analysis.

It uses Python 3.14, PyQt6, NumPy, SciPy, Matplotlib, and related scientific libraries. Major functionality includes spectral processing, background subtraction and normalization, PCA/NMF/MCR-ALS decomposition, fluorescence map analysis, and experimental self-absorption correction.

The application is under active development. Scientific correctness, reliability, maintainability, and a consistent user experience are the main priorities.

## 2. Development workflow

- Always inspect the relevant existing implementation before proposing or making changes. Do not assume how functionality works based solely on descriptions or previous discussions.
- For significant scientific, algorithmic, architectural, or GUI changes, first discuss the proposed approach, alternatives, and implications with the developer. Do not implement such changes until an approach has been agreed upon.
- For straightforward, explicitly authorized changes, proceed without unnecessary additional approval requests.
- Before significant modifications, identify the affected modules and briefly consider architectural implications, regression risks, and whether additional tests are justified.
- Keep modifications focused on the agreed task. Avoid unrelated changes or unsolicited improvements.
- After implementation, summarize what changed, which tests or checks were performed, and any remaining limitations.
- When uncertainty arises about intended scientific behavior or existing functionality, ask rather than make consequential assumptions.

## 3. Code architecture and package hygiene

- Maintain a clean, modular, logically organized package structure with clear separation of responsibilities.
- Prevent individual modules and classes from growing excessively or accumulating unrelated functionality.
- Prefer dedicated modules for substantial new workflows or functionality rather than continually expanding large existing modules.
- Consider small, incremental structural improvements when they naturally fit an ongoing development task, to avoid the need for major refactoring later.
- Avoid the opposite extreme: unnecessary fragmentation into numerous tiny modules, excessive abstraction, or complicated dependencies.
- Reuse existing utilities and components where appropriate instead of duplicating functionality.
- Follow established naming conventions, coding patterns, and package organization unless there is a clear reason to improve them.
- Do not undertake extensive refactoring or reorganize the package structure without prior discussion and approval.

The objective is gradual architectural improvement without unnecessary complexity or disruption.

## 4. Scientific correctness

- Preserve the scientific meaning of existing calculations, normalization procedures, fitting methods, and data transformations.
- Clearly distinguish physical assumptions, numerical approximations, and empirical corrections.
- Do not silently change mathematical definitions, default parameters, calibration conventions, or numerical algorithms.
- Pay particular attention to units, energy scales, normalization conventions, array dimensions, and data provenance.
- Prefer numerically stable, scientifically justified algorithms over unnecessary sophistication.
- For new scientific algorithms, discuss underlying assumptions, limitations, and validation methods before implementation.
- Maintain consistency between the implemented algorithms, GUI controls, and scientific explanations in Help.

Scientific behavior must never be changed merely for code simplification.

## 5. GUI development

- Follow the established PyQt6 GUI conventions and visual style unless explicitly told otherwise.
- Maintain consistency in terminology, layouts, labels, controls, dialogs, and plotting behavior.
- Avoid unnecessary GUI clutter and excessive configuration options.
- Preserve existing user workflows, interactions, and defaults unless changes are explicitly requested.
- Keep complex GUI workflows modular, separating numerical processing, data handling, and presentation logic wherever practical.
- Ensure that changes to one workflow do not unintentionally affect other windows, tabs, or analysis modes.
- Preserve existing session persistence and data transfer behavior.

## 6. Testing and regression prevention

- Run relevant existing tests after functional changes whenever the environment permits.
- Add new regression tests selectively, only when they provide meaningful long-term value by protecting important functionality, scientific correctness, or previously problematic behavior.
- Before adding a test, consider whether existing tests already provide sufficient coverage and whether the new test justifies its maintenance cost.
- Prefer a small, focused, high-value test suite over a large collection of redundant or overly implementation-specific tests.
- Do not routinely add regression tests for every minor change or bug fix.
- Prefer tests that verify observable behavior and numerical correctness rather than internal implementation details.
- Do not modify existing tests merely to accommodate incorrect application behavior.
- Report test failures and distinguish pre-existing failures from regressions introduced by the current changes.
- When GUI behavior cannot be verified automatically, clearly identify what requires manual testing.

## 7. Documentation and Help

- Keep the bundled Help documentation consistent with actual application behavior.
- Update the relevant Help sections when user-visible functionality changes.
- Maintain accurate scientific explanations, mathematical notation, and workflow descriptions.
- Use concise, clear, user-oriented language.
- Follow the established Help structure and terminology.
- Keep the Help "What's new" section limited to the 10 most recent official releases.
- Update the README and changelog when relevant, particularly for installation changes, significant features, fixes, and releases.
- Avoid unnecessary documentation files, temporary development notes, or duplicated explanations.

## 8. Development environment

- The source repository may be accessed from multiple Windows computers through a mapped network drive.
- Use the existing conda environment configured on the current computer. Do not assume its name or installation path is identical on different computers.
- Verify the Python interpreter and environment before running tests, builds, or application commands.
- Prefer conda-forge for Qt-related dependencies, including PyQt6, PyQt6-WebEngine, and Qt6.
- Do not install, remove, or upgrade dependencies without explicit approval.
- Do not modify system-wide Python or conda configurations.
- Preserve the established console entry point `exact`.
- Be mindful of network-drive latency, file locking, and interrupted connections when performing file-intensive operations.

## 9. Git and change management

- Treat the existing repository as the authoritative source.
- Inspect the working-tree state before substantial modifications.
- Preserve uncommitted user changes.
- Do not change branches, create commits, push, reset, clean, or execute destructive Git commands without explicit authorization.
- Avoid modifying the same repository simultaneously from different computers or development sessions.
- Keep changes focused and easy to review.
- Do not overwrite or discard files merely because they appear unrelated to the current task.
- If Git operations fail because of network-drive restrictions, report the problem rather than applying potentially destructive workarounds.

### Development branches and accepted builds

- Keep `main` at the latest official GitHub release. Make feature and fix iterations in the working repository on the active development branch, such as `develop-2.6.2`.
- A numbered build such as `2.6.2.build1` represents an accepted, recoverable state. Keep corrections under the same proposed build number until the developer accepts or rejects it.
- After explicit approval, record each accepted build as a local commit and give it a descriptive tag, such as `v2.6.2-build1`. Keep intermediate builds local unless the developer authorizes a push.
- Use temporary commits or separate branches for risky experiments only with approval. Treat them as experimental checkpoints.

### Returning to an earlier build

- Check the working tree before switching branches or restoring files. Identify and preserve unrelated or potentially valuable uncommitted work before discarding anything with explicit approval.
- When abandoning an approach or resuming from an earlier accepted build, keep all accepted commits and tags recoverable. Prefer a new branch from the chosen tag to preserve later history.
- Keep the existing editable install pointed at this working checkout so `exact` runs the source selected there.

## 10. Packaging and releases

- Maintain consistency between the application version, package metadata, changelog, and release documentation.
- Preserve the established source layout, entry points, and installation procedure unless changes are explicitly agreed upon.
- Keep release distributions clean and limited to necessary source files, resources, documentation, tests where appropriate, and installation metadata.
- Exclude caches, temporary files, generated development notes, intermediate builds, and unnecessary artifacts.
- Do not create `DEVELOPMENT_BUILD.txt`, build-specific `*_NOTES.md`, or similar files.
- During intermediate development, prepare source packages only when requested.
- Build wheels only when explicitly requested for a clean release.
- Verify package contents and installation instructions before preparing a release.
- Do not publish releases or push changes to remote repositories without explicit approval.

### Stage A — Audit and approval

- When the developer accepts a build as a release candidate, audit it without changing files. Compare it with the previous official release tag, such as `v2.6.1` for `v2.6.2`.
- Identify cumulative changes in functionality, scientific analysis, GUI behavior, installation requirements, and compatibility. Present the proposed release contents and required documentation, version, and packaging changes for approval.

### Stage B — Preparation and verification

- After approval, update `pyproject.toml`, package metadata, and other relevant locations to the official version and use the approved release date consistently.
- Review the README installation instructions, dependency requirements, and conda-forge Qt guidance. Audit all bundled Help against the final GUI and implementation. Correct obsolete guidance and keep explanations concise, scientifically accurate, and in the appropriate sections.
- Update `CHANGELOG.md` and Help **What's new** under **Added**, **Changed**, and **Fixed**, using only categories with meaningful entries. Group related changes and cover high-level changes users will see since the previous official release. Omit intermediate builds, internal refactoring, test additions, and bugs introduced and resolved within the development cycle. Keep GitHub release notes consistent with these summaries.
- Run the available regression tests and appropriate GUI smoke tests. Investigate failures. With explicit approval to build the release artifacts, prepare a clean source ZIP and Python wheel. Inspect both archives for the correct version, dependencies, entry points, required resources, and excluded artifacts.
- Present the final release notes, test results, archive contents, and outstanding issues for review before publication.

### Stage C — GitHub publication

- After explicit publication approval, create the official release commit from the verified candidate, preserve the accepted build checkpoint separately, and integrate the release into `main` while retaining development history.
- Tag the exact verified release source with the official version tag, such as `v2.6.2`. Push the approved changes and tag, then publish the GitHub release with concise release notes, the verified source ZIP, and the wheel.

### Post-release branch cleanup

- Use one temporary development branch per upcoming release. Start each new cycle from the latest official release on stable `main`, as described in Section 9.
- After successful GitHub publication and verification, obtain explicit cleanup approval before switching back to `main` and deleting the completed release's development branch.
- Before deletion, verify that `main` contains the complete development history and that all accepted build commits and tags remain recoverable. Avoid squash merges that discard individual checkpoints.
- Use `git branch -d` for safe deletion. Preserve any branch with unmerged or otherwise valuable changes. Force deletion requires separate explicit approval.

## 11. Communication and decision-making

- Keep explanations concise, technically precise, and focused on the actual implementation.
- Distinguish confirmed findings from hypotheses or suggestions.
- When diagnosing problems, identify the underlying cause before proposing a fix whenever practical.
- Present significant design alternatives with their advantages, limitations, and implications.
- Avoid unnecessary complexity or speculative features.
- Do not claim that code, tests, or GUI behavior have been verified unless they have actually been checked.
- When a task has been completed, provide a brief summary of the changes, verification results, and outstanding issues.

The overall development philosophy is to improve MAXIV-EXACT incrementally, preserving scientific correctness and established functionality while maintaining a clean, reliable, and sustainable codebase.