const state = {
  roomId: localStorage.getItem("monodeal_room_id") || "",
  playerId: localStorage.getItem("monodeal_player_id") || "",
  playerName: localStorage.getItem("monodeal_player_name") || "",
  data: null,
  actions: [],
  ws: null,
};

const el = (id) => document.getElementById(id);

function saveIdentity() {
  localStorage.setItem("monodeal_room_id", state.roomId);
  localStorage.setItem("monodeal_player_id", state.playerId);
  localStorage.setItem("monodeal_player_name", state.playerName);
}

function api(path, opts = {}) {
  return fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  }).then(async (r) => {
    const json = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(json.detail || "Request failed");
    return json;
  });
}

function connectWS() {
  if (!state.roomId) return;
  if (state.ws) state.ws.close();
  const wsProto = location.protocol === "https:" ? "wss" : "ws";
  state.ws = new WebSocket(`${wsProto}://${location.host}/ws/${state.roomId}`);
  state.ws.onmessage = (evt) => {
    const message = JSON.parse(evt.data);
    if (message.type === "state") {
      state.data = message.state;
      render();
      refreshActions();
    }
  };
}

function render() {
  const identity = state.playerName
    ? `${state.playerName}<br><span class="muted">${state.roomId || "No room"}</span>`
    : "Not signed in";
  el("identity").innerHTML = identity;

  if (!state.data) return;

  el("roomMeta").textContent = `Room ${state.data.room_id} • rev ${state.data.revision}`;

  const game = state.data.game;
  const playersHtml = state.data.players
    .map((p) => {
      const gp = game.players.find((x) => x.player_id === p.player_id);
      const active = game.turn_player_id === p.player_id ? "active" : "";
      return `<li class="player ${active}">
        <div><strong>${p.name}</strong> ${game.winner === p.name ? '<span class="winner">Winner</span>' : ""}</div>
        <div class="muted">${gp ? `${gp.hand_count} in hand` : "Lobby"}</div>
      </li>`;
    })
    .join("");
  el("playersList").innerHTML = playersHtml;

  if (!game.started) {
    el("turnInfo").textContent = "Game not started.";
  } else {
    el("turnInfo").innerHTML = `<strong>${game.turn_player_name}</strong>'s turn • ${game.actions_left} actions left • draw ${game.draw_count} • discard ${game.discard_count}`;
  }

  const me = game.players.find((p) => p.player_id === state.playerId);
  el("handCards").innerHTML = me ? me.hand.map((c) => `<span class="chip">${c}</span>`).join("") : "";

  const boardHtml = game.players
    .map((p) => {
      const sets = p.property_sets
        .map(
          (ps) =>
            `<div class="ps"><strong>${ps.colour}</strong> • rent ${ps.rent_value} ${ps.is_complete ? "(complete)" : ""}<br>${ps.cards.join(", ")}</div>`
        )
        .join("");
      return `<div><h4>${p.name}</h4>${sets || '<div class="muted">No property sets</div>'}</div>`;
    })
    .join("");
  el("boardView").innerHTML = boardHtml;

  el("startGameBtn").disabled = !(
    state.playerId &&
    state.data.players.length >= 2 &&
    state.playerId === state.data.players[0].player_id &&
    !game.started
  );
}

function renderActions() {
  const html = state.actions
    .map(
      (a) =>
        `<button class="action-btn" data-idx="${a.index}"><strong>${a.label}</strong><br><span class="muted">${a.type} • cost ${a.cost}</span></button>`
    )
    .join("");
  el("actionsList").innerHTML = html || '<div class="muted">No actions available right now.</div>';
  Array.from(document.querySelectorAll(".action-btn")).forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api(`/api/rooms/${state.roomId}/action`, {
          method: "POST",
          body: JSON.stringify({
            player_id: state.playerId,
            action_index: Number(btn.dataset.idx),
          }),
        });
        await refreshState();
        await refreshActions();
      } catch (err) {
        alert(err.message);
      }
    };
  });
}

async function refreshState() {
  if (!state.roomId) return;
  const resp = await api(`/api/rooms/${state.roomId}/state?player_id=${encodeURIComponent(state.playerId)}`);
  state.data = resp.state;
  render();
}

async function refreshActions() {
  if (!state.roomId || !state.playerId || !state.data?.game?.started) {
    state.actions = [];
    renderActions();
    return;
  }
  try {
    const resp = await api(`/api/rooms/${state.roomId}/actions?player_id=${encodeURIComponent(state.playerId)}`);
    state.actions = resp.actions;
    renderActions();
  } catch {
    state.actions = [];
    renderActions();
  }
}

el("createRoomBtn").onclick = async () => {
  const name = el("playerName").value.trim();
  if (!name) return alert("Enter your name");
  try {
    const resp = await api("/api/rooms", {
      method: "POST",
      body: JSON.stringify({ player_name: name }),
    });
    state.playerName = name;
    state.roomId = resp.room_id;
    state.playerId = resp.player_id;
    state.data = resp.state;
    saveIdentity();
    connectWS();
    render();
    await refreshActions();
  } catch (err) {
    alert(err.message);
  }
};

el("joinRoomBtn").onclick = async () => {
  const name = el("playerName").value.trim();
  const roomId = el("roomIdInput").value.trim().toUpperCase();
  if (!name || !roomId) return alert("Enter name and room code");
  try {
    const resp = await api(`/api/rooms/${roomId}/join`, {
      method: "POST",
      body: JSON.stringify({ player_name: name }),
    });
    state.playerName = name;
    state.roomId = roomId;
    state.playerId = resp.player_id;
    state.data = resp.state;
    saveIdentity();
    connectWS();
    render();
    await refreshActions();
  } catch (err) {
    alert(err.message);
  }
};

el("startGameBtn").onclick = async () => {
  try {
    await api(`/api/rooms/${state.roomId}/start`, {
      method: "POST",
      body: JSON.stringify({ player_id: state.playerId }),
    });
    await refreshState();
    await refreshActions();
  } catch (err) {
    alert(err.message);
  }
};

el("refreshActionsBtn").onclick = refreshActions;

el("endTurnBtn").onclick = async () => {
  try {
    await api(`/api/rooms/${state.roomId}/end-turn`, {
      method: "POST",
      body: JSON.stringify({ player_id: state.playerId }),
    });
    await refreshState();
    await refreshActions();
  } catch (err) {
    alert(err.message);
  }
};

async function bootstrap() {
  if (state.playerName) {
    el("playerName").value = state.playerName;
  }
  if (state.roomId) {
    el("roomIdInput").value = state.roomId;
    connectWS();
    try {
      await refreshState();
      await refreshActions();
    } catch {
      // stale local identity, ignore
    }
  }
  render();
  renderActions();
}

bootstrap();
