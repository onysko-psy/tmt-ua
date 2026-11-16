import { APP_VERSION, PARAMS } from './config.js';
import { devUrl } from './dev.js';
import { devScale } from './scale.js';
import { loadFonts } from './tmt/stimuli.js';
import { loadSartStimuli } from './sart/stimuli.js';
import { runSart } from './sart/run.js';
import { texts } from './texts.uk.js';

// Dev page ?mode=dev&tool=sart-timing (T3.3). Runs 60 trials of the SART
// without answers, the way the main part runs (the countdown first, then
// digits and masks in the fixed order), and shows what the screen did: the
// measured frame rate, how many frames make the digit, and the real time of
// each digit and each mask (from the frames in which they were drawn). To be
// run on every kind of screen the task may meet (a 60 Hz monitor, a 120 Hz
// MacBook) and the numbers sent to the developer. Nothing is sent.
//
// A frame rate can be faked for a check with &set.sart.frameMsOverride=8.3333.

const TRIALS = 60;
const num = (x, digits = 1) => (x === null || x === undefined ? '—' : x.toFixed(digits).replace('.', ','));

function stats(xs) {
  if (!xs.length) return null;
  const sorted = [...xs].sort((a, b) => a - b);
  const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
  const sd = xs.length > 1 ? Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / (xs.length - 1)) : 0;
  return { n: xs.length, mean, sd, min: sorted[0], max: sorted[sorted.length - 1], median: sorted[Math.floor(sorted.length / 2)] };
}

