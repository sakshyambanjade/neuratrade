from services.llm_quality import (
    ActionDistributionMonitor,
    extract_first_json_object,
    has_repetition_loop,
    validate_decision_payload,
)
from services.prompting import render_prompt, template_hash


def test_render_prompt_contains_paper_trading_context():
    prompt = render_prompt(
        market={"symbol": "BTCUSDT"},
        indicators={"rsi_14": 50},
        portfolio={"cash": 1000},
        risk={"dry_run": True},
    )

    assert "paper-trading" in prompt
    assert "BTCUSDT" in prompt
    assert template_hash()


def test_extract_first_json_object_recovers_prose_wrapped_json():
    data = extract_first_json_object('Here is the answer: {"action":"HOLD","confidence":0.5}')

    assert data["action"] == "HOLD"


def test_validate_decision_payload_flags_semantic_errors():
    events = validate_decision_payload(
        {
            "action": "BUY",
            "confidence": 1.5,
            "position_size_pct": 0,
            "reasoning": "short",
            "stop_loss": 110,
            "take_profit": 90,
        },
        current_price=100,
    )

    assert {event.hallucination_type for event in events} >= {
        "confidence_out_of_range",
        "position_size_out_of_range",
        "reasoning_too_short",
        "invalid_buy_brackets",
    }


def test_repetition_and_action_distribution_monitors():
    assert has_repetition_loop("buy now buy now buy now buy now buy now")
    monitor = ActionDistributionMonitor(window=4, max_share=1.0)

    assert [monitor.observe("HOLD") for _ in range(4)][-1] is True
