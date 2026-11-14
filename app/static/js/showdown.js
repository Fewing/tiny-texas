const ranks = "23456789TJQKA";
const suits = "cdhs";
const rankNames = {
  "straight flush": "同花顺", "four of a kind": "四条", "full house": "葫芦",
  flush: "同花", straight: "顺子", "three of a kind": "三条",
  "two pair": "两对", "one pair": "一对", "high card": "高牌",
  uncontested: "其余玩家弃牌", "无人争夺": "其余玩家弃牌",
};

export function rankName(name) {
  return rankNames[name] ?? name ?? "";
}

const effects = {
  "高牌": "high-card", "一对": "pair", "两对": "two-pair", "三条": "trips",
  "顺子": "straight", "同花": "flush", "葫芦": "full-house", "四条": "quads",
  "同花顺": "straight-flush", "皇家同花顺": "royal-flush",
};
const groupSizes = { "四条": [4], "葫芦": [3, 2], "三条": [3], "两对": [2, 2], "一对": [2], "高牌": [1] };

// Use the server's hand category to identify the cards that make the hand.
// This runs on public showdown cards only and never decides who gets paid.
export function showdownHand(name, cards) {
  let title = rankName(name);
  const sorted = [...cards].sort((a, b) => ranks.indexOf(b[0]) - ranks.indexOf(a[0]));
  const groups = new Map();
  for (const card of sorted) {
    if (!groups.has(card[0])) groups.set(card[0], []);
    groups.get(card[0]).push(card);
  }
  const sets = [...groups.values()];

  const suited = [...suits].map((suit) => sorted.filter((card) => card[1] === suit))
    .find((group) => group.length >= 5) ?? [];
  let highlights = [];
  if (title === "顺子" || title === "同花顺" || title === "皇家同花顺") {
    const source = title === "顺子" ? sorted : suited;
    const byRank = new Map(source.map((card) => [card[0], card]));
    const sequence = "A" + ranks;
    for (let end = sequence.length; end >= 5; end--) {
      const run = [...sequence.slice(end - 5, end)].map((rank) => byRank.get(rank));
      if (!run.every(Boolean)) continue;
      if (title === "同花顺" && run[0][0] === "T") title = "皇家同花顺";
      highlights = run;
      break;
    }
  } else if (title === "同花") {
    highlights = suited.slice(0, 5);
  } else {
    for (const size of groupSizes[title] ?? []) {
      const index = sets.findIndex((group) => group.length >= size);
      if (index >= 0) highlights.push(...sets.splice(index, 1)[0].slice(0, size));
    }
  }
  return { title, cards: highlights, effect: effects[title] ?? "fold" };
}
