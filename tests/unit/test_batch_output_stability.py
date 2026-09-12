from apps.api.senti_next import llm
from apps.api.senti_next.batch_planner import classify_provider_error
from apps.api.senti_next.providers.errors import ProviderFailure


def test_batch_output_budget_scales_with_review_count():
    assert llm.estimate_batch_output_tokens(1) == 1152
    assert llm.estimate_batch_output_tokens(10) == 2304
    assert llm.estimate_batch_output_tokens(40) == 6144
    assert llm.estimate_batch_output_tokens(80) == 11264
    assert llm.estimate_batch_output_tokens(100) == 13824


def test_long_review_keeps_head_and_tail():
    text = "A" * 6000 + "M" * 1000 + "Z" * 2000
    result = llm._sanitize_review_text(text)
    assert result.startswith("A" * 6000)
    assert result.endswith("Z" * 2000)
    assert "REVIEW TRUNCATED" in result
    assert len(result) == 6000 + len("\n[... REVIEW TRUNCATED: middle omitted ...]\n") + 2000


def test_truncation_is_classified_separately():
    error = ProviderFailure("OUTPUT_TRUNCATED", "cut off", {"finish_reason": "length"})
    assert classify_provider_error(error) == "OUTPUT_TRUNCATED"
