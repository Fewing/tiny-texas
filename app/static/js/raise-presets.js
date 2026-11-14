export function raisePresets(state, action, call, allIn) {
  const { big_blind: bigBlind } = state.room;
  const unopened = state.phase === "preflop" && state.current_bet === bigBlind &&
    !state.actions.some(({ action_type: type }) => ["raise", "bet", "all_in"].includes(type));
  const sizes = unopened
    ? [["2 BB", 2 * bigBlind], ["2.5 BB", 2.5 * bigBlind], ["3 BB", 3 * bigBlind]]
    : [["½ 底池", 0.5], ["¾ 底池", 0.75], ["满池", 1]].map(([label, fraction]) => [
      label, state.current_bet + fraction * (state.pot + (call?.amount ?? 0)),
    ]);
  const presets = [["最小", action.min], ...sizes].map(([label, amount]) => ({
    label,
    amount: Math.max(action.min, Math.min(action.max, Math.round(amount))),
  }));
  if (allIn) presets.push({ label: "全下", amount: allIn.amount, allIn: true });
  return presets;
}
