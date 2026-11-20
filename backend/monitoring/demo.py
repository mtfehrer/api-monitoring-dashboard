import asyncio
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Monitoring Demo API")
Endpoint = Literal["primary", "secondary"]


class Behavior(BaseModel):
    mode: Literal["healthy", "unavailable", "delayed"]
    delay_ms: int = Field(default=500, ge=1, le=30000)


behaviors: dict[Endpoint, Behavior] = {
    "primary": Behavior(mode="healthy"),
    "secondary": Behavior(mode="healthy"),
}


@app.get("/health")
async def health():
    return await endpoint_health("primary")


@app.get("/health/{endpoint}")
async def endpoint_health(endpoint: Endpoint):
    behavior = behaviors[endpoint]
    if behavior.mode == "delayed":
        await asyncio.sleep(behavior.delay_ms / 1000)
    healthy = behavior.mode != "unavailable"
    return JSONResponse(
        {"endpoint": endpoint, "status": "healthy" if healthy else "unavailable"},
        status_code=200 if healthy else 503,
    )


@app.get("/control")
async def get_behavior():
    return behaviors


@app.put("/control/{endpoint}")
async def update_behavior(endpoint: Endpoint, behavior: Behavior):
    behaviors[endpoint] = behavior
    return behavior
