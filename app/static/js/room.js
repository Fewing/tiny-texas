import { createRoomEffects } from "./room-effects.js?v=20261115-6";
import { raisePresets } from "./raise-presets.js?v=20261114-1";
import { showdownHand } from "./showdown.js?v=20261115-6";
import { showdownProfile, showdownRhythm } from "./showdown-effects.js?v=20261115-2";

const app = document.querySelector("#room-app");
const { roomCode } = app.dataset;
const isDemo = app.hasAttribute("data-demo");
const currentUserId = Number(app.dataset.currentUserId);
const isOwner = app.dataset.isOwner === "true";
const botOptions = JSON.parse(document.querySelector("#bot-options")?.textContent ?? "[]");
const connection = app.querySelector("#connection-state");
const feedback = app.querySelector("#room-feedback");
const seats = app.querySelector("#seats");
const phraseLayer = app.querySelector("#phrase-layer");
const community = app.querySelector("#community-cards");
const playerHand = app.querySelector("#player-hole-cards");
const pot = app.querySelector("#pot-value");
const street = app.querySelector("#street-label");
const controls = app.querySelector("#action-controls");
const settlementView = app.querySelector("#settlement");
const settlementTools = app.querySelector("#settlement-tools");
const settlementCaption = app.querySelector("#settlement-caption");
const settlementTitle = app.querySelector("#settlement-title");
const settlementAwards = app.querySelector("#settlement-awards");
const settlementSkip = app.querySelector("#settlement-skip");
const settlementDetails = app.querySelector("#settlement-details");
const resultBox = app.querySelector("#result-box");
const resultModal = app.querySelector("#result-modal");
const resultBody = app.querySelector("#result-modal-body");
const botModal = app.querySelector("#bot-modal");
const botForm = app.querySelector("#bot-form");
const botStrategy = app.querySelector("#bot-strategy-select");
const botVariant = app.querySelector("#bot-variant-select");
const botDescription = app.querySelector("#bot-variant-description");
const log = app.querySelector("#action-log");
const effects = createRoomEffects(app);

const phases = { waiting: "等待开局", preflop: "翻牌前", flop: "翻牌", turn: "转牌", river: "河牌" };
const actions = {
  small_blind: "小盲", big_blind: "大盲", fold: "弃牌", check: "过牌", call: "跟注",
  bet: "下注", raise: "加注", all_in: "全下", deal_flop: "发翻牌", deal_turn: "发转牌", deal_river: "发河牌",
};
const suits = { c: "♣", d: "♦", h: "♥", s: "♠" };
const suitNames = { c: "梅花", d: "方块", h: "红桃", s: "黑桃" };

let state = JSON.parse(document.querySelector("#initial-state")?.textContent ?? "null");
let socket;
let connected = false;
let deleted = false;
let awaitingSnapshot = true;
let pending;
let controlKey;
let layoutAnchor = viewerSeat()?.seat_index ?? 0;
let selectedBotSeat;
let phraseOpen = false;
let boardKey;
let handKey;
let resultKey;
let effectTimers = [];
let potCountFrame;
let settlement;
let featuredWinner;

const opponentPositions = {
  2: [[50, 15]],
  3: [[22, 23], [78, 23]],
  4: [[13, 55], [50, 15], [87, 55]],
  5: [[12, 56], [33, 17], [67, 17], [88, 56]],
  6: [[12, 56], [23, 18], [50, 15], [77, 18], [88, 56]],
  7: [[23, 73], [12, 45], [31, 16], [69, 16], [88, 45], [77, 73]],
  8: [[23, 73], [12, 45], [24, 17], [50, 15], [76, 17], [88, 45], [77, 73]],
  9: [[18, 73], [10, 43], [16, 18], [39, 15], [61, 15], [84, 18], [90, 43], [82, 73]],
};
const mobilePositions = {
  2: [[50, 16]],
  3: [[26, 18], [74, 18]],
  4: [[19, 30], [50, 13], [81, 30]],
  5: [[18, 29], [35, 13], [65, 13], [82, 29]],
  6: [[17, 29], [20, 13], [50, 13], [80, 13], [83, 29]],
  7: [[19, 78], [17, 32], [30, 13], [70, 13], [83, 32], [81, 78]],
  8: [[19, 78], [17, 32], [19, 13], [50, 13], [81, 13], [83, 32], [81, 78]],
  9: [[19, 78], [17, 32], [13, 13], [38, 13], [62, 13], [87, 13], [83, 32], [81, 78]],
};

function viewerSeat(snapshot = state) {
  return snapshot?.players.find((seat) => seat.occupied && seat.user_id === currentUserId);
}

function format(amount) {
  return amount.toLocaleString("zh-CN");
}

function displayName(player) {
  // Bots use negative runtime IDs even after they have left the table.
  return player.player_type === "bot" || player.user_id < 0
    ? player.username.replace(/BOT$/, "") || player.username
    : player.username;
}

