import { APP_VERSION } from './config.js';
import { isPlaceholder } from './blocks.js';
import { newParticipantCode } from './data/ids.js';

// Dev-mode screens (?mode=dev): a menu to jump to any block, a corner badge
// with the delivery queue that leads back to the menu, and a dump of the
// collected data at the end. Nothing here runs in main or pilot mode.

// Builds a dev link that keeps the current set.* overrides.
export function devUrl(session, extra = {}) {
  const query = new URLSearchParams({ mode: 'dev', ...(session.retestCode ? { r: session.retestCode } : {}), ...extra });
  if (extra.r === null) query.delete('r'); // a link to the first session
  for (const [path, value] of Object.entries(session.overrides)) query.set(`set.${path}`, value);
  return `?${query}`;
}

export function renderDevMenu(blocks, session) {
  const rows = blocks
    .map(
      (b) => `<tr data-block="${b.id}">
        <td>${b.label}</td>
        <td>${isPlaceholder(b) ? `заглушка, ${b.task}` : 'готово'}</td>
        <td><a href="${devUrl(session, { start: b.id })}">звідси</a></td>
        <td><a href="${devUrl(session, { only: b.id })}">лише цей</a></td>
      </tr>`,
    )
    .join('');
  document.body.innerHTML = `
    <main class="dev-menu">
      <h1>TMT-UA · dev · <span class="dev-version">${APP_VERSION}</span></h1>
      <p><a href="${devUrl(session, { start: blocks[0].id })}">${session.type === 'retest' ? 'Уся сесія ретесту з початку' : 'Уся сесія з початку'}</a>
        ${session.type === 'retest'
          ? `(код <code>${session.retestCode}</code>; <a href="${devUrl(session, { r: null })}">до першої сесії</a>)`
          : `· <a href="${devUrl(session, { r: newParticipantCode() })}">ретест із новим кодом</a>`}</p>
      <p><a href="${devUrl(session, { tool: 'env' })}">Перевірка середовища</a>: клавіші в
        повноекранному режимі, вихід із вкладки, масштаб. Нічого не надсилає.</p>
      <p><a href="${devUrl(session, { tool: 'tmt' })}">Стимули TMT</a>: розташування, розміри й
        шрифт у справжньому розмірі (спершу пройдіть калібрування в цьому браузері). Нічого не надсилає.</p>
      <p><a href="${devUrl(session, { tool: 'coding' })}">Фігурки кодування</a>: набори фігурок і ключ
        у справжньому розмірі (так само потрібне калібрування). Нічого не надсилає.</p>
      <p><a href="${devUrl(session, { tool: 'stroop' })}">Екран Stroop</a>: варіанти вигляду (кольори, слово,
        точка, плашки) у справжньому розмірі (так само потрібне калібрування). Нічого не надсилає.</p>
      <p><a href="${devUrl(session, { tool: 'sart' })}">Екран SART</a>: варіанти вигляду (цифри п'яти розмірів,
        маска, підказка, відлік) у справжньому розмірі (потрібне калібрування). Нічого не надсилає.</p>
      <p><a href="${devUrl(session, { tool: 'sart-timing' })}">SART: тайминг</a>: 60 проб без відповідей, виміряна частота
        екрана й справжня тривалість цифри та маски. Для перевірки на кожному екрані. Нічого не надсилає.</p>
      <table><tbody>${rows}</tbody></table>
      <p class="dev-hint">Параметри з <code>config.js</code> можна змінити в адресі,
        наприклад <code>&amp;set.tmt.timeLimitMs=20000</code>.</p>
    </main>`;
}

// Returns the badge element and update({ pending, rejected }) for the queue.
export function createDevBadge(session) {
  const badge = document.createElement('a');
  badge.className = 'dev-badge';
  badge.href = devUrl(session);
  const update = ({ pending, rejected }) => {
    badge.textContent = `dev ${APP_VERSION} · у черзі ${pending}`;
    if (rejected) badge.textContent += ` · відхилено ${rejected}`;
    badge.classList.toggle('dev-badge-alert', rejected > 0);
  };
  update({ pending: 0, rejected: 0 });
  return { element: badge, update };
}

export function renderDevEnd(jsPsych, session, badge, ending = null) {
  document.body.innerHTML = `
    <main class="dev-end">
      <h1>Кінець dev-сесії${ending ? ` · <span class="dev-status">${ending}</span>` : ''}</h1>
      <p><a href="${devUrl(session)}">До меню</a> · <a href="${devUrl(session, { tool: 'tmt' })}">Стимули TMT</a></p>
      <pre></pre>
    </main>`;
  document.querySelector('.dev-end pre').textContent = JSON.stringify(
    jsPsych.data.get().values(),
    null,
    2,
  );
  document.body.append(badge.element);
}
