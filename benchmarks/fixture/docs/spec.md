# Benchmark Fixture Spec

A pure-Dart utility package used as the deterministic target of the
pipeline parallelism benchmark. Every feature is an independent pure
function in its own file under `lib/src/`, so the ten tasks have no
predecessors and pairwise-disjoint `touches`.

The package ships with stubs only: each function throws
`UnimplementedError` until its task implements it. The single baseline
test (`test/smoke_test.dart`) only asserts the entrypoints are exported,
so the pristine suite is green and every task produces a genuine red.

## §1 slugify

`String slugify(String input)` lowercases the input, collapses every run
of non-alphanumeric characters to a single hyphen, and trims leading and
trailing hyphens. An empty or all-punctuation input returns `""`.

## §2 isPalindrome

`bool isPalindrome(String input)` compares the input to its reverse after
removing non-alphanumeric characters and lowercasing. The empty string is
a palindrome.

## §3 chunk

`List<List<T>> chunk<T>(List<T> items, int size)` splits a list into
consecutive chunks of at most `size` elements; the final chunk may be
shorter and an empty list yields `[]`. A `size` of zero or less throws
`ArgumentError`.

## §4 romanToInt

`int romanToInt(String numeral)` converts a valid Roman numeral to its
integer value, including the subtractive pairs `IV`, `IX`, `XL`, `XC`,
`CD`, and `CM`.

## §5 camelToSnake

`String camelToSnake(String input)` converts camelCase or PascalCase to
snake_case, splitting acronym boundaries (`HTTPServer` -> `http_server`).
An input that is already snake_case is returned unchanged.

## §6 wordCount

`Map<String, int> wordCount(String input)` counts whitespace-separated
words case-insensitively, keying the result by the lowercase word.

## §7 clampInt

`int clampInt(int value, int min, int max)` returns `value` bounded to the
inclusive range. A range where `min > max` throws `ArgumentError`.

## §8 binarySearch

`int binarySearch(List<int> sorted, int target)` returns the index of
`target` in an ascending sorted list, or `-1` when it is absent. An empty
list returns `-1`.

## §9 formatBytes

`String formatBytes(int bytes)` renders a byte count with one decimal
place and a unit suffix (`B`, `KB`, `MB`, `GB`), using 1024 as the step.

## §10 parseDuration

`Duration parseDuration(String input)` parses a compact duration such as
`1h30m`, `45s`, or `500ms`, summing the `h`, `m`, `s`, and `ms` components.
An unrecognized string throws `FormatException`.
