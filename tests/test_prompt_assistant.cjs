const test = require('node:test');
const assert = require('node:assert/strict');
const assistant = require('../yue2_app/static/prompt_assistant.js');

function element(value = '') {
  const listeners = new Map();
  return {
    value, disabled: false, hidden: false, textContent: '',
    classList: { toggle() {} },
    addEventListener(name, listener) { listeners.set(name, listener); },
    emit(name) { return listeners.get(name)?.(); },
    focus() {}
  };
}

function ui(ideaText, languageValue = 'ko') {
  const nodes = new Map([
    ['#prompt-idea', element(ideaText)],
    ['#prompt-language', element(languageValue)],
    ['#prompt-generate', element()],
    ['#prompt-status', element()],
    ['#prompt-result', element()],
    ['#prompt-result-title', element()],
    ['#prompt-result-style', element()],
    ['#prompt-result-lyrics', element()],
    ['#prompt-apply', element()]
  ]);
  nodes.get('#prompt-result').hidden = true;
  globalThis.document = { querySelector: (selector) => nodes.get(selector) };
  return (selector) => nodes.get(selector);
}

test.afterEach(() => {
  delete globalThis.document;
  delete globalThis.LanguageModel;
  delete globalThis.Translator;
  delete globalThis.isSecureContext;
});

test('YuE2 drafts require a bounded title, style and sectioned lyric', () => {
  const draft = assistant.parseDraft(JSON.stringify({
    title: 'First Light',
    style: 'English, indie pop, soft female vocal, 90 BPM, piano and drums',
    lyrics: '[Verse]\nFirst light\n\n[Chorus]\nStay with me'
  }), { language: 'ko', instrumental: false });
  assert.equal(draft.title, 'First Light');
  assert.match(draft.style, /^Korean, indie pop/);
  assert.equal(draft.lyrics, '[Verse]\nFirst light\n\n[Chorus]\nStay with me');
  assert.throws(() => assistant.parseDraft(JSON.stringify({ title: 'Song', style: 'pop', lyrics: 'Just words' }),
    { language: 'en', instrumental: false }), /가사 구조/);
  assert.throws(() => assistant.parseDraft(JSON.stringify({ title: 'Song', style: 'pop', lyrics: '[Verse]\n[Production: louder]\nHi' }),
    { language: 'en', instrumental: false }), /구간 태그/);
  assert.throws(() => assistant.parseDraft(JSON.stringify({ style: 'pop', lyrics: '[Verse]\nHi' }),
    { language: 'en', instrumental: false }), /제목/);
  assert.throws(() => assistant.parseDraft(JSON.stringify({ title: 'Line one\nLine two', style: 'pop', lyrics: '[Verse]\nHi' }),
    { language: 'en', instrumental: false }), /곡 제목/);
  assert.throws(() => assistant.parseDraft(JSON.stringify({ title: 'x'.repeat(121), style: 'pop', lyrics: '[Verse]\nHi' }),
    { language: 'en', instrumental: false }), /곡 제목/);
  assert.equal(assistant.parseDraft(JSON.stringify({ title: 'Quiet Room', style: 'ambient piano', lyrics: 'ignored' }),
    { language: 'en', instrumental: true }).lyrics, '');
});

test('an empty or rejected line translation keeps the draft and identifies affected lines', async () => {
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => warnings.push(args);
  try {
    const translatedInputs = [];
    const translator = {
      async translate(line) {
        translatedInputs.push(line);
        if (line === 'Oh') return '';
        if (line === 'Come home') throw new Error('model error');
        return `한국어 ${line}`;
      }
    };
    const result = await assistant.translateLyrics(
      '[Verse]\nRain at night\nOh\n이미 한국어\n\n[Chorus]\nCome home',
      translator, () => {}
    );
    assert.equal(result.untranslated, 2);
    assert.equal(result.lyrics, '[Verse]\n한국어 Rain at night\nOh\n이미 한국어\n\n[Chorus]\nCome home');
    assert.deepEqual(translatedInputs, ['Rain at night', 'Oh', 'Come home']);
    assert.deepEqual(warnings.map(([, details]) => details.lineNumber), [3, 7]);
  } finally {
    console.warn = originalWarn;
  }
});