function escapeHtml(value) {
  const symbols = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  return String(value).replace(/[&<>"']/g, (symbol) => symbols[symbol]);
}

function button(label, handler, className = "button secondary") {
  const node = document.createElement("button");
  node.className = className;
  node.type = "button";
  node.textContent = label;
  node.addEventListener("click", handler);
  return node;
}

function openModal(dialog) {
  setPhraseOpen(false);
  if (!dialog.open) dialog.showModal();
}

app.querySelector("#result-modal-close").addEventListener("click", () => resultModal.close());
settlementDetails.addEventListener("click", () => openModal(resultModal));
settlementSkip.addEventListener("click", () => {
  skipSettlement();
  settlementDetails.focus({ preventScroll: true });
});
document.querySelector("#motion-toggle").addEventListener("click", () => {
  if (effects.reduced()) skipSettlement();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) skipSettlement();
});
app.querySelector("#bot-modal-close")?.addEventListener("click", () => botModal.close());
app.querySelector("#bot-form-cancel")?.addEventListener("click", () => botModal.close());
for (const dialog of [resultModal, botModal].filter(Boolean)) {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
}

app.querySelector("#copy-invite")?.addEventListener("click", async (event) => {
  const target = event.currentTarget;
  const invite = new URL(location.pathname, location.origin);
  try {
    await navigator.clipboard.writeText(invite.href);
    target.textContent = "链接已复制";
    window.setTimeout(() => { target.textContent = "复制邀请链接"; }, 1600);
  } catch {
    window.prompt("复制此邀请链接", invite.href);
  }
});

function showFeedback(text = "") {
  feedback.textContent = text;
  feedback.hidden = !text;
}

function connect() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  awaitingSnapshot = true;
  socket = new WebSocket(`${protocol}://${location.host}/ws/rooms/${encodeURIComponent(roomCode)}`);
  socket.addEventListener("close", () => {
    if (deleted) return;
    connected = false;
    clearPending();
    connection.textContent = "重连中";
    connection.className = "connection-pill reconnecting";
    renderControls();
    window.setTimeout(connect, 1200);
  });

  socket.addEventListener("message", ({ data }) => {
    const message = JSON.parse(data);
    switch (message.type) {
      case "state.snapshot": {
        const previous = state;
        state = message.payload;
        connected = true;
        connection.textContent = "已连接";
        connection.className = "connection-pill connected";
        render(awaitingSnapshot ? null : previous);
        awaitingSnapshot = false;
        break;
      }
      case "action.accepted":
        if (message.request_id === pending?.id) clearPending();
        break;
      case "phrase.sent":
        showPhrase(message.payload);
        break;
      case "error":
        if (message.request_id === pending?.id) clearPending();
        showFeedback(message.payload.message);
        break;
      case "room.deleted":
        deleted = true;
        connected = false;
        clearPending();
        connection.textContent = "房间已删除";
        connection.className = "connection-pill reconnecting";
        showFeedback("房间已删除，正在返回大厅。");
        window.setTimeout(() => location.assign("/lobby"), 800);
        break;
    }
  });
}

function send(type, payload = {}) {
  if (pending) return false;
  if (!connected || socket?.readyState !== WebSocket.OPEN) {
    showFeedback("正在连接牌桌，请稍候。");
    return false;
  }

  showFeedback();
  const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const timer = window.setTimeout(() => {
    showFeedback("牌桌响应超时，正在重新同步。");
    socket.close();
  }, 15000);
  pending = { id, timer };
  socket.send(JSON.stringify({ version: 1, request_id: id, type, payload }));
  syncPending();
  effects.play("select");
  return true;
}

function syncPending() {
  app.dataset.pending = Boolean(pending);
  for (const node of controls.querySelectorAll("button, input")) {
    node.disabled = Boolean(pending) || !connected;
  }
}

function clearPending() {
  if (pending) window.clearTimeout(pending.timer);
  pending = null;
  syncPending();
}

function currentResult() {
  return state.phase === "waiting" && state.last_result?.hand_number === state.hand_number
    ? state.last_result
    : null;
}

function sameResult(left, right) {
  return left?.hand_number === right?.hand_number && left?.ended_at === right?.ended_at;
}

function render(previous = null) {
  layoutAnchor = viewerSeat()?.seat_index ?? layoutAnchor;
  if (!viewerSeat()?.hole_cards.length || !connected) phraseOpen = false;
  const result = currentResult();
  const newHand = previous && previous.hand_number !== state.hand_number;
  if (!previous || newHand) {
    effectTimers.forEach((timer) => window.clearTimeout(timer));
    effectTimers = [];
  }
  if (settlement && (!result || !sameResult(settlement.result, result))) {
    clearSettlement();
    effects.clear();
  }
  const newResult = Boolean(previous && result && !sameResult(result, previous.last_result));
  if (!result || newResult) {
    featuredWinner = null;
    delete settlementAwards.dataset.selected;
  }
  if (newResult && !effects.reduced() && !document.hidden) {
    settlement = { result, phase: "runout", progress: 0 };
  }

  renderBoard(previous, result);
  renderSeats(result, previous);
  renderPlayerHand(previous, result);
  renderControls();
  renderResult();
  renderLog();
  renderSettlement();
  if (previous) playUpdate(previous, result);
  if (newResult && settlement) startSettlement(previous);
  else if (newResult) effects.playWin(settlementSound(result));
}

