/* The sentence player.
 *
 * Audio is played one sentence at a time.  The next tile is fetched before
 * the current one ends, so the handover is inaudible, and the word timings
 * of the tile drive the karaoke highlight.
 */

import { api } from './api.js';
import { state } from './state.js';
import { splitWords, wordAt } from './util.js';

export class Player {
  constructor() {
    this.audio = new Audio();
    this.audio.preload = 'auto';
    this.blobUrls = new Map();
    this.words = [];
    this.sentenceId = null;
    this.playing = false;
    this.onSentence = null;
    this.onState = null;
    this.onError = null;
    this._pending = null;

    this.audio.addEventListener('ended', () => this._advance());
    this.audio.addEventListener('timeupdate', () => {
      this._tick();
      if (this.onTick) this.onTick();
    });
    this.audio.addEventListener('play', () => this._setPlaying(true));
    this.audio.addEventListener('pause', () => this._setPlaying(false));
    this.audio.addEventListener('error', () => {
      if (this._pending) {
        this._setPlaying(false);
        if (this.onError) this.onError('音频加载失败');
      }
    });
  }

  get rate() { return state.settings.rate || 1; }

  /** The play head inside the current sentence, in seconds. */
  get position() { return this.audio.currentTime || 0; }

  setRate(value) {
    state.setSetting('rate', value);
    this.audio.playbackRate = this.rate;
  }

  _setPlaying(value) {
    if (this.playing === value) return;
    this.playing = value;
    document.body.classList.toggle('is-playing', value);
    if (this.onState) this.onState(value);
  }

  /** Fetch the audio of a sentence, reusing the blob when it is known. */
  async _fetchAudio(sentenceId) {
    if (this.blobUrls.has(sentenceId)) return this.blobUrls.get(sentenceId);
    const response = await fetch(api.audioUrl(state.book.book_id, sentenceId));
    if (!response.ok) {
      let code = 'INTERNAL_ERROR';
      let message = '音频加载失败';
      try {
        const payload = await response.json();
        if (payload.error) {
          code = payload.error.code;
          message = payload.error.message;
        }
      } catch (error) { /* not json */ }
      throw Object.assign(new Error(message), { code, status: response.status });
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    this.blobUrls.set(sentenceId, url);
    return url;
  }

  async _fetchWords(sentenceId) {
    try {
      const payload = await api.getWords(state.book.book_id, sentenceId);
      return payload;
    } catch (error) {
      return { words: [], granularity: 'sentence', duration: 0 };
    }
  }

  /** Play one sentence from the beginning. */
  async play(sentenceId, { fromWord = null } = {}) {
    if (!state.book || !sentenceId) return;
    this.sentenceId = sentenceId;
    try {
      const [url, wordsPayload] = await Promise.all([
        this._fetchAudio(sentenceId),
        this._fetchWords(sentenceId),
      ]);
      this.words = wordsPayload.words || [];
      this.granularity = wordsPayload.granularity || 'sentence';
      this.audio.src = url;
      this.audio.playbackRate = this.rate;
      if (fromWord !== null && this.granularity === 'word') {
        const word = this.words[fromWord];
        if (word) this.audio.currentTime = Math.max(0, word.start);
      }
      await this.audio.play();
      if (this.onSentence) this.onSentence(sentenceId, this.words, this.granularity);
      this.prefetchNext();
    } catch (error) {
      this._setPlaying(false);
      if (this.onError) this.onError(error.message || '播放失败', error.code);
    }
  }

  /**
   * Fetch the next sentence while this one is still playing.
   *
   * The handover between two tiles has to be inaudible, and the first request
   * for a tile may have to synthesise it — which takes seconds.  Fetching one
   * sentence ahead removes both problems.
   */
  prefetchNext() {
    const sentences = state.sentences();
    const index = sentences.findIndex((sentence) => sentence.id === this.sentenceId);
    const next = sentences[index + 1];
    if (!next) return;
    Promise.all([
      this._fetchAudio(next.id).catch(() => null),
      this._fetchWords(next.id).catch(() => null),
    ]);
  }

  /** Move the play head inside the current sentence. */
  seekToWord(index) {
    if (!this.words.length) return;
    const word = this.words[index];
    if (!word) return;
    this.audio.currentTime = Math.max(0, word.start);
    if (!this.playing) this.audio.play().catch(() => {});
  }

  pause() {
    this.audio.pause();
  }

  async toggle() {
    if (this.playing) {
      this.pause();
      return;
    }
    const target = this.sentenceId
      || (state.cursor ? state.cursor.sentence_id : null);
    if (!target) return;
    if (this.audio.src && this.sentenceId === target && this.audio.currentTime > 0
        && this.audio.currentTime < this.audio.duration) {
      await this.audio.play();
      return;
    }
    await this.play(target);
  }

  stop() {
    this.audio.pause();
    this.audio.removeAttribute('src');
    this._setPlaying(false);
  }

  _advance() {
    if (!this.onSentence) return;
    const sentences = state.sentences();
    const index = sentences.findIndex((sentence) => sentence.id === this.sentenceId);
    const next = sentences[index + 1];
    if (!next) {
      this._setPlaying(false);
      if (this.onState) this.onState(false, true);
      return;
    }
    const gap = (state.settings.gap || 0) * 1000;
    const go = () => this.play(next.id);
    if (gap > 0) setTimeout(go, gap);
    else go();
  }

  /** Highlight the word that is being spoken right now. */
  _tick() {
    if (!this.words.length) return;
    const index = wordAt(this.words, this.audio.currentTime);
    if (index === this._currentWord) return;
    this._currentWord = index;
    const spans = document.querySelectorAll('.sent.is-current .w');
    spans.forEach((span, position) => {
      span.classList.toggle('is-now', position === index);
      span.classList.toggle('is-read', position < index);
    });
  }

  /** Progress of the current chapter, 0..1. */
  chapterProgress() {
    const sentences = state.sentences();
    if (!sentences.length) return 0;
    const index = sentences.findIndex((sentence) => sentence.id === this.sentenceId);
    if (index < 0) return 0;
    return (index + 1) / sentences.length;
  }

  release() {
    for (const url of this.blobUrls.values()) URL.revokeObjectURL(url);
    this.blobUrls.clear();
  }
}

export { splitWords };
