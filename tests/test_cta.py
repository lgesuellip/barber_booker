import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

os.environ.setdefault("TWILIO_AUTH_TOKEN", "dummy")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "dummy")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "dummy")

sys.modules.setdefault(
    "langgraph_sdk",
    types.SimpleNamespace(get_client=lambda **_: None),
)

from src.langgraph_whatsapp.channel import WhatsAppAgentTwilio

def test_send_whatsapp_message_cta(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "123")

    agent = WhatsAppAgentTwilio()
    monkeypatch.setattr(agent.twilio_client.messages, "create", lambda **kwargs: kwargs)

    captured = {}
    monkeypatch.setattr(agent, "_send_call_to_action", lambda to, text, url, title: captured.setdefault("args", (to, text, url, title)))

    body = {
        "text": "Need auth",
        "button": {"url": "https://auth", "text": "Auth", "use_cta": True}
    }
    agent.send_whatsapp_message("whatsapp:+999", body)

    assert captured["args"] == ("whatsapp:+999", "Need auth", "https://auth", "Auth")
