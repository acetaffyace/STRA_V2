# P0.5b Annotation Checklist

For every real source review:

- [ ] Read the complete review without model output or prior labels.
- [ ] Mark sentiment, including mixed/neutral/uncertain where appropriate.
- [ ] Mark issue presence; if present, select all justified issue labels.
- [ ] Mark explicit feature-request presence; do not infer it from dislike.
- [ ] Select all justified request labels.
- [ ] Capture exact source evidence spans where required.
- [ ] Record ambiguity or `needs_adjudication`; use `exclude` only with a reason.
- [ ] Preserve app ID, review ID, exact text, language, and source hash.
- [ ] For calibration records, complete an independent pass before discussion.
