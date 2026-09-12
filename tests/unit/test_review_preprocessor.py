import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[2] / "apps" / "api" / "senti_next" / "review_preprocessor.py"
SPEC = importlib.util.spec_from_file_location("review_preprocessor_under_test", MODULE_PATH)
review_preprocessor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = review_preprocessor
SPEC.loader.exec_module(review_preprocessor)


def test_normalization_is_comparison_only():
    assert review_preprocessor.normalize_for_comparison("  HÉLLO\r\n  WORLD  ") == "héllo\n world"
    assert review_preprocessor.normalize_for_comparison("ＡＢＣ\rfoo") == "abc\nfoo"


def test_repeated_lines_keep_first_natural_text_and_distinguish_versions():
    preprocessor = review_preprocessor.ReviewPreprocessor(mode="active")
    result = preprocessor.process(1, {"review_id": "r1", "review": "hello\nhello\npatch 1.2\npatch 1.3"})
    assert result.processed_text == "hello\npatch 1.2\npatch 1.3"
    assert result.removed_line_count == 1
    assert "repeated_line_removed" in result.flags


def test_mixed_art_keeps_useful_text():
    preprocessor = review_preprocessor.ReviewPreprocessor(mode="active", art_removal=True, line_dedup=False, paragraph_dedup=False)
    result = preprocessor.process(1, {"review_id": "r1", "review": "██████████\n██████████\ngame crashes"})
    assert result.processed_text == "game crashes"
    assert "ascii_art_candidate" in result.flags
    assert "ascii_art_removed" in result.flags


def test_short_useful_text_is_never_skipped_by_length():
    preprocessor = review_preprocessor.ReviewPreprocessor(mode="active")
    for text in ("crashes", "bad fps", "闪退", "掉帧"):
        result = preprocessor.process(1, {"review_id": text, "review": text})
        assert "short_text" in result.flags
        assert result.skip_llm is False


def test_nonlexical_skip_is_enabled_by_default_and_keeps_exceptions():
    default = review_preprocessor.ReviewPreprocessor(mode="active").process(1, {"review_id": "a", "review": "........."})
    enabled = review_preprocessor.ReviewPreprocessor(mode="active", nonlexical_skip=True).process(1, {"review_id": "b", "review": "........."})
    assert "pure_nonlexical" in default.flags
    assert default.skip_llm is True
    assert enabled.skip_llm is True
    assert review_preprocessor.ReviewPreprocessor(mode="active").process(1, {"review_id": "c", "review": "10/10"}).skip_llm is False


def test_exact_duplicate_group_is_scoped_by_app_id():
    preprocessor = review_preprocessor.ReviewPreprocessor(mode="active")
    same_app = preprocessor.process_reviews(1, [{"review_id": "a", "review": "Good"}, {"review_id": "b", "review": "good"}])
    other_app = preprocessor.process_reviews(2, [{"review_id": "c", "review": "Good"}])
    assert same_app.representatives == ["a"]
    assert same_app.members_by_representative["a"] == ["a", "b"]
    assert other_app.representatives == ["c"]


def test_off_mode_preserves_text_and_does_not_cleanup():
    result = review_preprocessor.ReviewPreprocessor(mode="off").process(1, {"review_id": "r", "review": "x\nx"})
    assert result.processed_text == "x\nx"
    assert result.removed_line_count == 0
