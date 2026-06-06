---
"intercal": patch
---

`get_entity(..., at_date=...)` now filters returned claim facts by valid-time instead of returning
every active fact for the entity. The corpus quality verifier also checks the Workstream 4
`get_entity ChatGPT as_of` proof for facts that fall outside the requested point-in-time window.
