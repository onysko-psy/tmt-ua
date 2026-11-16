import { PARAMS } from './config.js';
import { devUrl } from './dev.js';
import { devScale } from './scale.js';
import { loadFonts } from './tmt/stimuli.js';
import { CANDIDATES_URL, SYMBOLS_URL, loadJson, renderFigure, renderFrame, renderKey, keySize } from './coding/symbols.js';

// Dev page ?mode=dev&tool=coding (T3.1). Shows the sets of figures for the
// symbol coding task to choose from (decision 79): for each set the key with
// the digits in real size, the frame with each figure in real size, and the
// figures enlarged. Sizes are PARAMS.coding in mm (a proposal at the first
// stage of T3.1; any can be changed in the link, e.g. &set.coding.figureMm=10)
// through the last calibration made in dev mode in this browser (scale.js).
// Once the author has chosen (decision 144), the chosen set comes first, from
// stimuli/coding-symbols.json, the file the sessions load. Nothing is sent.

const ZOOM = 3;
const num = (x, digits = 1) => x.toFixed(digits).replace('.', ',');

export async function renderCodingSymbols(session, params = PARAMS) {
  document.body.innerHTML = '<p class="message">Завантаження…</p>';
  let candidates, fonts;
  try {
    [candidates, fonts] = await Promise.all([loadJson(CANDIDATES_URL), loadFonts([params.tmt.font])]);
  } catch (error) {
    document.body.innerHTML = `<p class="message">Не вдалося завантажити фігурки: ${error.message}</p>`;
    return;
  }
  const sizes = {
    figureMm: params.coding.figureMm,
    keyCellMm: params.coding.keyCellMm,
    keyDigitMm: params.coding.keyDigitMm,
    frameMm: params.coding.frameMm,
  };
  const font = fonts[0];
  const spec = { box: candidates.box, stroke: candidates.stroke, dot_r: candidates.dot_r };
  const scale = devScale();
  const { pxPerMm } = scale;

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
  const key = keySize(sizes);
  const pageW = window.innerWidth / pxPerMm;

  document.body.innerHTML = `
    <main class="dev-coding">
      <h1>Фігурки кодування символів</h1>
      <p><a href="${devUrl(session)}">До меню</a> · ${scaleNote}</p>
      <p>Розміри (пропозиція): фігурка ${num(sizes.figureMm, 0)} мм, клітинка ключа ${num(sizes.keyCellMm, 0)} мм
        (ключ ${num(key.w, 0)} × ${num(key.h, 0)} мм; ділянка завдань ${PARAMS.screen.minWidthMm} × ${PARAMS.screen.minHeightMm} мм,
        сторінка зараз ${num(pageW, 0)} мм), цифри ${num(sizes.keyDigitMm, 0)} мм, рамка ${num(sizes.frameMm, 0)} мм,
        товщина лінії ${num((spec.stroke / spec.box) * sizes.figureMm, 1)} мм. Змінити можна в адресі:
        <code>&amp;set.coding.figureMm=10</code>.</p>
      <div class="coding-sets"></div>
    </main>`;
  const root = document.querySelector('.coding-sets');

  const section = (set) => {
    const box = document.createElement('section');
    box.className = 'coding-set';
    box.dataset.set = set.id;
    box.innerHTML = `<h2>Набір ${set.id} · ${set.name}</h2>
      <div class="coding-label">Ключ у справжньому розмірі</div><div class="coding-key-row"></div>
      <div class="coding-label">Кожна фігурка в рамці, справжній розмір</div><div class="coding-row coding-frames"></div>
      <div class="coding-label">Збільшено в ${ZOOM} рази</div><div class="coding-row coding-zoom"></div>`;
    box.querySelector('.coding-key-row').append(renderKey({ symbols: set.symbols, spec, sizes, font, pxPerMm }));
    const frames = box.querySelector('.coding-frames');
    const zoom = box.querySelector('.coding-zoom');
    set.symbols.forEach((symbol, i) => {
      const cell = (node) => {
        const holder = document.createElement('figure');
        holder.append(node);
        const caption = document.createElement('figcaption');
        caption.textContent = `${i + 1}`;
        holder.append(caption);
        return holder;
      };
      frames.append(cell(renderFrame({ symbol, spec, sizes, pxPerMm })));
      zoom.append(cell(renderFigure({ symbol, spec, sizeMm: sizes.figureMm * ZOOM, pxPerMm })));
    });
    return box;
  };

  // After the choice (the candidates file names it): the chosen set comes
  // first, from the file the sessions load, then the other candidates.
  let sets = candidates.sets;
  if (candidates.chosen) {
    const chosen = await loadJson(SYMBOLS_URL);
    sets = [
      { id: chosen.set, name: `${chosen.name} (версія ${chosen.symbols_version})`, symbols: chosen.symbols },
      ...candidates.sets.filter((set) => set.id !== candidates.chosen),
    ];
  }
  for (const set of sets) root.append(section(set));

  // Handle for automated checks.
  window.tmtuaCoding = { sizes, spec, scale, sets, font };
}
