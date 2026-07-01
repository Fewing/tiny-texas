const app = document.querySelector("#room-app");

if (app) {
  const roomCode = app.dataset.roomCode;
  const currentUserId = Number(app.dataset.currentUserId);
  const initialState = JSON.parse(document.querySelector("#initial-state").textContent);
  const connectionState = document.querySelector("#connection-state");
  const seatsEl = document.querySelector("#seats");
  const communityEl = document.querySelector("#community-cards");
  const potEl = document.querySelector("#pot-value");
  const controlsEl = document.querySelector("#action-controls");
  const resultEl = document.querySelector("#result-box");
  const logEl = document.querySelector("#action-log");
  let socket = null;
  let state = initialState;

  function connect() {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${window.location.host}/ws/rooms/${roomCode}`);
    socket.addEventListener("open", () => {
      connectionState.textContent = "Connected";
    });
    socket.addEventListener("close", () => {
      connectionState.textContent = "Disconnected. Reconnecting...";
      window.setTimeout(connect, 1200);
    });
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "state.snapshot") {
        state = message.payload;
        render();
      }
      if (message.type === "error") {
        resultEl.innerHTML = `<p class="alert">${escapeHtml(message.payload.message)}</p>`;
      }
    });
  }

  function send(type, payload = {}) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      resultEl.innerHTML = '<p class="alert">Connection is not ready.</p>';
      return;
    }
    socket.send(JSON.stringify({ version: 1, request_id: crypto.randomUUID(), type, payload }));
  }

  function render() {
    potEl.textContent = state.pot;
    communityEl.innerHTML = state.community_cards.map(cardHtml).join("") || '<span class="muted">No board yet</span>';
    renderSeats();
    renderControls();
    renderResult();
    renderLog();
  }

  function renderSeats() {
    seatsEl.innerHTML = "";
    for (const seat of state.players) {
      const seatNode = document.createElement("article");
      seatNode.className = `seat${seat.occupied ? "" : " empty"}${state.current_turn_seat === seat.seat_index ? " current-turn" : ""}`;
      if (!seat.occupied) {
        seatNode.innerHTML = `<div>Seat ${seat.seat_index + 1}</div><button class="button secondary" type="button">Sit</button>`;
        seatNode.querySelector("button").addEventListener("click", () => send("seat.take", { seat_index: seat.seat_index }));
        seatsEl.appendChild(seatNode);
        continue;
      }

      const badges = [];
      if (state.dealer_seat === seat.seat_index) badges.push("Dealer");
      if (seat.ready) badges.push("Ready");
      if (seat.folded) badges.push("Folded");
      if (seat.all_in) badges.push("All-in");
      if (state.current_turn_seat === seat.seat_index) badges.push("Turn");

      seatNode.innerHTML = `
        <div class="seat-name">
          <span>${escapeHtml(seat.username)}</span>
          <span>#${seat.seat_index + 1}</span>
        </div>
        <div class="seat-meta">
          <span class="badge">Stack ${seat.stack}</span>
          <span class="badge">Bet ${seat.current_bet}</span>
          ${badges.map((badge) => `<span class="badge">${badge}</span>`).join("")}
        </div>
        <div class="card-row">${seat.hole_cards.map(cardHtml).join("")}</div>
      `;
      if (seat.user_id === currentUserId && state.phase === "waiting") {
        const row = document.createElement("div");
        row.className = "action-row";
        if (!seat.ready) {
          const ready = document.createElement("button");
          ready.className = "button primary";
          ready.type = "button";
          ready.textContent = "Ready";
          ready.addEventListener("click", () => send("room.ready", { ready: true }));
          row.appendChild(ready);
        }
        const stand = document.createElement("button");
        stand.className = "button secondary";
        stand.type = "button";
        stand.textContent = "Stand";
        stand.addEventListener("click", () => send("seat.leave", {}));
        row.appendChild(stand);
        seatNode.appendChild(row);
      }
      seatsEl.appendChild(seatNode);
    }
  }

  function renderControls() {
    controlsEl.innerHTML = "";
    const status = document.createElement("div");
    status.className = "status-line";
    status.textContent = `Phase: ${state.phase} / Hand: ${state.hand_number}`;
    controlsEl.appendChild(status);

    if (state.phase === "waiting" && state.can_start) {
      const start = document.createElement("button");
      start.className = "button primary";
      start.type = "button";
      start.textContent = "Start hand";
      start.addEventListener("click", () => send("hand.start", {}));
      controlsEl.appendChild(start);
    }

    if (!state.legal_actions.length) {
      return;
    }

    const actionRow = document.createElement("div");
    actionRow.className = "action-row";
    for (const action of state.legal_actions) {
      if (action.type === "bet" || action.type === "raise") {
        const input = document.createElement("input");
        input.type = "number";
        input.min = action.min;
        input.max = action.max;
        input.value = action.min;
        input.style.maxWidth = "120px";
        const button = actionButton(action.type, () => send("hand.action", { action_type: action.type, amount: Number(input.value) }));
        actionRow.appendChild(input);
        actionRow.appendChild(button);
        continue;
      }
      actionRow.appendChild(actionButton(labelFor(action), () => send("hand.action", { action_type: action.type, amount: action.amount || 0 })));
    }
    controlsEl.appendChild(actionRow);
  }

  function renderResult() {
    if (!state.last_result) {
      resultEl.innerHTML = "";
      return;
    }
    const awards = state.last_result.awards.map((award) => (
      `<div><strong>${escapeHtml(award.username)}</strong> wins ${award.amount} with ${escapeHtml(award.hand_rank)}</div>`
    )).join("");
    resultEl.innerHTML = `<h2>Last hand</h2>${awards}`;
  }

  function renderLog() {
    logEl.innerHTML = state.actions.slice(-12).reverse().map((action) => (
      `<li>${escapeHtml(action.phase)}: ${escapeHtml(action.action_type)} ${action.amount || ""}</li>`
    )).join("");
  }

  function actionButton(label, handler) {
    const button = document.createElement("button");
    button.className = "button secondary";
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  function labelFor(action) {
    if (action.type === "call") return `Call ${action.amount}`;
    if (action.type === "all_in") return `All-in ${action.amount}`;
    return action.type.replace("_", " ");
  }

  function cardHtml(card) {
    const red = card.endsWith("h") || card.endsWith("d");
    const hidden = card === "XX";
    const label = hidden ? "??" : `${card[0]}${suitSymbol(card[1])}`;
    return `<span class="card${red ? " red" : ""}${hidden ? " hidden" : ""}">${label}</span>`;
  }

  function suitSymbol(suit) {
    return { c: "C", d: "D", h: "H", s: "S" }[suit] || suit;
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  render();
  connect();
}

