import { showHandEffect, showdownProfile } from "./showdown-effects.js?v=20261116-5";

const tones = {
  select: [[640, 480, 0.045, 0.026, 0]],
  turn: [[510, 590, 0.11, 0.034, 0], [770, 860, 0.10, 0.025, 0.085]],
  chip: [[1680, 900, 0.045, 0.048, 0], [640, 330, 0.07, 0.04, 0.031]],
  check: [[380, 180, 0.066, 0.033, 0]],
  fold: [[280, 95, 0.11, 0.048, 0]],
  deal: [[430, 150, 0.085, 0.045, 0], [1450, 650, 0.045, 0.023, 0.045]],
  all_in: [[120, 43, 0.28, 0.18, 0], [360, 118, 0.16, 0.10, 0], [1120, 580, 0.1, 0.058, 0.07]],
  reveal: [[450, 650, 0.14, 0.043, 0], [690, 840, 0.1, 0.028, 0.08]],
  win: [[100, 50, 0.24, 0.19, 0], [294, 294, 0.16, 0.05, 0], [440, 440, 0.18, 0.055, 0.085],
    [587, 587, 0.36, 0.067, 0.16], [880, 880, 0.3, 0.036, 0.22]],
  winAccent: [[1175, 1175, 0.24, 0.045, 0.25]],
  winPeak: [[75, 42, 0.31, 0.11, 0.05], [1480, 1480, 0.29, 0.043, 0.30]],
  winFinale: [[196, 196, 0.3, 0.035, 0.10], [1760, 1760, 0.36, 0.035, 0.39]],
};

const textures = {
  deal: [0.075, 1300, 0.1, 0],
  fold: [0.105, 960, 0.12, 0],
  chip: [0.032, 3100, 0.08, 0.028],
  all_in: [0.13, 700, 0.13, 0],
};

