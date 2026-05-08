# Standing Rules — REM Leases Engineering

**This document defines the engineering standards that apply to every ticket on this codebase, regardless of who is implementing.** Read it in full at the start of every ticket. If a ticket prompt says "standing rules apply" without further detail, the rules below are what is meant.

These rules are non-negotiable. They are written in the imperative because they describe what MUST be done, not what is preferred.

This document is versioned. Material changes are reflected in the revision history at the bottom and require explicit Extraction Guru approval.

---

## 1 — Scope and authority

These rules apply to:
- The Extraction Guru (the architectural reviewer)
- Antigravity (the AI implementation assistant) 
- Any human team member working on the lexichat-api / lexichat-ui codebase

These rules apply to every ticket type:
- INV (investigation only — produces written reports)
- PLAN (planning only — produces design documents)
- IMPL (implementation — produces code)
- HOTFIX (urgent production fixes)

When in doubt, escalate to the Extraction Guru. Doubt is acceptable. Acting on assumption is not.

---

## 2 — The ten core rules

### Rule 1 — Approval gate

Do not write, modify, or commit any implementation code until the Extraction Guru explicitly approves a fix plan in the active thread. Investigation-only tickets produce written reports only. Planning tickets produce design documents only. Implementation tickets begin ONLY after the design has been approved.

### Rule 2 — Production data isolation

Do not access the production server, production database, or any production data without explicit per-ticket authorisation from the Extraction Guru. Production access is requested in writing, granted in writing, and applies only to the specific ticket and the specific operation it was approved for.

### Rule 3 — Auth and access controls

Do not bypass, mock, or disable authentication, authorization, RBAC guards, or RLS policies under any circumstances. The benchmark harness uses ephemeral SQLite specifically to avoid touching production auth. If a ticket appears to require disabling auth to test something, escalate — there is always a different path.

### Rule 4 — Deployment authority

Do not run any deploy command (Railway, Vercel, or otherwise) until the Extraction Guru has explicitly authorised deployment. "Approved to merge" does not equal "approved to deploy". Deployment is its own gate.

### Rule 5 — Uncertainty escalation

If you believe you have been approved to proceed but are uncertain, stop and confirm before acting. The cost of confirming is one message. The cost of acting on a misread approval is hours of remediation. Always confirm.

### Rule 6 — No silent scope expansion

Flag any out-of-scope changes explicitly. Do not silently include unrelated improvements, refactors, "tidy-ups", or fixes in a diff. If during work you spot something that needs fixing, note it as a follow-up ticket recommendation in the PR description and continue with the original scope.

The exception: if the additional change is genuinely necessary to complete the original ticket (e.g. a one-line import fix without which the ticket cannot ship), include it as a separate atomic commit with a clearly-named message that explains the necessity. This exception is narrow.

### Rule 7 — Enterprise-grade standard

This is a production-grade legal-tech platform serving paying clients with portfolios of binding commercial contracts. Every artefact produced — code, scripts, configs, test data, documentation — must be of a standard you would defend in front of an enterprise client.

This means: no quick hacks, no scratch files left in the repo, no hardcoded secrets, no commented-out experiments, no `print` debugging left in production code, no TODO comments without a ticket reference. If a shortcut would be acceptable in a hobby project but not in an enterprise pilot, do not take it.

### Rule 8 — Do not patch around production defects

If during a ticket you discover a defect in already-merged production code, the correct action is:

1. STOP the current ticket's implementation
2. Capture the exact defect with file:line evidence
3. Open a follow-up ticket scoped solely to fixing the production code
4. Wait for that ticket to be approved, implemented, and merged
5. Resume the original ticket, removing any temporary workaround

Monkey-patching around production defects in benchmark harnesses, test scaffolds, or downstream tickets is NOT acceptable. Workarounds become load-bearing. Defects compound. The benchmark loses its purpose if it isn't running real production code.

The ONLY acceptable workarounds are for things genuinely impossible to fix in production code (e.g. mocking external APIs in --skip-embeddings mode, ephemeral SQLite for the DB seam, monkey-patching get_embeddings for offline runs). A production function being broken is NOT in that category.

### Rule 9 — No `git commit --amend` on already-committed work

