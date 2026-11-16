import { svgEl, label } from '../tmt/field.js';

// The Stroop screen (T3.2, decisions 88, 90): a dark page; on the task area
// (240 x 150 mm) a dot at its centre, the word above the dot, and four plain
// coloured plates below it, one per colour, in a fixed order. Everything is
// SVG whose user unit is 1 mm, sized in CSS px from the calibration, like the
// TMT field. Used by the dev page (dev-stroop.js) and by the run (run.js).

const mm = (x) => Number(x.toFixed(3));

// Where the plates stand, in mm from the dot (x to the right, y down).
// layout 'row': a row under the dot; 'arc': on a circle round the dot, so that
// every plate is as far from the dot as any other.
export function platePlacements(spec, order) {
  const p = spec.plates;
  if (p.layout === 'arc') {
    return order.map((id, i) => {
      const a = (p.angles_deg[i] * Math.PI) / 180;
      return { id, cx: p.radius_mm * Math.sin(a), cy: p.radius_mm * Math.cos(a), w: p.w_mm, h: p.h_mm };
    });
  }
  const step = p.w_mm + p.gap_mm;
  const first = (-(order.length - 1) / 2) * step;
  return order.map((id, i) => ({ id, cx: first + i * step, cy: p.top_below_dot_mm + p.h_mm / 2, w: p.w_mm, h: p.h_mm }));
}

// What the screen takes up around the dot, in mm: the plates and the word.
// A check that it fits in the task area.
export function extent(spec, order, wordWidthMm = 0) {
  const plates = platePlacements(spec, order);
  const bottom = Math.max(...plates.map((p) => p.cy + p.h / 2));
  const side = Math.max(...plates.map((p) => Math.abs(p.cx) + p.w / 2), wordWidthMm / 2);
  const top = spec.word_above_dot_mm + spec.word_cap_mm / 2;
  return { top, bottom, side };
}

let ruler = null;
// Width in mm of `text` in the bundled font at font size `sizeMm`, measured
// with a canvas (the font must be loaded first).
export function measureText(text, sizeMm, font) {
  ruler ??= document.createElement('canvas').getContext('2d');
  ruler.font = `${font.weight} 100px '${font.family}'`;
  return (ruler.measureText(text).width / 100) * sizeMm;
}

export const FEEDBACK_CAP_MM = 5;

// Breaks a text into lines no wider than maxMm at the font size sizeMm.
export function wrapLines(text, maxMm, sizeMm, font) {
  const lines = [];
  let line = '';
  for (const word of text.split(' ')) {
    const next = line ? `${line} ${word}` : word;
    if (line && measureText(next, sizeMm, font) > maxMm) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

// Builds the screen. spec: one variant of stimuli/stroop-candidates.json (or the
// chosen one); words: { colorId: 'ЧЕРВОНИЙ', ... }; order: the colour ids in the
// order of the plates. Returns { root, svg, dot, plates: {id: rect}, word,
// setWord(colorId | null, inkId), setDotVisible(on), setHint(text | null) }.
export function createStroopScreen({ spec, words, order, area, font, pxPerMm, container = null }) {
  const root = document.createElement('div');
  root.className = 'stroop-screen';
  root.style.background = spec.bg;
  const svg = svgEl('svg', {
    viewBox: `0 0 ${area.w} ${area.h}`,
    width: mm(area.w * pxPerMm),
    height: mm(area.h * pxPerMm),
    class: 'stroop-area',
  });
  const cx = area.w / 2;
  const cy = area.h / 2;

  const plates = {};
  for (const placement of platePlacements(spec, order)) {
    const r = spec.plates.corner_mm ?? 3;
    const rect = svgEl('rect', {
      x: mm(cx + placement.cx - placement.w / 2),
      y: mm(cy + placement.cy - placement.h / 2),
      width: mm(placement.w),
      height: mm(placement.h),
      rx: r,
      fill: spec.colors[placement.id],
      class: 'stroop-plate',
      'data-color': placement.id,
    });
    plates[placement.id] = rect;
    svg.append(rect);
  }

  const dot = svgEl('g', { class: 'stroop-dot' });
  dot.append(svgEl('circle', { cx: mm(cx), cy: mm(cy), r: mm(spec.dot_hit_mm / 2), fill: 'transparent', class: 'stroop-dot-hit' }));
  dot.append(svgEl('circle', { cx: mm(cx), cy: mm(cy), r: mm(spec.dot_mm / 2), fill: spec.dot_color, class: 'stroop-dot-visible' }));
  svg.append(dot);

  const hint = label('', cx, cy + spec.hint_below_dot_mm, 4.5, font, { fill: spec.dot_color, class: 'stroop-hint' });
  hint.style.display = 'none';
  svg.append(hint);

  // The word: SVG text of capital height word_cap_mm, centred above the dot.
  let word = null;
  const wordY = cy - spec.word_above_dot_mm;
  function setWord(wordId, inkId) {
    word?.remove();
    word = null;
    if (wordId === null) return;
    word = label(words[wordId], cx, wordY, spec.word_cap_mm, font, {
      fill: spec.colors[inkId],
      class: 'stroop-word',
      'data-word': wordId,
      'data-ink': inkId,
    });
    svg.append(word);
  }

  // Feedback in training (decision 153): a short text in place of the word, in
  // the neutral colour of the dot (never in one of the four colours), broken
  // into lines that fit the area.
  let feedback = null;
  function setFeedback(text, kind = null) {
    feedback?.remove();
    feedback = null;
    if (!text) return;
    const capMm = FEEDBACK_CAP_MM;
    const lines = wrapLines(text, area.w - 16, capMm / font.cap, font);
    const lineGap = capMm * 1.9;
    feedback = svgEl('g', { class: 'stroop-feedback', 'data-kind': kind ?? '' });
    lines.forEach((line, n) => {
      feedback.append(label(line, cx, wordY + (n - (lines.length - 1) / 2) * lineGap, capMm, font, { fill: spec.dot_color }));
    });
    svg.append(feedback);
  }

  root.append(svg);
  container?.append(root);
  return {
    root,
    svg,
    dot,
    plates,
    get word() {
      return word;
    },
    setWord,
    setDotVisible(on) {
      dot.style.display = on ? '' : 'none';
    },
    setFeedback,
    setHint(text) {
      hint.textContent = text ?? '';
      hint.style.display = text ? '' : 'none';
    },
  };
}
