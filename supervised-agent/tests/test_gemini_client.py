import json

from src.gemini_client import client, generate_mock_response


def test_gemini_client_uses_local_mock_by_default():
    response = client.models.generate_content(
        model="gemini-3-flash", contents="Assess matter intake"
    )
    payload = json.loads(response.text)
    assert payload["matter_type"] == "privacy"


def test_mock_response_stays_legal_ops_scoped():
    text = generate_mock_response("gemini-3-flash", "risk assessment")
    payload = json.loads(text)
    assert "findings" in payload
    assert payload["export_allowed"] is False
