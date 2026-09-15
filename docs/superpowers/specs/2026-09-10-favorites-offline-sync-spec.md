# Offline-First Favorites List — Spec

**Date:** 2026-09-10
**Plan:** `docs/superpowers/plans/2026-09-10-favorites-offline-sync.md`
**JSON plan:** `docs/superpowers/plans/2026-09-10-favorites-offline-sync-plan.json`

## §1 Goal

Add a favorites feature: users mark items as favorite, state persists
locally, syncs to a remote store when online, last-write-wins conflict
resolution on `favoritedAt`.

## §2 Scopes and tiers

- Trivial (§3–§5): model, in-memory repository, toggle button.
- Medium (§6–§8): local persistence, screen states, offline queue.
- Hard (§9–§11): offline wiring with deliberate brief gap, sync service,
  integration on reconnect.

## §3 FavoriteItem model

- Immutable class `FavoriteItem { String id; DateTime favoritedAt; }`.
- `toJson`/`fromJson` round-trip; `==`/`hashCode` by value.

## §4 FavoritesRepository interface

- Abstract `FavoritesRepository` with `add`, `remove`, `list`.
- `LocalFavoritesRepository` in-memory backed by `List<FavoriteItem>`.
- No persistence at this stage.

## §5 FavoriteButton widget

- Stateless, `IconButton` with `Icons.favorite` / `Icons.favorite_border`.
- Inputs: `isFavorite`, `onToggle`. No repository knowledge.

## §6 Local persistence

- Inject `KeyValueStore`; persist on every `add`/`remove`.
- Wrap `shared_preferences` or the project's existing local-storage
  package — check dependencies before adding a new one.
- Tests use a fake in-memory `KeyValueStore`; items survive re-creation.

## §7 FavoritesScreen states

- Drives loading / error / data states off `FavoritesRepository.list()`.
- Each list item renders a `FavoriteButton` (§5).
- Reuse the app's existing state pattern if present.

## §8 OfflineQueue

- FIFO `ToggleAction { String id; bool favorite; }`.
- `enqueue`, `drain(Future<void> Function(ToggleAction))` in order, clears.

## §9 Offline wiring (deliberate brief gap)

- `LocalFavoritesRepository` takes `isOnline()` + `OfflineQueue`.
- Offline writes apply locally immediately, plus enqueue `ToggleAction`.
- Gap: same item toggled twice offline — implement straightforward
  version (both actions queue, replayed in order), flag in commit/review
  notes. Do not invent a collapse rule.

## §10 Sync service (last-write-wins)

- `FavoritesSyncService.sync()` drains `OfflineQueue`, pushes each action
  to a remote client (mocked in tests).
- Conflict: newer `favoritedAt` wins (local or remote).
- Clears queue only after all actions succeed.

## §11 Integration on reconnect

- Screen listens for connectivity changes (existing mechanism, else inject
  `Stream<bool> onConnectivityChanged`).
- On reconnect: `sync()`, then refresh list. Cross-cutting over §3–§10.

## Global constraints

- Flutter/Dart; `flutter test` + `flutter analyze` green per task.
- TDD: RED test first, verified failing, then minimal GREEN implementation.
- English-only internal artifacts; UI copy follows product locale.
- One commit per task with the message listed in the plan.
