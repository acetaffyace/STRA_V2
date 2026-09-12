param([int]$Port = 8765)

$ErrorActionPreference = 'Stop'
& .\.venv311\Scripts\python.exe -m tooling.evals.player_voice.annotation_app `
  --input P0_5B_annotation_batch.jsonl `
  --output P0_5B_annotation_batch.annotated.jsonl `
  --draft P0_5B_external_model_draft.jsonl `
  --port $Port
