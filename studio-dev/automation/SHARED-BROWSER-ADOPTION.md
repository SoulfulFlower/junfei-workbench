# Shared browser coordinator: adoption boundary

Date: 2026-11-06. Source inventory only; line references describe the source at review time.

## What this increment does, and does not do

This increment supplies a standalone coordination primitive and offline tests. **No production browser adapter is integrated or activated.** Inclusion in a corresponding-source archive is not inclusion in the executable's runtime imports. It does not restart the workbench, provision a production coordinator, enable continuous discovery, or establish that existing EGO clients cooperate. The original blocked pilot under `outputs/live-discovery-20261106`, including its space 6 run and evidence, remains untouched. A new operation ID, DATA directory, installation, or coordinator must never be used to retry that operation.

The intended resource is `(ego-lite default local profile, numeric TaskSpace ID)`. A fixed, explicitly provisioned coordinator under the Windows user's OS-resolved LocalAppData can coordinate participating processes using that same Windows identity. It is **not a machine-wide guarantee across Windows users, other profiles, raw EGO clients, or old builds**. CLI path, page label, workbench account, DATA directory and installation path must not split this resource key. Conservative overlocking is preferable to treating CLI aliases or upgrades as separate browsers.

## Current dispatch inventory

No existing function intercepts every route. These are the application and CLI dispatch boundaries found in the maintained source:

| Route | Caller and actual EGO boundary | Current protection / adoption requirement |
| --- | --- | --- |
| Manual discovery: seller, store, search, family | `listing-workbench/server.py:409-417` -> `discovery_browser.capture*` at `709-722` -> `_capture:735`, direct `subprocess.run` at `816` | Attempts and space-history checks at `753-786`, `532-549` use that account runtime's `discovery_browser.sqlite3`. A future shared reservation must precede dispatch and remain unresolved through result verification and receipt persistence at `819-858`. |
| Isolated continuous discovery | `server.py:418-422` -> `discovery_live.start`; worker -> `discovery_browser.capture_live:725-732` -> the same `_capture:816` | `discovery_live` leases and `live_runs/live_steps` are in the same local discovery DB. `_browser_guard:349-358` is not cross-DATA. Preserve all source-only, TEMP, nonproduction-space and non-worker/frozen restrictions in `_policy:189-227`. |
| Workbench ERP observation | `agent_center.py:894-908` -> `agent_erp.observe:96-99` -> `_observe:102-135`; subprocess at `123-124` invokes `runtime_environment.ego_command` | Project-local `automation/data/ego-workbench.lock` at `agent_erp.py:79-93`, then the automation adapter below. |
| Workbench existing-draft copy | `agent_center.py:912-932` -> `agent_erp.sync_copy:138-145` -> `_sync_copy:148-177`; `ego_link.ego_draft_command` at `156`, raw returned command executed at `159` | Same project-local lock plus per-draft/content receipt. Bypasses `automation/ego_browser.py` for the save; subsequent `_observe` uses that adapter. |
| Workbench product-library package | `agent_center.py:926-931` -> `agent_library.sync_library:160-206`; subprocess at `189-190` | Same project-local lock, SKU/package receipts, then automation adapter. Upload/save remains a separate consequential workflow; coordination grants no business authorization. |
| Automation status, resume and run | `automation/ego_browser.py:43-95`; direct EGO CLI subprocess at `83-84` | `run` has per-script-path/content receipt at `64-78`; status/resume have no equivalent receipt. None has a shared TaskSpace mutex. Resume calls `takeOverTaskSpace` and also needs coordination, without implying takeover permission. |
| Source/frozen automation dispatch | `runtime_environment.py:76-84` selects Python adapter or `--workbench-tool ego-browser`; `desktop_launcher.py:11-13` -> `portable_support.handle_cli:107-136` -> `runpy.run_path` at `134` | These build/dispatch commands, not an additional EGO boundary. A source-only integration does not update an already-built executable. |
| Publisher connection / connection check | `junfei-publisher/ego_link.py:45-63` generates a raw EGO CLI command; `app.py:102-104` -> `start:201-211`, or `app.py:274-276` | No common workbench lock. Even read-only connection/status uses the space and must participate if exclusivity is claimed. |
| Publisher existing-draft copy | `ego_link.py:89-166` generates raw EGO CLI; `app.py:156-161` -> `start:211`, also workbench save above | JS duplicate receipt is per project/content, not a shared-space reservation. Command generation is not dispatch and cannot safely own a lease that is later abandoned. |
| Low-level image staging/library save | `ego_link.ego_image_command:169-287` returns raw EGO CLI | Public Python helper, not currently exposed by the desktop app import list. Generated JS gets `taskSpace` at `256` **before** acquiring project-local lock at `258-261`; failures retain that local lock. Future direct callers must use a reviewed executor, not execute a raw command. |

