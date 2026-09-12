# Steam Review Enrichment v1 — Audit

The Steam review API payload already carries the five requested source fields and the repository preserves the complete payload in `reviews.data`. Before this phase, canonical SQL columns and a safe API contract were missing. Existing purchase/Steam Deck segmentation was also reading these fields; that path is now inert for v1.

There is no broad review snapshot subsystem. This phase therefore adds current canonical values only and does not introduce a history subsystem.

The existing external-content player FTS index projects only `review_text`; developer responses are not indexed. Existing evidence verification receives player text only.
