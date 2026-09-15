# Plan: Offline-First Favorites List

**Date:** 2026-09-10
**Save to (both repos, identical content):** `docs/superpowers/plans/2026-09-10-favorites-offline-sync.md`

> **Benchmark fixture notice — read before running.**
> This plan exists to be executed, unmodified, through two different
> harnesses for cost comparison:
> 1. `obra/superpowers` → `subagent-driven-development`
> 2. `CarlosMonteiroNeto/superpowers-two-model-pipeline` → `two-model-sdd-pipeline`
>
> Run it in a fresh worktree per harness, sequentially (never in parallel),
> same underlying models on both sides. Do not edit tasks between runs —
> any change invalidates the comparison. See **Appendix: Benchmarking
> Instructions** at the end for what to record.

## Overview

Add a "favorites" feature to the app: users can mark items as favorite,
the state persists locally, and syncs to a remote store when online, with
last-write-wins conflict resolution. Deliberately spans trivial → hard
complexity so both harnesses' cost profile shows up across the full range,
not just one tier.

## File Structure

| File | Responsibility |
|---|---|
| `lib/models/favorite_item.dart` | Data model for a favorited item (id, timestamp, dirty flag) |
| `lib/repositories/favorites_repository.dart` | Abstract repository interface |
| `lib/repositories/local_favorites_repository.dart` | In-memory + local-persistence implementation |
| `lib/services/favorites_sync_service.dart` | Remote sync + conflict resolution |
| `lib/services/offline_queue.dart` | Queues toggle actions made while offline |
| `lib/widgets/favorite_button.dart` | Toggle button widget |
| `lib/screens/favorites_screen.dart` | List screen: loading/error/data states |
| `test/models/favorite_item_test.dart` | Model serialization tests |
| `test/repositories/local_favorites_repository_test.dart` | Repository + persistence tests |
| `test/services/offline_queue_test.dart` | Offline queue tests |
| `test/services/favorites_sync_service_test.dart` | Sync + conflict tests |
| `test/widgets/favorite_button_test.dart` | Button widget test |
| `test/screens/favorites_screen_test.dart` | Screen states + integration test |

## Tasks

### Task 1: Favorite item model (Tier: trivial)
**Files:** `lib/models/favorite_item.dart`, `test/models/favorite_item_test.dart`

**Test first (RED):**
```dart
test('round-trips through JSON', () {
  final item = FavoriteItem(id: 'abc', favoritedAt: DateTime.utc(2026, 1, 1));
  final json = item.toJson();
  final restored = FavoriteItem.fromJson(json);
  expect(restored, equals(item));
});
```

**Implementation (GREEN):** Immutable class with `id` (String),
`favoritedAt` (DateTime), `toJson`/`fromJson`, `==`/`hashCode`.

**Verify:** `flutter test test/models/favorite_item_test.dart`
**Commit:** `feat: add FavoriteItem model`

---

### Task 2: Repository interface + in-memory implementation (Tier: trivial)
**Files:** `lib/repositories/favorites_repository.dart`,
`lib/repositories/local_favorites_repository.dart`,
`test/repositories/local_favorites_repository_test.dart`

**Test first (RED):**
```dart
test('add then list returns the item', () async {
  final repo = LocalFavoritesRepository();
  await repo.add(FavoriteItem(id: 'x', favoritedAt: DateTime.utc(2026,1,1)));
  expect(await repo.list(), hasLength(1));
});
test('remove deletes the item', () async { /* ... */ });
```

**Implementation (GREEN):** Abstract `FavoritesRepository` with
`add`/`remove`/`list`; in-memory `LocalFavoritesRepository` backed by a
`List<FavoriteItem>`. No persistence yet — that's Task 4.

**Verify:** `flutter test test/repositories/local_favorites_repository_test.dart`
**Commit:** `feat: add favorites repository (in-memory)`

---

### Task 3: Favorite toggle button (Tier: trivial)
**Files:** `lib/widgets/favorite_button.dart`,
`test/widgets/favorite_button_test.dart`