`agent_center.py:761` runs `listing.mjs` without `--run` for local preflight; it is not an EGO call. `discovery_run.py` is a simulator/inspector, not another browser dispatcher. The three `packaging/verify_live_*.py` tools invoke the discovery API and therefore reach its existing direct boundary; they are not shared-coordinator integration tests today.

## Identity and storage

- `app_paths.py:5-8` derives DATA from `JUNFEI_ACCOUNT_DATA`. `account_spaces.py:22,39,43-49` starts same-user child processes with separate `account-workspaces/<id>` DATA and inherits the parent environment. It passes the central `JUNFEI_ACCOUNTS_DB`, but no shared browser coordinator identity.
- `accounts.py:14,21` defines a configurable accounts DB and integer user IDs, not a stable cross-install account UUID. Audit identity must distinguish accounts DB/installation plus local account ID; this identity must not be part of the TaskSpace resource key. Do not publish another account's paths or task metadata in an API blocker.
- `runtime_environment.py:23-39` resolves project from `JUNFEI_PROJECT_ROOT`, `project-root.txt`, or source layout. `portable_support.py:39-70` creates a per-DATA `portable-runtime`. Existing ERP lock and execution receipts therefore split when project roots differ.
- Resolve the coordinator's production location from the Windows known-folder API, not DATA, install path, mutable project config, or an environment-only LocalAppData override. Same-user workers naturally share this OS identity, but availability/ACL/path validation must fail closed. Provisioning and identity pinning are explicit; missing or corrupt state is not permission to initialize a replacement.

## Why wrapping only ego_browser.py is unsafe

Discovery and `ego_link` dispatch directly. In addition, `ego_browser.execute` imports arbitrary reviewed `.mjs` files; its bootstrap only checks its own configured space. A script can call `taskSpace` again and touch a different space.

Concrete source examples are the 16 top-level `automation/ego_round_*.mjs` scripts, which call `taskSpace(1)`; `automation/ego-rounds/pvc-source-search-20261102/round-01.mjs` through `round-18.mjs`, also space 1; `ego-rounds/cyclic30-A1CL1EHU54VFT9-20261104/round-04-new-space.mjs`, which requests a named space; and `ego-rounds/workbench-image-20261104/round-01-create-space.mjs`, which requests another named space. Locking the wrapper's config space does not cover these accesses.

Future supported adapters should generate fixed, reviewed programs with a constrained, explicitly verified TaskSpace contract. A text search for `taskSpace` is an inventory aid, not a security boundary for arbitrary JavaScript/imports. Until migrated, explicitly exclude ad hoc scripts, generated/archive scripts, raw `ego-browser nodejs`, direct EGO tool use, old source copies and executables, and clients running under other Windows identities/profiles. Quiesce conflicting clients before activation; cooperative locks cannot prevent their access.

Legacy non-EGO routes are separate exclusions: `junfei-publisher/brain-worker.mjs:186` launches a persistent Edge profile, and `listing.mjs:138-140` launches Edge with `--run`. The desktop app's `require_legacy_browser` gate at `app.py:167-172` is not a universal gate for direct legacy script invocation. Do not add an automatic Edge fallback. Browser extensions, manual user control, and ZiNiao store/plugin operations are not made safe by an EGO TaskSpace lock.

## Future integration seam and ownership spans

The smallest practical common seam is a **new reviewed executor used by every actual EGO dispatch boundary**, not a global subprocess monkeypatch and not the per-account HTTP router. Adopt discovery's raw call, the automation adapter, and all three publisher command builders/callers deliberately.

