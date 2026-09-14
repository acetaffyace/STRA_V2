"""Seed an untracked presentation-only acceptance database.

The fixture uses aggregate values from the reviewed HELLDIVERS 2 semantic run
and synthetic source-review payloads. It contains no real Steam review text and
is intended only for local browser contract/visual checks.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.api.senti_next import db, storage
from apps.api.senti_next.classification_materialization import (
    bind_materialization_to_analysis_run,
    bind_measurement_to_analysis_run,
    create_classification_materialization,
)
from apps.api.senti_next.classifier_taxonomy import baseline_classifier_taxonomy
from apps.api.senti_next.llm import classification_identity
from apps.api.senti_next.research_population_snapshot import freeze_analysis_run_population
from apps.api.senti_next.research_core import build_snapshot_research_report
from apps.api.senti_next.semantic_measurement_bundle import create_measurement_bundle


RUN_ID = "b92ba25b9f9b4230945d8eb6f92126ff"
APP_ID = 553850


def _report() -> dict:
    population = [{"recommendationid": f"fixture-{index:03d}", "review": f"Synthetic frozen source review {index} for local presentation acceptance.", "language": "english", "voted_up": index < 70, "timestamp_created": 1700000000 - index, "timestamp_updated": 1700000000 - index, "steam_purchase": True, "author": {"playtime_at_review": 10, "playtime_forever": 100}} for index in range(80)]
    metadata = {"collection_complete": False, "truncated_by_max_reviews": True, "stop_reason": "max_reviews_reached", "coverage_start_time": None, "coverage_end_time": None, "coverage_status": "incomplete", "sampling_contract": {"app_id": APP_ID, "start_time": None, "end_time": None, "languages": ["english"], "review_type": "all", "purchase_type": "all", "collection_order": "recent", "include_offtopic_activity": False, "max_reviews": 80}}
    return build_snapshot_research_report(population, metadata=metadata)


def _semantic(population_fingerprint: str, materialization_id: str) -> dict:
    counts = [("other/meme", 23), ("other/general", 15), ("online_community/multiplayer_experience", 11), ("gameplay/mechanics", 10), ("gameplay/balance", 7), ("technical/bugs", 6), ("gameplay/difficulty", 4), ("developer_updates/patch_quality", 3), ("gameplay/progression", 3), ("monetization_value/value_for_money", 3)]
    issues = {"gameplay/balance": 7, "technical/bugs": 6, "content_design/replayability": 2, "developer_updates/patch_quality": 2, "gameplay/ai": 2, "gameplay/difficulty": 2}
    requests = {"content_design/customization": 1, "developer_updates/update_frequency": 1, "online_community/social_features": 1, "technical/bugs": 1, "technical/compatibility": 1}
    rows = []
    for key, count in counts:
        rows.append({"taxonomy_key": key, "topic_n": count, "topic_share": count / 80, "observed_classified_topic_share": count / 80, "primary_n": count, "primary_share": count / 80, "issue_n": issues.get(key, 0), "issue_share": issues.get(key, 0) / 80, "request_n": requests.get(key, 0), "request_share": requests.get(key, 0) / 80, "topic_validation": {"status": "PROVISIONAL"}, "issue_validation": {"status": "PROVISIONAL"}, "request_validation": {"status": "PROVISIONAL"}})
    for key in sorted((set(issues) | set(requests)) - {row["taxonomy_key"] for row in rows}):
        rows.append({"taxonomy_key": key, "topic_n": 0, "topic_share": 0.0, "observed_classified_topic_share": 0.0, "primary_n": 0, "primary_share": 0.0, "issue_n": issues.get(key, 0), "issue_share": issues.get(key, 0) / 80, "request_n": requests.get(key, 0), "request_share": requests.get(key, 0) / 80, "topic_validation": {"status": "PROVISIONAL"}, "issue_validation": {"status": "PROVISIONAL"}, "request_validation": {"status": "PROVISIONAL"}})
    return {
        "schema_version": "semantic-measurement-result-v1", "run_id": RUN_ID, "classification_materialization_id": materialization_id, "measurement_bundle_id": "measurement_bundle_afa0fd5e732d8b6476d3457df3447143", "claim_status": "PROVISIONAL", "population_n": 80, "materialized_n": 80, "classified_n": 80, "validated_llm_n": 80, "fallback_n": 0, "missing_n": 0, "classification_coverage": 1.0, "coverage_status": "FULL", "topics": rows, "limitations": ["Observed classified review share; not a player-population prevalence estimate."], "provenance": {"measurement_bundle_id": "measurement_bundle_afa0fd5e732d8b6476d3457df3447143", "measurement_status": "PROVISIONAL", "validation_status": "UNAVAILABLE", "taxonomy_version": "sentinext-taxonomy-v1", "taxonomy_fingerprint": "418f27caf82290b258ded444a3f1eec8b7975a0f0989e248965e7279adb71b7d", "classifier_provider": "deepseek", "classifier_model_id": "deepseek-v4-flash", "classifier_prompt_version": "steam_review_insights_v16_basic_labels", "classifier_schema_version": "review-classification-schema-v1", "population_fingerprint": population_fingerprint}, "semantic_measurement_result_fingerprint": "350a102670a0e9bc43adf5b16cf05fc9e60d606d0e48f8824cc1957f74af1695"}


def seed() -> None:
    db.init_db()
    storage.save_starred_game(APP_ID, "HELLDIVERS 2", {"header_image": None}, None, [], ["Action"], ["Multiplayer"])
    storage.create_general_analysis_run(RUN_ID, APP_ID, config={"analysis": {"analysis_mode": "current_snapshot"}}, requested_languages=["english"], requested_review_count=80, provider="deepseek", model_id="deepseek-v4-flash", prompt_version="steam_review_insights_v16_basic_labels", taxonomy_version="sentinext-taxonomy-v1", analysis_version="stage4c-fixture")
    storage.transition_general_analysis_run(RUN_ID, "running", phase="analyzing")
    reviews = [{"recommendationid": f"fixture-{index:03d}", "review_id": f"fixture-{index:03d}", "review": f"Synthetic frozen source review {index} for local presentation acceptance.", "language": "english", "voted_up": index < 70, "timestamp_created": 1700000000 - index} for index in range(80)]
    snapshot = freeze_analysis_run_population(run_id=RUN_ID, app_id=APP_ID, reviews=reviews)
    contract = baseline_classifier_taxonomy()
    bundle = create_measurement_bundle(taxonomy_contract=contract, measurement_status="PROVISIONAL", limitations=["not_formally_validated"], bundle_id="measurement_bundle_afa0fd5e732d8b6476d3457df3447143")
    with db.get_connection() as conn:
        from sqlalchemy import text
        conn.execute(text("UPDATE semantic_measurement_bundles SET classifier_provider='deepseek', classifier_model_id='deepseek-v4-flash', is_active=1 WHERE bundle_id=:id"), {"id": bundle["bundle_id"]})
    bundle = {**bundle, "classifier_provider": "deepseek", "classifier_model_id": "deepseek-v4-flash", "classifier_prompt_version": "steam_review_insights_v16_basic_labels", "classifier_schema_version": "review-classification-schema-v1"}
    label_keys = ["other/meme"] * 23 + ["other/general"] * 15 + ["online_community/multiplayer_experience"] * 11 + ["gameplay/mechanics"] * 10 + ["gameplay/balance"] * 7 + ["technical/bugs"] * 6 + ["gameplay/difficulty"] * 4 + ["developer_updates/patch_quality"] * 3 + ["gameplay/progression"] * 3 + ["monetization_value/value_for_money"] * 3
    labels = {}
    for review, key in zip(reviews, label_keys):
        identity = classification_identity(review, None, provider=bundle["classifier_provider"], model_id=bundle["classifier_model_id"], prompt_version=bundle["classifier_prompt_version"], taxonomy_contract=contract)
        labels[review["review_id"]] = {"payload": {"subcategories": [key], "issue_subcategories": [], "request_subcategories": [], "evidence": {}}, "label_origin": "llm", "validated": True, "provider": bundle["classifier_provider"], "model_id": bundle["classifier_model_id"], "prompt_version": bundle["classifier_prompt_version"], "taxonomy_version": contract.taxonomy_version, "taxonomy_snapshot_id": contract.snapshot_id, "taxonomy_fingerprint": contract.taxonomy_fingerprint, "review_hash": identity["review_hash"], "classification_input_hash": identity["classification_input_hash"]}
    materialization = create_classification_materialization(run_id=RUN_ID, app_id=APP_ID, all_reviews=reviews, bundle=bundle, taxonomy_contract=contract, labels=labels)
    bind_materialization_to_analysis_run(RUN_ID, materialization["materialization_id"])
    bind_measurement_to_analysis_run(RUN_ID, bundle)
    semantic = _semantic(snapshot["population_fingerprint"], materialization["materialization_id"])
    quantitative = _report()
    unified = {"schema_version": "unified-research-result-v1", "run_id": RUN_ID, "quantitative": quantitative, "semantic": semantic, "result_fingerprint": "8871964458deadb096e82aee7c1a668ac811a0483524f004c46cecf531ec5fd3"}
    storage.finalize_general_analysis_run(RUN_ID, APP_ID, {"run_id": RUN_ID, "app_id": APP_ID, "name": "HELLDIVERS 2", "analysis_population_count": 80, "population_fingerprint": snapshot["population_fingerprint"], "requested": 80, "language": "english", "filter": "recent"}, {"five_questions": {}}, [], counts={"available_matching_reviews": 821512, "retrieved_count": 80, "deduplicated_count": 80, "analysis_population_count": 80, "valid_review_count": 80, "classified_count": 80}, research_report=quantitative, semantic_status={"status": "available"}, semantic_measurement_result=semantic, unified_research_result=unified)
    discovery = {"schema_version": "semantic-discovery-materialization-v1", "materialization_id": "8981ae13c2e36802dff360a8cf02e4db9ec55d8059f2ffeeeccd97541419518d", "status": "completed", "discovery_fingerprint": "e3789e2cf69b6e2dace56a03d12f625cf3c421d39d37c1c71bbaf5bb165154e4", "dense_region_n": 2, "rare_region_n": 0, "outlier_review_n": 48, "clustered_review_share": 0.4, "unclustered_review_share": 0.6, "stability_distribution": {"stable": 39, "moderate": 11}, "taxonomy_audit": {"review_level_label_coverage": 1.0, "well_covered_region_n": 0, "mixed_existing_labels_region_n": 2, "potential_gap_region_n": 0, "insufficient_taxonomy_coverage_region_n": 48}, "regions": [], "interpretation": {"dry_run_status": "completed", "real_status": "BLOCKED_PROVIDER_TIMEOUT", "attempted_region_n": 2, "completed_region_n": 0, "timed_out_region_n": 2}}
    with db.get_connection() as conn:
        from sqlalchemy import text
        conn.execute(text("INSERT OR REPLACE INTO semantic_discovery_materializations(materialization_id, structure_run_id, structure_fingerprint, context_schema_version, context_fingerprint, semantic_index_id, research_run_id, population_fingerprint, semantic_index_fingerprint, report_json, status, completed_at) VALUES (:id, :sr, :sf, :csv, :cf, :si, :rr, :pf, :sif, :report, 'completed', datetime('now'))"), {"id": discovery["materialization_id"], "sr": "fixture-structure", "sf": "fixture-structure-fp", "csv": "fixture-v1", "cf": "fixture-context-fp", "si": "fixture-index", "rr": RUN_ID, "pf": snapshot["population_fingerprint"], "sif": "fixture-index-fp", "report": json.dumps(discovery)})
    print(json.dumps({"run_id": RUN_ID, "population_n": 80, "population_fingerprint": snapshot["population_fingerprint"], "materialization_id": materialization["materialization_id"]}))


if __name__ == "__main__":
    seed()
