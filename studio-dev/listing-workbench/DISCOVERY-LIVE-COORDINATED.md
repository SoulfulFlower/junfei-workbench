# Whole-run discovery coordination: offline integration fixture

## Status and exact boundary

`discovery_live_coordinated.py` is a **source-only, offline-only integration fixture**. It wraps the actual `discovery_live.start` daemon worker and the actual `discovery_browser.capture_live` Python bridge in one shared coordinator operation. The browser subprocess is replaced by a fixed synchronous synthetic transport. No EGO runtime, Node, browser, network, paid model, upload, save, or publication is invoked.

The fixed chain is search → seller → store → literal title prefix → search. It records five synthetic controller observations, including four synthetic browser captures. Actual browser calls, qualified products, imported products, paid calls, uploads and publications are all **zero**. A coordinator `completed` state means this fixture was verified and persisted; it does not mean commercial selection, production readiness, ERP success, or Amazon availability.

No existing controller, browser adapter, coordinator primitive, HTTP route, production configuration, enrollment or database was changed. The default application behavior is unchanged. This entry is not activated by the desktop application, server, frozen executable or employee account worker. It is not a real-browser entry with a feature flag waiting to be enabled.

The original blocked pilot under `outputs/live-discovery-20261106`, its evidence and TaskSpace 6 are not touched. This fixture cannot accept existing DATA/project paths and requires synthetic space IDs of at least 10000. It must not be used to retry the original run.

## Trusted source interface

`run_fixture(coordinator_root=..., expected_identity=..., namespace=..., account_id=..., space_id=..., run_id=..., scenario='complete')`

- The coordinator must already have been explicitly provisioned in a dedicated TEMP root, and its identity must be independently supplied. This entry never provisions, adopts, repairs, resets or falls back to another coordinator. It refuses the production default root and paths outside TEMP.
- `namespace` identifies a synthetic account authority; `account_id` is a positive synthetic account integer. Neither partitions the resource: every participating account/namespace using the same coordinator and space competes for the same space.
- `run_id` is one-use. Matching repetition returns the persisted operation with `replayed=True`, no workspace and no runnable capability, whether completed or unresolved. Changed input with the same identity conflicts. New IDs/accounts cannot bypass an unresolved operation on that enrolled space.
- `scenario` is a fixed offline test enum. There are no HTTP inputs for coordinator paths, capabilities, callbacks, transport functions, scripts, URLs, existing DATA or verifier selection.
- Imports do not create enrollment or import `app_paths`/discovery modules in the parent. Execution is refused in frozen/account-worker mode.
- A newly allocated TEMP workspace is created only after the shared dispatch intent is committed. It contains new input, evidence, DATA, project configuration and a dummy non-executable CLI file. Successful and unresolved run artifacts are retained by the entry. Test teardown removes only exact roots allocated by that test, after owned children have ended.

These are trusted local Python fixture APIs, not an adversarial sandbox. Arbitrary local Python callers can bypass application code. Socket/subprocess deny patches defend the reviewed fixed program, including its discovery imports; they are not a security boundary for hostile imported code.

## Whole-run ownership and process lifetime

The parent acquires one `reserve` lease, then uses one `dispatch_once` for the complete run. Shared `dispatch_unknown` is persisted before child launch. There is no per-step release or nested child acquisition. The child receives the immutable dispatch identity as receipt-binding data only; it never receives/reconstructs a lease and never opens a coordinator capability.

The fixed Python child is launched with `-I -B -X utf8`. Its TEMP environment is set before importing discovery. It still executes every existing source-only/TEMP/non-production-space gate. The actual daemon thread is retained by exact object identity and joined. Unhandled thread `BaseException` is recorded. The parent waits for the child process to exit before inspecting its terminal evidence. Local status becoming `stopped` or a proof file appearing while the child remains alive does not release the shared operation.

Ownership is retained during all five controller actions, between actions, through thread/process joins, parent receipt verification and durable final evidence persistence. It is not held by a long-running SQLite transaction.

A parent crash may leave its bounded offline child briefly alive. That does not release ownership: the durable operation remains unresolved. There is no TTL, PID cleanup, stop-based release, new-ID escape, force-unlock, recovery capability or automatic resume. Read-only inspection/replay is the only supported post-failure behavior. Restoring an entire coherent old ledger, using a different enrollment, malicious local rewriting and another Windows user are outside the cooperative guarantee.