function cardHtml(card, extra = "", index = 0) {
  if (!card) return '<span class="card card-slot" aria-hidden="true"></span>';
  const style = `style="--card-index:${index}"`;
  if (card === "XX") {
    return `<span class="card card-back ${extra}" ${style} role="img" aria-label="盖牌"><span aria-hidden="true">♠</span></span>`;
  }
  const rank = card[0] === "T" ? "10" : card[0];
  const suit = card[1];
  const color = suit === "h" || suit === "d" ? "red" : "";
  return `<span class="card card-face ${color} ${extra}" ${style} data-card="${card}" role="img" aria-label="${suitNames[suit]} ${rank}">
    <span class="card-corner" aria-hidden="true"><b>${rank}</b><span>${suits[suit]}</span></span>
    <span class="card-pip" aria-hidden="true">${suits[suit]}</span>
  </span>`;
}

function renderBoard(previous, result) {
  const cards = result?.community_cards ?? state.community_cards;
  const key = JSON.stringify([state.hand_number, cards]);
  if (key !== boardKey) {
    const revealed = previous?.hand_number === state.hand_number ? previous.community_cards.length : 0;
    community.innerHTML = Array.from({ length: 5 }, (_, index) => {
      const entering = previous && index >= revealed && index < cards.length;
      return cardHtml(cards[index], entering ? "card-reveal" : "", index - revealed);
    }).join("");
    boardKey = key;
  }

  if (result) {
    cancelAnimationFrame(potCountFrame);
    potCountFrame = null;
    pot.textContent = format(settlement ? Math.round(result.pot * (1 - settlement.progress)) : 0);
    street.textContent = `第 ${state.hand_number} 手 · ${result.reason === "showdown" ? "摊牌" : "弃牌结算"}`;
    return;
  }
  const total = state.pot;
  const before = previous?.hand_number === state.hand_number
    ? (previous.phase === "waiting" && previous.last_result?.hand_number === previous.hand_number
      ? previous.last_result.pot : previous.pot)
    : null;
  if (total !== before || !potCountFrame) {
    cancelAnimationFrame(potCountFrame);
    const onIncrease = before !== null && total > before && !effects.reduced();
    if (onIncrease) {
      const start = performance.now();
      pot.animate([{ scale: 1 }, { scale: 1.1, offset: 0.35 }, { scale: 1 }], { duration: 285 });
      const count = (now) => {
        const progress = Math.min(1, (now - start) / 290);
        pot.textContent = format(Math.round(before + (total - before) * (1 - (1 - progress) ** 3)));
        potCountFrame = progress < 1 ? requestAnimationFrame(count) : null;
      };
      potCountFrame = requestAnimationFrame(count);
    } else {
      potCountFrame = null;
      pot.textContent = format(total);
    }
  }

  street.textContent = state.hand_number && state.phase !== "waiting" ? `第 ${state.hand_number} 手 · ${phases[state.phase]}`
    : phases.waiting;
}

function renderPlayerHand(previous, result) {
  const player = viewerSeat();
  const shown = result?.showdown_players.find((entry) => entry.user_id === currentUserId);
  const cards = shown?.hole_cards ?? player?.hole_cards ?? [];
  const deal = previous && (previous.hand_number !== state.hand_number || !viewerSeat(previous)?.hole_cards.length);
  const key = JSON.stringify([state.hand_number, cards, player?.folded, result?.hand_number, phraseOpen]);
  if (key === handKey) return;
  handKey = key;
  playerHand.classList.toggle("hand-folded", Boolean(player?.folded));
  const row = cards.map((card, index) => cardHtml(card, deal && !result ? "card-dealt" : "", index)).join("");
  const folding = player?.folded && previous && !viewerSeat(previous)?.folded;
  playerHand.innerHTML = row ? `<div class="card-row own-cards${folding ? " folding-cards" : ""}">${row}</div>` : "";
  if (player?.hole_cards.length && !result && !isDemo) {
    const phrase = button("短语", () => setPhraseOpen(!phraseOpen), "ghost-button phrase-trigger");
    phrase.setAttribute("aria-expanded", phraseOpen);
    playerHand.append(phrase);
  }
}

function positionSeat(node, seatIndex) {
  const count = state.players.length;
  const index = (seatIndex - layoutAnchor + count) % count;
  const desktop = index === 0 ? [50, 86] : opponentPositions[count][index - 1];
  const mobile = index === 0 ? [50, 88] : mobilePositions[count][index - 1];
  node.style.setProperty("--desk-x", `${desktop[0]}%`);
  node.style.setProperty("--desk-y", `${desktop[1]}%`);
  node.style.setProperty("--mobile-x", `${mobile[0]}%`);
  node.style.setProperty("--mobile-y", `${mobile[1]}%`);
}

