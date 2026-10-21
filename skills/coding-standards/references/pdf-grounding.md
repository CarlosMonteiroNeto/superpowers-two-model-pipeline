# PDF Grounding — Coding Standards (Algoritmos U1-U3)

## 1. Algorithms and Logic Essentials
- Sequence, decision, and repetition are the three canonical building blocks; every algorithm composes them.
- Boolean logic drives decisions and loop conditions; truth tables define AND, OR, and NOT outcomes.
- Entry -> Process -> Exit frames every program: read and validate inputs, transform data, emit outputs.
- An algorithm is a finite, ordered, unambiguous step sequence; a program is its encoding in a programming language.
- Pseudocode describes logic in structured natural language; flowcharts express the same logic with symbols and arrows.
- Top-down decomposition splits a problem into subproblems first, then refines each level before coding.

## 2. Control Structures and Types Essentials
- Primitive types include integer, real, character, string, and boolean; compound types aggregate them into arrays, records, or lists.
- Identifiers name variables and constants; naming rules plus initialization discipline prevent undefined values.
- Coercion is implicit type conversion by the language; casting is the explicit, programmer-requested conversion.
- Switch selects one branch among many constants; each case needs break (or explicit fall-through intent) to avoid unintended chaining.
- For repeats a known count, while checks before each iteration for a possibly-zero count, do-while checks after for at-least-once execution.
- Loop pitfalls include off-by-one bounds, missing termination updates, division-by-zero, and unvalidated ranges on input-driven counts.

## 3. Modularization Essentials
- A function returns a value to its caller; a procedure executes actions without returning a value.
- High cohesion keeps one module focused on one responsibility; low coupling minimizes dependencies between modules.
- Iteration repeats with an explicit loop state; recursion solves by self-calls that must shrink toward a base case.
- Local scope lives inside a block or routine, global scope is visible program-wide, static retains its value across calls.
- Value parameters copy data into the routine; reference parameters expose the caller variable for in-place updates.
- Pure routines avoid side effects: return values instead of mutating shared state and encapsulate any shared data explicitly.
