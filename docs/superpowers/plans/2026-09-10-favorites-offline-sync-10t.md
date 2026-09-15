# Plan: Offline-First Favorites List (10-task benchmark variant)

**Date:** 2026-09-10
**Spec:** `docs/superpowers/specs/2026-09-10-favorites-offline-sync-10t-spec.md`
**Source fixture:** `C:\Users\Carlos_Neto\Downloads\2026-09-10-favorites-offline-sync.md` (9 tasks) + §12 hardening task to induce 10.

> **Benchmark fixture notice.** Execute unmodified through both harnesses
> sequentially in fresh worktrees, same models. Do not edit tasks between runs.

## Overview

Favorites with local persistence, offline queue, last-write-wins sync.
Tiers: trivial 1-3, medium 4-6, hard 7-10.

## Global Constraints

- Flutter/Dart; `flutter test` + `flutter analyze` green per task.
- TDD: RED verified failing, then minimal GREEN.
- English-only internal artifacts.
- One commit per task with the listed message.

---

### Task 1: Favorite item model (Tier: trivial)

**Files:** Create `lib/models/favorite_item.dart`, `test/models/favorite_item_test.dart`
- [ ] Step 1: Write failing test `round-trips through JSON` (FavoriteItem id/favoritedAt, toJson/fromJson, ==).
- [ ] Step 2: Run `flutter test test/models/favorite_item_test.dart` — expect FAIL (FavoriteItem undefined).
- [ ] Step 3: Implement immutable class with toJson/fromJson/==/hashCode.
- [ ] Step 4: Re-run — expect PASS.
- [ ] Step 5: Commit `feat: add FavoriteItem model`.

### Task 2: Repository interface + in-memory (Tier: trivial)

**Files:** Create `lib/repositories/favorites_repository.dart`, `lib/repositories/local_favorites_repository.dart`, `test/repositories/local_favorites_repository_test.dart`
- [ ] Step 1: Write failing tests `add then list`, `remove deletes`.
- [ ] Step 2: Run focused test — expect FAIL.
- [ ] Step 3: Implement abstract + in-memory List-backed repo (no persistence).
- [ ] Step 4: Re-run — expect PASS.
- [ ] Step 5: Commit `feat: add favorites repository (in-memory)`.

### Task 3: Favorite toggle button (Tier: trivial)

**Files:** Create `lib/widgets/favorite_button.dart`, `test/widgets/favorite_button_test.dart`
- [ ] Step 1: Write widget test `tapping toggles icon`.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement stateless IconButton favorite/favorite_border with isFavorite+onToggle.
- [ ] Step 4: Re-run — expect PASS.
- [ ] Step 5: Commit `feat: add FavoriteButton widget`.

### Task 4: Local persistence (Tier: medium)

**Files:** Modify `lib/repositories/local_favorites_repository.dart`, extend test.
- [ ] Step 1: Write failing test `items survive re-creation` with fake KeyValueStore.
- [ ] Step 2: Run — expect FAIL (no `store` param).
- [ ] Step 3: Inject KeyValueStore, persist on add/remove.
- [ ] Step 4: Re-run — expect PASS.
- [ ] Step 5: Commit `feat: persist favorites locally`.

### Task 5: Favorites screen states (Tier: medium)

**Files:** Create `lib/screens/favorites_screen.dart`, `test/screens/favorites_screen_test.dart`
- [ ] Step 1: Write widget tests `spinner then list`, `error message on throw`.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement loading/error/data off repository.list(), render FavoriteButton per item.
- [ ] Step 4: Re-run — expect PASS.
- [ ] Step 5: Commit `feat: add favorites screen states`.

### Task 6: Offline queue (Tier: medium)

**Files:** Create `lib/services/offline_queue.dart`, `test/services/offline_queue_test.dart`
- [ ] Step 1: Write test `enqueue then drain replays in order`.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement FIFO ToggleAction enqueue/drain+clear.
- [ ] Step 4: Re-run — expect PASS.
- [ ] Step 5: Commit `feat: add offline action queue`.

### Task 7: Wire offline queue into repository (Tier: hard — gap deliberate)

**Files:** Modify `lib/repositories/local_favorites_repository.dart`, extend test.
- [ ] Step 1: Write test `toggling offline enqueues (pendingActionsCount==1)`.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement isOnline()+queue wiring; both-actions-queue straightforward; flag double-toggle collapse gap in commit notes, do not invent rule.
- [ ] Step 4: Re-run — expect PASS.
- [ ] Step 5: Commit `feat: enqueue toggles made while offline`.

### Task 8: Sync service last-write-wins (Tier: hard)

**Files:** Create `lib/services/favorites_sync_service.dart`, `test/services/favorites_sync_service_test.dart`
- [ ] Step 1: Write tests `local wins if newer`, `remote wins if newer`, `drain clears on success`.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement sync() draining queue to mocked remote, newer favoritedAt wins, clear only on full success.
- [ ] Step 4: Re-run — expect PASS.
- [ ] Step 5: Commit `feat: add sync service with last-write-wins`.

### Task 9: Integration on reconnect (Tier: hard)

**Files:** Modify `lib/screens/favorites_screen.dart`, extend test.
- [ ] Step 1: Write test `going online triggers sync and updates list`.
- [ ] Step 2: Run — expect FAIL.
- [ ] Step 3: Implement onConnectivityChanged listener calling sync() then refresh.
- [ ] Step 4: Run focused + `flutter test` full — expect PASS.
- [ ] Step 5: Commit `feat: wire offline sync into favorites screen`.

### Task 10: Empty-state + clear-all + regression gate (Tier: hard)

**Files:** Modify `lib/screens/favorites_screen.dart`, `lib/repositories/local_favorites_repository.dart`, extend tests.
- [ ] Step 1: Write tests `empty shows empty-state after load`, `clearAll empties store`.
- [ ] Step 2: Run — expect FAIL (clearAll undefined).
- [ ] Step 3: Implement empty-state + clearAll (clears persisted + queued toggles for deleted ids only; no collapse-rule invention).
- [ ] Step 4: Run `flutter test` + `flutter analyze` — expect green.
- [ ] Step 5: Commit `feat: add empty-state and clear-all gate`.

## Appendix: Benchmarking

Per task record input/output tokens, cache-hit vs miss, request count,
correction rounds, wall-clock (brief-ready → commit-approved). Tiers:
trivial 1-3, medium 4-6, hard 7-10. Headline: tokens per approved task.
Task 7 is the expected correction-round point on both harnesses.
