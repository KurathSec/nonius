# nonius

Compose the benchmark you already have — and find out for free whether you can.

- [Quickstart](quickstart.md)
- [The rulings](spec/rulings.md) — every composition decision, with an immutable id
- [Honesty](honesty.md) — what is measured, what is assumed, what is refused
- [Validation](validation.md) — the reference audit, and its negative result

A saturated benchmark is kept because every historical comparison was computed against it.
Switching instruments costs comparability; staying costs signal. nonius offers a third
move: compose the committed items into harder ones whose gold is a deterministic function
of the component golds, computed by the benchmark's own oracle. No examiner, no authored
items, no model calls.

It also refuses, and the refusal is the part with no precedent. Most item sets cannot be
composed, and the reason is rarely the one you would guess — see
[the liveness ruling](spec/rulings.md).
