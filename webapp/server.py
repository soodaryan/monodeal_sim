from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import Room


class CreateRoomRequest(BaseModel):
    player_name: str = Field(min_length=1, max_length=32)


class JoinRoomRequest(BaseModel):
    player_name: str = Field(min_length=1, max_length=32)


class StartRoomRequest(BaseModel):
    player_id: str


class ActionRequest(BaseModel):
    player_id: str
    action_index: int


class EndTurnRequest(BaseModel):
    player_id: str


class RoomManager:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def create_room(self, player_name: str) -> tuple[Room, str]:
        async with self._lock:
            room = Room(host_name=player_name)
            host = room.players[0]
            self._rooms[room.room_id] = room
            self._connections[room.room_id] = set()
            return room, host.player_id

    async def get_room(self, room_id: str) -> Room:
        room_id = room_id.upper()
        async with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                raise ValueError("Room not found")
            return room

    async def join_room(self, room_id: str, player_name: str) -> str:
        room_id = room_id.upper()
        async with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                raise ValueError("Room not found")
            player = room.add_player(player_name)
            room.revision += 1
            return player.player_id

    async def broadcast_room(self, room_id: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            conns = list(self._connections.get(room_id, set()))
        stale: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                stale.append(ws)
        if stale:
            async with self._lock:
                current = self._connections.get(room_id, set())
                for ws in stale:
                    current.discard(ws)

    async def connect(self, room_id: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            if room_id not in self._connections:
                self._connections[room_id] = set()
            self._connections[room_id].add(ws)

    async def disconnect(self, room_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.get(room_id, set()).discard(ws)


manager = RoomManager()
app = FastAPI(title="Monodeal Web")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/rooms")
async def create_room(payload: CreateRoomRequest) -> dict[str, Any]:
    room, player_id = await manager.create_room(payload.player_name)
    state = room.state_for(player_id)
    await manager.broadcast_room(room.room_id, {"type": "state", "state": state})
    return {"room_id": room.room_id, "player_id": player_id, "state": state}


@app.post("/api/rooms/{room_id}/join")
async def join_room(room_id: str, payload: JoinRoomRequest) -> dict[str, Any]:
    room_id = room_id.upper()
    try:
        player_id = await manager.join_room(room_id, payload.player_name)
        room = await manager.get_room(room_id)
        state = room.state_for(player_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    await manager.broadcast_room(
        room_id, {"type": "state", "state": room.state_for(None)}
    )
    return {"room_id": room_id, "player_id": player_id, "state": state}


@app.post("/api/rooms/{room_id}/start")
async def start_room(room_id: str, payload: StartRoomRequest) -> dict[str, Any]:
    room_id = room_id.upper()
    try:
        room = await manager.get_room(room_id)
        if room.players[0].player_id != payload.player_id:
            raise ValueError("Only host can start")
        room.start()
        state = room.state_for(payload.player_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    await manager.broadcast_room(
        room_id, {"type": "state", "state": room.state_for(None)}
    )
    return {"state": state}


@app.get("/api/rooms/{room_id}/state")
async def get_state(
    room_id: str, player_id: str | None = Query(default=None)
) -> dict[str, Any]:
    room_id = room_id.upper()
    try:
        room = await manager.get_room(room_id)
        return {"state": room.state_for(player_id)}
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@app.get("/api/rooms/{room_id}/actions")
async def get_actions(room_id: str, player_id: str) -> dict[str, Any]:
    room_id = room_id.upper()
    try:
        room = await manager.get_room(room_id)
        if room.game is None:
            return {"actions": []}
        actions = room.game.available_actions(player_id)
        return {"actions": actions}
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@app.post("/api/rooms/{room_id}/action")
async def apply_action(room_id: str, payload: ActionRequest) -> dict[str, Any]:
    room_id = room_id.upper()
    try:
        room = await manager.get_room(room_id)
        if room.game is None:
            raise ValueError("Game has not started")
        room.game.apply_action(payload.player_id, payload.action_index)
        room.revision += 1
        state = room.state_for(payload.player_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    await manager.broadcast_room(
        room_id, {"type": "state", "state": room.state_for(None)}
    )
    return {"state": state}


@app.post("/api/rooms/{room_id}/end-turn")
async def end_turn(room_id: str, payload: EndTurnRequest) -> dict[str, Any]:
    room_id = room_id.upper()
    try:
        room = await manager.get_room(room_id)
        if room.game is None:
            raise ValueError("Game has not started")
        room.game.end_turn(payload.player_id)
        room.revision += 1
        state = room.state_for(payload.player_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    await manager.broadcast_room(
        room_id, {"type": "state", "state": room.state_for(None)}
    )
    return {"state": state}


@app.websocket("/ws/{room_id}")
async def room_ws(room_id: str, websocket: WebSocket) -> None:
    room_id = room_id.upper()
    await manager.connect(room_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(room_id, websocket)