function renderSeats(result = currentResult(), previous = null) {
  const focusedSeat = document.activeElement?.closest(".seat");
  const focusIndex = focusedSeat?.dataset.seatIndex;
  const focusAction = focusedSeat && document.activeElement.dataset.seatAction;
  const viewer = viewerSeat();
  const currentActions = (state.actions || []).filter((action) => action.phase === state.phase);
  const previousRebuys = new Map(previous?.players.filter((seat) => seat.occupied)
    .map((seat) => [seat.user_id, seat.rebuy_count ?? 0]));
  seats.replaceChildren();
  for (const seat of state.players) {
    const index = seat.seat_index;
    const self = seat.occupied && seat.user_id === currentUserId;
    const award = result?.awards.find((entry) => entry.user_id === seat.user_id);
    const winner = settlement?.phase === "runout" ? null : award;
    const revealed = result?.showdown_players.find((entry) => entry.user_id === seat.user_id);
    const revealCards = revealed && settlement?.phase === "reveal";
    const viewCards = revealed
      ? (settlement?.phase === "runout" ? ["XX", "XX"] : revealed.hole_cards)
      : (seat.folded ? [] : seat.hole_cards);
    const turn = index === state.current_turn_seat;
    const latest = currentActions.findLast((action) => action.seat_index === index);
    const node = document.createElement("article");
    node.dataset.seatIndex = index;
    node.className = ["seat", !seat.occupied && "empty", self && "self-seat", turn && "current-turn",
      seat.folded && "folded-seat", winner && "winner-seat", seat.all_in && "all-in-seat"].filter(Boolean).join(" ");
    positionSeat(node, index);
    if (!seat.occupied) {
      node.innerHTML = `<span class="empty-label">${index + 1} 号座</span>`;
      if (state.phase === "waiting") {
        const row = document.createElement("div");
        row.className = "seat-actions";
        const take = button(viewer ? "换座" : "入座", () => send("seat.take", { seat_index: index }));
        take.dataset.seatAction = "take";
        row.append(take);
        if (isOwner && botOptions.length) {
          const bot = button("+ BOT", () => openBotModal(index));
          bot.dataset.seatAction = "bot";
          bot.setAttribute("aria-label", `添加机器人到 ${index + 1} 号座`);
          row.append(bot);
        }
        node.append(row);
      }
    } else {
      const badges = [
        ["dealer", result?.summary.dealer_seat ?? state.dealer_seat, "庄家"],
        ["small_blind", result?.summary.small_blind_seat ?? state.small_blind_seat, "小盲"],
        ["big_blind", result?.summary.big_blind_seat ?? state.big_blind_seat, "大盲"],
      ].filter(([, roleSeat]) => roleSeat === index).map(([role, , label]) => {
        const amount = latest?.action_type === role && latest.amount ? ` ${format(latest.amount)}` : "";
        return `<span class="seat-tag role-${role}">${label}${amount}</span>`;
      });
      let subtitle = "";
      if (winner) {
        const { title } = resultHand(result, winner);
        subtitle = settlement ? title : `${title} · +${format(winner.amount)}`;
      }
      else if (seat.all_in) subtitle = "全下";
      else if (seat.folded) subtitle = "弃牌";
      else if (turn) subtitle = "行动中";
      else if (revealed && settlement?.phase !== "runout") subtitle = resultHand(result, revealed).title;
      else if (state.phase === "waiting" && seat.ready && !settlement) subtitle = "已准备";
      else if (latest && !["small_blind", "big_blind"].includes(latest.action_type)) {
        subtitle = [actions[latest.action_type], seat.current_bet ? format(seat.current_bet) : ""].filter(Boolean).join(" ");
      }
      else if (state.phase !== "waiting" && !seat.in_hand) subtitle = "观战";
      if (!seat.connected && seat.player_type !== "bot" && !self && !subtitle) subtitle = "离线";

      if (subtitle) badges.push(`<span class="seat-tag seat-status">${escapeHtml(subtitle)}</span>`);
      if (seat.rebuy_count) {
        const previousCount = previousRebuys.get(seat.user_id);
        const activated = previousCount !== undefined && seat.rebuy_count > previousCount;
        badges.push(`<span class="seat-tag rebuy-badge${activated ? " rebuy-activated" : ""}">复活甲 ×${format(seat.rebuy_count)}</span>`);
      }
      const name = escapeHtml(displayName(seat));
      node.innerHTML = `
        ${!self && viewCards?.length ? `<div class="card-row seat-cards">${viewCards.map((card, cardIndex) => cardHtml(card, revealCards ? "showdown-card" : "", cardIndex)).join("")}</div>` : ""}
        <div class="seat-plate">
          <div class="seat-name" title="${name}">${name}</div>
          <div class="seat-balance">
            <strong class="seat-stack">${format(displayStack(seat, award))}</strong>
            ${self ? '<span class="seat-identity self-identity">我</span>'
              : seat.player_type === "bot" ? '<span class="seat-identity">BOT</span>' : ""}
          </div>
        </div>
        ${badges.length ? `<div class="seat-tags">${badges.join("")}</div>` : ""}
      `;
      if (isOwner && seat.player_type === "bot" && state.phase === "waiting" && !settlement) {
        const remove = button("×", () => send("bot.remove", { seat_index: index }), "ghost-button remove-bot");
        remove.dataset.seatAction = "remove";
        remove.title = "移除机器人";
        remove.setAttribute("aria-label", `移除机器人 ${displayName(seat)}`);
        node.append(remove);
      }
      if (self && phraseOpen) renderPhrasePicker(node);
    }
    seats.append(node);
  }
  if (focusAction) seats.querySelector(`[data-seat-index="${focusIndex}"] [data-seat-action="${focusAction}"]`)?.focus({ preventScroll: true });
}

