/* The application state.
 *
 * There is exactly one position in here: `cursor`.  Reading, listening,
 * following and resuming are all projections of it.
 */

const SETTINGS_KEY = 'lector.settings';
const BOOK_KEY = 'lector.book';

const DEFAULT_SETTINGS = {
  theme: 'paper',
  fontSize: 20,
  lineHeight: 1.9,
  paraSpacing: 0.9,
  measure: 36,
  indent: false,
  rate: 1.0,
  gap: 0,
  voiceId: '',
  follow: true,
};

function loadSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return { ...DEFAULT_SETTINGS };
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
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
  }

  saveSettings() {
    try {
      localStorage.setItem(SETTINGS_KEY, JSON.stringify(this.settings));
    } catch (error) { /* storage may be unavailable */ }
    this.emit('settings', this.settings);
  }

  setSetting(key, value) {
    this.settings[key] = value;
    this.saveSettings();
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
