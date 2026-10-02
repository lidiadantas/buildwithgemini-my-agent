# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.a2ui_utils import a2ui_callback
from app.tools import (
    list_workout_logs,
    get_workout_log,
    add_workout_log,
    save_user_profile,
    get_user_profile,
    calculate_training_zones,
    generate_weekly_plan,
    analyze_bioimpedance,
    fetch_outdoor_workout_weather,
    geocode_address,
    find_nearby_places,
    generate_workout_image,
    generate_exercise_demo_video,
)


def _get_code_executor() -> AgentEngineSandboxCodeExecutor:
    """Initialize AgentEngineSandboxCodeExecutor using deployment_metadata.json if available."""
    metadata_path = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
    agent_engine_id = None
    sandbox_id = None
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r") as f:
                data = json.load(f)
                agent_engine_id = data.get("remote_agent_runtime_id") or data.get("agent_engine_resource_name")
                sandbox_id = data.get("sandbox_resource_name") or data.get("sandbox_id")
        except Exception:
            pass

    if sandbox_id:
        return AgentEngineSandboxCodeExecutor(sandbox_resource_name=sandbox_id)
    elif agent_engine_id:
        return AgentEngineSandboxCodeExecutor(agent_engine_resource_name=agent_engine_id)
    else:
        return AgentEngineSandboxCodeExecutor()


async def generate_memories_callback(callback_context: CallbackContext):
    """Callback to extract durable memories at the end of each agent turn."""
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        # Ignore gracefully if memory service is not attached (e.g. in standalone test runners)
        pass
    return None


def memory_service_builder() -> VertexAiMemoryBankService:
    """Memory service builder configured for Vertex AI Memory Bank on Agent Engine."""
    return VertexAiMemoryBankService(
        project="qwiklabs-gcp-02-22f397fe66a7",
        location="us-central1",
        agent_engine_id="2314796882154487808",
    )


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are a stateful Fitness & Athletic Coach AI agent. Your mission is to help athletes plan, "
        "track, and optimize their athletic training while preventing injuries.\n\n"
        "Key capabilities & guidelines:\n"
        "1. Cross-Session Long-Term Memory: You automatically recall user fitness preferences, allergies, goals, and history "
        "across sessions using Vertex AI Memory Bank.\n"
        "2. Sandbox Code Execution: Execute Python code in a safe Agent Engine sandbox to run complex calculations, "
        "data modeling, or custom athletic zone analytics.\n"
        "3. Image Generation: Use `generate_workout_image` (gemini-3.1-flash-lite-image in global region) "
        "to generate athletic visual guides, route maps, or workout motivation graphics. Images are automatically saved "
        "as Playground artifacts and uploaded to a public Cloud Storage bucket.\n"
        "4. Location & Nearby Places: Use `geocode_address` (Google Maps Geocoding API) to convert addresses/cities to coordinates. "
        "Use `find_nearby_places` (Google Places API New) to locate nearby gyms, parks, tracks, and athletic facilities.\n"
        "5. Real-time Outdoor Workout Weather: Use `fetch_outdoor_workout_weather` (Open-Meteo REST API) "
        "to check real live weather, temperature, humidity, and wind conditions before outdoor runs or rides.\n"
        "6. Bioimpedance & Body Composition Assessment: Use `analyze_bioimpedance` to evaluate body fat %, "
        "skeletal muscle mass, total body water, and visceral fat prior to prescribing workout plans.\n"
        "7. Onboarding & Assessment Questionnaire: Ask about primary fitness goals, resting HR, max HR, FTP, "
        "and injury notes. Use `save_user_profile` and `get_user_profile` to record and retrieve profile data in Firestore.\n"
        "8. Physiological Zone Calculations: Use `calculate_training_zones` to compute Karvonen heart-rate zones "
        "and cycling power zones.\n"
        "9. Workout Plan Generation: Use `generate_weekly_plan` to build custom multi-week training schedules.\n"
        "10. Workout Tracking: Use `list_workout_logs`, `get_workout_log`, and `add_workout_log` to log and review workouts.\n"
        "11. Video Generation: Use `generate_exercise_demo_video` (gemini-omni-flash-preview in global region) "
        "to generate short 5-second exercise movement/posture demonstration videos. Videos are saved as Playground "
        "artifacts and uploaded directly to a public Cloud Storage bucket.\n"
        "12. Multilingual Support: If the user communicates in Portuguese or specifies `[Language: pt-BR]`, "
        "respond entirely in natural, fluent, and encouraging Brazilian Portuguese (pt-BR). Use metric units (kg, km, bpm, W) "
        "and standard Brazilian athletic terminology."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=_get_code_executor(),
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        get_weather,
        get_current_time,
        list_workout_logs,
        get_workout_log,
        add_workout_log,
        save_user_profile,
        get_user_profile,
        calculate_training_zones,
        generate_weekly_plan,
        analyze_bioimpedance,
        fetch_outdoor_workout_weather,
        geocode_address,
        find_nearby_places,
        generate_workout_image,
        generate_exercise_demo_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
