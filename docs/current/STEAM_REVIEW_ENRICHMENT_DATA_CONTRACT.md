# Steam Review Enrichment Data Contract

The fields `developer_response`, `timestamp_dev_responded`, `steam_purchase`, `received_for_free`, and `primarily_steam_deck` are Steam source metadata. Missing historical values are null, never false. The developer response is exact source text and is not passed through the LLM.

The fields are currently stored for future analysis and contextual inspection only. They do not currently affect analytical conclusions.

Player evidence and player FTS contain player review text only. Future analysis phases must define populations, denominators, bias limitations, support thresholds, and evidence requirements before activating any enrichment field.