**Test first (RED):**
```dart
testWidgets('tapping toggles icon between outline and filled', (tester) async {
  bool isFavorite = false;
  await tester.pumpWidget(FavoriteButton(
    isFavorite: isFavorite,
    onToggle: () => isFavorite = !isFavorite,
  ));
  await tester.tap(find.byType(FavoriteButton));
  expect(isFavorite, isTrue);
});
```

**Implementation (GREEN):** Stateless widget, `IconButton` with
`Icons.favorite`/`Icons.favorite_border`, takes `isFavorite` + `onToggle`
callback. No repository knowledge — pure presentation.

**Verify:** `flutter test test/widgets/favorite_button_test.dart`
**Commit:** `feat: add FavoriteButton widget`

---

### Task 4: Local persistence for the repository (Tier: medium)
**Files:** `lib/repositories/local_favorites_repository.dart` (modify),
`test/repositories/local_favorites_repository_test.dart` (extend)

**Test first (RED):**
```dart
test('items survive repository re-creation (persisted)', () async {
  final repo1 = LocalFavoritesRepository(store: fakeStore);
  await repo1.add(FavoriteItem(id: 'y', favoritedAt: DateTime.utc(2026,1,1)));
  final repo2 = LocalFavoritesRepository(store: fakeStore);
  expect(await repo2.list(), hasLength(1));
});
```