export async function renderSartTiming(session, params = PARAMS) {
  document.body.innerHTML = '<p class="message">Завантаження…</p>';
  let stimuli, fonts;
  try {
    [stimuli, fonts] = await Promise.all([loadSartStimuli(), loadFonts([params.tmt.font])]);
  } catch (error) {
    document.body.innerHTML = `<p class="message">Не вдалося завантажити стимули: ${error.message}</p>`;
    return;
  }
  const { look, sequence } = stimuli;
  const font = fonts[0];
  const scale = devScale();
  const p = params.sart;
  const note = scale.source === 'fallback' ? ' Калібрування не було: розмір цифр приблизний (на тайминг це не впливає).' : '';

  function intro(previous = null) {
    document.body.innerHTML = `
      <main class="dev-sart">
        <h1>SART: тайминг</h1>
        <p><a href="${devUrl(session)}">До меню</a> · <a href="${devUrl(session, { tool: 'sart' })}">Екран SART</a></p>
        <p>Прогін ${TRIALS} проб без відповідей: 3 с «Приготуйтеся…», далі цифри й маски (≈ ${num((TRIALS * (p.digitMs + p.maskMs)) / 1000, 0)} с).
          <b>Нічого не натискайте</b>, нехай вікно браузера лишається на передньому плані й нічого поруч не грає.
          Для кожного екрана, на якому тест можуть проходити (звичайний монітор, ноутбук), запустіть окремо у тому браузері,
          що й тест, і надішліть підсумковий текст.${note}</p>
        <p><button id="sart-timing-start" type="button">Почати прогін</button></p>
        <div id="sart-timing-result"></div>
      </main>`;
    if (previous) document.getElementById('sart-timing-result').innerHTML = previous;
    document.getElementById('sart-timing-start').addEventListener('click', () => {
      document.getElementById('sart-timing-start').blur();
      go();
    });
  }

  async function go() {
    const holder = document.createElement('div');
    document.body.append(holder);
    const config = {
      mode: 'main',
      look,
      area: look.area,
      items: sequence.main.slice(0, TRIALS),
      nogoDigit: sequence.nogo_digit,
      limits: {
        digitMs: p.digitMs,
        maskMs: p.maskMs,
        feedbackMs: p.feedbackMs,
        countdownMs: p.countdownMs,
        fastMs: p.fastMs,
        measureFrames: p.measureFrames,
        frameMsOverride: p.frameMsOverride,
      },
      texts: { countdown: texts.sart.countdown },
      font,
      pxPerMm: scale.pxPerMm,
    };
    const result = await runSart(holder, config).promise;
    holder.remove();
    if (!result) return;
    window.tmtuaSartTiming = result;
    intro(report(result));
  }

  function report(r) {
    const digit = stats(r.trials.map((t) => t.digit_ms).filter((x) => x !== null));
    const mask = stats(r.trials.map((t) => t.mask_ms).filter((x) => x !== null));
    const trial = stats(r.trials.map((t) => t.digit_ms + t.mask_ms).filter((x) => !Number.isNaN(x)));
    const frame = r.frame_ms;
    const off = r.trials.filter((t) => t.digit_ms !== null && Math.abs(t.digit_ms - p.digitMs) > frame * 1.01).length;
    const row = (name, s, target) =>
      s
        ? `<tr><td>${name}</td><td>${num(target, 0)}</td><td>${num(s.mean)}</td><td>${num(s.median)}</td><td>${num(s.min)}</td><td>${num(s.max)}</td><td>${num(s.sd, 2)}</td></tr>`
        : '';
    const text = [
      `SART timing, app ${APP_VERSION}`,
      `screen ${screen.width}x${screen.height} @${window.devicePixelRatio}x, window ${window.innerWidth}x${window.innerHeight}`,
      `browser ${navigator.userAgent}`,
      `measured frame ${num(r.frame_ms, 2)} ms = ${num(r.refresh_hz)} Hz (measure ok: ${r.measure_ok}${r.override_ms ? `, FAKED ${r.override_ms} ms` : ''})`,
      `plan: digit ${r.digit_frames} frames, trial ${r.total_frames} frames`,
      digit ? `digit ms: mean ${num(digit.mean)}, median ${num(digit.median)}, min ${num(digit.min)}, max ${num(digit.max)}, sd ${num(digit.sd, 2)} (n ${digit.n})` : '',
      mask ? `mask ms: mean ${num(mask.mean)}, median ${num(mask.median)}, min ${num(mask.min)}, max ${num(mask.max)}, sd ${num(mask.sd, 2)}` : '',
      trial ? `trial ms: mean ${num(trial.mean)}, min ${num(trial.min)}, max ${num(trial.max)}` : '',
      `digit off by more than one frame: ${off} of ${digit?.n ?? 0}; mean |digit - ${p.digitMs}| ${num(r.digit_dev_mean_ms, 2)}, max ${num(r.digit_dev_max_ms, 1)}`,
    ]
      .filter(Boolean)
      .join('\n');
    const values = r.trials.map((t) => `${num(t.digit_ms)}`).join(' · ');
    return `<h2>Результат</h2>
      <table class="sart-timing-table">
        <thead><tr><th></th><th>має бути, мс</th><th>середня</th><th>медіана</th><th>мін.</th><th>макс.</th><th>SD</th></tr></thead>
        <tbody>${row('Цифра', digit, p.digitMs)}${row('Маска', mask, p.maskMs)}${row('Проба', trial, p.digitMs + p.maskMs)}</tbody>
      </table>
      <p>Виміряна частота: <b>${num(r.refresh_hz)} Гц</b> (кадр ${num(r.frame_ms, 2)} мс); цифра = <b>${r.digit_frames}</b> кадрів, проба = ${r.total_frames}.
        ${r.measure_ok ? '' : '<b class="tmt-warn">Частоту виміряти не вдалося, взято 60 Гц.</b>'}
        Цифр, що відхилилися більш ніж на кадр: <b>${off}</b> з ${digit?.n ?? 0}.</p>
      <p>Надішліть цей текст:</p>
      <textarea id="sart-timing-text" rows="10" readonly>${text}</textarea>
      <details><summary>Тривалість кожної цифри, мс</summary><p>${values}</p></details>`;
  }

  intro();
}
