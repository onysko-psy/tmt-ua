import { APP_VERSION, RECEIVER_URL } from './config.js';
import { texts } from './texts.uk.js';
import { parseUrl, buildParams, selectBlocks } from './session.js';
import { blocksFor, isPlaceholder } from './blocks.js';
import { initJsPsych, libsLoaded } from './lib.js';
import { renderDevMenu, createDevBadge, renderDevEnd } from './dev.js';
import { renderEnvCheck } from './dev-env.js';
import { renderTmtOptions } from './dev-tmt.js';
import { renderCodingSymbols } from './dev-coding.js';
import { taskScale } from './scale.js';
import { loadTmtStimuli } from './tmt/stimuli.js';
import { loadCodingStimuli } from './coding/symbols.js';
import { newSessionId, newParticipantCode } from './data/ids.js';
import { deviceInfo } from './data/device.js';
import { createSender } from './data/sender.js';
import { createMonitor } from './data/monitor.js';
import { fullscreenGate } from './tasks/fullscreen.js';
import { completeHtml } from './tasks/closing.js';
import {
  createFullscreenBanner,
  exitFullscreen,
  fullscreenWanted,
  isFullscreen,
} from './fullscreen.js';

// Entry point: reads the URL, then either shows a dev page or runs the
// session blocks in their fixed order, sending each block's data when the
// block ends.

// A text, or { html } for the end of a session that went through (own texts).
function showMessage(content) {
  const message = document.createElement(content.html ? 'div' : 'p');
  message.className = 'message';
  if (content.html) message.innerHTML = content.html;
  else message.textContent = content;
  document.body.replaceChildren(message);
}

// Adds what the monitor recorded around a task to the task's own message.
function withEnvironment(message, env) {
  if (!message || !env) return message;
  return {
    ...message,
    summary: { ...message.summary, ...env.summary },
    log: { ...message.log, env: env.log },
  };
}

// Marks the message of the block that ended the session early.
const withStatus = (message, status) => ({ ...message, summary: { ...message?.summary, status } });

async function start() {
  document.title = texts.common.pageTitle;

  const session = parseUrl(window.location.search);
  if (session.error) return showMessage(texts.errors.badLink);
  if (!libsLoaded) return showMessage(texts.errors.loadFailed);

  const isDev = session.mode === 'dev';
  if (isDev && session.devTool !== null) {
    if (session.devTool === 'env') return renderEnvCheck(session);
    if (session.devTool === 'tmt') {
      try {
        return renderTmtOptions(session, buildParams(session.overrides));
      } catch (error) {
        return showMessage(error.message);
      }
    }
    if (session.devTool === 'coding') {
      try {
        return renderCodingSymbols(session, buildParams(session.overrides));
      } catch (error) {
        return showMessage(error.message);
      }
    }
    return showMessage(`Unknown dev tool: ${session.devTool}`);
  }
  if (isDev && session.devStart === null && session.devOnly === null) {
    return renderDevMenu(blocksFor(session), session);
  }

  // Both can throw only in dev mode: overrides and block choice come from dev links.
  let params, blocks;
  try {
    params = buildParams(session.overrides);
    blocks = selectBlocks(blocksFor(session), session);
  } catch (error) {
    return showMessage(error.message);
  }

  // The layouts and the font of the TMT circles, the figures and the sequence
  // of the coding task: without them the session does not start.
  let stimuli;
  try {
    stimuli = { tmt: await loadTmtStimuli(params.tmt), coding: await loadCodingStimuli() };
  } catch {
    return showMessage(texts.errors.loadFailed);
  }

  // Until every block is built, main mode sends nothing, so the main
  // spreadsheet stays empty until data collection starts.
  const collecting = session.mode !== 'main' || !blocksFor(session).some(isPlaceholder);

  const badge = isDev ? createDevBadge(session) : null;
  // A retest keeps the participant code of the first session, which the
  // personal link carries (decision 52); the session itself is new.
  const ids = { session_id: newSessionId(), participant_code: session.retestCode ?? newParticipantCode() };
  let atEnd = false;
  // Set by a block that ends the session early (e.g. 'screen_too_small'):
  // the block finishes, its message carries the status, and nothing after it runs.
  let ending = null;
  const endText = () => (ending ? texts.end[ending] : { html: completeHtml(ctx) });
  const sender = createSender({
    url: RECEIVER_URL,
    base: { ...ids, mode: session.mode, app_version: APP_VERSION },
    meta: { session_type: session.type, started_at: new Date().toISOString(), ...deviceInfo() },
    ...params.send,
    onChange: (state) => {
      badge?.update(state);
      if (atEnd && !isDev && state.pending === 0) showMessage(endText());
    },
  });

  const monitor = createMonitor();
  const banner = createFullscreenBanner(
    texts.fullscreen.banner,
    () => monitor.active() !== null && fullscreenWanted() && !isFullscreen(),
  );

  const jsPsych = initJsPsych({
    display_element: 'jspsych-target',
    on_finish: () => {
      exitFullscreen();
      if (isDev) return renderDevEnd(jsPsych, session, badge, ending);
      // The participant may close the tab right after the last screen, so
      // the thank-you text appears only once everything is delivered.
      atEnd = true;
      if (sender.pending() === 0) return showMessage(endText());
      showMessage(texts.data.sending);
      sender.flush().then((done) => done || showMessage(texts.data.offline));
    },
  });
  jsPsych.data.addProperties({ app_version: APP_VERSION, mode: session.mode, session_id: ids.session_id });

  if (isDev) {
    document.body.append(badge.element);
    // Handle for debugging in the browser console and for automated checks.
    window.tmtua = { jsPsych, params, session, sender, ids, monitor, ctx: null };
  }

  const ctx = {
    jsPsych,
    params,
    session,
    sender,
    monitor,
    stimuli,
    calibration: null, // set by the calibration block: { pxPerMm, ... }
    // px per mm for a task: from the calibration; on dev links that skip it,
    // the last dev calibration in this browser or a fallback (scale.js).
    scale: () => taskScale(ctx),
    ids,
    end: (status) => {
      ending ??= status;
    },
    ending: () => ending,
  };
  if (isDev) window.tmtua.ctx = ctx;
  const timeline = blocks.map((b) => {
    const node = {
      timeline: b.build(b, ctx),
      on_timeline_start: () => {
        if (b.isTask) monitor.startBlock(b.id);
        banner.refresh();
      },
      on_timeline_finish: () => {
        const env = b.isTask ? monitor.endBlock() : null;
        banner.refresh();
        let message = withEnvironment(b.message(b, ctx), env);
        if (ending) message = withStatus(message, ending);
        if (collecting) sender.send(b.id, message);
        if (ending) jsPsych.abortExperiment();
      },
    };
    return b.isTask ? { timeline: [fullscreenGate(), node] } : node;
  });
  jsPsych.run(timeline);
}

// The mark tells automated checks that the first screen is up: the stimuli
// are loaded before it.
start().finally(() => {
  document.documentElement.dataset.tmtuaReady = '1';
});
