

def test_meta_lists_the_featured_voices(client):
    """The interface offers a handful of familiar voices."""
    payload = client.get("/api/v1/meta").json()
    assert payload["default_voice"] == "zh-CN-YunxiNeural"
    assert payload["default_voices"] == {
        "zh": "zh-CN-YunxiNeural",
        "en": "en-US-GuyNeural",
    }
    featured = payload["featured_voices"]
    assert 5 <= len(featured) <= 20
    assert any(v.startswith("en-US") for v in featured)
    assert any(v.startswith("en-GB") for v in featured)
    assert any(v.startswith("zh-CN") for v in featured)


def test_featured_voices_exist_in_the_engine(client):
    """Every offered voice is really available."""
    payload = client.get("/api/v1/meta").json()
    available = {voice["voice_id"] for voice in client.get("/api/v1/tts/voices").json()["voices"]}
    for voice_id in payload["featured_voices"]:
        assert voice_id in available
