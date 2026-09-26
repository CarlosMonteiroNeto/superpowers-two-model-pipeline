# Codex compatibility review of the complete two-model pipeline

Date: 2026-09-25. Reviewed checkout: `596951fa0da14b0010998c29c2810bff4f2e8b02`.
Repository: `CarlosMonteiroNeto/superpowers-two-model-pipeline`.

## Review basis and limits

After `git fetch origin`, local `main`, `origin/main`, and the remote default
branch all resolved to the reviewed commit. Ahead/behind was `0/0` and the
checkout was clean. Another local worktree/branch exists; its changes are not
part of this review. In particular, its model configuration must not be
mistaken for the configuration on `main`.

This review follows `README-LLM.md` and `CONTEXT.md` through the actual scripts,
role definitions, prompts, skills, packaging paths, and existing test surfaces.
Documentation describes intent; executable behavior takes precedence when they
disagree. Findings below distinguish direct Codex incompatibilities from
existing defects that would carry into a Codex port.

Local evidence: Codex CLI `0.156.1`; Git Bash `5.3.15`; Python `3.12.10`.
Git Bash can resolve `python3`, `git`, `rtk`, `codex`, and `gh`; `jq` was not
found in that shell. PowerShell resolves the npm `codex.ps1` wrapper, whereas
Git Bash resolves the npm `codex` wrapper. A native executable must be resolved
deliberately before a Python subprocess is used on Windows.

The current official Codex manual was fetched using the OpenAI Docs helper.
CLI help was checked for fresh execution, resume, output schemas, and App
Server. No paid model run, application implementation, install, global config
change, commit, push, or session deletion was performed. This is a source and
contract review with small offline reproductions, not an end-to-end runtime
certification.

## Findings

P1 means a release blocker for the proposed Codex runtime. P2 means a necessary
compatibility or reliability adaptation. Source line numbers refer to the
reviewed commit.

