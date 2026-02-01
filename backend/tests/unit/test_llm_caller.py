from app.application.llm_caller.service import _build_openai_messages, extract_chart_images


def test_build_openai_messages_without_images():
    messages = _build_openai_messages("hello", [])
    assert messages == [{"role": "user", "content": "hello"}]


def test_build_openai_messages_with_images():
    images = [{"image_url": "https://example.com/chart.png"}]
    messages = _build_openai_messages("prompt", images)
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert content[0] == {"type": "text", "text": "prompt"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == "https://example.com/chart.png"


def test_extract_chart_images_filters_input_images():
    payload = {
        "chart_snapshots": [
            {"type": "input_image", "image_url": "https://example.com/one.png", "ticker": "BTC"},
            {"type": "ignored", "image_url": "https://example.com/two.png"},
        ]
    }
    images = extract_chart_images(payload)
    assert images == [{"image_url": "https://example.com/one.png", "ticker": "BTC", "interval": None}]
