from services.latency import FixedLatencyModel, UniformLatencyModel


def test_fixed_latency_model_returns_configured_value():
    assert FixedLatencyModel(42).sample_ms() == 42


def test_uniform_latency_model_is_seedable():
    first = UniformLatencyModel(min_ms=10, max_ms=20, seed=7)
    second = UniformLatencyModel(min_ms=10, max_ms=20, seed=7)

    assert [first.sample_ms() for _ in range(3)] == [second.sample_ms() for _ in range(3)]
