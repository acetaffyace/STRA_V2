# V1/P1 Known Limitations

- External provider behavior is not revalidated in this autonomous run. This is deferred as `EXTERNAL_PROVIDER_REVALIDATION` and is not a release blocker.
- Offline fixture labels are deterministic development labels, not human Gold and not provider output.
- Codex fixture heuristics are not a model-quality benchmark.
- Historical subcategory precision remains approximately 0.24; taxonomy overprediction is not redesigned here.
- First-pass LLM sentiment remains unavailable.
- Steam reviews have self-selection and language coverage bias.
- Small-N and rare-language observations remain unstable/unavailable where denominators do not support a claim.
- FastAPI `BackgroundTasks` remains local-process execution; restart recovery is explicit, but this is not a distributed durable queue.
- SQLite remains single-host/local-first and is not a multi-user production service.
- Existing frontend lint warnings and Pydantic deprecation warnings remain non-blocking technical debt.