function openBotModal(index) {
  selectedBotSeat = index;
  botStrategy.replaceChildren(...botOptions.map((option) => new Option(option.label || option.name, option.name)));
  renderBotVariants();
  openModal(botModal);
}

function renderBotVariants() {
  const strategy = botOptions.find((option) => option.name === botStrategy.value);
  botVariant.replaceChildren(...strategy.variants.map((variant) => new Option(variant.label || variant.name, variant.name)));
  botVariant.value = strategy.default_variant ?? botVariant.options[0]?.value;
  renderBotDescription();
}

function renderBotDescription() {
  const strategy = botOptions.find((option) => option.name === botStrategy.value);
  botDescription.textContent = strategy.variants.find((option) => option.name === botVariant.value)?.description || strategy.description || "";
}

botStrategy?.addEventListener("change", renderBotVariants);
botVariant?.addEventListener("change", renderBotDescription);
botForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  if (send("bot.add", { seat_index: selectedBotSeat, strategy: botStrategy.value, variant: botVariant.value })) botModal.close();
});

function setPhraseOpen(open) {
  if (open === phraseOpen) return;
  phraseOpen = open;
  renderSeats();
  renderPlayerHand(null, currentResult());
  (open ? seats.querySelector(".phrase-option") : playerHand.querySelector(".phrase-trigger"))?.focus();
}

document.addEventListener("click", (event) => {
  if (phraseOpen && !event.target.closest(".phrase-picker, .phrase-trigger")) setPhraseOpen(false);
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") setPhraseOpen(false);
});

function renderPhrasePicker(seat) {
  const picker = document.createElement("div");
  picker.className = "phrase-picker";
  for (const phrase of state.quick_phrases) {
    picker.append(button(phrase, () => {
      if (send("phrase.send", { text: phrase })) setPhraseOpen(false);
    }, "ghost-button phrase-option"));
  }
  seat.append(picker);
}

function showPhrase(phrase) {
  const bubble = document.createElement("div");
  const index = phrase.seat_index;
  phraseLayer.querySelector(`[data-seat-index="${index}"]`)?.remove();
  bubble.dataset.seatIndex = index;
  bubble.className = "phrase-bubble";
  bubble.textContent = phrase.text;
  positionSeat(bubble, index);
  phraseLayer.append(bubble);
  window.setTimeout(() => bubble.remove(), phrase.duration_ms || 4000);
}

function renderControls() {
  if (isDemo) return;
  controls.hidden = Boolean(settlement);
  const player = viewerSeat();
  const active = state.players[state.current_turn_seat];
  const legal = state.legal_actions;
  const context = JSON.stringify([connected, state.hand_number, state.phase, state.current_bet, state.pot,
    player?.seat_index, player?.ready, active?.username, player?.folded, player?.all_in,
    state.can_start, legal, currentResult()?.hand_number]);
  if (context === controlKey) return;
  controlKey = context;

  const title = !connected ? "正在同步牌桌" : legal.length ? "轮到你" :
    state.phase === "waiting" ? (player ? (player.ready ? "已准备" : "准备下一手") : "选择空座入座") :
    player?.folded ? "你已弃牌" : player?.all_in ? "你已全下" :
    active ? `等待 ${displayName(active)}` : "牌局进行中";
  const detail = connected && legal.length
    ? (legal.some((action) => action.type === "call") ? "本轮有下注" : "可以过牌")
    : state.phase === "waiting" && player?.ready ? "等其他玩家准备" : "";
  controls.innerHTML = `<div class="action-status${legal.length && connected ? " your-turn" : ""}" role="status">
    <strong>${escapeHtml(title)}</strong>${detail ? `<span>${detail}</span>` : ""}
  </div>`;
  const row = document.createElement("div");
  row.className = "action-row";
  controls.append(row);

  if (state.phase === "waiting" && player) {
    if (!player.ready) row.append(button("准备", () => send("room.ready", { ready: true }), "button primary"));
    else if (state.can_start) row.append(button("开始发牌", () => send("hand.start"), "button primary"));
    row.append(button("离座", () => send("seat.leave")));
  }

  if (legal.length) {
    const sized = legal.find(({ type }) => type === "bet" || type === "raise");
    const allIn = legal.find(({ type }) => type === "all_in");
    const call = legal.find(({ type }) => type === "call");
    for (const action of legal) {
      if (action === sized || action === allIn) continue;
      const label = action === call ? `跟注 ${format(action.amount)}` : actions[action.type];
      row.append(button(label, () => send("hand.action", { action_type: action.type, amount: action.amount }),
        `button action-button action-${action.type}`));
    }
    if (sized) renderSizing(row, sized, call, allIn);
    else if (allIn) {
      const amount = allIn.amount - player.current_bet;
      const review = button(`全下 ${format(amount)}`, () => {
        review.hidden = true;
        confirm.hidden = false;
        back.hidden = false;
        confirm.focus();
      }, "button danger action-button");
      const confirm = button(`确认全下 ${format(amount)}`, () => send("hand.action", { action_type: "all_in", amount: allIn.amount }),
        "button danger action-button");
      const back = button("取消", () => {
        review.hidden = false;
        confirm.hidden = true;
        back.hidden = true;
        review.focus();
      }, "button secondary");
      confirm.hidden = true;
      back.hidden = true;
      row.append(review, confirm, back);
    }
  }

  if (!row.childElementCount) row.remove();
  syncPending();
}

