const profiles = {
  fold:            { sound: 0, hold: 525, chips: 6, sparks: 0, color: "#8ee9de" },
  "high-card":     { sound: 0, hold: 670, chips: 6, sparks: 0, color: "#addefa", slash: 1 },
  pair:            { sound: 0, hold: 700, chips: 7, sparks: 0, color: "#80f4dd", pinch: 2 },
  "two-pair":      { sound: 1, hold: 750, chips: 8, sparks: 2, color: "#65ffca", ripple: 2 },
  trips:           { sound: 1, hold: 780, chips: 9, sparks: 3, color: "#6ef4ff", strike: 3 },
  straight:        { sound: 1, hold: 825, chips: 10, sparks: 5, color: "#7de4ff", rail: 5 },
  flush:           { sound: 2, hold: 870, chips: 11, sparks: 6, color: "#77afff", wave: 3 },
  "full-house":    { sound: 2, hold: 925, chips: 12, sparks: 8, color: "#b5a8ff", frame: 5 },
  quads:           { sound: 2, hold: 985, chips: 13, sparks: 12, color: "#ff9a8c", lock: 4, shock: 1 },
  "straight-flush": { sound: 3, hold: 1060, chips: 15, sparks: 14, color: "#d4a9ff", comet: 5, halo: 1 },
  "royal-flush":   { sound: 3, hold: 1175, chips: 17, sparks: 18, color: "#ffe1a4", ray: 5, crown: 1, halo: 2 },
};

// Each entry pairs a card's highlight time in milliseconds with its pitch.
const rhythms = {
  "high-card": [[0, 523]],
  pair: [[0, 587], [105, 587]],
  "two-pair": [[0, 587], [85, 587], [285, 698], [370, 698]],
  trips: [[0, 523], [95, 659], [190, 784]],
  straight: [[0, 392], [86, 440], [172, 494], [258, 523], [344, 587]],
  flush: [[0, 784], [78, 784], [156, 784], [234, 784], [312, 784]],
  "full-house": [[0, 587], [74, 587], [148, 587], [347, 784], [466, 784]],
  quads: [[0, 330], [102, 330], [204, 330], [306, 330]],
  "straight-flush": [[0, 523], [73, 587], [146, 659], [219, 784], [292, 1047]],
  "royal-flush": [[0, 523], [112, 659], [224, 784], [336, 1047], [490, 1319]],
};

export function showdownProfile(effect) {
  return profiles[effect] ?? profiles.fold;
}

export function showdownRhythm(effect) {
  return rhythms[effect] ?? [];
}

export function showHandEffect(layer, banner, effect) {
  const { sound, hold, chips, sparks, color, ...shapes } = showdownProfile(effect);
  if (!Object.keys(shapes).length) return;
  const frame = layer.getBoundingClientRect();
  const title = banner.getBoundingClientRect();
  const scale = frame.width / layer.clientWidth || 1;
  const stage = document.createElement("div");
  stage.className = "showdown-effect";
  stage.dataset.effect = effect;
  stage.style.left = `${(title.left + title.width / 2 - frame.left) / scale}px`;
  stage.style.top = `${(title.top + title.height / 2 - frame.top) / scale}px`;
  stage.style.width = `${title.width / scale}px`;
  stage.style.height = `${title.height / scale}px`;
  stage.style.setProperty("--accent", color);
  stage.style.animationDuration = `${hold}ms`;
  for (const [kind, count] of Object.entries(shapes)) {
    for (let index = 0; index < count; index++) {
      const shape = document.createElement("i");
      shape.className = `showdown-${kind}`;
      shape.style.setProperty("--index", index);
      shape.style.setProperty("--centered", index - (count - 1) / 2);
      stage.append(shape);
    }
  }
  stage.addEventListener("animationend", (event) => {
    if (event.target === stage) stage.remove();
  });
  layer.append(stage);
}
