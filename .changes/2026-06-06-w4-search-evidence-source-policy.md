---
"@intercal/core": patch
---

Tighten `search_evidence` source-policy handling so citation-only or summary-forbidden document
bodies are not searched or emitted, while title/citation metadata remains searchable.
