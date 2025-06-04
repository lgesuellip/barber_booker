# channel.py
import base64, logging, requests
from abc import ABC, abstractmethod

from fastapi import Request, HTTPException
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

from src.langgraph_whatsapp.agent import Agent
from src.langgraph_whatsapp.config import (
    TWILIO_AUTH_TOKEN,
    TWILIO_ACCOUNT_SID,
    TWILIO_WHATSAPP_NUMBER,
)

LOGGER = logging.getLogger("whatsapp")


def twilio_url_to_data_uri(url: str, content_type: str = None) -> str:
    """Download the Twilio media URL and convert to data‑URI (base64)."""
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        raise RuntimeError("Twilio credentials are missing")

    LOGGER.info(f"Downloading image from Twilio URL: {url}")
    resp = requests.get(url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=20)
    resp.raise_for_status()

    # Use provided content_type or get from headers
    mime = content_type or resp.headers.get('Content-Type')

    # Ensure we have a proper image mime type
    if not mime or not mime.startswith('image/'):
        LOGGER.warning(f"Converting non-image MIME type '{mime}' to 'image/jpeg'")
        mime = "image/jpeg"  # Default to jpeg if not an image type

    b64 = base64.b64encode(resp.content).decode()
    data_uri = f"data:{mime};base64,{b64}"

    return data_uri

class WhatsAppAgent(ABC):
    @abstractmethod
    async def handle_message(self, request: Request) -> str: ...

class WhatsAppAgentTwilio(WhatsAppAgent):
    def __init__(self) -> None:
        if not (TWILIO_AUTH_TOKEN and TWILIO_ACCOUNT_SID and TWILIO_WHATSAPP_NUMBER):
            raise ValueError("Twilio credentials are not configured")
        self.agent = Agent()
        self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        self.from_number = f"whatsapp:{TWILIO_WHATSAPP_NUMBER}"

    def send_carousel(self, to: str) -> None:
        """Send a simple one-card carousel with a booking button."""
        content = self.client.content.v1.contents.create(
            friendly_name="barber_booking",
            language="en",
            types=[
                {
                    "type": "twilio/carousel",
                    "cards": [
                        {
                            "title": "Book your appointment",
                            "body": "Choose your slot on our website",
                            "actions": [
                                {
                                    "type": "link",
                                    "label": "Book now",
                                    "url": "https://example.com/booking",
                                }
                            ],
                        }
                    ],
                }
            ],
        )

        self.client.messages.create(
            from_=self.from_number,
            to=to,
            content_sid=content.sid,
        )

    async def handle_message(self, request: Request) -> str:
        form = await request.form()

        sender  = form.get("From", "").strip()
        content = form.get("Body", "").strip()
        if not sender:
            raise HTTPException(400, detail="Missing 'From' in request form")

        # Send carousel when the user explicitly requests booking options
        if content.lower() == "book":
            self.send_carousel(sender)
            twiml = MessagingResponse()
            twiml.message("We've sent you our booking options")
            return str(twiml)

        # Collect ALL images (you'll forward only the first one for now)
        images = []
        for i in range(int(form.get("NumMedia", "0"))):
            url   = form.get(f"MediaUrl{i}", "")
            ctype = form.get(f"MediaContentType{i}", "")
            if url and ctype.startswith("image/"):
                try:
                    images.append({
                        "url": url,
                        "data_uri": twilio_url_to_data_uri(url, ctype),
                    })
                except Exception as err:
                    LOGGER.error("Failed to download %s: %s", url, err)

        # Assemble payload for the LangGraph agent
        input_data = {
            "id": sender,
            "user_message": content,
        }
        if images:
            # Pass all images to the agent
            input_data["images"] = [
                {"image_url": {"url": img["data_uri"]}} for img in images
            ]

        reply = await self.agent.invoke(**input_data)

        twiml = MessagingResponse()
        
        # Check if reply is a dict with button information
        if isinstance(reply, dict) and "text" in reply and "button" in reply:
            # For WhatsApp interactive messages with buttons, we need to format the message
            # with the button as a link in the text
            message_text = f"{reply['text']}\n\n{reply['button']['text']}: {reply['button']['url']}"
            twiml.message(message_text)
        else:
            # Regular text message
            twiml.message(reply)
        
        return str(twiml)
