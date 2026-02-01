from app.application.llm_response_worker.service import LlmResponseWorker


def test_parses_json_array_marker():
    response = "JSON_ARRAY [{\"action\": \"OPEN_LONG\", \"symbol\": \"BTC\"}]"
    worker = LlmResponseWorker()
    result = worker.parse(response)
    assert result.success is True
    assert len(result.ideas) == 1
    assert result.ideas[0].action.value == "OPEN_LONG"
    assert result.ideas[0].symbol == "BTC"


def test_parses_json_code_block():
    response = "```json\n{\"action\": \"HOLD\", \"symbol\": \"ETH\"}\n```"
    worker = LlmResponseWorker()
    result = worker.parse(response)
    assert result.success is True
    assert result.ideas[0].action.value == "HOLD"
    assert result.ideas[0].symbol == "ETH"


def test_extracts_considerations():
    response = "JSON_CONSIDER [{\"symbol\": \"SOL\", \"reasoning\": \"test\"}]"
    worker = LlmResponseWorker()
    result = worker.parse(response)
    assert result.considerations == [{"symbol": "SOL", "reasoning": "test"}]


def test_fails_on_invalid_response():
    response = "no json here"
    worker = LlmResponseWorker()
    result = worker.parse(response)
    assert result.success is False
