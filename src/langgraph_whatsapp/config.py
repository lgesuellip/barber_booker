from os import environ
import logging

LOGGER = logging.getLogger(__name__)

LANGGRAPH_URL = environ.get("LANGGRAPH_URL")
ASSISTANT_ID = environ.get("LANGGRAPH_ASSISTANT_ID", "agent")
CONFIG = environ.get("CONFIG") or "{}"
TWILIO_AUTH_TOKEN = environ.get("TWILIO_AUTH_TOKEN")
TWILIO_ACCOUNT_SID = environ.get("TWILIO_ACCOUNT_SID")
TWILIO_PHONE_NUMBER = environ.get("TWILIO_PHONE_NUMBER")
ARCADE_USER_ID = environ.get("ARCADE_USER_ID")