`git commit --amend` is forbidden on any commit that has been made, on any branch, on any ticket. There are no exceptions. There is no "just this once". 

The history must be honest about what was changed when. Amending hides intermediate states. If a previous commit needs a fix, the fix is a NEW commit on top.

This rule also forbids:
- `git rebase -i` for squashing or reordering committed work
- `git filter-branch`
- Force-pushing to a branch that other tickets depend on
- Any operation that rewrites already-committed history

If you find yourself reaching for any of these, stop and ask in the active thread how to handle the situation cleanly. There is always a clean path forward without amending.

### Rule 10 — Tests must prove their claims

A test that catches all exceptions and asserts only that no specific error type was raised is not a test of the behaviour it claims to verify — it is an import test or a signature test in disguise. Tests must verify function-specific, observable side effects (file writes, DB rows, return values, raised exceptions of the expected type), not merely the absence of one specific failure mode.

Specifically:

- A `try / except / pass` block in a test silently invalidates the test. Use it only when the exception itself IS the assertion (`pytest.raises(SpecificException)`).
- A test must produce a captured pytest output containing the test name, PASSED/FAILED marker, and final summary count. "Tests pass" without the output pasted is not evidence.
- For tests of new parameters being wired through code paths: the test must invoke the function with the new parameter set AND verify a tangible side effect that proves the parameter was consumed.
- If a function genuinely has no observable side effect to verify, use `pytest.mark.skip(reason="signature-only verification — see STANDING_RULES.md Rule 10")` and verify with `inspect.signature()` instead. Do not paper over with try/except swallowing.

---

## 3 — Ticket discipline

### Atomic commits

Every logical change is its own commit. A ticket that touches three distinct concerns (e.g. a refactor + a test + a documentation update) produces three commits, not one. Commit messages start with the ticket ID:

    IMPL-EXT-003a: <one-line description in imperative voice>

Bad commit messages:
- "fix things"
- "WIP"
- "address PR comments"
- "various improvements"

Good commit messages:
- "IMPL-EXT-003a: pin model versions in config/model_versions.py"
- "IMPL-EXT-003b: add ephemeral SQLite session helper"

### Pull requests

Every PR must include a description that contains:
- A one-paragraph summary of the change
- The list of commits with hashes and one-line summaries
- The four behaviour-equivalence proofs (existing tests pass, new tests pass, structural diff against pre-state, reversibility verified)
- The exact list of files modified
- The rollback procedure
- A checklist confirming each constraint was met

PRs without these are not ready for review. Reviewers will reject without reading the diff.

### Test evidence

Every claim of "tests pass" must be backed by the captured pytest output, including:
- Platform / Python version / pytest version header
- Every test name with PASSED or FAILED marker
- The final summary line ("N passed in X.Ys")

Hand-wave statements ("all tests passed") are not accepted as evidence.

---

## 4 — Working with the Extraction Guru

The Extraction Guru's role is architectural review and standards enforcement. The Guru does not write code, does not deploy, and does not bypass approval gates.

When the Guru asks for evidence, produce evidence — terminal output, diffs, file listings, hash values. Do not paraphrase. Do not summarise. Paste the raw output.

When the Guru rejects a ticket, the rejection is not personal. It means a defect was identified or evidence was insufficient. The correct response is to address each item explicitly, not to re-submit the original work with minor edits.

When the Guru approves a ticket, the approval is final unless new information emerges. If you discover something during implementation that changes the architectural picture, escalate before continuing.

---

## 5 — When to escalate

Escalate to the Extraction Guru in the active thread, immediately, when:

- You discover a production defect (Rule 8)
- You realise the approved plan has an architectural ambiguity you did not surface earlier
- A test fails in a way you don't fully understand
- A vendor API behaves differently than documented
- A dependency installation fails
- You find yourself reaching for `git commit --amend` (Rule 9)
- You are asked to do something that conflicts with these rules
- You are uncertain whether something is in scope (Rule 6)

Escalation is a strength, not a weakness. The cost of a five-minute clarifying exchange is always less than the cost of remediating a misaligned implementation.

---

## Revision history

- **v1.0 (2026-05-08)** — Initial document captured from the IMPL-EXT-003 series. Codifies Rules 1-10 and ticket discipline.