**Implementation (GREEN):** Inject a `KeyValueStore` (wrap
`shared_preferences` or the project's existing local-storage package —
check what's already a dependency before adding a new one) and persist on
every `add`/`remove`. Use a fake in-memory `KeyValueStore` in tests.

**Verify:** `flutter test test/repositories/local_favorites_repository_test.dart`
**Commit:** `feat: persist favorites locally`

---

### Task 5: Favorites screen with loading/error/data states (Tier: medium)
**Files:** `lib/screens/favorites_screen.dart`,
`test/screens/favorites_screen_test.dart`

**Test first (RED):**
```dart
testWidgets('shows spinner while loading, then list on success', (tester) async {
  // pump with a repository whose list() Future has not resolved yet -> spinner
  // resolve it -> list renders
});
testWidgets('shows error message when list() throws', (tester) async { /* ... */ });
```

**Implementation (GREEN):** `StatefulWidget` (or the app's existing state
pattern — reuse whatever Task 8 of the earlier tier work established, if
present in this codebase) driving three states off
`FavoritesRepository.list()`. Each list item renders a `FavoriteButton`
from Task 3.

**Verify:** `flutter test test/screens/favorites_screen_test.dart`
**Commit:** `feat: add favorites screen states`

---

### Task 6: Offline queue for toggle actions (Tier: medium)
**Files:** `lib/services/offline_queue.dart`,
`test/services/offline_queue_test.dart`

**Test first (RED):**
```dart
test('enqueue then drain replays actions in order', () async {
  final queue = OfflineQueue();
  queue.enqueue(ToggleAction(id: 'a', favorite: true));
  queue.enqueue(ToggleAction(id: 'b', favorite: false));
  final replayed = <ToggleAction>[];
  await queue.drain((action) async => replayed.add(action));
  expect(replayed, hasLength(2));
});
```

**Implementation (GREEN):** Simple FIFO queue of `ToggleAction {id,
favorite}`, `enqueue`, `drain(Future<void> Function(ToggleAction))` that
processes and clears in order.

**Verify:** `flutter test test/services/offline_queue_test.dart`
**Commit:** `feat: add offline action queue`

---

### Task 7: Wire offline queue into the repository (Tier: hard — brief intentionally underspecified)
**Files:** `lib/repositories/local_favorites_repository.dart` (modify),
`lib/services/offline_queue.dart` (modify if needed),
`test/repositories/local_favorites_repository_test.dart` (extend)

**Test first (RED):**
```dart
test('toggling while offline enqueues instead of syncing immediately', () async {
  final repo = LocalFavoritesRepository(store: fakeStore, isOnline: () => false);
  await repo.add(FavoriteItem(id: 'z', favoritedAt: DateTime.utc(2026,1,1)));
  expect(repo.pendingActionsCount, equals(1));
});
```

**Implementation (GREEN):** When `isOnline()` is false, local writes still
apply immediately (Task 4 behavior unchanged) but also enqueue a
`ToggleAction` via the `OfflineQueue` from Task 6, instead of calling the
(not-yet-built) sync service.

**Note — brief gap, do not resolve without confirming:** this brief does
not specify what happens if the **same item** is toggled twice while
offline (e.g. favorited then unfavorited before reconnecting) — whether
both actions queue, or they should collapse to a no-op. Implement the
straightforward version (both actions queue, replayed in order) and flag
it in the task's commit message / review notes rather than guessing at
a collapse rule. This gap is deliberate — it's the task expected to need
a correction round.

**Verify:** `flutter test test/repositories/local_favorites_repository_test.dart`
**Commit:** `feat: enqueue toggles made while offline`

---

### Task 8: Remote sync service with last-write-wins conflict resolution (Tier: hard)
**Files:** `lib/services/favorites_sync_service.dart`,
`test/services/favorites_sync_service_test.dart`

**Test first (RED):**
```dart
test('local change wins when its timestamp is newer', () async {
  final result = resolveConflict(local: newerItem, remote: olderItem);
  expect(result, equals(newerItem));
});
test('remote change wins when its timestamp is newer', () async { /* ... */ });
test('sync drains the offline queue and clears it on success', () async { /* ... */ });
```

**Implementation (GREEN):** `FavoritesSyncService.sync()` drains the
`OfflineQueue` (Task 6), pushes each action to a (mocked in tests) remote
client, and on conflict picks whichever of local/remote `favoritedAt` is
newer. Clears the queue only after all actions succeed.

**Verify:** `flutter test test/services/favorites_sync_service_test.dart`
**Commit:** `feat: add sync service with last-write-wins`

---

### Task 9: Integration — wire screen, repository, queue, and sync together (Tier: hard, cross-cutting)
**Files:** `lib/screens/favorites_screen.dart` (modify),
`test/screens/favorites_screen_test.dart` (extend)

**Test first (RED):**
```dart
testWidgets('going online triggers a sync and updates the list', (tester) async {
  // start offline, toggle an item (queues), simulate reconnect,
  // assert sync() was called and the list reflects the synced state
});
```

**Implementation (GREEN):** Screen listens for connectivity changes (use
whatever connectivity mechanism already exists in the app; if none,
inject a simple `Stream<bool> onConnectivityChanged` for testability) and
calls `FavoritesSyncService.sync()` on reconnect, then refreshes the list.
This task touches every file from Tasks 1-8 — treat it as the interface
convergence point.

**Verify:** `flutter test test/screens/favorites_screen_test.dart && flutter test`
(full suite, to catch regressions across all 8 prior tasks)
**Commit:** `feat: wire offline sync into favorites screen`

---

## Appendix: Benchmarking Instructions

Not part of the native plan template — added for this comparison run.

1. Two fresh worktrees, one per harness, same base commit.
2. Same models configured on both sides before starting.
3. Run harness A (subagent-driven-development) task 1 → 9 in order, no
   manual intervention beyond what each harness's own gates require.
4. Repeat with harness B (two-model-sdd-pipeline) in its own worktree.
5. Per task, record: total input/output tokens, cache-hit vs. cache-miss
   tokens, request count, correction-round count, wall-clock time
   (brief-ready → commit-approved).
6. Expect Task 7 to be the key data point — it's the one task with a
   deliberately incomplete brief, so it's where a correction round is
   most likely on both harnesses. Compare cost-per-correction-round
   between the two, not just total cost.
7. Report per-task and tier-aggregated (trivial: 1-3, medium: 4-6, hard:
   7-9), plus the headline number: tokens per *approved* task.
