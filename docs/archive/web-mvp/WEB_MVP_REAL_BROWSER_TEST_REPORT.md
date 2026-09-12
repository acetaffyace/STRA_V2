# Web MVP Real Browser Test Report

The requested real-browser smoke could not be executed because the Codex in-app browser bridge reported: `privileged native pipe bridge is not available; browser-client is not trusted`.

HTTP contract verification was executed against the local FastAPI app with the MVP database. `GET /analysis/4012810/dashboard` returned HTTP 200 and reported:

- 500 reviews;
- `ANALYSIS_INCOMPATIBLE`;
- 0 validated classifications / 0% coverage;
- completed run ID present;
- design and evidence unavailable.

This report intentionally does not claim a browser visual pass.
