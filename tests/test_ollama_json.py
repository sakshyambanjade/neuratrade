import json

import httpx

from services.ollama_client import OllamaClient, OllamaDecisionError, parse_ollama_decision


def test_ollama_client_returns_valid_json_decision():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["format"]["required"] == [
            "action",
            "confidence",
            "position_size_pct",
            "reasoning",
            "stop_loss",
            "take_profit",
        ]
        return httpx.Response(
            200,
            json={
                "response": (
                    '{"action":"BUY","confidence":0.72,"position_size_pct":0.15,'
                    '"reasoning":"Momentum confirmed","stop_loss":0.02,"take_profit":0.04}'
                )
            },
        )

    client = OllamaClient(base_url="http://ollama.test", transport=httpx.MockTransport(handler))

    decision = client.decide("Decide BTC trade")

    assert decision.action == "BUY"
    assert decision.confidence == 0.72
    assert decision.position_size_pct == 0.15
    assert decision.stop_loss == 0.02
    assert decision.take_profit == 0.04


def test_ollama_parser_rejects_invalid_json():
    try:
        parse_ollama_decision({"response": "BUY with high confidence"})
    except OllamaDecisionError as exc:
        assert "valid JSON" in str(exc)
    else:
        raise AssertionError("invalid JSON should raise OllamaDecisionError")


def test_ollama_timeout_returns_hold_fallback():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = OllamaClient(base_url="http://ollama.test", transport=httpx.MockTransport(handler))

    decision = client.decide("Decide BTC trade")

    assert decision.action == "HOLD"
    assert decision.confidence == 0.0
    assert decision.position_size_pct == 0.0
    assert "unavailable" in decision.reasoning


def test_ollama_parser_normalizes_common_model_variants():
    decision = parse_ollama_decision(
        {
            "response": (
                "```json\n"
                '{"action":"HOLD","confidence":50,"position_size_pct":20,'
                '"reasoning":"The safest paper trading action is hold while indicators are incomplete.",'
                '"stop_loss":null,"take_profit":null}'
                "\n```"
            )
        }
    )

    assert decision.action == "HOLD"
    assert decision.confidence == 0.5
    assert decision.position_size_pct == 0.0
    assert decision.stop_loss == 0.0
    assert decision.take_profit == 0.0
