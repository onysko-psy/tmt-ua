import { PARAMS } from './config.js';
import { devUrl } from './dev.js';
import { devScale } from './scale.js';
import { loadFonts } from './tmt/stimuli.js';
import { loadJson } from './coding/symbols.js';
import { createSartScreen } from './sart/screen.js';

// Dev page ?mode=dev&tool=sart (T3.3). Shows the candidate looks of the SART
// screen in real size, through the last calibration made in dev mode in this
// browser (scale.js): for each variant the five digit sizes, a trial screen
// with a digit, the mask, the hint in training and the countdown. Nothing is
// sent.

export const CANDIDATES_URL = 'stimuli/sart-candidates.json';
const num = (x, digits = 1) => x.toFixed(digits).replace('.', ',');

export async function renderSartLooks(session, params = PARAMS) {
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
    <main class="dev-sart">
      <h1>Екран SART: варіанти вигляду</h1>
      <p><a href="${devUrl(session)}">До меню</a> · ${scaleNote}</p>
      <p>Усе в справжніх міліметрах на ділянці завдань ${data.area.w} × ${data.area.h} мм (її межа — тонка лінія); сторінка зараз
        ${num(window.innerWidth / pxPerMm, 0)} × ${num(window.innerHeight / pxPerMm, 0)} мм. Розміри цифр — висота цифри в мм,
        у пропорції п'яти розмірів шрифту оригіналу (${data.original_pt.join(', ')} пунктів). Параметри варіанта можна змінити в
        <code>stimuli/sart-candidates.json</code>.</p>
      <div class="sart-variants"></div>
    </main>`;
  const root = document.querySelector('.sart-variants');
  const info = [];

  for (const spec of data.variants) {
    const section = document.createElement('section');
    section.className = 'sart-variant';
    section.dataset.variant = spec.id;
    const biggest = Math.max(...spec.digit_cap_mm);
    section.innerHTML = `<h2>Варіант ${spec.id} · ${spec.name}</h2>
      <p class="sart-facts">Фон ${spec.bg}, цифри й маска ${spec.fg}. Висота цифр: ${spec.digit_cap_mm.map((x) => num(x, 1)).join(' · ')} мм
        (найбільша займає ${num((biggest / data.area.h) * 100, 0)}% висоти ділянки). Маска — кільце Ø${num(spec.mask_mm, 0)} мм
        з діагональним хрестиком. Підказка в тренуванні — ${num(spec.hint_cap_mm, 0)} мм, на ${num(spec.hint_below_center_mm, 0)} мм нижче центру.</p>
      <div class="sart-label">П'ять розмірів цифри 3 і цифри 8 підряд (справжній розмір)</div>
      <div class="sart-sizes" style="background:${spec.bg}"></div>
      <div class="sart-label">Усі цифри 1–9 найбільшим і найменшим розміром</div>
      <div class="sart-digits" style="background:${spec.bg}"></div>
      <div class="sart-label">Екрани проби: цифра (250 мс) → маска (1200 мс) → підказка в тренуванні → відлік перед основною частиною</div>
      <div class="sart-screens"></div>`;
    root.append(section);

    const strip = (digits, sizeIndexes, host) => {
      for (const digit of digits) {
        for (const sizeIndex of sizeIndexes) {
          const cell = document.createElement('span');
          cell.className = 'sart-cell';
          cell.style.cssText = `font: 600 ${(spec.digit_cap_mm[sizeIndex] / font.cap) * pxPerMm}px '${font.family}'; color:${spec.fg}`;
          cell.textContent = digit;
          cell.dataset.digit = digit;
          cell.dataset.size = sizeIndex;
          host.append(cell);
        }
      }
    };
    strip([3, 8], [0, 1, 2, 3, 4], section.querySelector('.sart-sizes'));
    const all = section.querySelector('.sart-digits');
    strip([1, 2, 3, 4, 5, 6, 7, 8, 9], [4], all);
    all.append(document.createElement('br'));
    strip([1, 2, 3, 4, 5, 6, 7, 8, 9], [0], all);

    const holder = section.querySelector('.sart-screens');
    const makeScreen = (caption, fill) => {
      const wrap = document.createElement('figure');
      wrap.className = 'sart-figure';
      const screen = createSartScreen({ spec, area: data.area, font, pxPerMm, container: wrap });
      screen.svg.style.outline = '1px solid #777';
      fill(screen);
      const cap = document.createElement('figcaption');
      cap.textContent = caption;
      wrap.append(cap);
      holder.append(wrap);
    };
    makeScreen('Цифра 3, найбільший розмір', (s) => s.setDigit(3, 4));
    makeScreen('Цифра 7, найменший розмір', (s) => s.setDigit(7, 0));
    makeScreen('Маска', (s) => s.setMask());
    makeScreen('Підказка в тренуванні після помилки (на 3)', (s) => {
      s.setMask();
      s.setHint('Це була 3 — на неї не натискайте.');
    });
    makeScreen('Підказка в тренуванні (пропуск)', (s) => {
      s.setMask();
      s.setHint('Ви не натиснули пробіл.');
    });
    makeScreen('Відлік «Приготуйтеся…» (смужка зменшується за 3 с)', (s) => s.setCountdown(0.65));
    info.push({ spec });
  }
  window.tmtuaSart = { data, scale, font, info };
}
