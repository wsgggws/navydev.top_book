/* The application state.
 *
 * There is exactly one position in here: `cursor`.  Reading, listening,
 * following and resuming are all projections of it.
 */

const SETTINGS_KEY = 'lector.settings';
const BOOK_KEY = 'lector.book';
/** 每本书自己的东西：音色、倍速、读到哪。 */
const BOOK_PREFS_KEY = 'lector.books';

const BOOK_SETTINGS = {
  rate: 'rate', gap: 'gap', voiceId: 'voiceId', voiceGender: 'gender',
  voiceTouched: 'voiceTouched', voiceGenderTouched: 'voiceGenderTouched',
};

const DEFAULT_SETTINGS = {
  theme: 'sepia',
  themeTouched: false,
  fontSize: 20,
  lineHeight: 1.9,
  paraSpacing: 0.9,
  measure: 36,
  indent: false,
  rate: 1.0,
  gap: 0,
  voiceId: '',
  voiceTouched: false,
  voiceGender: 'male',
  voiceGenderTouched: false,
};

function loadBookPrefs() {
  try {
    const raw = localStorage.getItem(BOOK_PREFS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (error) {
    return {};
  }
}

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    const saved = JSON.parse(raw);
    const settings = { ...DEFAULT_SETTINGS, ...saved };
    // 旧的全局朗读设置不能成为另一本书的默认值。
    for (const key of Object.keys(BOOK_SETTINGS)) settings[key] = DEFAULT_SETTINGS[key];
    if (saved.themeTouched !== true) {
      settings.theme = DEFAULT_SETTINGS.theme;
    }
    return settings;
  } catch (error) {
    return { ...DEFAULT_SETTINGS };
  }
}

class Emitter {
  constructor() { this._listeners = new Map(); }

  on(event, handler) {
    if (!this._listeners.has(event)) this._listeners.set(event, new Set());
    this._listeners.get(event).add(handler);
    return () => this._listeners.get(event).delete(handler);
  }

  emit(event, payload) {
    const handlers = this._listeners.get(event);
    if (!handlers) return;
    for (const handler of handlers) handler(payload);
  }
}

export const state = new (class Store extends Emitter {
  constructor() {
    super();
    this.settings = loadSettings();
    /** book_id → { voiceId, gender, rate, position } */
    this.bookPrefs = loadBookPrefs();
    this.books = [];
    this.book = null;
    this.chapter = null;
    this.chapterIds = [];
    this.toc = [];
    this.timeline = [];
    this.cursor = null;
    this.sentenceIndex = -1;
    this.voices = [];
    this.defaultVoice = '';
    this.featuredVoices = [];
    this.defaultVoices = {};
    this.defaultRates = {};
  }

  saveSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(Object.fromEntries(
        Object.entries(this.settings).filter(([key]) => !(key in BOOK_SETTINGS)),
      )));
    } catch (error) { /* storage may be unavailable */ }
    this.emit('settings', this.settings);
  }

  setSetting(key, value) {
    this.settings[key] = value;
    if (key in BOOK_SETTINGS && this.book) {
      this.setPref(this.book.book_id, BOOK_SETTINGS[key], value);
    }
    this.saveSettings();
  }

  /** 换书时完整恢复朗读配置，缺省字段始终使用产品默认值。 */
  restoreBookSettings(bookId) {
    const prefs = this.prefsFor(bookId);
    for (const [key, pref] of Object.entries(BOOK_SETTINGS)) {
      this.settings[key] = prefs[pref] ?? DEFAULT_SETTINGS[key];
    }
    if (!Number.isFinite(this.settings.rate) || this.settings.rate < 0.75 || this.settings.rate > 2) {
      this.settings.rate = DEFAULT_SETTINGS.rate;
    }
    if (!['male', 'female'].includes(this.settings.voiceGender)) {
      this.settings.voiceGender = DEFAULT_SETTINGS.voiceGender;
      this.setPref(bookId, 'gender', this.settings.voiceGender);
    }
    this.settings.voiceTouched = Boolean(prefs.voiceId);
  }

  /** 一本书自己的偏好。 */
  prefsFor(bookId) {
    if (!this.bookPrefs[bookId]) this.bookPrefs[bookId] = {};
    return this.bookPrefs[bookId];
  }

  /** 记下这本书的偏好：换书再切回来时还在。 */
  setPref(bookId, key, value) {
    if (!bookId) return;
    this.prefsFor(bookId)[key] = value;
    try {
      localStorage.setItem(BOOK_PREFS_KEY, JSON.stringify(this.bookPrefs));
    } catch (error) { /* storage may be unavailable */ }
    this.emit('prefs', { bookId, key, value });
  }

  rememberBook(bookId) {
    try { localStorage.setItem(BOOK_KEY, bookId); } catch (error) { /* ignore */ }
  }

  lastBookId() {
    try { return localStorage.getItem(BOOK_KEY); } catch (error) { return null; }
  }

  /** Move the one cursor. */
  setCursor(cursor, source = 'user') {
    this.cursor = cursor;
    this.emit('cursor', { cursor, source });
  }

  /** Every sentence of the current chapter, in reading order. */
  sentences() {
    if (!this.chapter) return [];
    const list = [];
    for (const block of this.chapter.blocks) {
      for (const sentence of block.sentences) list.push(sentence);
    }
    return list;
  }

  findSentence(sentenceId) {
    return this.sentences().find((sentence) => sentence.id === sentenceId) || null;
  }
})();
