import { svgEl, label } from '../tmt/field.js';

// The SART screen (T3.3): the task area (240 x 150 mm) with one thing at its
// centre: a digit of one of five sizes, the mask (a ring with a diagonal
// cross) or, in the countdown, a text with a bar. Everything is SVG whose user
// unit is 1 mm, sized in CSS px from the calibration, like the TMT field.
// Used by the dev page (dev-sart.js) and, later, by the run.

const mm = (x) => Number(x.toFixed(3));

// The mask: a ring of diameter mask_mm with a diagonal cross inside it.
export function maskGroup(spec, cx, cy) {
  const r = (spec.mask_mm - spec.mask_line_mm) / 2;
  const k = r / Math.SQRT2;
  const g = svgEl('g', { class: 'sart-mask' });
  g.append(svgEl('circle', { cx: mm(cx), cy: mm(cy), r: mm(r), fill: 'none', stroke: spec.mask_color, 'stroke-width': spec.mask_line_mm }));
  g.append(
    svgEl('path', {
      d: `M${mm(cx - k)} ${mm(cy - k)}L${mm(cx + k)} ${mm(cy + k)}M${mm(cx - k)} ${mm(cy + k)}L${mm(cx + k)} ${mm(cy - k)}`,
      stroke: spec.mask_color,
      'stroke-width': spec.mask_line_mm,
      fill: 'none',
    }),
  );
  return g;
}

// Builds the screen. spec: one variant of stimuli/sart-candidates.json (or the
// chosen one). Returns { root, svg, setDigit(digit, sizeIndex), setMask(),
// setBlank(), setHint(text | null), setCountdown(share | null) }.
export function createSartScreen({ spec, area, font, pxPerMm, container = null }) {
  const root = document.createElement('div');
  root.className = 'sart-screen';
  root.style.background = spec.bg;
  const svg = svgEl('svg', {
    viewBox: `0 0 ${area.w} ${area.h}`,
    width: mm(area.w * pxPerMm),
    height: mm(area.h * pxPerMm),
    class: 'sart-area',
  });
  const cx = area.w / 2;
  const cy = area.h / 2;

  const stage = svgEl('g', { class: 'sart-stage' });
  const hint = svgEl('g', { class: 'sart-hint' });
  const countdown = svgEl('g', { class: 'sart-countdown' });
  svg.append(stage, hint, countdown);

  root.append(svg);
  container?.append(root);

  function clear() {
    stage.replaceChildren();
  }
  return {
    root,
    svg,
    setDigit(digit, sizeIndex) {
      clear();
      stage.append(
        label(String(digit), cx, cy, spec.digit_cap_mm[sizeIndex], font, {
          fill: spec.fg,
          class: 'sart-digit',
          'data-digit': digit,
          'data-size': sizeIndex,
        }),
      );
    },
    setMask() {
      clear();
      stage.append(maskGroup(spec, cx, cy));
    },
    setBlank() {
      clear();
    },
    // A short text under the middle of the screen (feedback in training).
    setHint(text) {
      hint.replaceChildren();
      if (text) hint.append(label(text, cx, cy + spec.hint_below_center_mm, spec.hint_cap_mm, font, { fill: spec.hint_color }));
    },
    // The countdown: the text and a bar of `share` (0..1) of its full width.
    setCountdown(share, text = 'Приготуйтеся…') {
      countdown.replaceChildren();
      if (share === null) return;
      const c = spec.countdown;
      countdown.append(label(text, cx, cy - c.text_above_center_mm, c.text_cap_mm, font, { fill: spec.fg }));
      const top = cy + c.bar_below_center_mm;
      countdown.append(
        svgEl('rect', { x: mm(cx - c.bar_w_mm / 2), y: mm(top), width: mm(c.bar_w_mm), height: mm(c.bar_h_mm), fill: 'none', stroke: spec.hint_color, 'stroke-width': 0.3 }),
        svgEl('rect', { x: mm(cx - c.bar_w_mm / 2), y: mm(top), width: mm(c.bar_w_mm * share), height: mm(c.bar_h_mm), fill: spec.fg, class: 'sart-bar' }),
      );
    },
  };
}