The standalone API in `shared_browser_space.py` uses explicit `provision(root)` enrollment, then `Coordinator(expected_identity, root=None)`. Its `reserve(space_id, owner, operation_id, request_sha256)` returns `Reservation(record, lease | None)`; `dispatch_once(lease, action, verify)` returns `DispatchResult(value, record)`. An identical replay returns history without a dispatch capability. Dispatch intent is durable before the action callback. `cancel_before_dispatch(lease)` applies only to the original live reservation capability; it is not a stale-lock clearing API. An explicit root is trusted offline-test injection, not a future browser request parameter. See `SHARED-BROWSER-SPACE.md` for the core contract.

Two spans must be designed separately:

1. **One dispatch:** hold ownership through subprocess completion, validation of exact operation evidence, and required durable receipt writes. The parent ERP lock and the nested automation subprocess must not independently acquire the same non-reentrant shared reservation. Either reserve only in the lowest reviewed executor or define explicit opaque child delegation with a fixed owner, operation and resource. An environment string or JSON field alone must not grant lease authority.
2. **A whole run:** continuous discovery expects exclusive use between steps as well as during each call. **The current primitive is operation-scoped; inter-step protection is absent.** A future run capability must retain the space across steps and bind each child operation, with no automatic takeover after timeout, process death, stop, or restart. Do not hold a SQLite write transaction open while doing browser work.

No generic lease/token, coordinator path, verifier choice or success flag should become an HTTP request parameter. Trusted adapters derive these internally after normal account, policy, target and authorization checks. Coordination is additional exclusion, not permission to navigate, upload, save, publish or take over user ownership.

## Terminal evidence and unknown results

Exit code zero, an output file existing, a syntactically valid JSON object, or a bare `status: blocked` does not establish a safe terminal result. In particular, discovery's `capture_evidence_or_scope_invalid` is assigned after dispatch; it cannot be treated as proof that no browser effects happened.

A reviewed verifier must bind evidence to the exact coordinator/resource/owner/operation/request/fence/nonce identity supplied to the action. It must validate the intended target, scope and adapter-specific result, then return the primitive's bound `TerminalEvidence`. `refused_before_effects` requires affirmative evidence that the relevant effects were not dispatched. A completed browser operation still does not prove product qualification, ERP business success or Amazon live status.

Timeouts, nonzero exits, missing/malformed output, changed scope, failed identity checks, verifier failure and failed receipt persistence must leave an unresolved barrier. Late output, elapsed time, PID absence, a new account/DATA directory, stop/cancel, or a renamed script must not release or replay it. Existing domain receipts and unknown history stay intact; any future reconciliation is a separately reviewed design, not deletion of a lock or creation of a fresh coordinator.

## Offline adoption tests and rollout gates

This slice does not run the real adapter adoption tests below. They are required before later claims of integration:

- Use fresh TEMP roots and an explicitly isolated test coordinator. Run child Python processes as different application accounts, with different DATA/project roots and mocked CLI aliases, but the same coordinator identity and TaskSpace. Start them concurrently behind a barrier; exactly one fake dispatch may occur. Different spaces may proceed independently.
- Use fake action callbacks and synthetic, exact-bound receipts. No EGO/Node/browser/network launch, paid model call, upload, save or publication is allowed. Avoid importing startup modules that create production DATA or launch workers.
- Kill a test child after reservation, after durable dispatch intent, and before result commit. Restart with new account/runtime paths and operation IDs; the space must stay blocked. Test identical replay, conflicting replay, coordinator deletion/corruption/replacement, unavailable storage, stale fences and forged/cross-operation evidence.
- Exercise valid completion, explicit pre-effect refusal, timeout, nonzero exit, missing/malformed output, zero exit with invalid receipt, post-dispatch `blocked`, changed binding and receipt-write failure. Verify only reviewed terminal evidence releases the participating scope.
- Test source and frozen command construction, the `runpy` import path, nested ERP observation/save/library spans, status/resume, all four discovery kinds, and whole-run inter-step interference separately. `portable_support.py:134` does not add the automation directory to `sys.path`; `packaging/build_portable.py:80,117-120` explicitly selects/copies adapter files. A new coordinator file is not automatically bundled or integrated.
- Keep production adapter defaults unchanged until every supported boundary adopts the same pinned protocol, packaging is verified, existing unknowns are reconciled through an approved process, and conflicting old/manual clients are quiesced. Require a separately authorized, new isolated real-browser verification before any production activation.

Report the actual coverage as cooperating same-Windows-user participants, with an explicit list of integrated entry points and exclusions. Standalone core tests do not close the production coordination gap or prove another computer's cold start.
