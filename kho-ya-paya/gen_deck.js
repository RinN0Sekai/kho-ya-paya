// Kho-Ya-Paya pitch deck — pptxgenjs. Run: node gen_deck.js
const Pptx = require("pptxgenjs");
const p = new Pptx();
p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";

const INK = "14282E", WHITE = "FFFFFF", SAFFRON = "E87722", TEAL = "1D6E7A",
  MUTE = "5F6B6E", GREEN = "1D9E75", AMBER = "B7791F", RED = "CF3B3B", LIGHT = "F4F1EA";
const H = "Cambria", B = "Calibri";
const W = 13.333, HT = 7.5, M = 0.7;

function card(s, x, y, w, h, fill) {
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, fill: { color: fill || LIGHT },
    line: { type: "none" }, rectRadius: 0.1 });
}
function dot(s, x, y, color, ch) {
  s.addShape(p.ShapeType.ellipse, { x, y, w: 0.5, h: 0.5, fill: { color } });
  s.addText(ch, { x, y, w: 0.5, h: 0.5, align: "center", valign: "middle",
    fontFace: B, fontSize: 16, bold: true, color: WHITE });
}

// ---- Slide 1: title (dark) ----
let s = p.addSlide(); s.background = { color: INK };
s.addText("खोया–पाया", { x: M, y: 1.3, w: 6, h: 0.7, fontFace: H, fontSize: 26, color: SAFFRON });
s.addText("Kho-Ya-Paya", { x: M, y: 2.0, w: 12, h: 1.4, fontFace: H, fontSize: 60, bold: true, color: WHITE });
s.addText("Cross-center reunification for Kumbh Mela 2027", { x: M, y: 3.35, w: 12, h: 0.7, fontFace: B, fontSize: 24, color: "CADCFC" });
s.addText([
  { text: "A person found at any Kho-Ya-Paya center, ", options: {} },
  { text: "instantly searchable at every other", options: { color: SAFFRON, bold: true } },
  { text: " — offline, multilingual, with a human as the only authority that confirms a reunion.", options: {} },
], { x: M, y: 4.5, w: 11.5, h: 1.2, fontFace: B, fontSize: 17, color: "D6DEDF", lineSpacingMultiple: 1.2 });
s.addText("Claude Impact Lab · Mumbai 2026 · 80 million pilgrims, thousands lost each day", { x: M, y: 6.5, w: 12, h: 0.5, fontFace: B, fontSize: 13, color: MUTE });

// ---- Slide 2: the one gap ----
s = p.addSlide(); s.background = { color: WHITE };
s.addText("The one gap", { x: M, y: 0.6, w: 8, h: 0.8, fontFace: H, fontSize: 40, bold: true, color: INK });
s.addText('"A person registered at Center A is invisible to a family searching at Center B."', {
  x: M, y: 1.7, w: 7.4, h: 2.0, fontFace: H, fontSize: 26, italic: true, color: TEAL, lineSpacingMultiple: 1.15 });
s.addText("10 manual lost-and-found centers. No cross-search. Today the bridge between them is paper, PA announcements, and luck — and the people who go missing are mostly phoneless, non-literate, multilingual elders.", {
  x: M, y: 4.0, w: 7.4, h: 1.8, fontFace: B, fontSize: 16, color: "334144", lineSpacingMultiple: 1.25 });
// right: A --x-- B visual
card(s, 8.7, 2.0, 1.9, 1.2, LIGHT); s.addText("Center A", { x: 8.7, y: 2.0, w: 1.9, h: 1.2, align: "center", valign: "middle", fontFace: B, fontSize: 16, bold: true, color: INK });
card(s, 11.0, 2.0, 1.9, 1.2, LIGHT); s.addText("Center B", { x: 11.0, y: 2.0, w: 1.9, h: 1.2, align: "center", valign: "middle", fontFace: B, fontSize: 16, bold: true, color: INK });
s.addShape(p.ShapeType.line, { x: 10.6, y: 2.6, w: 0.4, h: 0, line: { color: RED, width: 3, dashType: "dash" } });
s.addText("✕", { x: 10.55, y: 2.25, w: 0.5, h: 0.5, align: "center", fontFace: B, fontSize: 22, bold: true, color: RED });
s.addText("found here", { x: 8.7, y: 3.2, w: 1.9, h: 0.4, align: "center", fontFace: B, fontSize: 12, color: MUTE });
s.addText("family searches here", { x: 11.0, y: 3.2, w: 1.9, h: 0.4, align: "center", fontFace: B, fontSize: 12, color: MUTE });
card(s, 8.7, 4.3, 4.2, 1.3, "FBEFE6"); s.addText("That one sentence drives the entire architecture.", { x: 8.9, y: 4.3, w: 3.8, h: 1.3, valign: "middle", fontFace: B, fontSize: 16, bold: true, color: SAFFRON });

