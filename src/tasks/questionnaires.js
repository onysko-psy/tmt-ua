import { HtmlButtonResponse } from '../lib.js';
import { texts } from '../texts.uk.js';
import { FormPlugin } from '../plugins/form.js';

// Blocks before the calibration (T2.2): consent, criteria, biography, the
// screen before the tasks with the conditions questionnaire. Texts are the
// drafts of docs/12, part 2. Every answer goes to the receiver as it is (a
// code, not the label); the codes are listed in docs/11, 5.1.
//
// A refusal or a failed criterion ends the session (ctx.end): the block's
// message then carries the status, and nothing after it runs (main.js).
// Decisions 86 (only the reason is kept for a person who does not fit), 105
// (no separate question about military service), 142 (three condition
// questions).

const state = (ctx, key) => (ctx.forms ??= {})[key] ?? (ctx.forms[key] = {});

const yesNo = () => [
  { value: 'yes', label: texts.criteria.yes },
  { value: 'no', label: texts.criteria.no },
];
const numbered = (labels, first = 1) => labels.map((label, i) => ({ value: String(first + i), label }));

const form = (html, fields, onAnswers) => ({
  type: FormPlugin,
  html,
  fields,
  messages: { required: texts.forms.required, format: texts.forms.ageFormat },
  button: texts.common.next,
  on_finish: (data) => onAnswers(data.response),
});

// ---------- Consent ----------

export function consentScreens(block, ctx) {
  const consent = state(ctx, 'consent');
  return [
    {
      type: HtmlButtonResponse,
      stimulus: `<div class="screen consent"><h2>${texts.consent.title}</h2>${texts.consent.body}</div>`,
      choices: [texts.consent.agree, texts.consent.decline],
      on_finish: (data) => {
        consent.agreed = data.response === 0;
        if (consent.agreed) consent.at = new Date().toISOString();
        else ctx.end('no_consent');
      },
    },
  ];
}

// A refusal leaves a row with the status alone: the device and the start
// time stay unsent (withoutMeta, sender.js), because there is no consent.
export function consentMessage(block, ctx) {
  const consent = state(ctx, 'consent');
  if (consent.agreed === undefined) return null;
  if (!consent.agreed) return { summary: {}, withoutMeta: true };
  return { summary: { consent_at: consent.at } };
}

// ---------- Criteria ----------

// The first criterion that is not met, in the order of the questions.
export function exclusionReason(answers, params) {
  if (answers.age < params.criteria.ageMin || answers.age > params.criteria.ageMax) return 'age';
  if (answers.tbi === 'yes') return 'tbi';
  if (answers.color_vision === 'yes') return 'color_vision';
  return null;
}

export function criteriaScreens(block, ctx) {
  const criteria = state(ctx, 'criteria');
  const t = texts.criteria;
  const { ageMin, ageMax } = ctx.params.criteria;
  return [
    form(
      t.title,
      [
        { name: 'age', type: 'integer', label: t.age, min: 1, max: 120 },
        { name: 'tbi', type: 'radio', label: t.tbi, options: yesNo() },
        { name: 'color_vision', type: 'radio', label: t.colorVision, options: yesNo() },
      ],
      (answers) => {
        criteria.reason = exclusionReason(answers, ctx.params);
        criteria.age = answers.age;
        if (criteria.reason) ctx.end('excluded_criteria');
      },
    ),
  ];
}

// Only the reason is kept for someone who does not fit; for the others, the
// age (the other two answers are "no" by definition).
export function criteriaMessage(block, ctx) {
  const criteria = state(ctx, 'criteria');
  if (criteria.age === undefined) return null;
  return { summary: criteria.reason ? { exclusion_reason: criteria.reason } : { age: criteria.age } };
}

// ---------- Biography ----------

export function demographicsScreens(block, ctx) {
  const demographics = state(ctx, 'demographics');
  const t = texts.bio;
  return [
    form(
      t.title,
      [
        {
          name: 'sex',
          type: 'radio',
          label: t.sex,
          options: Object.entries(t.sexOptions).map(([value, label]) => ({ value, label })),
        },
        { name: 'education', type: 'radio', label: t.education, layout: 'column', options: numbered(t.educationOptions) },
      ],
      (answers) => Object.assign(demographics, answers),
    ),
  ];
}

export function demographicsMessage(block, ctx) {
  const { sex, education } = state(ctx, 'demographics');
  if (sex === undefined) return null;
  return { summary: { sex, education: Number(education) } };
}

// ---------- Before the tasks, conditions ----------

export function conditionsScreens(block, ctx) {
  const conditions = state(ctx, 'conditions');
  const t = texts.conditions;
  return [
    {
      type: HtmlButtonResponse,
      stimulus: `<div class="screen">${texts.prepare}</div>`,
      choices: [texts.common.next],
    },
    form(
      t.title,
      [
        { name: 'sleep', type: 'radio', label: t.sleep, options: numbered(t.sleepOptions, 4) },
        { name: 'fatigue', type: 'radio', label: t.fatigue, options: numbered(t.fatigueOptions) },
        { name: 'others', type: 'radio', label: t.others, options: yesNo() },
        {
          name: 'pointer',
          type: 'radio',
          label: t.pointer,
          layout: 'column',
          options: Object.entries(t.pointerOptions).map(([value, label]) => ({ value, label })),
          note: t.pointerNote,
        },
      ],
      (answers) => Object.assign(conditions, answers),
    ),
  ];
}

// sleep_h: 4 means "4 or fewer", 10 "10 or more"; fatigue 1 (not at all) to
// 5 (very much); others_present 1 / 0; pointer_self mouse / touchpad / other.
export function conditionsMessage(block, ctx) {
  const answers = state(ctx, 'conditions');
  if (answers.sleep === undefined) return null;
  return {
    summary: {
      sleep_h: Number(answers.sleep),
      fatigue: Number(answers.fatigue),
      others_present: answers.others === 'yes' ? 1 : 0,
      pointer_self: answers.pointer,
    },
  };
}
