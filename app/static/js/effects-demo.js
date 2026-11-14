const hands = [
  ["高牌", "2c 5d 8s Jh 3c", "As Qd", "Kd 9h"],
  ["一对", "2c 5d 8s Jh 3c", "As Ad", "Kd 9h"],
  ["两对", "5d Qd 6h Qs 4h", "Ac Ah", "Th Kc"],
  ["三条", "2c 5d 8s Jh 3c", "Jc Jd", "Kd 9h"],
  ["顺子", "2c 5d 8s 7h 3c", "6s 4d", "Kd 9h"],
  ["同花", "2s 5s 8s Jh 3c", "As Qs", "Kd 9h"],
  ["葫芦", "2c 5d 8s Jh 5c", "Jc Jd", "Kd 9h"],
  ["四条", "2c 5d 8s Jh Js", "Jc Jd", "Kd 9h"],
  ["同花顺", "2s 5s 6s Jh 3c", "3s 4s", "Kd 9h"],
  ["皇家同花顺", "Ts Js Qs 2c 3d", "As Ks", "Kd 9h"],
];
const clips = [
  { name: "发牌", event: "deal" },
  { name: "加注", event: "raise" },
  { name: "全下", event: "all_in" },
  { name: "弃牌收池", event: "fold" },
  ...hands.map(([name, board, own, opponent]) => ({
    name, board: board.split(" "), own: own.split(" "), opponent: opponent.split(" "),
  })),
];

function action(state, action_type, seat_index, amount = 0) {
  return { sequence: state.actions.length + 1, hand_number: state.hand_number, phase: state.phase,
    action_type, seat_index, user_id: state.players[seat_index]?.user_id, amount };
}

function snapshots(clip, hand_number) {
  const { name, event } = clip;
  const board = clip.board ?? ["5d", "Qd", "6h", "Qs", "4h"];
  const own = clip.own ?? ["Ac", "Ah"];
  const opponent = clip.opponent ?? ["Th", "Kc"];
  const phase = event === "deal" ? "preflop" : !event ? "turn" : "flop";
  const base = {
    room: { big_blind: 20, seat_count: 2 },
    phase, hand_number, dealer_seat: 0, small_blind_seat: 0, big_blind_seat: 1,
    current_turn_seat: 1, current_bet: 0, pot: event === "deal" ? 30 : 320,
    community_cards: board.slice(0, phase === "turn" ? 4 : phase === "flop" ? 3 : 0),
    legal_actions: [], actions: [], last_result: null,
    players: [
      { seat_index: 0, user_id: 1, username: "你", occupied: true, connected: true, in_hand: true, stack: 840, hole_cards: own },
      { seat_index: 1, user_id: 2, username: "对手", occupied: true, connected: true, in_hand: true, stack: 840, hole_cards: ["XX", "XX"] },
    ],
  };
  const next = structuredClone(base);
  if (event === "deal") {
    base.hand_number--;
    base.phase = "waiting";
    for (const player of base.players) player.hole_cards = [];
    next.phase = "flop";
    next.community_cards = board.slice(0, 3);
  } else if (event === "raise" || event === "all_in") {
    const amount = event === "all_in" ? 840 : 180;
    next.pot += amount;
    next.current_turn_seat = 0;
    next.actions = [action(base, event, 1, amount)];
    Object.assign(next.players[1], { stack: 840 - amount, current_bet: amount, all_in: event === "all_in" });
  } else {
    const fold = event === "fold";
    next.phase = "waiting";
    next.current_turn_seat = null;
    next.community_cards = fold ? base.community_cards : board;
    next.players[0].stack += base.pot;
    for (const player of next.players) Object.assign(player, { in_hand: false, hole_cards: [] });
    if (fold) next.actions = [action(base, "fold", 1)];
    next.last_result = {
      hand_number, ended_at: String(hand_number), pot: base.pot, reason: fold ? "fold" : "showdown",
      summary: { dealer_seat: 0, small_blind_seat: 0, big_blind_seat: 1 },
      community_cards: next.community_cards,
      awards: [{ seat_index: 0, user_id: 1, username: "你", amount: base.pot, hand_rank: fold ? "无人争夺" : name }],
      showdown_players: fold ? [] : [
        { seat_index: 0, user_id: 1, username: "你", hand_rank: name, hole_cards: own },
        { seat_index: 1, user_id: 2, username: "对手", hand_rank: ["两对", "葫芦"].includes(name) ? "一对" : "高牌", hole_cards: opponent },
      ],
    };
  }
  return [base, next];
}

export function startDemo(app, show) {
  const select = app.querySelector("#demo-clip");
  const play = app.querySelector("#demo-play");
  const playAll = app.querySelector("#demo-play-all");
  const status = app.querySelector("#demo-status");
  let timer;
  let handNumber = 1;
  let continuous = false;
  clips.forEach((clip, index) => select.add(new Option(clip.name, index)));
  select.value = clips.findIndex((clip) => clip.name === "两对");

  function stop() {
    window.clearTimeout(timer);
    continuous = false;
    playAll.textContent = "连续播放";
  }

  function playClip(index) {
    window.clearTimeout(timer);
    const clip = clips[index];
    const [before, after] = snapshots(clip, handNumber++);
    select.value = index;
    show(before, false);
    status.textContent = `正在播放 · ${clip.name}`;
    timer = window.setTimeout(() => {
      show(after, true);
      timer = window.setTimeout(() => {
        if (continuous && index + 1 < clips.length) playClip(index + 1);
        else {
          status.textContent = continuous ? "全部片段已播完" : `${clip.name} · 播放完毕`;
          stop();
        }
      }, after.last_result ? 3100 : 1450);
    }, 230);
  }

  select.addEventListener("change", () => { stop(); playClip(Number(select.value)); });
  play.addEventListener("click", () => { stop(); playClip(Number(select.value)); });
  playAll.addEventListener("click", () => {
    if (continuous) {
      stop();
      status.textContent = "已停止连续播放";
    } else {
      continuous = true;
      playAll.textContent = "停止连播";
      playClip(0);
    }
  });
  show(snapshots(clips[Number(select.value)], handNumber++)[0], false);
  status.textContent = "点播放查看当前片段，或连续播放全部特效。";
}
