from __future__ import annotations

from apps.api.senti_next.runtime_diagnostics import diagnose_runtime


def test_runtime_diagnostics_reports_validated_environment(monkeypatch):
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    result = diagnose_runtime()
    assert result["missing_required_packages"] == []
    assert result["ready"] is True