## Terminal proof accepted by this fixture

The sole allowed successful outcome is the fixed action-limit run with five fully observed steps and four fully captured attempts. There is no successful `blocked`, generic pre-effect-refusal, partial run, requested stop, time limit, exception, timeout or crash path.

The parent independently rereads the current run workspace after child exit and checks:

1. Exact, strictly typed schema/version and current coordinator ID, engine, space, owner, operation ID, request digest, fence and dispatch nonce. Boolean/integer aliases, extra/missing fields and duplicate JSON keys are rejected.
2. Durable intent and worker-terminal rows, matching child PID, the exact finite request, a joined worker, no thread errors and four fixed transport calls.
3. Exactly one run, five contiguous observed steps, four captured attempts, one graph cycle and six graph events. Each step is linked to its exact expected request, prior event, observation, logical target and persisted attempt; no unused/missing steps or attempts are accepted.
4. Strict run/step/attempt schemas, terminal reason `action_limit`, exact budgets, no stop request, exact stop-control path and no stop marker. A swallowed controller exception yields `worker_stopped_for_review` or another invalid terminal condition and cannot release.
5. Exact generated configuration, isolation marker, dummy CLI bytes, effective binding, binding/config fingerprints, current source collector hashes, per-attempt request digest and captured navigation flags.
6. Current graph lineage and the worker's snapshot digest against reread persisted run/step/attempt/graph rows. The fixed worker validated captures through the existing Python bridge. This is not a general-purpose real-browser result verifier.
7. Four durable transport rows, each bound to the same complete shared identity and exact step/capture ID, with unique confined capture directories and current script/result SHA-256 hashes. Missing/extra transport rows, changed files and path escapes fail closed.
8. A final `parent_verified` receipt containing the bound worker proof, transport proofs, current input/configuration/database hashes and explicit synthetic summary. This is committed in a rollback-journal SQLite database with `synchronous=FULL`, then reread before `TerminalEvidence` is returned.

Any adapter proof write/read failure or lost adapter commit acknowledgement before coordinator completion retains the unresolved barrier. If the coordinator final commit acknowledgement is lost, a fresh read can show either unresolved or durably completed; the original operation remains replay-only in both cases. An exception is never permission to repeat its external work. Durable history and receipts are never reset by this entry.

## Uncoordinated coexistence is an exclusion

The lock protects only participating calls to this new fixture entry using the same pinned coordinator under the same Windows user. Existing `discovery_live.start`, manual discovery, old source/executable builds, direct EGO calls, automation/ERP/publisher adapters and other profiles/users do **not** acquire it.

An independent offline test deliberately holds a shared reservation, invokes the old `start` in fresh isolated DATA with its worker launch mocked, and observes that the old entry still starts. No browser is launched in that witness. This proves the bypass/exclusion, not safe simultaneous access. Do not run a future real guarded entry concurrently with unmodified clients and claim protection.

Before a real integration, supported dispatch boundaries must adopt one reviewed pinned enrollment, conflicting old/manual clients must be quiesced, outstanding historical unknowns must be reconciled through an approved process, exact real-browser terminal evidence must be designed, and a separately authorized isolated browser test must pass. Those steps are not implemented or proven here.

## Offline validation

From `listing-workbench`:

`python -B -X utf8 -m unittest test_discovery_live_coordinated test_discovery_live_coordinated_adversarial -v`

The focused tests cover the fixed chain, immutable replay, strict inputs and proof identity, wrong/missing enrollment, source/account-worker gates, blocked/unknown/swallowed exception/BaseException/stop/crash results, persisted-ledger and capture-artifact tampering, and receipt-write failure/lost acknowledgement. Independent acceptance adds real separate-process competition across accounts during inter-step/verification/persistence spans, process death, early local terminal proof, import behavior, late scope/stop changes, and the legacy bypass witness.

All coverage is synthetic. It does not prove real EGO integration, arbitrary discovery chains, machine-global coordination, production activation, cold start on another computer, qualification/sourcing/profit evaluation, image generation, or publication.