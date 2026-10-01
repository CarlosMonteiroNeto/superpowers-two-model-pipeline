# Reusable asset planning flow

Use this flow during brainstorming and planning after establishing the project
scope. It works for generic tooling tasks and ecosystem-specific product work.

## Resolve local capabilities first

1. Identify the project ecosystem, user-facing surfaces, locale when known,
   product type, explicit exclusions, and required checks from the request and
   repository.
2. Discover installed skills before considering any external skill. Match by
   skill description and declared task coverage. A missing required skill blocks
   a credible plan and is reported; an optional missing skill is recorded as
   an omission with its reason. Do not install skills implicitly.
3. Resolve the generic requirement profile plus only profiles whose declared
   applicability matches the project context. Do not infer a Flutter, form,
   authentication, payment, analytics, regional, or server requirement from a
   generic request. If applicability is genuinely ambiguous, ask one focused
   question.
4. Apply an opt-out only when the plan records its reason. Conflicting
   applicable requirements become questions; do not silently choose one.
   After conflicts and opt-outs, validate the dependency graph. A requirement
   whose dependencies were excluded is removed from the actionable set and
   reported as `{"type":"unresolved_dependency","requirement_id":"…","dependencies":["…"]}`.
   Unknown dependency IDs use the same question. Cycles remove their members
   and downstream dependents and produce
   `{"type":"dependency_cycle","requirement_ids":["…"]}` with sorted IDs.
   The resolver propagates unavailable dependencies to a fixed point and sorts
   dependency question IDs so profile order does not change the result.
5. For coverage still missing, consult already cached and explicitly available
   external skill sources. Installing external skills requires the user's
   explicit approval.

## Recall and select reusable assets

Use the initialized local catalog in deterministic read-only mode. Filter by
project ecosystem, category, compatibility, freshness, and dependency needs.
A valid empty result is a normal miss; malformed or unavailable catalog setup
is reported as a setup issue. Do not download source code while recalling.

A candidate is reusable only when source provenance, version, license,
compatibility evidence, and required dependency versions are known. Technical
checks and applicable requirements must pass before automatic adoption. A
score or popularity verdict alone never authorizes adoption. Unknown license or
compatibility evidence and dependency conflicts become questions. An update to
a pinned asset first produces a diff preview; local edits remain intact and
same-path conflicts require an explicit merge.

## Consolidated baseline for the plan

Before presenting the design or implementation plan, summarize together:

- required installed skills and any optional omissions;
- generic and applicable ecosystem profile IDs and versions;
- selected reusable assets pinned to immutable versions and source identities;
- requirements covered by assets and remaining checks;
- explicit exceptions and their reasons;
- unresolved applicability, provenance, license, compatibility, or merge
  questions.

Ask only for unresolved applicability, conflicts, and exceptions in this
baseline. Continue with the normal design and task-plan approval boundary.

## Fixture examples

A Python CLI maintenance task resolves the generic profile, its installed
Python/testing skills, and compatible local assets. It does not acquire Flutter
form validation, input masks, or Dart tooling requirements. If its required
Python skill is absent, planning records a blocking gap; a cached optional
formatting skill may be omitted without installation.

A Flutter sign-up form resolves the generic and UI profiles plus the Flutter
form profile because the ecosystem, UI, and product type match. It may reuse a
fresh, license-known Flutter asset after API, test, dependency, and local-edit
checks. A form mask stays separate from field validation. A mismatch in project
SDK support or a same-file update conflict is surfaced before adoption.

Generic fixtures validate contract behavior only. They do not establish
production support for Python or any other new ecosystem.