test('Korean brief and lyrics use local translation, then require explicit apply', async () => {
  const get = ui('비 오는 밤의 인디 팝', 'ko');
  const calls = [];
  let emptyChorus = false;
  let emptyTitle = false;
  globalThis.LanguageModel = {
    availability: async (options) => {
      assert.deepEqual(options.expectedInputs[0].languages, ['en']);
      return 'available';
    },
    create: async (options) => {
      assert.match(options.initialPrompts[0].content, /YuE2 grammar/);
      return {
        prompt: async (input, promptOptions) => {
          assert.match(input, /rainy indie pop/);
          assert.deepEqual(promptOptions.responseConstraint.required, ['title', 'style', 'lyrics']);
          return JSON.stringify({ title: 'Rain at Night', style: 'indie pop, female vocal, 90 BPM, piano', lyrics: '[Verse]\nRain at night\n\n[Chorus]\nCome home' });
        },
        destroy() { calls.push('model destroyed'); }
      };
    }
  };
  globalThis.Translator = {
    availability: async () => 'available',
    create: async ({ sourceLanguage, targetLanguage }) => {
      calls.push(`${sourceLanguage}-${targetLanguage}`);
      return {
        translate: async (value) => sourceLanguage === 'ko' ? 'rainy indie pop'
          : (emptyChorus && value === 'Come home') || (emptyTitle && value === 'Rain at Night') ? '' : `한글 ${value}`,
        destroy() { calls.push('translator destroyed'); }
      };
    }
  };
  let applied;
  assistant.init({ getMode: () => 'original', isInstrumental: () => false, applyDraft: (draft) => { applied = draft; } });
  await new Promise(setImmediate);
  assert.equal(get('#prompt-generate').disabled, false);
  await get('#prompt-generate').emit('click');
  assert.equal(applied, undefined);
  assert.equal(get('#prompt-result').hidden, false);
  assert.equal(get('#prompt-result-title').textContent, '한글 Rain at Night');
  assert.match(get('#prompt-result-lyrics').textContent, /\[Verse\]\n한글 Rain at night/);
  assert.ok(calls.includes('ko-en'));
  assert.ok(calls.includes('en-ko'));
  get('#prompt-apply').emit('click');
  assert.equal(applied.title, '한글 Rain at Night');
  assert.match(applied.style, /^Korean, indie pop/);
  assert.match(applied.lyrics, /\[Chorus\]\n한글 Come home/);

  emptyChorus = true;
  emptyTitle = true;
  await new Promise(setImmediate);
  const originalWarn = console.warn;
  console.warn = () => {};
  try {
    await get('#prompt-generate').emit('click');
  } finally {
    console.warn = originalWarn;
  }
  assert.equal(get('#prompt-result').hidden, false);
  assert.equal(get('#prompt-result-title').textContent, 'Rain at Night');
  assert.match(get('#prompt-status').textContent, /제목과 가사 1줄이 번역되지 않아 원문으로 남았습니다/);
  assert.match(get('#prompt-result-lyrics').textContent, /\[Chorus\]\nCome home/);
  get('#prompt-apply').emit('click');
  assert.equal(applied.title, 'Rain at Night');
});

test('Korean instrumental drafts translate the title without translating lyrics', async () => {
  const get = ui('Soft ambient piano', 'ko');
  const translated = [];
  globalThis.LanguageModel = {
    availability: async () => 'available',
    create: async () => ({
      prompt: async () => JSON.stringify({ title: 'Quiet Room', style: 'ambient piano', lyrics: '' })
    })
  };
  globalThis.Translator = {
    availability: async () => 'available',
    create: async () => ({
      translate: async (value) => { translated.push(value); return '조용한 방'; }
    })
  };
  let applied;
  assistant.init({ getMode: () => 'original', isInstrumental: () => true, applyDraft: (draft) => { applied = draft; } });
  await new Promise(setImmediate);
  assert.equal(get('#prompt-generate').disabled, false);
  await get('#prompt-generate').emit('click');
  assert.deepEqual(translated, ['Quiet Room']);
  assert.equal(get('#prompt-result-title').textContent, '조용한 방');
  get('#prompt-apply').emit('click');
  assert.equal(applied.title, '조용한 방');
  assert.equal(applied.lyrics, '');
});

test('unsupported browser keeps manual editor available', async () => {
  const get = ui('A gentle piano song', 'en');
  assistant.init({ getMode: () => 'original', isInstrumental: () => false, applyDraft() {} });
  await new Promise(setImmediate);
  assert.equal(get('#prompt-generate').disabled, true);
  assert.match(get('#prompt-status').textContent, /사용할 수 없습니다/);
});

test('an insecure LAN origin explains why local AI is disabled', async () => {
  const get = ui('A gentle piano song', 'en');
  globalThis.isSecureContext = false;
  assistant.init({ getMode: () => 'original', isInstrumental: () => false, applyDraft() {} });
  await new Promise(setImmediate);
  assert.equal(get('#prompt-generate').disabled, true);
  assert.match(get('#prompt-status').textContent, /HTTPS 또는 localhost/);
});