export function createRoomEffects(app) {
  const table = app.querySelector("#table-surface");
  const pot = app.querySelector("#pot-box");
  const settlement = app.querySelector("#settlement");
  const layer = app.querySelector("#effects-layer");
  const soundToggle = document.querySelector("#sound-toggle");
  const motionToggle = document.querySelector("#motion-toggle");
  const motionPreference = matchMedia("(prefers-reduced-motion: reduce)");
  let soundOn = preference("sound") !== "off";
  let lessMotion = preference("motion");
  let context;
  let noise;

  function preference(key, value) {
    try {
      if (value !== undefined) localStorage.setItem(`tiny-texas:${key}`, value);
      return localStorage.getItem(`tiny-texas:${key}`);
    } catch {
      return null;
    }
  }

  function reduced() {
    return lessMotion === null ? motionPreference.matches : lessMotion === "on";
  }

  function updateSettings() {
    soundToggle.setAttribute("aria-pressed", soundOn);
    soundToggle.textContent = soundOn ? "音效 · 开" : "音效 · 关";
    motionToggle.setAttribute("aria-pressed", reduced());
    app.dataset.reducedMotion = reduced();
    if (reduced()) layer.replaceChildren();
  }

  function unlock() {
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!soundOn || !Audio) return;
    context ??= new Audio();
    if (context.state === "suspended") context.resume().catch(() => {});
  }

  document.addEventListener("pointerdown", unlock);
  document.addEventListener("keydown", unlock);
  motionPreference.addEventListener("change", updateSettings);
  soundToggle.addEventListener("click", () => {
    soundOn = !soundOn;
    preference("sound", soundOn ? "on" : "off");
    updateSettings();
    if (soundOn) unlock();
    else context?.suspend().catch(() => {});
  });
  motionToggle.addEventListener("click", () => {
    lessMotion = reduced() ? "off" : "on";
    preference("motion", lessMotion);
    updateSettings();
  });
  updateSettings();

  function play(name) {
    if (!soundOn || context?.state !== "running" || document.hidden) return;
    if (textures[name]) playTexture(textures[name]);
    const type = name.startsWith("win") || name === "turn" ? "sine" : "triangle";
    for (const note of tones[name]) synthesize(note, type);
  }

  function synthesize([start, end, duration, volume, delay], type) {
    const at = context.currentTime + delay;
    const wave = context.createOscillator();
    const envelope = context.createGain();
    wave.type = type;
    wave.frequency.setValueAtTime(start, at);
    wave.frequency.exponentialRampToValueAtTime(end, at + duration);
    envelope.gain.setValueAtTime(0.001, at);
    envelope.gain.exponentialRampToValueAtTime(volume, at + 0.012);
    envelope.gain.exponentialRampToValueAtTime(0.001, at + duration);
    wave.connect(envelope).connect(context.destination);
    wave.start(at);
    wave.stop(at + duration);
  }

  function playTexture([duration, frequency, volume, delay]) {
    if (!noise) {
      noise = context.createBuffer(1, Math.ceil(context.sampleRate * 0.15), context.sampleRate);
      const samples = noise.getChannelData(0);
      for (let index = 0; index < samples.length; index += 1) samples[index] = Math.random() * 2 - 1;
    }
    const at = context.currentTime + delay;
    const source = context.createBufferSource();
    const filter = context.createBiquadFilter();
    const envelope = context.createGain();
    source.buffer = noise;
    filter.type = "bandpass";
    filter.frequency.value = frequency;
    envelope.gain.setValueAtTime(0.001, at);
    envelope.gain.exponentialRampToValueAtTime(volume, at + 0.009);
    envelope.gain.exponentialRampToValueAtTime(0.001, at + duration);
    source.connect(filter).connect(envelope).connect(context.destination);
    source.start(at, 0, duration);
  }

  function playHandNote(effect, pitch, last) {
    if (!soundOn || context?.state !== "running" || document.hidden) return;
    const level = showdownProfile(effect).sound;
    const duration = [0.085, 0.105, 0.15, 0.17][level];
    synthesize([pitch, pitch * .985, duration, .13, 0], level === 2 ? "sine" : "triangle");
    if (level >= 2) synthesize([pitch * 2, pitch * 2, .065, .035, 0], "sine");
    if (effect === "quads") synthesize([115, 57, .14, .09, 0], "sine");
    if (last && level === 3) synthesize([pitch / 2, pitch / 2, .29, .07, 0], "sine");
  }

  function playWin(level) {
    play("win");
    if (level > 0) play("winAccent");
    if (level > 1) play("winPeak");
    if (level > 2) play("winFinale");
  }

  function revealHand(effect) {
    if (!reduced()) showHandEffect(layer, settlement, effect);
  }

  function flash(type) {
    if (reduced()) return;
    const node = table.querySelector(".table-flash");
    node.className = "table-flash";
    void node.offsetWidth;
    node.classList.add(type);
  }

  function clear() {
    table.querySelector(".table-flash").className = "table-flash";
    layer.replaceChildren();
  }

  function center(node) {
    const bounds = node.getBoundingClientRect();
    const frame = layer.getBoundingClientRect();
    const scale = frame.width / layer.clientWidth || 1;
    return { x: (bounds.left + bounds.width / 2 - frame.left) / scale, y: (bounds.top + bounds.height / 2 - frame.top) / scale };
  }

  function chips(seat, amount, award = false, heavy = false, effect = "fold") {
    if (!seat || reduced()) return;
    const start = center(award ? settlement : seat);
    const finish = center(award ? seat : pot);
    const profile = showdownProfile(effect);
    const count = award ? profile.chips : heavy ? 5 : 2;
    for (let index = 0; index < count; index += 1) {
      const chip = document.createElement("i");
      chip.className = `flying-chip${award ? " award-chip" : ""}${heavy ? " heavy-chip" : ""}`;
      if (award) chip.style.setProperty("--accent", profile.color);
      chip.style.left = `${start.x}px`;
      chip.style.top = `${start.y}px`;
      const spread = award ? (index % 4 - 1.5) * 8 : (index - 1) * 8;
      chip.style.setProperty("--dx", `${finish.x - start.x + spread}px`);
      chip.style.setProperty("--dy", `${finish.y - start.y + (index % 2) * 5}px`);
      chip.style.setProperty("--arc", `${(index % 4 - 1.5) * 14}px`);
      chip.style.animationDelay = `${index * (award ? 100 / (count - 1) : 31)}ms`;
      layer.append(chip);
      chip.addEventListener("animationend", () => chip.remove(), { once: true });
    }
    const label = document.createElement("span");
    label.className = award ? "flying-value award-value" : "flying-value";
    label.textContent = `${award ? "+" : ""}${amount.toLocaleString("zh-CN")}`;
    label.style.left = `${finish.x}px`;
    label.style.top = `${finish.y}px`;
    layer.append(label);
    label.addEventListener("animationend", () => label.remove(), { once: true });
  }

  function land(seat, effect) {
    if (!seat || reduced()) return;
    const finish = center(seat);
    const impact = document.createElement("i");
    impact.className = "award-impact";
    const profile = showdownProfile(effect);
    impact.style.setProperty("--accent", profile.color);
    impact.style.setProperty("--impact-size", `${82 + profile.sparks * 2}px`);
    impact.style.left = `${finish.x}px`;
    impact.style.top = `${finish.y}px`;
    layer.append(impact);
    impact.addEventListener("animationend", () => impact.remove(), { once: true });
    const sparkCount = profile.sparks;
    for (let index = 0; index < sparkCount; index++) {
      const spark = document.createElement("i");
      const angle = index * 2 * Math.PI / sparkCount;
      const reach = 34 + sparkCount * 2 + (index % 2) * 13;
      spark.className = "award-spark";
      spark.style.setProperty("--accent", profile.color);
      spark.style.left = `${finish.x}px`;
      spark.style.top = `${finish.y}px`;
      spark.style.setProperty("--dx", `${Math.cos(angle) * reach}px`);
      spark.style.setProperty("--dy", `${Math.sin(angle) * reach * .65}px`);
      layer.append(spark);
      spark.addEventListener("animationend", () => spark.remove(), { once: true });
    }
  }

  return { play, playHandNote, playWin, revealHand, flash, chips, land, reduced, clear };
}