function renderSizing(row, action, call, allIn) {
  const presets = raisePresets(state, action, call, allIn);
  const editor = document.createElement("div");
  editor.className = "raise-editor";
  editor.innerHTML = `
    <div class="raise-presets" role="group" aria-label="常用金额"></div>
    <div class="raise-adjust">
      <input class="raise-slider" type="range" aria-label="调整${actions[action.type]}金额">
      <label>${action.type === "raise" ? "加注到" : "下注额"} <input class="raise-number" type="number" step="1" inputmode="numeric" required></label>
    </div>`;
  const presetRow = editor.querySelector(".raise-presets");
  const slider = editor.querySelector(".raise-slider");
  const input = editor.querySelector(".raise-number");
  let selected = presets[0];
  function isAllIn() {
    return allIn && Number(input.value) === allIn.amount;
  }
  for (const field of [slider, input]) {
    field.min = action.min;
    field.max = action.max;
    field.value = selected.amount;
  }

  function sync() {
    const value = Number(slider.value);
    const ratio = action.max === action.min ? 1 : (value - action.min) / (action.max - action.min);
    slider.style.setProperty("--fill", `${ratio * 100}%`);
    for (const [index, node] of [...presetRow.children].entries()) {
      node.setAttribute("aria-pressed", presets[index] === selected);
    }
    commit.textContent = isAllIn() ? "确认全下" : actions[action.type];
    commit.classList.toggle("danger", Boolean(isAllIn()));
    commit.classList.toggle("primary", !isAllIn());
  }

  function setAmount(amount, preset) {
    input.value = amount;
    slider.value = amount;
    selected = preset;
    sync();
  }

  const commit = button(actions[action.type], () => {
    if (!input.reportValidity()) return;
    send("hand.action", { action_type: isAllIn() ? "all_in" : action.type, amount: Number(input.value) });
  }, "button primary action-button");
  row.append(commit);

  for (const preset of presets) {
    const shortcut = button(preset.label, () => {
      setAmount(preset.amount, preset);
      effects.play("select");
    }, `raise-preset${preset.allIn ? " all-in-preset" : ""}`);
    shortcut.title = `${actions[action.type]}${action.type === "raise" ? "到" : " "}${format(preset.amount)}`;
    presetRow.append(shortcut);
  }

  slider.addEventListener("input", () => setAmount(Number(slider.value), null));
  input.addEventListener("input", () => {
    if (input.checkValidity()) slider.value = input.value;
    selected = null;
    sync();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") commit.click();
  });
  controls.append(editor);
  sync();
}

function renderResult() {
  const result = state.last_result;
  const key = JSON.stringify(result && [result.hand_number, result.ended_at]);
  if (key === resultKey) return;
  resultKey = key;
  resultBox.hidden = !result;
  if (!result) {
    resultBox.replaceChildren();
    resultModal.close();
    return;
  }
  const winners = result.awards.map((award) =>
    `<span class="result-winner"><b>${escapeHtml(displayName(award))}</b> <strong>+${format(award.amount)}</strong> <small>${escapeHtml(resultHand(result, award).title)}</small></span>`
  ).join("");
  resultBox.innerHTML = `<div class="result-caption">第 ${result.hand_number} 手结算</div><div class="result-winners">${winners}</div>`;
  resultBox.append(button("查看详情", () => openModal(resultModal), "ghost-button"));
  resultBody.innerHTML = `
    <div class="result-summary">第 ${result.hand_number} 手 · 底池 ${format(result.pot)} · ${result.reason === "showdown" ? "摊牌" : "弃牌结算"}</div>
    <div class="result-winners">${winners}</div>
    ${result.community_cards.length ? `<div class="card-row">${result.community_cards.map((card) => cardHtml(card)).join("")}</div>` : ""}
    <div class="showdown-list">${result.showdown_players.map((player) => `
      <article class="showdown-row">
        <div><strong>${escapeHtml(displayName(player))}</strong><span>${escapeHtml(resultHand(result, player).title)}</span></div>
        <div class="card-row">${player.hole_cards.map((card) => cardHtml(card)).join("")}</div>
      </article>`).join("")}</div>`;
}

function displayStack(seat, award) {
  return seat.stack - (settlement && award ? Math.round(award.amount * (1 - settlement.progress)) : 0);
}

function resultHand(result, entry) {
  const hole = entry.hole_cards ?? result.showdown_players.find((player) => player.user_id === entry.user_id)?.hole_cards;
  return showdownHand(entry.hand_rank, hole ? [...result.community_cards, ...hole] : []);
}

function settlementSound(result) {
  return Math.max(0, ...result.awards.map((award) => showdownProfile(resultHand(result, award).effect).sound));
}

