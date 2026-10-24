"""Optional provider contract and malformed response behavior; no live calls."""
from datetime import date

import pytest

from hkrbc_agent.retrieval import Hit
from hkrbc_agent.routing import ModelRouter, ModelSettings
from hkrbc_agent.security import Principal, Role
from hkrbc_agent.store import Document


def hit():
    return Hit(Document(document_id="official-example", version="1.0", title="Capital background",
        section="Synthetic test section", url="https://www.ia.org.hk/en/example.html",
        reviewed_at=date(2026, 10, 24), status="verified_baseline", text="Capital evidence for testing.",
        provenance="Synthetic original fixture.", redistribution="Synthetic test fixture."), 1.0)


def test_external_request_disables_storage_and_bounds_output(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-unit-test-key")
    calls = []
    def transport(url, body, headers):
        calls.append((url, body, headers))
        return {"choices": [{"message": {"content": "A short background summary."}}]}
    router = ModelRouter(ModelSettings(external_enabled=True, external_model="configured-test-model"), transport)
    text, provider = router.summarize(Principal("reviewer", Role.REVIEWER), "capital background", [hit()], mode="external", approved=True)
    assert text == "A short background summary."
    assert provider == "approved-external-openai"
    assert calls[0][1]["store"] is False
    assert calls[0][1]["max_completion_tokens"] == 512
    assert "temperature" not in calls[0][1]


@pytest.mark.parametrize("response", [{}, {"choices": []}, {"choices": None}, None])
def test_malformed_external_responses_fail_with_controlled_error(monkeypatch, response):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-unit-test-key")
    router = ModelRouter(ModelSettings(external_enabled=True, external_model="configured-test-model"), lambda *args: response)
    with pytest.raises(ValueError, match="External model response"):
        router.summarize(Principal("reviewer", Role.REVIEWER), "capital background", [hit()], mode="external", approved=True)


def test_malformed_local_response_fails_with_controlled_error():
    router = ModelRouter(ModelSettings(local_model="configured-local-model"), lambda *args: {})
    with pytest.raises(ValueError, match="Local model response"):
        router.summarize(Principal("analyst", Role.ANALYST), "capital background", [hit()])