// ---- Slide 3: data reality ----
s = p.addSlide(); s.background = { color: WHITE };
s.addText("What the data says — and what kills naive solutions", { x: M, y: 0.6, w: 12, h: 0.8, fontFace: H, fontSize: 32, bold: true, color: INK });
const facts = [
  ["Mobile is 100% unique (2,008 / 2,008)", "It's the family's number → never a person key. Dedup on it catches zero cross-center duplicates."],
  ["Gender contradicts the description 48%", "Put gender in the blocking key and you silently drop ~half the true pairs of the exact elderly cohort."],
  ["14.8% no name · 19.7% no mobile · no photos", "Face-rec & self-serve search have no input on the missing side. Description + Claude is the identity."],
  ["CCTV is coordinates-only — no video feed", "YOLO has nothing to run on, and would cost $0.6–1.8M in GPUs to reunite no one."],
];
let y = 1.7;
facts.forEach((f, i) => {
  dot(s, M, y + 0.05, [TEAL, SAFFRON, TEAL, RED][i], String(i + 1));
  s.addText(f[0], { x: M + 0.75, y: y - 0.05, w: 11.2, h: 0.45, fontFace: B, fontSize: 18, bold: true, color: INK });
  s.addText(f[1], { x: M + 0.75, y: y + 0.4, w: 11.2, h: 0.65, fontFace: B, fontSize: 14, color: "44504F", lineSpacingMultiple: 1.1 });
  y += 1.3;
});

// ---- Slide 4: architecture ----
s = p.addSlide(); s.background = { color: WHITE };
s.addText("The system", { x: M, y: 0.6, w: 8, h: 0.8, fontFace: H, fontSize: 40, bold: true, color: INK });
s.addText("Two centers as two SQLite replicas. Pure-stdlib Python — runs on an $800 offline box.", { x: M, y: 1.45, w: 12, h: 0.5, fontFace: B, fontSize: 16, color: MUTE });
const comps = [
  ["Offline-first registry", "Append-only, full local replica. Works with the network down; converges on a USB courier."],
  ["Matching brain", "Blocking + evidence-gated bands. Nothing AUTO-SUGGESTs without a strong identifier."],
  ["Claude (advisory)", "Cross-script names (Lokkhi = Lakshmi) + voice intake. Ranks & explains; never confirms."],
  ["Crowd reachability", "Density inverts the search radius — a crush bounds where a lost elder can be."],
  ["Privacy kernel", "Confirm-only search, audited PII, minors police-only. Enforced in code, not slides."],
  ["Reunification", "Routes both parties to the nearest handoff; notifies family with no location leak."],
];
const cw = 3.9, ch = 1.75, gx = 0.25, gy = 0.3;
comps.forEach((c, i) => {
  const cx = M + (i % 3) * (cw + gx), cy = 2.2 + Math.floor(i / 3) * (ch + gy);
  card(s, cx, cy, cw, ch, LIGHT);
  s.addText(c[0], { x: cx + 0.25, y: cy + 0.15, w: cw - 0.5, h: 0.5, fontFace: B, fontSize: 17, bold: true, color: TEAL });
  s.addText(c[1], { x: cx + 0.25, y: cy + 0.62, w: cw - 0.5, h: 1.0, fontFace: B, fontSize: 13, color: "44504F", lineSpacingMultiple: 1.08 });
});