| ID | Priority / kind | Evidence | Failure and required adaptation |
|---|---|---|---|
| C01 | P1, Codex | `scripts/check-superpowers:22`; `skills/using-superpowers/SKILL.md:8`; `agent/flutter-pipeline.md:11` | Startup assumes the OpenCode vendor checkout, invokes its install/reset flow, and asks to restart OpenCode. Codex needs a package-aware entry point and read-only capability check. An installed plugin cache must never be treated as a mutable vendor checkout. |
| C02 | P1, distribution | `scripts/package-codex-plugin.sh:235`; `skills/brainstorming/scripts/orient-llm:17` | The portal archive selects `.codex-plugin`, assets, skills, README, license, and conduct files; it omits the root harness README, context, root scripts, and `agent/`. Its orientation script expects the omitted README. The current installed Git-marketplace bundle does contain these files: this is a portal-package defect, not a claim that the installed bundle is missing them. Make every delivery route self-contained. |
| C03 | P1, Codex | `scripts/dispatch:25,63,95,120` under `skills/two-model-sdd-pipeline` | Launch, prompt attachment, event parsing, and session capture are OpenCode-specific. Changing `OPENCODE_BIN` to `codex` cannot work. Add an explicit backend with Codex argv, stdin, JSONL, and final-output handling. |
| C04 | P1, Codex | `agent/two-model-coder.md:2-8`; reviewer and director equivalents; `README-LLM.md:469` | OpenCode YAML `mode`, `variant`, permissions, and provider-qualified model names are not Codex configuration. Main currently defines Terra/low and Sol/high, while the README/CONTEXT describe DeepSeek. Resolve model and effort explicitly for each role, validate availability, and record the actual configuration. |
| C05 | P1, Codex | `agent/two-model-coder.md:7`; `agent/two-model-reviewer.md:7`; `agent/two-model-task-generator.md:7` | OpenCode permissions do not transfer. Workspace write access alone does not enforce no-git/no-delegation/scoped commands; read-only access alone does not forbid tests. Use Codex sandbox policy, deterministic tool guards, explicit role instructions, and post-run integrity checks. Hooks are guardrails, not an OS security boundary. |
| C06 | P1, Codex + inherited | `parse_review.py:117,178,198,219`; `coder-gate:137-169`; `task-run:200` | Both semantic parsers require OpenCode text events. The review parser can also salvage APPROVED from malformed JSON. Normalize provider output first and validate exactly one final result with strict schemas and task/attempt identity. Never route from arbitrary stream text. |
| C07 | P1, inherited | `coder-gate:324-326`; `flutter-app-pipeline/scripts/green-gate:90,146-148` | Both paths swallow reviewer dispatch errors with `|| true`. Flutter also treats a failed commit as nothing to commit and continues toward review. Require successful candidate creation before review. A transport failure must remain a review-pending infrastructure condition and must not trigger a new coder round or consume an earlier verdict. |
| C08 | P1, inherited | `run-pipeline:434-448,457` | Closing dispatch exit zero is immediately recorded as `final_review`, and push follows without parsing the director's assessment. Structural rejection or a plan changed during closing can therefore be treated as closure. Add an explicit final verdict tied to the reviewed HEAD and plan revision; re-open work when requested. |
| C09 | P1, inherited | `task-run:256-279,326-349`; `wave-next:5-8` | Each worktree director can independently append the same next task ID or edit a divergent tracked plan. The scheduler's isolated-episode rule does not serialize episodes already running inside a wave. Make the director return proposals and let one script transaction allocate IDs and modify the canonical plan. |
| C10 | P1, identity | `worktree-alloc:26,38,48`; `worktree-release:28,30`; `pipeline-workspace:46` | Workspaces use plan basenames, but task branches and worktrees use only numeric IDs. Two plans or Codex tasks in the same repository can collide; basename-only plan names also collide. Namespace all identities by repository, canonical plan path, and run, and verify ownership before reuse/release. |
| C11 | P1, inherited recovery | `dispatch:61,95,174`; `dispatch-retry:9-15`; `run-pipeline:344-375` | A stale session file can survive a fresh failed launch; most nonzero process exits are blindly retried; there is no run-level owned-process cancellation protocol. Distinguish pre-start transient failure from ambiguous post-start execution, persist identity atomically, and stop only owned processes. |
| C12 | P2, context | `brief-scaffold:29,78-140` | The scaffold emits task fields but omits global constraints and task `interfaces`/`verification`. It prints relative references to skills and unquoted absolute runner paths. Fresh Codex workers need a complete curated package with explicit source roots, worktree root, and safe commands. |
| C13 | P1, toolchain | `brief-scaffold:29,122-132`; `red-form-check:32,98`; `resolve-toolchain:64`; `package.json` | All briefs suggest a Flutter runner, while RED supports Flutter/Dart/Python/Go only and detection advertises Node/Rust too. This repository has `package.json` without npm test/lint scripts. A Codex port needs explicit runner descriptors and preflight validation, not marker-only commands followed by endless correction. |
| C14 | P2, Windows | `run-gates:29-38`; `final-gate:171`; `lib/path-normalize.sh`; `brief-scaffold:122` | String splitting cannot preserve quoted command arguments and executable paths with spaces. Bash and Windows Python use different path forms. Retain argv arrays internally and provide a PowerShell launcher into an explicitly selected Git Bash runtime. |
| C15 | P2, lifecycle | `session-clean:38-40`; `worktree-release:59`; `README-LLM.md:237` | Cleanup invokes OpenCode session deletion and removes handles even on failure. Worktree release removes ignored task evidence after ledger merge, without exporting all logs/session manifests. Preserve evidence before release; retire only run-owned handles and avoid private Codex database manipulation. |
| C16 | P1, multi-toolchain | `worktree-alloc:74`; `integrate:75`; `final-gate:49`; `gate-entry-for` | A child receives only the last gate entry; integration/final verification select the first gate entry. A mixed project can be checked against the wrong language. Copy resolved toolchains and validate every affected toolchain during integration/closure. |
| C17 | P2, drift | `skills/using-superpowers/references/codex-tools.md:17`; actual collaboration-tool contract | The reference claims full-history forks accept model overrides. The active tool contract explicitly forbids those overrides. It also encourages manual spawns where the pipeline needs script-owned dispatch. Keep native SDD guidance distinct from the deterministic Codex pipeline. |
| C18 | P2, documentation gate | `doc-check:20-28` | The check only examines the last commit and accepts any README instead of both required READMEs. A branch-wide Codex change can escape this check. Compare the run's fixed base through the candidate HEAD and verify both documents when runtime contracts change. |
| C19 | P2, instruction lifecycle | `using-superpowers`, `brainstorming`, `writing-plans`, `two-model-sdd-pipeline` skills | Generic skill startup/approval/delegation procedures can recursively restart planning inside workers. Codex `AGENTS.md`, plugin skills, global instructions, and configured tools are inherited inputs. Provide a worker-role boundary, pin the bundle, and report incompatible effective policy before dispatch. |
| C20 | P2, evidence accuracy | `README-LLM.md`, `CONTEXT.md`, role files, current scripts | Intent and implementation diverge on model selection, statelessness versus resume, reviewer retention, no-op tasks, package downloads, RTK bypass, and integration strategy. The Codex docs must identify current guarantees and tested limitations rather than copy old descriptions. |

Paths without a directory prefix in the table refer to
`skills/two-model-sdd-pipeline/scripts/`.

## Offline reproductions

Using `parse_review.py` directly, without invoking any model:

1. Feed a documented Codex `item.completed` / `agent_message` containing a
   valid APPROVED JSON result into `extract_from_log`: result is `None`.
2. Feed `{"verdict": "APPROVED", broken` into `extract_verdict`: result is
   `{'verdict': 'APPROVED'}`. The fallback can accept invalid/incomplete output.

