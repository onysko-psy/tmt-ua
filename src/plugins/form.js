import { ParameterType } from '../lib.js';

// A questionnaire screen as a jsPsych trial (T2.2, T2.3): radio questions, a
// whole-number question, an e-mail address and a free text on one page. Every
// question is required, so the covariates have no gaps (docs/12, 2.9), except
// a free text marked optional: without an answer the page shows a message
// under the question and does not go on. Whatever the participant
// typed is kept; nothing is sent from here: the answers go to the block's
// message.
//
// fields: [{ name, type: 'radio' | 'integer' | 'email' | 'text', label (HTML),
//   options: [{ value, label }] (radio), layout: 'row' | 'column' (radio),
//   note (HTML under the question), min, max (integer: the plausible range),
//   maxLength (text), optional (text: an empty answer is null) }]
// messages: { required, format } shown under a question.
// secondary: a second button that finishes the page without answers and
// without checking them ("No, thanks"); the result then has skipped: true.
// The result is { response: { name: value }, skipped }; radio values are the
// options' values (strings), an integer is a number, an e-mail a trimmed
// string, a text a trimmed string or null.
export class FormPlugin {
  static info = {
    name: 'tmtua-form',
    version: '1.0.0',
    parameters: {
      html: { type: ParameterType.HTML_STRING, default: '' },
      fields: { type: ParameterType.OBJECT },
      messages: { type: ParameterType.OBJECT },
      button: { type: ParameterType.STRING },
      secondary: { type: ParameterType.STRING, default: null },
    },
    data: {
      response: { type: ParameterType.OBJECT },
      skipped: { type: ParameterType.BOOL },
      rt: { type: ParameterType.INT },
    },
  };

  constructor(jsPsych) {
    this.jsPsych = jsPsych;
  }

  trial(displayElement, trial) {
    const root = document.createElement('div');
    root.className = 'screen form';
    root.innerHTML = trial.html;

    const form = document.createElement('form');
    form.noValidate = true;
    const widgets = trial.fields.map((field) => buildField(field));
    for (const widget of widgets) form.append(widget.element);
    const button = document.createElement('button');
    button.type = 'submit';
    button.className = 'jspsych-btn form-submit';
    button.textContent = trial.button;
    const actions = document.createElement('div');
    actions.className = 'form-actions';
    actions.append(button);
    form.append(actions);
    root.append(form);
    displayElement.replaceChildren(root);

    const shown = performance.now();
    if (trial.secondary) {
      const skip = document.createElement('button');
      skip.type = 'button';
      skip.className = 'jspsych-btn form-secondary';
      skip.textContent = trial.secondary;
      skip.addEventListener('click', () => {
        displayElement.replaceChildren();
        this.jsPsych.finishTrial({ response: {}, skipped: true, rt: Math.round(performance.now() - shown) });
      });
      actions.append(skip);
    }
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const response = {};
      let first = null;
      for (const [index, widget] of widgets.entries()) {
        const field = trial.fields[index];
        const { value, problem } = widget.read(field);
        widget.error.textContent = problem ? trial.messages[problem] : '';
        widget.error.hidden = !problem;
        if (problem) first ??= widget;
        else response[field.name] = value;
      }
      if (first) return first.focus();
      displayElement.replaceChildren();
      this.jsPsych.finishTrial({ response, skipped: false, rt: Math.round(performance.now() - shown) });
    });
  }
}

function buildField(field) {
  const element = document.createElement(field.type === 'radio' ? 'fieldset' : 'div');
  element.className = 'field';
  element.dataset.name = field.name;
  const error = document.createElement('p');
  error.className = 'field-error';
  error.hidden = true;
  error.setAttribute('role', 'alert');

  if (field.type === 'radio') {
    const legend = document.createElement('legend');
    legend.innerHTML = field.label;
    const options = document.createElement('div');
    options.className = `options options-${field.layout ?? 'row'}`;
    for (const option of field.options) {
      const label = document.createElement('label');
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = field.name;
      input.value = option.value;
      label.append(input, ` ${option.label}`);
      options.append(label);
    }
    element.append(legend, options);
    appendNote(element, field);
    element.append(error);
    return {
      element,
      error,
      read: () => {
        const checked = element.querySelector('input:checked');
        return checked ? { value: checked.value } : { problem: 'required' };
      },
      focus: () => element.querySelector('input').focus(),
    };
  }

  if (field.type === 'text') return buildText(field, element, error);

  const label = document.createElement('label');
  label.innerHTML = field.label;
  const input = document.createElement('input');
  const email = field.type === 'email';
  input.type = email ? 'email' : 'text';
  if (!email) input.inputMode = 'numeric';
  input.autocomplete = 'off';
  input.name = field.name;
  input.className = email ? 'field-email' : 'field-number';
  label.htmlFor = input.id = `field-${field.name}`;
  element.append(label, input);
  appendNote(element, field);
  element.append(error);
  return {
    element,
    error,
    read: () => {
      const text = input.value.trim();
      if (email) return EMAIL_RE.test(text) && text.length <= 254 ? { value: text } : { problem: 'format' };
      if (text === '') return { problem: 'required' };
      const value = /^\d{1,3}$/.test(text) ? Number(text) : NaN;
      if (!(value >= field.min && value <= field.max)) return { problem: 'format' };
      return { value };
    },
    focus: () => input.focus(),
  };
}

// The same pattern as the receiver's (receiver/Code.gs): what it would refuse
// is not sent.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function buildText(field, element, error) {
  const label = document.createElement('label');
  label.innerHTML = field.label;
  const area = document.createElement('textarea');
  area.name = field.name;
  area.rows = 3;
  area.maxLength = field.maxLength;
  area.className = 'field-text';
  label.htmlFor = area.id = `field-${field.name}`;
  element.append(label, area);
  appendNote(element, field);
  element.append(error);
  return {
    element,
    error,
    read: () => {
      const text = area.value.trim();
      if (text === '') return field.optional ? { value: null } : { problem: 'required' };
      return { value: text };
    },
    focus: () => area.focus(),
  };
}

function appendNote(element, field) {
  if (!field.note) return;
  const note = document.createElement('p');
  note.className = 'field-note';
  note.innerHTML = field.note;
  element.append(note);
}
