from __future__ import annotations

import pytest

from apps.api.senti_next.providers.circuit import ProviderOperationCircuit
from apps.api.senti_next.providers.errors import ProviderFailure


def test_provider_circuit_blocks_pending_calls_after_systemic_failure():
    circuit = ProviderOperationCircuit(cooldown_seconds=60)
    circuit.open("deepseek:test")
    with pytest.raises(ProviderFailure) as exc:
        circuit.check("deepseek:test")
    assert exc.value.code == "PROVIDER_SERVER"
    circuit.close("deepseek:test")
    circuit.check("deepseek:test")

