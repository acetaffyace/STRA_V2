"""Five deterministic offline scenarios used by the V1/P1 release gate."""
from __future__ import annotations


def scenario(name: str) -> tuple[int, list[dict], dict]:
    scenarios = {
        "live_service_regression": (92001, [
            {"review_id": "s1", "language": "english", "voted_up": False, "review": "The update causes network stutter and crashes."},
            {"review_id": "s2", "language": "english", "voted_up": True, "review": "Matches are fun when the network works."},
        ], {"expected_action": "FIX"}),
        "strong_positive_feature": (92002, [
            {"review_id": "s3", "language": "english", "voted_up": True, "review": "The soundtrack and visuals are excellent."},
            {"review_id": "s4", "language": "german", "voted_up": True, "review": "Beautiful atmosphere and music."},
        ], {"expected_action": "AMPLIFY"}),
        "explicit_feature_request": (92003, [
            {"review_id": "s5", "language": "english", "voted_up": True, "review": "Please add a photo mode and more tracks."},
            {"review_id": "s6", "language": "spanish", "voted_up": True, "review": "Add remapping options, please."},
        ], {"expected_action": "BUILD"}),
        "mixed_version_update": (92004, [
            {"review_id": "s7", "language": "english", "voted_up": False, "review": "The patch fixed crashes but added stutter."},
            {"review_id": "s8", "language": "english", "voted_up": True, "review": "New content is excellent."},
        ], {"expected_action": "FIX"}),
        "low_information_small_n": (92005, [
            {"review_id": "s9", "language": "english", "voted_up": True, "review": "Good."},
        ], {"expected_action": "UNSTABLE"}),
    }
    try:
        return scenarios[name]
    except KeyError as exc:
        raise ValueError(f"Unknown offline scenario: {name}") from exc


SCENARIO_NAMES = tuple((
    "live_service_regression", "strong_positive_feature", "explicit_feature_request",
    "mixed_version_update", "low_information_small_n",
))

