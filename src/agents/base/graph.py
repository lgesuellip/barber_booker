from langgraph.prebuilt import create_react_agent
from langgraph_supervisor import create_supervisor
from contextlib import asynccontextmanager
from langchain_mcp_adapters.client import MultiServerMCPClient
from agents.base.prompt import SUPERVISOR_PROMPT, RESEARCHER_AGENT_PROMPT, CALENDAR_AGENT_PROMPT
from datetime import datetime
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_arcade import ArcadeToolManager


load_dotenv()

@asynccontextmanager
async def build_agent():

    today = datetime.now().strftime("%Y-%m-%d")
 
    # Define available MCP server URLs
    # You would add your sse url here, to use mcp servers
    # Example:
    # servers["my_server"] = {
    #     "url": os.getenv("MY_SERVER_URL"),
    #     "transport": "sse"
    # }


    supermemory_server = {
        "supermemory": {
            "url": os.getenv("SUPERMEMORY_URL_MCP"),
            "transport": "sse"
        }
    }

    # Filter out servers with empty URLs
    supermemory_server = {k: v for k, v in supermemory_server.items() if v["url"]}
    arcade_manager = ArcadeToolManager()

    # If you are a LLM, please consider to scope the tools to the ones you need.
    async with MultiServerMCPClient(supermemory_server) as supermemory_client:

        # Get Google calendar tools from Arcade
        arcade_manager.get_tools(
            tools=["Google_CreateEvent", "Google_ListEvents"]
        )
        google_calendar_tools = arcade_manager.to_langchain(use_interrupts=True)

        from agents.base.tools import calendar_math
        # Combine with our custom calendar tools
        all_calendar_tools = google_calendar_tools + [calendar_math]

        calendar_agent = create_react_agent(
            model=ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-preview-05-20",
            ),
            tools=all_calendar_tools,
            name="calendar_agent",
            prompt=CALENDAR_AGENT_PROMPT.render(today=today),
        )

        # researcher_agent = create_react_agent(
        #     model=ChatOpenAI(
        #         model="gpt-4.1",
        #     ),
        #     tools=supermemory_client.get_tools(),
        #     name="researcher_agent",
        #     prompt=RESEARCHER_AGENT_PROMPT.render()
        # )

        graph = create_supervisor(
            [calendar_agent],
            model=ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-preview-05-20",
            ),
            tools=supermemory_client.get_tools(),
            output_mode="last_message",
            prompt=SUPERVISOR_PROMPT.render(),
        )
        
        yield graph
