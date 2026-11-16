import { texts } from '../texts.uk.js';
import { FormPlugin } from '../plugins/form.js';
import { PassPlugin } from '../plugins/pass.js';

// Blocks after the tasks (T2.3): PSS-10, the questions after the tasks, the
// invitation to the retest, the thanks. Texts are the drafts of docs/12, part
// 3. Answers go to the receiver as codes, as they are (decision 103: the sum
// of PSS-10 is calculated here, and every answer and the version of the scale
// are kept beside it).

const state = (ctx, key) => (ctx.closing ??= {})[key] ?? (ctx.closing[key] = {});

const numbered = (labels, first = 0) => labels.map((label, i) => ({ value: String(first + i), label }));

const form = (html, fields, onAnswers, extra = {}) => ({
  type: FormPlugin,
  html,
  fields,
  messages: { required: texts.forms.required, format: texts.forms.ageFormat },
  button: texts.common.next,
  on_finish: (data) => onAnswers(data.response, data),
  ...extra,
});

// ---------- PSS-10 ----------

// Which version of the text and the scoring was shown: Appendix A of
// Veldbrekht & Tavrovetska (2022), decision 103.
export const PSS_VERSION = 'veldbrekht_tavrovetska_2022_appendix_a';
// Items 4, 5, 7, 8 (numbers from 1) are worded positively and scored in
// reverse: 4 minus the answer.
const PSS_REVERSED = [4, 5, 7, 8];

// answers: ten numbers 0-4 in the order of the items; returns 0-40.
export function pssTotal(answers) {
  return answers.reduce((sum, a, i) => sum + (PSS_REVERSED.includes(i + 1) ? 4 - a : a), 0);
}

export function pssScreens(block, ctx) {
  const pss = state(ctx, 'pss');
  const t = texts.pss;
  return [
    form(
      t.title + t.instruction,
      t.items.map((item, i) => ({
        name: `pss_${i + 1}`,
        type: 'radio',
        label: `${i + 1}. ${item}`,
        options: numbered(t.options),
      })),
      (answers) => {
        pss.answers = t.items.map((_, i) => Number(answers[`pss_${i + 1}`]));
      },
    ),
  ];
}

export function pssMessage(block, ctx) {
  const { answers } = state(ctx, 'pss');
  if (!answers) return null;
  const summary = {};
  answers.forEach((a, i) => (summary[`pss_${i + 1}`] = a));
  return { summary: { ...summary, pss_total: pssTotal(answers), pss_version: PSS_VERSION } };
}

// ---------- After the tasks ----------

export function postScreens(block, ctx) {
  const post = state(ctx, 'post');
  const t = texts.post;
  return [
    form(
      t.title,
      [
        { name: 'distraction', type: 'radio', label: t.distraction, options: numbered(t.distractionOptions) },
        {
          name: 'interruption',
          type: 'radio',
          label: t.interruption,
          options: Object.entries(t.interruptionOptions).map(([value, label]) => ({ value, label })),
        },
        { name: 'effort', type: 'radio', label: t.effort, options: numbered(t.effortOptions, 1) },
        {
          name: 'comment',
          type: 'text',
          label: t.comment,
          note: `<em>${t.commentNote}</em>`,
          optional: true,
          maxLength: 1000,
        },
      ],
      (answers) => Object.assign(post, answers),
    ),
  ];
}

// post_distraction 0 (no) / 1 (a little) / 2 (noticeably); post_interrupted
// 1 / 0; post_effort 1 (not at all) to 5 (very); post_comment free text or
// empty.
export function postMessage(block, ctx) {
  const answers = state(ctx, 'post');
  if (answers.distraction === undefined) return null;
  return {
    summary: {
      post_distraction: Number(answers.distraction),
      post_interrupted: answers.interruption === 'yes' ? 1 : 0,
      post_effort: Number(answers.effort),
      post_comment: answers.comment,
    },
  };
}

// ---------- Invitation to the retest ----------

const MONTHS = [
  'січня', 'лютого', 'березня', 'квітня', 'травня', 'червня',
  'липня', 'серпня', 'вересня', 'жовтня', 'листопада', 'грудня',
];
export const dateInWords = (date) => `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()} року`;

// The personal link of the retest (docs/11, 5.3): the page of the site and
// the code; outside the main mode the mode too, so that a test link writes
// into the test spreadsheets.
export function retestLink(location, code, mode) {
  const base = `${location.origin}${location.pathname}`;
  return `${base}?r=${code}${mode === 'main' ? '' : `&mode=${mode}`}`;
}

export function retestLetter({ date, link }) {
  const t = texts.retestLetter;
  const body = t.body.join('\n').replace('{date}', dateInWords(date)).replace('{link}', link);
  return `Тема: ${t.subject}\n\n${body}`;
}

export function inviteScreens(block, ctx) {
  const invite = state(ctx, 'invite');
  const t = texts.email;
  return [
    form(
      t.title,
      [{ name: 'email', type: 'email', label: t.label }],
      (answers, data) => {
        invite.answered = true;
        invite.email = data.skipped ? null : answers.email;
      },
      { button: t.send, secondary: t.skip, messages: { required: t.invalid, format: t.invalid } },
    ),
  ];
}

// The address goes only to the contacts spreadsheet, with the ready letter
// (decisions 37, 52); the results get just a mark that one was left.
export function inviteMessage(block, ctx) {
  const invite = state(ctx, 'invite');
  if (!invite.answered) return null;
  if (!invite.email) return { summary: { email_left: 0 } };
  const link = retestLink(window.location, ctx.ids.participant_code, ctx.session.mode);
  return {
    summary: { email_left: 1 },
    contact: { email: invite.email, letter: retestLetter({ date: new Date(), link }) },
  };
}

// ---------- Thanks ----------

export const thanksScreens = () => [{ type: PassPlugin }];

// The session went through: the status and the time of the end. A finished
// retest also marks the contacts row of the code as done (docs/11, 5.3); the
// receiver ignores the mark if the code has no row there.
export function thanksMessage(block, ctx) {
  const finishedAt = new Date().toISOString();
  const message = { summary: { status: 'complete', finished_at: finishedAt } };
  if (ctx.session.type === 'retest') message.contact = { retest_done_at: finishedAt };
  return message;
}

// The last screen (decision 69: no results). The sentence about the
// invitation only for those who left an address; the retest has its own text.
export function completeHtml(ctx) {
  const t = texts.end;
  if (ctx.session.type === 'retest') return t.completeRetest.join('');
  const left = Boolean(state(ctx, 'invite').email);
  return t.complete.join('') + (left ? t.completeEmail : '') + t.completeContact;
}