function renderSettlement() {
  const result = currentResult();
  app.dataset.settlement = result ? settlement?.phase ?? "complete" : "";
  const runout = settlement?.phase === "runout";
  settlementView.hidden = !result || runout;
  settlementTools.hidden = !result;
  settlementSkip.hidden = !settlement;
  settlementDetails.hidden = Boolean(settlement);
  delete app.dataset.handEffect;
  if (!result || runout) return;

  const focus = result.awards.find((award) => award.user_id === featuredWinner)
    ?? result.awards.find((award) => award.user_id === currentUserId)
    ?? result.awards.reduce((largest, award) => !largest || award.amount > largest.amount ? award : largest, null);
  if (!focus) {
    settlementCaption.textContent = "";
    settlementTitle.textContent = "本手结束";
    settlementAwards.replaceChildren();
    return;
  }
  const hand = resultHand(result, focus);
  const split = result.awards.length > 1;
  const self = focus.user_id === currentUserId;
  settlementView.classList.toggle("viewer-won", self);
  app.dataset.handEffect = hand.effect;
  settlementView.style.setProperty("--hand-accent", showdownProfile(hand.effect).color);
  settlementCaption.textContent = split ? `分池 · ${self ? "你" : displayName(focus)}`
    : self ? "你赢下底池" : `${displayName(focus)}获胜`;
  const title = result.reason === "showdown" ? hand.title : "其余玩家弃牌";
  if (settlementTitle.textContent !== title) settlementTitle.textContent = title;

  if (split && settlementAwards.dataset.selected !== String(focus.user_id)) {
    settlementAwards.dataset.selected = String(focus.user_id);
    settlementAwards.replaceChildren(...result.awards.map((award) => {
      const selector = button(`${award.user_id === currentUserId ? "你" : displayName(award)} +${format(award.amount)}`, () => {
        featuredWinner = award.user_id;
        renderSettlement();
        settlementAwards.querySelector('[aria-pressed="true"]')?.focus({ preventScroll: true });
      }, "settlement-award");
      selector.setAttribute("aria-pressed", award === focus);
      return selector;
    }));
  } else if (!split) {
    delete settlementAwards.dataset.selected;
    settlementAwards.innerHTML = `<strong class="settlement-amount">+${format(focus.amount)}</strong>`;
  }

  for (const card of app.querySelectorAll(".table-surface .card-face")) {
    const owner = card.closest(".seat")?.dataset.seatIndex;
    const ownCard = playerHand.contains(card);
    const onBoard = community.contains(card);
    const eligible = onBoard || (ownCard ? self : Number(owner) === focus.seat_index);
    const matched = eligible && hand.cards.includes(card.dataset.card);
    card.classList.toggle("winning-card", matched);
    card.classList.toggle("unused-card", onBoard && hand.cards.length > 0 && !matched);
    if (matched) {
      const beat = showdownRhythm(hand.effect)[hand.cards.indexOf(card.dataset.card)];
      card.style.setProperty("--winning-delay", `${beat?.[0] ?? 0}ms`);
    }
  }
}

function startSettlement(previous) {
  const run = settlement;
  const result = run.result;
  const previousCards = previous.hand_number === result.hand_number ? previous.community_cards.length : 0;
  const newCards = Math.max(0, result.community_cards.length - previousCards);
  const sound = settlementSound(result);
  const revealDelay = result.reason === "showdown" ? (newCards ? 325 + (newCards - 1) * 80 : 180) : 150;
  run.timer = window.setTimeout(() => {
    run.phase = "reveal";
    renderSeats(result);
    renderSettlement();
    const handEffect = app.dataset.handEffect;
    effects.revealHand(handEffect);
    const beats = showdownRhythm(handEffect);
    if (!beats.length) effects.play("reveal");
    beats.forEach(([delay, pitch], index) => {
      cue(delay, () => {
        if (settlement === run) effects.playHandNote(handEffect, pitch, index === beats.length - 1);
      });
    });
    run.timer = window.setTimeout(() => collectSettlement(run, sound), showdownProfile(handEffect).hold);
  }, revealDelay);
}

function collectSettlement(run, sound) {
  const { result } = run;
  run.phase = "collect";
  renderSettlement();
  effects.flash("payout");
  result.awards.forEach((award) => effects.chips(seatForUser(award.user_id)?.querySelector(".seat-plate"), award.amount, true, false, resultHand(result, award).effect));
  const launched = performance.now();
  const duration = 520;
  function count(now) {
    run.progress = Math.min(1, Math.max(0, (now - launched - 475) / duration));
    if (run.progress > 0 && !run.landed) {
      run.landed = true;
      effects.playWin(sound);
      for (const award of result.awards) {
        const plate = seatForUser(award.user_id)?.querySelector(".seat-plate");
        effects.land(plate, resultHand(result, award).effect);
        plate?.animate(
          [{ scale: 1 }, { scale: 1.055, offset: 0.28 }, { scale: 1 }],
          { duration: 320, easing: "ease-out" },
        );
      }
    }
    pot.textContent = format(Math.round(result.pot * (1 - run.progress)));
    for (const award of result.awards) {
      const seat = state.players.find((player) => player.user_id === award.user_id);
      const stack = seatForUser(award.user_id)?.querySelector(".seat-stack");
      if (seat && stack) stack.textContent = format(displayStack(seat, award));
    }
    if (run.progress < 1) run.frame = requestAnimationFrame(count);
    else finishSettlement();
  }
  run.frame = requestAnimationFrame(count);
}

