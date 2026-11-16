import { PARAMS } from './config.js';
import { devUrl } from './dev.js';
import { devScale } from './scale.js';
import { loadFonts } from './tmt/stimuli.js';
import { loadJson } from './coding/symbols.js';
import { createStroopScreen, extent, measureText } from './stroop/screen.js';

// Dev page ?mode=dev&tool=stroop (T3.2). Shows the candidate looks of the
// Stroop screen (decisions 88, 90) in real size, through the last calibration
// made in dev mode in this browser (scale.js): for each variant the screen as
// the participant sees it in a trial, the four words in their own colours and
// in other colours, the colours with their contrast against the background.
// Nothing is sent.

export const CANDIDATES_URL = 'stimuli/stroop-candidates.json';
const num = (x, digits = 1) => x.toFixed(digits).replace('.', ',');

// WCAG contrast ratio of two #rrggbb colours.
function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}
export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export async function renderStroopLooks(session, params = PARAMS) {
  document.body.innerHTML = '<p class="message">Завантаження…</p>';
  let data, fonts;
  try {
    [data, fonts] = await Promise.all([loadJson(CANDIDATES_URL), loadFonts([params.tmt.font])]);
  } catch (error) {
    document.body.innerHTML = `<p class="message">Не вдалося завантажити варіанти: ${error.message}</p>`;
    return;
  }
  const font = fonts[0];
  const scale = devScale();
  const { pxPerMm } = scale;
  const words = Object.fromEntries(data.words.map((w) => [w.id, w.word]));
  const ids = data.order;

  const calibrate = `<a href="${devUrl(session, { only: 'calibration' })}">відкалібрувати</a>`;
  let scaleNote;
  if (scale.source === 'fallback') {
    scaleNote = `<b class="tmt-warn">Масштаб приблизний: ${num(pxPerMm, 2)} px/мм — у цьому браузері калібрування ще не було, розміри несправжні.</b> Спершу треба ${calibrate}.`;
  } else {
    const zoomed =
      scale.dpr !== window.devicePixelRatio
        ? ` <b class="tmt-warn">Масштаб сторінки змінився після калібрування — розміри несправжні.</b>`
        : '';
    scaleNote = `Масштаб: ${num(pxPerMm, 2)} px/мм · ${calibrate} ще раз.${zoomed}`;
  }
  document.body.innerHTML = `
    <main class="dev-stroop">
      <h1>Екран Stroop: варіанти вигляду</h1>
      <p><a href="${devUrl(session)}">До меню</a> · ${scaleNote}</p>
      <p>Усе в справжніх міліметрах на ділянці завдань ${data.area.w} × ${data.area.h} мм (її межа тонка лінія); сторінка зараз
        ${num(window.innerWidth / pxPerMm, 0)} × ${num(window.innerHeight / pxPerMm, 0)} мм. Слово тут — приклад однієї проби
        (СИНІЙ червоним, неконгруентна); у справжньому тесті слова й кольори змінюються. Параметри варіанта можна змінити в
        <code>stimuli/stroop-candidates.json</code>.</p>
      <div class="stroop-variants"></div>
    </main>`;
  const root = document.querySelector('.stroop-variants');
  const info = [];

  for (const spec of data.variants) {
    const section = document.createElement('section');
    section.className = 'stroop-variant';
    section.dataset.variant = spec.id;
    const widest = Math.max(...Object.values(words).map((w) => measureText(w, spec.word_cap_mm / font.cap, font)));
    const box = extent(spec, ids, widest);
    const rows = ids
      .map((id) => {
        const ratio = contrast(spec.colors[id], spec.bg);
        return `<span class="stroop-swatch"><i style="background:${spec.colors[id]}"></i>${id} ${spec.colors[id]} · ${num(ratio)}:1</span>`;
      })
      .join('');
    const p = spec.plates;
    const platesText =
      p.layout === 'row'
        ? `ряд із 4 плашок ${num(p.w_mm, 0)}×${num(p.h_mm, 0)} мм, проміжок ${num(p.gap_mm, 0)} мм, верх плашок на ${num(p.top_below_dot_mm, 0)} мм нижче точки`
        : `4 плашки ${num(p.w_mm, 0)}×${num(p.h_mm, 0)} мм на дузі радіусом ${num(p.radius_mm, 0)} мм навколо точки (кожна на однаковій відстані від неї)`;
    section.innerHTML = `<h2>Варіант ${spec.id} · ${spec.name}</h2>
      <p class="stroop-facts">Фон ${spec.bg}. Слово: великі літери висотою ${num(spec.word_cap_mm, 0)} мм, найширше (ЧЕРВОНИЙ)
        ${num(widest, 0)} мм завширшки, центр слова на ${num(spec.word_above_dot_mm, 0)} мм вище точки. Точка Ø${num(spec.dot_mm, 0)} мм
        (лише орієнтир для погляду, на неї не натискають). Плашки: ${platesText}. Використано по висоті: від ${num(box.top, 0)} мм
        вище точки до ${num(box.bottom, 0)} мм нижче (є ${num(data.area.h / 2, 0)} мм вгору й вниз).</p>
      <div class="stroop-swatches">${rows} <span class="stroop-swatch">контраст з фоном</span></div>
      <div class="stroop-trial"></div>
      <div class="stroop-label">Усі слова своїм кольором (конгруентні) і чужим (неконгруентні), справжній розмір слова</div>
      <div class="stroop-words" style="background:${spec.bg}"></div>`;
    root.append(section);

    const holder = section.querySelector('.stroop-trial');
    holder.style.background = spec.bg;
    const screen = createStroopScreen({ spec, words, order: ids, area: data.area, font, pxPerMm, container: holder });
    screen.setWord('blue', 'red');
    screen.svg.style.outline = '1px solid #777';

    const strip = section.querySelector('.stroop-words');
    const pairs = [
      ...ids.map((id) => [id, id]),
      ['red', 'yellow'],
      ['green', 'blue'],
      ['blue', 'red'],
      ['yellow', 'green'],
    ];
    for (const [wordId, inkId] of pairs) {
      const cell = document.createElement('span');
      cell.className = 'stroop-word-cell';
      cell.style.cssText = `font: 600 ${(spec.word_cap_mm / font.cap) * pxPerMm}px '${font.family}'; color:${spec.colors[inkId]}`;
      cell.textContent = words[wordId];
      cell.dataset.word = wordId;
      cell.dataset.ink = inkId;
      strip.append(cell);
    }
    info.push({ spec, widest, box });
  }

  // Handle for automated checks.
  window.tmtuaStroop = { data, scale, font, info };
}