The local `orient-llm` preflight succeeds when invoked through Git Bash. The
earlier PowerShell call at root `scripts/orient-llm` was the wrong path and
invocation; the actual file is `skills/brainstorming/scripts/orient-llm`.

## Coverage of the complete flow

| Stage | Disposition for Codex | Findings / requirements |
|---|---|---|
| Installation, discovery, updates, orientation | Adapt | C01, C02, C19; immutable runtime bundle and Codex launcher |
| Phase 1a requirements and Category Skeleton | Preserve intent; adapt entry | Derive the tooling category from this request; prevent worker re-entry |
| Phase 1b architecture and persistent context | Preserve | English artifacts; complete spec and plan; no dependence on chat memory |
| Phase 1c UI design | Conditional preservation | `apple-design` applies to product UI tasks; not to this CLI migration |
| Phase 2a package/template research | Preserve algorithms; adapt environment | Script/network dependencies and credentials checked separately from Codex login; Tavily availability is not assumed |
| Phase 2b human selection | Preserve | Existing user decisions survive handoff; do not repeat authorization |
| Phase 2c plan creation and optional fusion | Adapt validation | Strict DAG/paths/spec/runner checks; fusion stays pre-runtime and explicitly selected |
| Dependency resolution / `pub-sync` | Preserve with explicit writable paths | `pub get` downloads packages; Phase 2 lockfile-only claims need correction |
| Workspace/gate preflight | Adapt | C10, C13, C14, C16; fail before any model work on unsupported setup |
| BRIEF | Adapt | C12, C19; include global constraints, interfaces, verification, precise runner |
| RED / operator dispatch | Adapt | C03-C06, C11, C13; structured status and fresh evidence |
| GREEN / formatting / scope / commit | Preserve script ownership; strengthen boundaries | C05, C07, C14, C16; Codex worker cannot authorize a commit |
| Review package and independent review | Adapt transport and validation | Full diff plus tests, spec context, strict result, independent session |
| CORRECTIVE / ARBITRATE | Adapt | C09; script-applied proposals; bounded re-escalation preserved |
| Waves, worktrees, integration | Adapt identity/lifecycle; retain deterministic scheduling | C10, C11, C15, C16; all shared writes accounted for |
| Final gate and holistic review | Adapt | C08, C18; exact candidate revision and final verdict |
| Push / PR / desktop handoff | Adapt | Explicit publication mode; no assumed native app API available from shell |
| Resume, compaction, cancellation, retention | Adapt | C11, C15; task-family sessions plus durable script state |
| RTK | Preserve raw-exit contract; close command-path gaps | C12-C14; model-visible command output compressed; machine evidence stays raw |
| Jev Sites 1-5 and catalog | Preserve semantics; bind provenance | Advisory only; separate credentials/timeouts; never dispatch authority |
| Packaging and acceptance | Adapt | C02, C19, C20; test extracted packages as well as source checkout |

## Programmatic execution options

| Mechanism | Directly controlled by script? | Fit |
|---|---|---|
| `codex exec --json` / explicit-ID `exec resume` | Yes | Recommended for the existing Bash/Python engine; CLI lifecycle and schema output match its subprocess boundaries. |
| Codex TypeScript SDK | Yes | Valid alternative with start/resume/run APIs; adds Node/library integration without a requirement for it here. |
| Codex Python SDK (`openai-codex`) | Yes | Current official docs describe a stable SDK using App Server with a pinned runtime. Reconsider if typed streaming and active steering become primary requirements. |
| Direct App Server JSON-RPC | Yes | Exposes thread/turn lifecycle and archive operations; requires a maintained bidirectional protocol client. Avoid building that additional control layer for the first port. |
| Native conversation subagents | Model calls collaboration tools | Suitable for interactive delegation; no documented external spawn entry point was established that gives an arbitrary script this chat's native subagent relationship. Do not claim it is impossible internally. |
| Model coordinator calling workers | No, relative to this requirement | Introduces an LLM into routing and dispatch; excluded. |

The recommended workers are real independent Codex agent sessions, not fake
OpenCode agents and not children of this desktop conversation. Desktop tree
linkage/appearance is not a promised contract. There is no need to enable
model-directed multi-agent delegation for script fan-out.

## Official references consulted

- [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
  — stdin prompts, JSONL events, output schemas, explicit session resume.
- [Developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
  — CLI options; installed `--help` is the local executable contract.
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)
  — TypeScript and Python programmatic interfaces.
- [App Server](https://learn.chatgpt.com/docs/app-server)
  — thread/turn APIs, permissions, notifications, archive lifecycle.
- [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
  — native model-directed delegation and role configuration.
- [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
  — inherited instructions and discovery limits.
- [Hooks](https://learn.chatgpt.com/docs/hooks)
  — command/edit interception and explicit coverage limitations.
- [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
  — developer instructions, model/effort, hooks, and feature configuration.

No end-to-end compatibility claim is justified yet. The accompanying spec and
plan define the implementation and evidence required for that claim.
