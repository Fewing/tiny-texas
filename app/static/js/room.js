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
  const resultModal = document.querySelector("#result-modal");
  const resultModalBody = document.querySelector("#result-modal-body");
  const resultModalClose = document.querySelector("#result-modal-close");
  const logEl = document.querySelector("#action-log");
  let socket = null;
  let state = initialState;
  let shownResultHandNumber = null;
  let roomDeleted = false;

  resultModalClose?.addEventListener("click", () => {
    resultModal.hidden = true;
  });

  function connect() {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${window.location.host}/ws/rooms/${roomCode}`);
    socket.addEventListener("open", () => {
      connectionState.textContent = "已连接";
    });
    socket.addEventListener("close", () => {
      if (roomDeleted) {
        return;
      }
      connectionState.textContent = "连接已断开，正在重连...";
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
      if (message.type === "room.deleted") {
        roomDeleted = true;
        connectionState.textContent = "房间已删除";
        resultEl.innerHTML = '<p class="alert">房间已删除，正在返回大厅...</p>';
        window.setTimeout(() => window.location.assign("/lobby"), 800);
      }
    });
  }

  function send(type, payload = {}) {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      resultEl.innerHTML = '<p class="alert">连接尚未就绪。</p>';
      return;
    }
    socket.send(JSON.stringify({ version: 1, request_id: makeRequestId(), type, payload }));
  }

  function makeRequestId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    if (window.crypto && typeof window.crypto.getRandomValues === "function") {
      const values = new Uint32Array(4);
      window.crypto.getRandomValues(values);
      return `${Date.now().toString(36)}-${Array.from(values, (value) => value.toString(36)).join("-")}`;
    }
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  }

  function render() {
    potEl.textContent = state.pot;
    communityEl.innerHTML = state.community_cards.map(cardHtml).join("") || '<span class="muted">尚未发公共牌</span>';
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
        seatNode.innerHTML = `<div>${seat.seat_index + 1} 号座位</div><button class="button secondary" type="button">入座</button>`;
        seatNode.querySelector("button").addEventListener("click", () => send("seat.take", { seat_index: seat.seat_index }));
        seatsEl.appendChild(seatNode);
        continue;
      }

      const badges = [];
      if (state.dealer_seat === seat.seat_index) badges.push("庄位");
      if (seat.ready) badges.push("已准备");
      if (seat.folded) badges.push("已弃牌");
      if (seat.all_in) badges.push("全下");
      if (state.current_turn_seat === seat.seat_index) badges.push("行动中");
      const rebuyBadge = seat.rebuy_count > 0
        ? `<span class="badge rebuy-badge">复活甲 x${seat.rebuy_count}</span>`
        : "";

      seatNode.innerHTML = `
        <div class="seat-name">
          <span>${escapeHtml(seat.username)}</span>
          <span>#${seat.seat_index + 1}</span>
        </div>
        <div class="seat-meta">
          <span class="badge">筹码 ${seat.stack}</span>
          <span class="badge">下注 ${seat.current_bet}</span>
          ${rebuyBadge}
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
          ready.textContent = "准备";
          ready.addEventListener("click", () => send("room.ready", { ready: true }));
          row.appendChild(ready);
        }
        const stand = document.createElement("button");
        stand.className = "button secondary";
        stand.type = "button";
        stand.textContent = "离座";
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
    status.textContent = `阶段：${phaseLabel(state.phase)} / 第 ${state.hand_number} 手牌`;
    controlsEl.appendChild(status);

    if (state.phase === "waiting" && state.can_start) {
      const start = document.createElement("button");
      start.className = "button primary";
      start.type = "button";
      start.textContent = "开始手牌";
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
        const button = actionButton(actionLabel(action.type), () => send("hand.action", { action_type: action.type, amount: Number(input.value) }));
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
    resultEl.innerHTML = `<h2>上一手牌</h2>${resultAwardsHtml(state.last_result)}`;
    if (shownResultHandNumber !== state.last_result.hand_number) {
      shownResultHandNumber = state.last_result.hand_number;
      showResultModal(state.last_result);
    }
  }

  function showResultModal(result) {
    if (!resultModal || !resultModalBody) return;
    resultModalBody.innerHTML = `
      <div class="result-summary">
        <span class="badge">第 ${result.hand_number} 手牌</span>
        <span class="badge">底池 ${result.pot}</span>
        <span class="badge">${result.reason === "showdown" ? "摊牌结算" : "弃牌结算"}</span>
      </div>
      <div>
        <h3>赢家</h3>
        ${resultAwardsHtml(result)}
      </div>
      ${result.community_cards.length ? `
        <div>
          <h3>公共牌</h3>
          <div class="card-row">${result.community_cards.map(cardHtml).join("")}</div>
        </div>
      ` : ""}
      ${result.showdown_players?.length ? `
        <div>
          <h3>开牌玩家</h3>
          <div class="showdown-list">${result.showdown_players.map(showdownPlayerHtml).join("")}</div>
        </div>
      ` : ""}
    `;
    resultModal.hidden = false;
  }

  function resultAwardsHtml(result) {
    return `<div class="award-list">${result.awards.map((award) => (
      `<div class="award-row">
        <strong>${escapeHtml(award.username)}</strong>
        <span>赢得 ${award.amount} 筹码</span>
        <span>${escapeHtml(handRankLabel(award.hand_rank))}</span>
      </div>`
    )).join("")}</div>`;
  }

  function showdownPlayerHtml(player) {
    return `
      <article class="showdown-row">
        <div>
          <strong>${escapeHtml(player.username)}</strong>
          <span>${player.seat_index + 1} 号座位 / ${escapeHtml(handRankLabel(player.hand_rank))}</span>
        </div>
        <div class="card-row">${player.hole_cards.map(cardHtml).join("")}</div>
      </article>
    `;
  }

  function renderLog() {
    logEl.innerHTML = state.actions.slice(-12).reverse().map((action) => (
      `<li>${escapeHtml(phaseLabel(action.phase))}：${escapeHtml(actionLabel(action.action_type))} ${action.amount || ""}</li>`
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
    if (action.type === "call") return `跟注 ${action.amount}`;
    if (action.type === "all_in") return `全下 ${action.amount}`;
    return actionLabel(action.type);
  }

  function phaseLabel(phase) {
    return {
      waiting: "等待中",
      preflop: "翻牌前",
      flop: "翻牌",
      turn: "转牌",
      river: "河牌",
    }[phase] || phase;
  }

  function actionLabel(actionType) {
    return {
      small_blind: "小盲",
      big_blind: "大盲",
      fold: "弃牌",
      check: "过牌",
      call: "跟注",
      bet: "下注",
      raise: "加注",
      all_in: "全下",
      deal_flop: "发翻牌",
      deal_turn: "发转牌",
      deal_river: "发河牌",
    }[actionType] || actionType;
  }

  function handRankLabel(rank) {
    return {
      "straight flush": "同花顺",
      "four of a kind": "四条",
      "full house": "葫芦",
      flush: "同花",
      straight: "顺子",
      "three of a kind": "三条",
      "two pair": "两对",
      "one pair": "一对",
      "high card": "高牌",
      uncontested: "无人争夺",
    }[rank] || rank;
  }

  function cardHtml(card) {
    const red = card.endsWith("h") || card.endsWith("d");
    const hidden = card === "XX";
    const label = hidden ? "??" : `${card[0]}${suitSymbol(card[1])}`;
    return `<span class="card${red ? " red" : ""}${hidden ? " hidden" : ""}">${label}</span>`;
  }

  function suitSymbol(suit) {
    return { c: "♣", d: "♦", h: "♥", s: "♠" }[suit] || suit;
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