// ---- Slide 5: the demo ----
s = p.addSlide(); s.background = { color: WHITE };
s.addText("Close the gap — live", { x: M, y: 0.6, w: 10, h: 0.8, fontFace: H, fontSize: 40, bold: true, color: INK });
s.addText("Two laptops. Pull the network cable.", { x: M, y: 1.45, w: 12, h: 0.5, fontFace: B, fontSize: 16, color: MUTE });
const steps = [
  ["Report at A", "A son reports his mother by voice in Maithili — no name typed, no phone of hers. Saved offline in 2s."],
  ["Find at B, offline", "A volunteer logs a confused elder at Center B. Cross-search returns 0 matches from A — she's invisible."],
  ["Courier sync", "A USB courier carries the records both ways. The partition heals."],
  ["Reunite", "Lakshmi Jha surfaces — held at REVIEW (no name), so the operator confirms via the family, never the elder."],
];
y = 2.2;
steps.forEach((st, i) => {
  dot(s, M, y, SAFFRON, String(i + 1));
  s.addText(st[0], { x: M + 0.75, y: y - 0.05, w: 11, h: 0.45, fontFace: B, fontSize: 19, bold: true, color: INK });
  s.addText(st[1], { x: M + 0.75, y: y + 0.4, w: 11, h: 0.55, fontFace: B, fontSize: 14, color: "44504F", lineSpacingMultiple: 1.1 });
  y += 1.15;
});

// ---- Slide 6: the numbers (dark) ----
s = p.addSlide(); s.background = { color: INK };
s.addText("The numbers", { x: M, y: 0.6, w: 10, h: 0.8, fontFace: H, fontSize: 40, bold: true, color: WHITE });
const stats = [
  ["$24k + $36/day", "the whole system vs $0.6–1.8M for a YOLO camera farm with no feed", SAFFRON],
  ["0%", "false-confident matches in a negative-control eval (never claim a stranger)", GREEN],
  ["95%", "recall@5 finding a no-name elder across centers — the hard core case", "CADCFC"],
  ["0.29 km", "crowd-modulated search radius at Ramkund on a snan day (6× tighter than normal)", SAFFRON],
];
stats.forEach((st, i) => {
  const cx = M + (i % 2) * 6.1, cy = 2.0 + Math.floor(i / 2) * 2.4;
  s.addText(st[0], { x: cx, y: cy, w: 5.9, h: 1.0, fontFace: H, fontSize: 40, bold: true, color: st[2], fit: "shrink" });
  s.addText(st[1], { x: cx, y: cy + 1.05, w: 5.8, h: 1.0, fontFace: B, fontSize: 15, color: "C7D0D1", lineSpacingMultiple: 1.15 });
});

// ---- Slide 7: why it wins (dark) ----
s = p.addSlide(); s.background = { color: INK };
s.addText("Why it wins", { x: M, y: 0.6, w: 10, h: 0.8, fontFace: H, fontSize: 40, bold: true, color: WHITE });
const crit = [
  ["Deployability", "$800 offline boxes, existing centers/police/CCTV, pure stdlib — no cloud on the life-safety path."],
  ["Real-world fit", "Closes the literal cross-center gap from the problem statement, for the cohort that actually goes missing."],
  ["UX", "Operator-mediated voice + icon, 10 languages, no smartphone or literacy required."],
  ["System design", "Offline-first, append-only sync, duplicate + incomplete-data handling, evidence-gated matching."],
  ["Responsible data", "Confirm-only search, audited PII, AMBER governor, police-only minors, no location leaks."],
];
y = 1.9;
crit.forEach((c) => {
  s.addText(c[0], { x: M, y, w: 3.0, h: 0.7, fontFace: B, fontSize: 18, bold: true, color: SAFFRON });
  s.addText(c[1], { x: M + 3.1, y, w: 8.9, h: 0.7, fontFace: B, fontSize: 15, color: "D6DEDF", valign: "middle", lineSpacingMultiple: 1.05 });
  y += 1.0;
});
s.addText("Build the partition demo, not the dashboard demo — that's how you reunite a phoneless grandmother on the one day 120 million people show up.", {
  x: M, y: 6.7, w: 12, h: 0.6, fontFace: B, fontSize: 14, italic: true, color: SAFFRON });

p.writeFile({ fileName: "Kho-Ya-Paya-pitch.pptx" }).then(f => console.log("wrote", f));
