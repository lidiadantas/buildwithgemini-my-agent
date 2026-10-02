"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.
"""

import json
import os
import re
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types import (
    AgentCard,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TextPart,
    TransportProtocol,
)
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Try loading default AGENT_ENGINE_RESOURCE_NAME from deployment_metadata.json if available
_metadata_path = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
_default_resource = ""
if os.path.exists(_metadata_path):
    try:
        with open(_metadata_path, "r") as f:
            data = json.load(f)
            _default_resource = data.get("remote_agent_runtime_id", "")
    except Exception:
        pass

RESOURCE = os.environ.get("AGENT_ENGINE_RESOURCE_NAME", _default_resource)
if not RESOURCE:
    raise ValueError("AGENT_ENGINE_RESOURCE_NAME environment variable or deployment_metadata.json is required.")

# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")
# Location is embedded in the resource name: projects/<p>/locations/<loc>/reasoningEngines/<id>.
LOCATION = RESOURCE.split("/locations/")[1].split("/")[0]

# A2A endpoint for an Agent Runtime deployment, via the Agent Engine HTTP
# passthrough. The card lives at the well-known path under this base.
A2A_BASE = (
    f"https://{LOCATION}-aiplatform.googleapis.com/reasoningEngines/v1/"
    f"{RESOURCE}/api/a2a/{AGENT_DIRECTORY}"
)
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    _creds.refresh(google.auth.transport.requests.Request())
    return {
        "Authorization": f"Bearer {_creds.token}",
        "Content-Type": "application/json",
    }


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        resp = await client.get(A2A_CARD_URL)
        resp.raise_for_status()
        card = AgentCard(**resp.json())
        # Agent Runtime does not serve a public card URL, so point the client at
        # the passthrough base for message sends.
        card.url = A2A_BASE
        _card = card
    return _card


_DATAPART_RE = re.compile(r"<a2a_datapart_json>(.*?)</a2a_datapart_json>", re.DOTALL)
_A2UI_KEYS = ("beginRendering", "surfaceUpdate", "dataModelUpdate", "deleteSurface")


def _parse_a2ui_obj(obj: dict) -> dict | None:
    """Extract A2UI message dict if present in obj or obj['data']."""
    if not isinstance(obj, dict):
        return None
    data = obj.get("data") if obj.get("kind") == "data" else obj
    if isinstance(data, dict) and any(k in data for k in _A2UI_KEYS):
        return data
    return None


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI.

    Strips raw <a2a_datapart_json> tags and JSON code blocks from text responses
    and converts them into {"kind": "a2ui", "data": ...} parts.
    """
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)

        # 1. Handle inline data / bytes / data attributes
        data_val = getattr(root, "data", None)
        if data_val is not None:
            if isinstance(data_val, bytes):
                try:
                    data_val = data_val.decode("utf-8")
                except Exception:
                    pass
            if isinstance(data_val, str):
                try:
                    parsed = json.loads(data_val)
                    if a2ui_msg := _parse_a2ui_obj(parsed):
                        out.append({"kind": "a2ui", "data": a2ui_msg})
                        continue
                except Exception:
                    pass
            elif isinstance(data_val, dict):
                if a2ui_msg := _parse_a2ui_obj(data_val):
                    out.append({"kind": "a2ui", "data": a2ui_msg})
                    continue

        # 2. Handle TextPart (or text strings)
        text = getattr(root, "text", None) if isinstance(root, TextPart) or hasattr(root, "text") else None
        if not text and isinstance(root, str):
            text = root

        if text:
            # Extract <a2a_datapart_json>... tags embedded in text
            matches = _DATAPART_RE.findall(text)
            for m in matches:
                try:
                    val = json.loads(m.strip())
                    if a2ui_msg := _parse_a2ui_obj(val):
                        out.append({"kind": "a2ui", "data": a2ui_msg})
                except Exception:
                    pass

            # Remove <a2a_datapart_json> tags from text
            text = _DATAPART_RE.sub("", text)

            # Check if remaining text is a pure A2UI JSON object or code block
            stripped_text = text.strip()
            if stripped_text.startswith("```"):
                clean_block = re.sub(r"^```(?:json)?\s*", "", stripped_text, flags=re.I)
                clean_block = re.sub(r"\s*```$", "", clean_block)
                try:
                    val = json.loads(clean_block)
                    if a2ui_msg := _parse_a2ui_obj(val):
                        out.append({"kind": "a2ui", "data": a2ui_msg})
                        continue
                except Exception:
                    pass
            elif stripped_text.startswith("{") and stripped_text.endswith("}"):
                try:
                    val = json.loads(stripped_text)
                    if a2ui_msg := _parse_a2ui_obj(val):
                        out.append({"kind": "a2ui", "data": a2ui_msg})
                        continue
                except Exception:
                    pass

            if stripped_text:
                out.append({"kind": "text", "text": stripped_text})

        elif isinstance(root, FilePart):
            uri = getattr(getattr(root, "file", None), "uri", None)
            if uri:
                out.append({"kind": "text", "text": uri})

    return out


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    language = body.get("language", "en")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    full_message = f"[Language: {language}]\n{message}" if language in ("pt-BR", "pt") and not message.startswith("[Language:") else message

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        factory = ClientFactory(
            ClientConfig(
                supported_transports=[
                    TransportProtocol.jsonrpc,
                    TransportProtocol.http_json,
                ],
                httpx_client=client,
            )
        )
        a2a_client = factory.create(card)

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.user,
            parts=[Part(root=TextPart(text=full_message))],
            context_id=_contexts.get(user_id),
        )

        last_task = None
        got_artifact_update = False
        async for event in a2a_client.send_message(msg):
            if not isinstance(event, tuple):
                continue
            task, update = event
            if task is not None:
                last_task = task
                if getattr(task, "context_id", None):
                    _contexts[user_id] = task.context_id
            if isinstance(update, TaskArtifactUpdateEvent):
                got_artifact_update = True
                parts.extend(_extract_parts(update.artifact.parts))

        # Non-streaming fallback: pull parts from the final task's artifacts.
        if not got_artifact_update and last_task is not None:
            for artifact in getattr(last_task, "artifacts", None) or []:
                parts.extend(_extract_parts(artifact.parts))

    if not parts:
        # The turn produced no text or UI (e.g. the agent only ran tools, or a
        # tool stalled). Be honest rather than silent.
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.get("/")
async def get_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(
        index_path,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )

# Serve the chat UI (keep this mount last so /chat and / win).
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