function seatForUser(userId) {
  const seat = state.players.find((player) => player.occupied && player.user_id === userId);
  return seat ? seats.querySelector(`[data-seat-index="${seat.seat_index}"]`) : null;
}

function clearSettlement() {
  if (!settlement) return;
  window.clearTimeout(settlement.timer);
  cancelAnimationFrame(settlement.frame);
  settlement = null;
}

function finishSettlement() {
  if (!settlement) return;
  clearSettlement();
  const result = currentResult();
  renderBoard(null, result);
  renderSeats(result);
  renderControls();
  renderSettlement();
}

function skipSettlement() {
  if (!settlement) return;
  effectTimers.forEach((timer) => window.clearTimeout(timer));
  effectTimers = [];
  effects.clear();
  finishSettlement();
}

function renderLog() {
  if (!log) return;
  log.innerHTML = state.actions.slice(-12).reverse().map((action) => {
    const player = state.players.find((seat) => seat.occupied && seat.user_id === action.user_id);
    const name = player ? displayName(player) : (Number.isInteger(action.seat_index) ? `${action.seat_index + 1} 号座` : "牌桌");
    return `<li><span>${phases[action.phase] ?? ""}</span><strong>${escapeHtml(name)}</strong>
      <span>${actions[action.action_type] ?? ""} ${action.amount ? format(action.amount) : ""}</span></li>`;
  }).join("") || '<li class="muted">本手尚无动作</li>';
}

function cue(delay, callback) {
  const timer = window.setTimeout(() => {
    effectTimers = effectTimers.filter((entry) => entry !== timer);
    if (!document.hidden) callback();
  }, delay);
  effectTimers.push(timer);
}

function playUpdate(previous, result) {
  const sameHand = previous.hand_number === state.hand_number;
  const lastSequence = sameHand ? previous.actions.at(-1)?.sequence ?? 0 : 0;
  const events = state.actions.filter((event) => event.sequence > lastSequence);
  const cardsBefore = sameHand ? previous.community_cards.length : 0;
  const cardsAfter = (result?.community_cards ?? state.community_cards).length;
  const findSeat = (index, userId) => state.players[index]?.user_id === userId
    ? seats.querySelector(`[data-seat-index="${index}"]`) : null;

  if (!sameHand && !result) effects.play("deal");
  for (let index = cardsBefore; index < cardsAfter; index += 1) {
    cue(75 + (index - cardsBefore) * 80, () => effects.play("deal"));
  }

  const playerEvents = events.filter(({ action_type }) =>
    ["fold", "check", "call", "bet", "raise", "all_in"].includes(action_type));
  const addedChips = new Map();
  for (const event of events) {
    if (event.seat_index === null || !event.amount) continue;
    addedChips.set(event.user_id, (addedChips.get(event.user_id) ?? 0) + event.amount);
  }
  const remaining = new Map(previous.players.filter((seat) => seat.occupied).map((seat) => [seat.user_id, seat.stack]));
  if (!sameHand) {
    remaining.clear();
    for (const seat of state.players) {
      if (seat.occupied && !result) remaining.set(seat.user_id, seat.stack + (addedChips.get(seat.user_id) ?? 0));
    }
  }
  const impacts = playerEvents.map((event) => {
    const left = remaining.get(event.user_id);
    if (left !== undefined) remaining.set(event.user_id, left - event.amount);
    return { event, heavy: event.action_type === "all_in" || (event.amount > 0 && left === event.amount) };
  });
  impacts.slice(-5).forEach(({ event, heavy }, index) => {
    cue(index * 88, () => {
      const node = findSeat(event.seat_index, event.user_id);
      if (heavy) effects.flash("impact");
      if (event.amount) effects.chips(node, event.amount, false, heavy);
      if (event.action_type === "fold") animateFold(node, event.user_id);
      effects.play(heavy ? "all_in" : event.amount ? "chip" : event.action_type);
    });
  });

  if (!result && state.legal_actions.length && (!previous.legal_actions.length || events.length)) {
    cue(190, () => effects.play("turn"));
  }
}

function animateFold(node, userId) {
  if (!node || userId === currentUserId || effects.reduced()) return;
  const cards = document.createElement("div");
  cards.className = "card-row seat-cards";
  cards.innerHTML = cardHtml("XX").repeat(2);
  cards.setAttribute("aria-hidden", "true");
  node.prepend(cards);
  cards.animate([{ opacity: 1 }, { opacity: 0, translate: "0 22px", scale: 0.7 }], {
    duration: 220, easing: "ease-in",
  }).onfinish = () => cards.remove();
}

if (isDemo) {
  const { startDemo } = await import("./effects-demo.js?v=20261115-1");
  connected = true;
  startDemo(app, (snapshot, animate) => {
    if (!animate) {
      clearSettlement();
      effects.clear();
      resultModal.close();
    }
    const previous = state;
    state = snapshot;
    render(animate ? previous : null);
  });
} else {
  render();
  connect();
}
