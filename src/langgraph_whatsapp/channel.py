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

        LOGGER.info(f"Formatting reply - Type: {type(reply)}, Content: {reply}")

        if isinstance(reply, dict) and "text" in reply and "button" in reply:
            LOGGER.info("Reply already formatted with button")
            return reply

        if isinstance(reply, str):
            # Check if the string contains a JSON object with button
            # First try to find JSON in the string
            if '{\n    "text":' in reply and '"button":' in reply:
                try:
                    # Extract JSON from the string
                    json_start = reply.find('{\n    "text":')
                    json_str = reply[json_start:]
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict) and "text" in parsed and "button" in parsed:
                        LOGGER.info("Extracted and parsed JSON reply successfully as button message")
                        return parsed
                except json.JSONDecodeError as e:
                    LOGGER.error(f"Failed to parse extracted JSON: {e}")
            
            # Try parsing the whole string as JSON
            try:
                parsed = json.loads(reply)
                if isinstance(parsed, dict) and "text" in parsed and "button" in parsed:
                    LOGGER.info("Parsed entire reply as JSON button message")
                    return parsed
            except json.JSONDecodeError:
                LOGGER.debug("Reply is not JSON, treating as plain text")
                pass

        LOGGER.info("Returning plain string reply")
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

        LOGGER.info(f"send_whatsapp_message called - to: {to}, body type: {type(body)}, body: {body}")

        params = {
            "from_": f"whatsapp:{TWILIO_PHONE_NUMBER}",
            "to": to,
        }

        if isinstance(body, dict):
            text = body.get("text", "")
            button = body.get("button", {})
            LOGGER.info(f"Dict body - text: {text}, button: {button}")
            if isinstance(button, dict) and button.get("url"):
                LOGGER.info(f"Sending template message for auth button")
                # Use template message for auth buttons
                self._send_template_message(
                    to=to,
                    text=text,
                    url=button["url"],
                    template_sid="HXc2abe9968746afb615cd602f8d85b6a5",
                )
                return
            params["body"] = text
        else:
            params["body"] = body

        LOGGER.info("Sending regular WhatsApp message with params: %s", params)
        self.twilio_client.messages.create(**params)

    def _send_template_message(self, to: str, text: str, url: str, template_sid: str) -> None:
        """Send a WhatsApp message using a pre-approved template with variables."""
        
        # Remove https:// prefix if present
        if url.startswith("https://"):
            url = url[8:]
        
        LOGGER.info(f"Sending template message with SID: {template_sid}")
        LOGGER.info(f"Template variables - reply_text: {text}, auth_link: {url}")
        
        try:
            # Create the content variables for the template
            # Using the exact variable names from your template
            content_variables = {
                "auth_text": text,
                "auth_link": url,
            }
            
            params = {
                "from_": f"whatsapp:{TWILIO_PHONE_NUMBER}",
                "to": to,
                "content_sid": template_sid,
                "content_variables": json.dumps(content_variables),
            }
            
            LOGGER.info("Sending WhatsApp template message with params: %s", params)
            message = self.twilio_client.messages.create(**params)
            LOGGER.info(f"Template message sent successfully: {message.sid}")
        except Exception as e:
            LOGGER.error(f"Failed to send template message: {str(e)}")
            # Fall back to regular text message
            LOGGER.info("Falling back to regular text message")
            self.twilio_client.messages.create(
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=to,
                body=f"{text}\n\nAuthorization link: {url}"
            )

