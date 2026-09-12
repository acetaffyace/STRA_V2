# Web MVP Root Cause Report

For app `4012810`, the local database contains 500 reviews and a completed compatibility result. The result has a `five_questions` shell, but the attached run reports `classified_count=0`; no analysis design is attached and evidence is unavailable.

Root causes:

1. Compatibility-result existence was treated as analysis readiness.
2. Review ingestion and semantic classification were not represented separately in the Web state.
3. Missing Steam author/playtime fields were coerced into zeros, producing misleading Purchase and Active cards and library-bucket labels.
4. Legacy metadata did not consistently carry mode/source/window/run provenance.

Fixes: added the authoritative dashboard readiness contract, made `ANALYSIS_INCOMPATIBLE` block analytical rendering, added explicit unavailable states, changed library labels to factual Steam-library ranges, and stamped future live runs with provider/source/window/run metadata.
