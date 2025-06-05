# channel.py
import base64
import logging
import json
from abc import ABC, abstractmethod

import requests
from fastapi import Request, HTTPException
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

from src.langgraph_whatsapp.agent import Agent
from src.langgraph_whatsapp.config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
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
    mime = content_type or resp.headers.get("Content-Type")

    # Ensure we have a proper image mime type
    if not mime or not mime.startswith("image/"):
        LOGGER.warning(f"Converting non-image MIME type '{mime}' to 'image/jpeg'")
        mime = "image/jpeg"  # Default to jpeg if not an image type

    b64 = base64.b64encode(resp.content).decode()
    data_uri = f"data:{mime};base64,{b64}"

    return data_uri


class WhatsAppAgent(ABC):
    @abstractmethod
    async def handle_message(self, request: Request) -> str:
        """Handle an incoming FastAPI request and return TwiML XML"""
        raise NotImplementedError

    @abstractmethod
    async def process_form(self, form: dict) -> str | dict:
        """Process a parsed Twilio form payload and return text reply"""
        raise NotImplementedError


class WhatsAppAgentTwilio(WhatsAppAgent):
    def __init__(self) -> None:
        if not (TWILIO_AUTH_TOKEN and TWILIO_ACCOUNT_SID):
            raise ValueError("Twilio credentials are not configured")
        self.agent = Agent()
        self.twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    async def handle_message(self, request: Request) -> str:
        form = await request.form()
        message_text = await self.process_form(form)

        twiml = MessagingResponse()
        twiml.message(message_text)
        return str(twiml)

    async def process_form(self, form: dict) -> str | dict:
        sender = form.get("From", "").strip()
        content = form.get("Body", "").strip()
        if not sender:
            raise HTTPException(400, detail="Missing 'From' in request form")

        images = []
        for i in range(int(form.get("NumMedia", "0"))):
            url = form.get(f"MediaUrl{i}", "")
            ctype = form.get(f"MediaContentType{i}", "")
            if url and ctype.startswith("image/"):
                try:
                    images.append(
                        {
                            "url": url,
                            "data_uri": twilio_url_to_data_uri(url, ctype),
                        }
                    )
                except Exception as err:
                    LOGGER.error("Failed to download %s: %s", url, err)

        input_data = {
            "id": sender,
            "user_message": content,
        }
        if images:
            input_data["images"] = [
                {"image_url": {"url": img["data_uri"]}} for img in images
            ]

        # Invoke the agent to process the message
        reply = await self.agent.invoke(**input_data)
        return self._format_reply(reply)

    def _format_reply(self, reply):
        """Normalize assistant responses for WhatsApp delivery.

        If the assistant returns a dictionary with a ``button`` field, keep the
        structure intact so ``send_whatsapp_message`` can generate a WhatsApp
        button using Twilio's ``persistent_action`` parameter. When the
        assistant returns a JSON string, attempt to parse it so the button can
        be extracted correctly. Otherwise convert the reply to a plain string.
        """

        LOGGER.debug("Formatting reply: %s", reply)

        if isinstance(reply, dict) and "text" in reply and "button" in reply:
            LOGGER.debug("Reply already formatted with button")
            return reply

        if isinstance(reply, str):
            try:
                parsed = json.loads(reply)
                if isinstance(parsed, dict) and "text" in parsed and "button" in parsed:
                    LOGGER.debug("Parsed JSON reply successfully")
                    return parsed
            except json.JSONDecodeError:
                LOGGER.debug("Failed to parse reply as JSON")
                pass

        LOGGER.debug("Returning plain string reply")
        return str(reply)

    def send_whatsapp_message(self, to: str, body: str | dict) -> None:
        """Send a WhatsApp message via Twilio.

        ``body`` may be a plain string or a dictionary containing ``text`` and a
        ``button`` with a ``url``. In the latter case we use Twilio's
        ``persistent_action`` field so the link appears as a tappable button in
        WhatsApp. Set ``include_url`` inside the ``button`` dictionary to
        ``True`` if the raw URL should also be appended to the message text.
        """

        if not TWILIO_PHONE_NUMBER:
            raise RuntimeError("TWILIO_PHONE_NUMBER not configured")

        params = {
            "from_": f"whatsapp:{TWILIO_PHONE_NUMBER}",
            "to": to,
        }

        if isinstance(body, dict):
            text = body.get("text", "")
            button = body.get("button", {})
            if isinstance(button, dict) and button.get("url"):
                # Use template message for auth buttons
                self._send_template_message(
                    to=to,
                    text=text,
                    url=button["url"],
                    template_sid="HX8203e2ad9ade23ede0b373fefdcee1eb",
                )
                return
            params["body"] = text
        else:
            params["body"] = body

        LOGGER.debug("Sending WhatsApp message with params: %s", params)
        self.twilio_client.messages.create(**params)

    def _send_template_message(self, to: str, text: str, url: str, template_sid: str) -> None:
        """Send a WhatsApp message using a pre-approved template with variables."""
        
        LOGGER.debug(f"Sending template message with SID: {template_sid}")
        
        # Create the content variables for the template
        content_variables = {
            "1": text,  # {{reply_text}}
            "2": url,   # {{auth_link}}
        }
        
        params = {
            "from_": f"whatsapp:{TWILIO_PHONE_NUMBER}",
            "to": to,
            "content_sid": template_sid,
            "content_variables": json.dumps(content_variables),
        }
        
        LOGGER.debug("Sending WhatsApp template message with params: %s", params)
        self.twilio_client.messages.create(**params)

    def _send_carousel_message(self, to: str, text: str, url: str, button_text: str) -> None:
        """Send a WhatsApp carousel message with an interactive button."""
        
        # Create the URL action for the button
        action = self.twilio_client.content.v1.contents.CardAction(
            {
                "type": "URL",
                "title": button_text[:25],  # Max 25 chars for carousel buttons
                "url": url,
            }
        )
        
        # Create the carousel card
        card = self.twilio_client.content.v1.contents.TwilioCard(
            {
                "title": "Calendar Authorization",
                "body": text[:160],  # Max 160 chars for carousel body
                "media": ["https://www.twilio.com/assets/icons/twilio-icon-512_maskable.png"],  # Required media
                "actions": [action],
            }
        )
        
        # Create the carousel content
        twilio_carousel = self.twilio_client.content.v1.contents.TwilioCarousel(
            {
                "cards": [card],
            }
        )
        
        # Create the content types
        types = self.twilio_client.content.v1.contents.Types(
            {"twilio_carousel": twilio_carousel}
        )
        
        # Create the content request
        request = self.twilio_client.content.v1.contents.ContentCreateRequest(
            {
                "friendly_name": "carousel_auth",  # ephemeral template
                "language": "en",
                "types": types,
            }
        )
        
        LOGGER.debug("Creating Twilio carousel template: %s", request.to_dict())
        content = self.twilio_client.content.v1.contents.create(request)
        
        LOGGER.debug("Sending carousel message with content SID: %s", content.sid)
        self.twilio_client.messages.create(
            from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
            to=to,
            content_sid=content.sid,
        )
