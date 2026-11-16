import { svgEl, label } from '../tmt/field.js';

// The figures of the symbol coding task (T3.1, decisions 79, 82): loading and
// drawing in real millimetres. A figure is strokes of one thickness plus
// dots, in a 100 x 100 box (tools/coding_symbols.py), so every browser draws
// the same thing and no font is involved. The key (nine figures with the
// digits 1-9 under them) and the frame with the current figure are SVG whose
// user unit is 1 mm, sized in CSS px from the calibration, like the TMT field.

export const SYMBOLS_URL = 'stimuli/coding-symbols.json'; // the chosen set
export const CANDIDATES_URL = 'stimuli/coding-symbol-candidates.json'; // sets to choose from

const mm = (x) => Number(x.toFixed(3));

export async function loadJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json();
}

// The figure as a nested SVG `sizeMm` wide with its top left corner at (x, y).
// spec: { box, stroke, dot_r } from the figures file.
export function figure(symbol, spec, x, y, sizeMm) {
  const root = svgEl('svg', {
    x: mm(x),
    y: mm(y),
    width: mm(sizeMm),
    height: mm(sizeMm),
    viewBox: `0 0 ${spec.box} ${spec.box}`,
    class: 'coding-figure',
    'data-symbol': symbol.id,
  });
  const lines = svgEl('g', {
    fill: 'none',
    stroke: '#000',
    'stroke-width': spec.stroke,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
  });
  for (const d of symbol.paths) lines.append(svgEl('path', { d }));
  root.append(lines);
  for (const [cx, cy] of symbol.dots) root.append(svgEl('circle', { cx, cy, r: spec.dot_r, fill: '#000' }));
  return root;
}

const CELL_PAD_MM = 3; // space between a figure or a digit and the border of its cell
export const KEY_LINE_MM = 0.3;

// Size of the key in mm for the given sizes: nine cells in a row, a figure
// over a digit.
export function keySize(sizes) {
  const figureCell = sizes.figureMm + 2 * CELL_PAD_MM;
  const digitCell = sizes.keyDigitMm + 2 * CELL_PAD_MM;
  return { w: 9 * sizes.keyCellMm, h: figureCell + digitCell, figureCell, digitCell };
}

// sizes: { figureMm, keyCellMm, keyDigitMm }. font: { family, weight, cap }
// like in tmt/field.js. Cell i holds figure i + 1 and the digit i + 1.
export function renderKey({ symbols, spec, sizes, font, pxPerMm }) {
  const size = keySize(sizes);
  const half = KEY_LINE_MM / 2;
  const svg = svgEl('svg', {
    class: 'coding-key',
    width: mm(size.w * pxPerMm),
    height: mm(size.h * pxPerMm),
    viewBox: `0 0 ${mm(size.w)} ${mm(size.h)}`,
  });
  symbols.forEach((symbol, i) => {
    const x = i * sizes.keyCellMm;
    svg.append(
      svgEl('rect', {
        x: mm(x + half),
        y: half,
        width: mm(sizes.keyCellMm - KEY_LINE_MM),
        height: mm(size.h - KEY_LINE_MM),
        fill: '#fff',
        stroke: '#000',
        'stroke-width': KEY_LINE_MM,
      }),
      svgEl('line', {
        x1: mm(x),
        x2: mm(x + sizes.keyCellMm),
        y1: mm(size.figureCell),
        y2: mm(size.figureCell),
        stroke: '#000',
        'stroke-width': KEY_LINE_MM,
      }),
      figure(symbol, spec, x + (sizes.keyCellMm - sizes.figureMm) / 2, CELL_PAD_MM, sizes.figureMm),
      label(String(i + 1), x + sizes.keyCellMm / 2, size.figureCell + size.digitCell / 2, sizes.keyDigitMm, font, {
        'data-digit': i + 1,
      }),
    );
  });
  return svg;
}

// The frame with the figure the participant has to answer to.
// sizes: { figureMm, frameMm }.
export function renderFrame({ symbol, spec, sizes, pxPerMm }) {
  const { frameMm, figureMm } = sizes;
  const svg = svgEl('svg', {
    class: 'coding-frame',
    width: mm(frameMm * pxPerMm),
    height: mm(frameMm * pxPerMm),
    viewBox: `0 0 ${mm(frameMm)} ${mm(frameMm)}`,
  });
  svg.append(
    svgEl('rect', {
      x: KEY_LINE_MM,
      y: KEY_LINE_MM,
      width: mm(frameMm - 2 * KEY_LINE_MM),
      height: mm(frameMm - 2 * KEY_LINE_MM),
      fill: '#fff',
      stroke: '#000',
      'stroke-width': KEY_LINE_MM * 2,
    }),
    figure(symbol, spec, (frameMm - figureMm) / 2, (frameMm - figureMm) / 2, figureMm),
  );
  return svg;
}

// One figure alone, `sizeMm` wide, as its own SVG (enlarged views).
export function renderFigure({ symbol, spec, sizeMm, pxPerMm }) {
  const svg = svgEl('svg', {
    class: 'coding-single',
    width: mm(sizeMm * pxPerMm),
    height: mm(sizeMm * pxPerMm),
    viewBox: `0 0 ${mm(sizeMm)} ${mm(sizeMm)}`,
  });
  svg.append(figure(symbol, spec, 0, 0, sizeMm));
  return svg;
}

export const SEQUENCE_URL = 'stimuli/coding-sequence.json';

// What the coding block needs: the chosen set of figures and the fixed
// sequence (decisions 89, 144). Loaded before the session starts, like the
// TMT stimuli. The sequence names the version of the set it was made for.
export async function loadCodingStimuli() {
  const [set, sequence] = await Promise.all([loadJson(SYMBOLS_URL), loadJson(SEQUENCE_URL)]);
  if (sequence.symbols_version !== set.symbols_version) {
    throw new Error(`${SEQUENCE_URL}: made for figures version ${sequence.symbols_version}, not ${set.symbols_version}`);
  }
  return { set, sequence };
}
