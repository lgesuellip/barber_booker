import os
from twilio.rest import Client

# Load required environment variables
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    raise RuntimeError("Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER")

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Replace with the recipient WhatsApp number (with 'whatsapp:' prefix)
RECIPIENT = os.getenv("RECIPIENT_NUMBER", "whatsapp:+123456789")


def send_google_cta():
    """Send a WhatsApp Call-To-Action button that opens Google."""
    action = client.content.v1.contents.CallToActionAction(
        {
            "type": "URL",
            "title": "Go to Google",
            "url": "https://www.google.com",
        }
    )

    twilio_cta = client.content.v1.contents.TwilioCallToAction(
        {
            "body": "Search the web",
            "actions": [action],
        }
    )

    types = client.content.v1.contents.Types({"twilio_call_to_action": twilio_cta})

    request = client.content.v1.contents.ContentCreateRequest(
        {
            "friendly_name": "cta_google",
            "language": "en",
            "types": types,
        }
    )

    content = client.content.v1.contents.create(request)

    client.messages.create(
        from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
        to=RECIPIENT,
        content_sid=content.sid,
    )


if __name__ == "__main__":
    send_google_cta()
