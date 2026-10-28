/* navydev.top_ebook — the browser application. */

import { api, getToken, setToken } from './api.js';
import { state } from './state.js';
import { Player } from './player.js';
import { LibraryView } from './views/library.js';
import { ReaderView } from './views/reader.js';
import { TocDrawer } from './views/toc.js';
import {
  chapterTimeMetrics, clamp, debounce, el, formatTime, isTypingTarget,
} from './util.js';

const $ = (selector) => document.querySelector(selector);

const dom = {
  body: document.body,
  topbar: $('#topbar'),
  topbarBook: $('#topbar-book'),
  topbarChapter: $('#topbar-chapter'),
  btnBack: $('#btn-back'),
  btnMenu: $('#btn-menu'),
  btnTheme: $('#btn-theme'),
  btnFont: $('#btn-font'),
  btnSettings: $('#btn-settings'),
  library: $('#library'),
  reader: $('#reader'),
  readingChapterProgress: $('#reading-progress'),
  readingChapterFill: $('#reading-chapter-fill'),
  drawerToc: $('#drawer-toc'),
  drawerSettings: $('#drawer-settings'),
  overlay: $('#overlay'),
  toast: $('#toast'),
  player: $('#player'),
  playerPanel: $('#player-panel'),
  playerChapter: $('#player-chapter'),
  playerProgress: $('#player-progress'),
  playerTime: $('#player-time'),
  playerStatus: $('#player-status'),
  btnPlay: $('#btn-play'),
  btnPrev: $('#btn-prev'),
  btnNext: $('#btn-next'),
  btnRate: $('#btn-rate'),
  rateMenu: $('#rate-menu'),
  btnVoice: $('#btn-voice'),
  btnPlayerToggle: $('#btn-player-toggle'),
};

const player = new Player();

/* ------------------------------------------------------------------ */
/* 提示与抽屉                                                          */
/* ------------------------------------------------------------------ */

let toastTimer = null;

/** The server refused the request — ask for the access token. */
function askForToken() {
  if (window.__lectorTokenAsked) return;
  window.__lectorTokenAsked = true;
  const token = window.prompt('需要访问令牌（LECTOR_TOKEN）');
  window.__lectorTokenAsked = false;
  if (token) {
    setToken(token.trim());
    window.location.reload();
  }
}

function toast(message) {
  dom.toast.textContent = message;
  dom.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { dom.toast.hidden = true; }, 2600);
}

const drawerTimers = new Map();
let activeDrawer = null;
let drawerTrigger = null;

function setBackgroundInert(inert) {
  for (const node of [dom.topbar, $('.stage'), dom.player]) node.inert = inert;
}

function openDrawer(name) {
  dom.body.classList.remove('immersive');
  const trigger = activeDrawer ? drawerTrigger : document.activeElement;
  closeDrawers({ restoreFocus: false });
  closeRateMenu();
  const drawer = name === 'toc' ? dom.drawerToc : dom.drawerSettings;
  clearTimeout(drawerTimers.get(drawer));
  drawerTimers.delete(drawer);
  activeDrawer = drawer;
  drawerTrigger = trigger;
  drawer.hidden = false;
  drawer.inert = false;
  requestAnimationFrame(() => {
    if (activeDrawer === drawer) drawer.classList.add('is-open');
  });
  (name === 'toc' ? dom.btnMenu : dom.btnSettings).setAttribute('aria-expanded', 'true');
  dom.overlay.hidden = false;
  setBackgroundInert(true);
  drawer.querySelector(name === 'toc' ? '#search-input' : '#btn-settings-close')
    .focus({ preventScroll: true });
}

function closeDrawers({ restoreFocus = true } = {}) {
  const wasOpen = activeDrawer !== null;
  activeDrawer = null;
  for (const drawer of [dom.drawerToc, dom.drawerSettings]) {
    drawer.classList.remove('is-open');
    drawer.inert = true;
    clearTimeout(drawerTimers.get(drawer));
    if (!drawer.hidden) {
      drawerTimers.set(drawer, setTimeout(() => {
        drawer.hidden = true;
        drawerTimers.delete(drawer);
      }, 240));
    }
  }
  dom.btnMenu.setAttribute('aria-expanded', 'false');
  dom.btnSettings.setAttribute('aria-expanded', 'false');
  dom.overlay.hidden = true;
  setBackgroundInert(false);
  if (wasOpen && restoreFocus && drawerTrigger?.isConnected) {
    drawerTrigger.focus({ preventScroll: true });
  }
  drawerTrigger = null;
}

function drawerOpen() {
  return activeDrawer !== null;
}

// Handle Escape before inputs and keep keyboard navigation inside the modal.
document.addEventListener('keydown', (event) => {
  if (!activeDrawer) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopImmediatePropagation();
    closeDrawers();
    return;
  }
  if (event.key !== 'Tab') return;
  const controls = [...activeDrawer.querySelectorAll(
    'button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]',
  )].filter(node => node.getClientRects().length > 0 && !node.closest('[hidden], [inert]'));
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}, true);

dom.overlay.addEventListener('click', closeDrawers);
$('#btn-toc-close').addEventListener('click', closeDrawers);
$('#btn-settings-close').addEventListener('click', closeDrawers);

/* ------------------------------------------------------------------ */
/* 设置                                                                */
/* ------------------------------------------------------------------ */

const settings = {
  fontSize: $('#s-fontsize'),
  lineHeight: $('#s-lineheight'),
  paraSpacing: $('#s-paraspace'),
  measure: $('#s-measure'),
  indent: $('#s-indent'),
  theme: $('#s-theme'),
  gender: $('#s-gender'),
  voice: $('#s-voice'),
  rate: $('#s-rate'),
  gap: $('#s-gap'),
};

function applySettings() {
  const s = state.settings;
  const root = document.documentElement;
  root.dataset.theme = s.theme;
  root.style.setProperty('--line-height', String(s.lineHeight));
  root.style.setProperty('--para-spacing', `${s.paraSpacing}em`);
  root.style.setProperty('--measure-user', `${s.measure}em`);
  root.style.setProperty('--indent', s.indent ? '2em' : '0em');
  if (s.fontSizeTouched) root.style.setProperty('--font-size', `${s.fontSize}px`);

  $('#v-lineheight').textContent = Number(s.lineHeight).toFixed(2);
  $('#v-paraspace').textContent = `${Number(s.paraSpacing).toFixed(2)}em`;
  $('#v-measure').textContent = `${s.measure}em`;
  $('#v-rate').textContent = `${Number(s.rate).toFixed(2)}×`;
  $('#v-gap').textContent = `${Number(s.gap).toFixed(1)}s`;
  $('#v-fontsize').textContent = s.fontSizeTouched ? `${s.fontSize}px` : '默认';
  settings.fontSize.value = s.fontSize;
  settings.lineHeight.value = s.lineHeight;
  settings.paraSpacing.value = s.paraSpacing;
  settings.measure.value = s.measure;
  settings.indent.checked = Boolean(s.indent);
  settings.rate.value = s.rate;
  settings.gap.value = s.gap;
  for (const button of settings.theme.querySelectorAll('button')) {
    button.classList.toggle('is-active', button.dataset.theme === s.theme);
  }
  for (const button of settings.gender.querySelectorAll('button')) {
    button.classList.toggle('is-active', button.dataset.gender === s.voiceGender);
  }
  dom.btnRate.textContent = `${Number(s.rate).toFixed(2)}×`;
}

settings.fontSize.addEventListener('input', () => {
  state.setSetting('fontSize', Number(settings.fontSize.value));
  state.setSetting('fontSizeTouched', true);
  applySettings();
});
settings.lineHeight.addEventListener('input', () => {
  state.setSetting('lineHeight', Number(settings.lineHeight.value));
  applySettings();
});
settings.paraSpacing.addEventListener('input', () => {
  state.setSetting('paraSpacing', Number(settings.paraSpacing.value));
  applySettings();
});
settings.measure.addEventListener('input', () => {
  state.setSetting('measure', Number(settings.measure.value));
  applySettings();
});
settings.indent.addEventListener('change', () => {
  state.setSetting('indent', settings.indent.checked);
  applySettings();
});
settings.gender.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-gender]');
  if (!button) return;
  state.setSetting('voiceGenderTouched', true);
  state.setSetting('voiceGender', button.dataset.gender);
  // 换了性别，之前挑的音色就不作数了，让它按语言与性别重新挑。
  state.setSetting('voiceId', '');
  state.setSetting('voiceTouched', false);
  applySettings();
  await loadVoices();
  applySettings();
});

settings.theme.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-theme]');
  if (!button) return;
  state.settings.themeTouched = true;
  state.setSetting('theme', button.dataset.theme);
  applySettings();
});
settings.rate.addEventListener('input', () => {
  player.setRate(Number(settings.rate.value));
  applySettings();
});
settings.gap.addEventListener('input', () => {
  state.setSetting('gap', Number(settings.gap.value));
  applySettings();
});
settings.voice.addEventListener('change', () => {
  state.setSetting('voiceId', settings.voice.value);
  if (player.playing && player.sentenceId) void player.play(player.sentenceId);
  state.setSetting('voiceTouched', true);
  dom.btnVoice.textContent = settings.voice.selectedOptions[0]
    ? settings.voice.selectedOptions[0].textContent
    : '—';
});

dom.btnTheme.addEventListener('click', cycleTheme);
dom.btnFont.addEventListener('click', () => {
  const next = clamp(state.settings.fontSize + 1, 14, 26);
  state.setSetting('fontSize', next);
  state.setSetting('fontSizeTouched', true);
  applySettings();
});
dom.btnSettings.addEventListener('click', () => {
  if (dom.drawerSettings.classList.contains('is-open')) closeDrawers();
  else openDrawer('settings');
});
dom.btnMenu.addEventListener('click', () => {
  if (dom.drawerToc.classList.contains('is-open')) closeDrawers();
  else openDrawer('toc');
});
dom.btnBack.addEventListener('click', () => showLibrary());

function cycleTheme() {
  const order = ['paper', 'sepia', 'night', 'qingshan'];
  const index = order.indexOf(state.settings.theme);
  const next = index < 0 ? 0 : (index + 1) % order.length;
  state.settings.themeTouched = true;
  state.setSetting('theme', order[next]);
  applySettings();
}

/* ------------------------------------------------------------------ */
/* 书架与阅读                                                          */
/* ------------------------------------------------------------------ */

const library = new LibraryView(dom.library, {
  onOpen: (book) => openBook(book.book_id),
});

const reader = new ReaderView(dom.reader, {
  onCursorMove: (sentenceId, options) => moveCursor(sentenceId, options),
  onSentenceClick: (sentenceId) => onSentenceClick(sentenceId),
});

const toc = new TocDrawer(dom.drawerToc, {
  onNavigate: (node) => onNavigate(node),
  onToast: toast,
});

function appBasePath() {
  return (window.lectorBase || '').replace(/\/+$/, '');
}

function libraryUrl() {
  return appBasePath() || '/';
}

function bookUrl(bookId, chapterId = null) {
  const base = appBasePath();
  const suffix = chapterId ? `/${bookId}/${chapterId}` : `/${bookId}`;
  return `${base}${suffix}`;
}

function parseReaderRoute() {
  const base = appBasePath();
  let path = window.location.pathname;
  if (base) {
    if (path !== base && !path.startsWith(`${base}/`)) return {};
    path = path.slice(base.length);
  }
  const parts = path.split('/').filter(Boolean);
  if (!parts.length) return {};
  return { bookId: parts[0], chapterId: parts[1] || null };
}

function updateUrl(bookId, chapterId = null, { replace = false } = {}) {
  const url = bookId ? bookUrl(bookId, chapterId) : libraryUrl();
  if (window.location.pathname === url && !window.location.search) return;
  const method = replace ? 'replaceState' : 'pushState';
  window.history[method]({ bookId, chapterId }, '', url);
}

function showLibrary({ fromRoute = false, replace = false } = {}) {
  closeDrawers({ restoreFocus: false });
  closeRateMenu();
  dom.body.classList.remove('view-reader');
  dom.body.classList.add('view-library');
  dom.library.hidden = false;
  dom.reader.hidden = true;
  dom.btnBack.hidden = true;
  dom.topbarBook.textContent = '有声电子书';
  dom.topbarChapter.textContent = '';
  dom.player.hidden = true;
  player.release();
  library.refresh();
  if (!fromRoute || replace) updateUrl(null, null, { replace });
}

async function openBook(bookId, { chapterId = null, fromRoute = false } = {}) {
  try {
    const payload = await api.getBook(bookId);
    // 换书就换书：上一本的音频要停掉，缓存也要清掉。
    if (state.book && state.book.book_id !== bookId) {
      player.release();
      if (state.cursor) reader.clearWords(state.cursor.sentence_id);
    }
    state.book = payload.book;
    state.restoreBookSettings(bookId);
    player.setRate(state.settings.rate);
    applySettings();
    if (!fromRoute) {
      updateUrl(bookId);
      void api.recordOpen(bookId)
        .then((result) => {
          const known = state.books.find((book) => book.book_id === bookId);
          if (known) known.open_count = result.open_count;
          if (state.book && state.book.book_id === bookId) {
            state.book.open_count = result.open_count;
          }
        })
        .catch(() => {
          // 计数失败不影响打开书籍。
        });
    }
    state.setPref(bookId, 'lastOpened', Date.now());
    state.rememberBook(bookId);
    dom.body.classList.remove('view-library');
    dom.body.classList.add('view-reader');
    dom.library.hidden = true;
    dom.reader.hidden = false;
    dom.player.hidden = false;
    setPlayerCollapsed(false);
    dom.btnBack.hidden = false;
    dom.topbarBook.textContent = payload.book.title;
    await loadToc();

    await loadVoices();
    applySettings();
    // 位置只认本地这一份：网页与终端各记各的，互不影响。
    const local = state.prefsFor(bookId).position;
    const sameChapter = local && (!chapterId || local.chapter_id === chapterId);
    const target = chapterId
      ? {
          chapter_id: chapterId,
          sentence_id: sameChapter ? local.sentence_id : null,
          word_index: sameChapter ? local.word_index : null,
        }
      : (local
          ? {
              chapter_id: local.chapter_id,
              sentence_id: local.sentence_id,
              word_index: local.word_index,
            }
          : null);
    if (target) {
      await loadChapter(target.chapter_id, target.sentence_id || null);
    } else {
      await openFirstReadableChapter();
    }
    if (target && target.sentence_id && reader.elementFor(target.sentence_id)) {
      const restored = {
        ...target,
        book_id: bookId,
        word_index: target.word_index ?? null,
      };
      state.setCursor(restored, 'restore');
      reader.setCurrent(target.sentence_id);
      rememberPosition(restored);
      measureProgress();
      updateReadingProgress();
    } else {
      const first = reader.firstSentenceId();
      if (first && (!state.cursor || !reader.elementFor(state.cursor.sentence_id))) {
        moveCursor(first);
      }
    }
  } catch (error) {
    toast(error.message || '打开失败');
    if (fromRoute) showLibrary({ fromRoute: true, replace: true });
  }
}

/**
 * Open the first chapter that has words.
 *
 * Books often start with cover and copyright pages that carry no text at all;
 * dropping the reader into an empty chapter is a bad first impression.
 */
async function openFirstReadableChapter() {
  // 目录里排在前面的章节优先：封面、版权页之后就是正文，
  // 免得打开书先落在"目录"那一页上。
  const ids = await chapterIds();
  const limit = Math.min(ids.length, 8);
  let lastChapter = null;
  for (let index = 0; index < limit; index += 1) {
    const chapterId = ids[index];
    const payload = await api.getChapter(state.book.book_id, chapterId);
    lastChapter = payload.chapter;
    if (payload.chapter.sentence_count > 0) {
      await loadChapter(chapterId);
      const first = reader.firstSentenceId();
      if (first) {
        moveCursor(first);
        reader.jumpTo(first, { smooth: false });
      }
      return;
    }
  }
  if (lastChapter) {
    await loadChapter(lastChapter.chapter_id);
  } else {
    await loadChapter(ids[0] || 'c0');
  }
}

async function loadToc() {
  try {
    const payload = await api.getToc(state.book.book_id);
    toc.setToc(payload.toc);
  } catch (error) {
    toc.setToc([]);
  }
}

async function loadChapter(chapterId, sentenceId = null) {
  try {
    const payload = await api.getChapter(state.book.book_id, chapterId);
    state.chapter = payload.chapter;
    dom.topbarChapter.textContent = payload.chapter.title;
    dom.playerChapter.textContent = payload.chapter.title;
    reader.render(payload.chapter);
    if (sentenceId) {
      requestAnimationFrame(() => reader.jumpTo(sentenceId, { smooth: false }));
    }
    updateUrl(state.book.book_id, chapterId, { replace: true });
    await loadTimeline(chapterId);
    warmAhead(chapterId);
    updateReadingProgress();
  } catch (error) {
    toast(error.message || '章节加载失败');
  }
}

async function loadTimeline(chapterId) {
  try {
    const payload = await api.getTimeline(state.book.book_id, chapterId);
    state.timeline = payload.sentences || [];
    updatePlayerTime();
  } catch (error) {
    state.timeline = [];
  }
}

/* ------------------------------------------------------------------ */
/* 游标与进度                                                          */
/* ------------------------------------------------------------------ */

/**
 * 位置只记在浏览器本地。
 *
 * 网页与终端是两套独立的阅读器：在终端读到哪，不会把网页顶走，
 * 反之亦然。服务端只帮忙把游标换算成百分比，不存位置。
 */
function rememberPosition(cursor) {
  if (!state.book) return;
  const bookId = state.book.book_id;
  const previous = state.prefsFor(bookId).position || {};
  const sameSentence = previous.chapter_id === cursor.chapter_id
    && previous.sentence_id === cursor.sentence_id;
  state.setPref(bookId, 'position', {
    chapter_id: cursor.chapter_id,
    sentence_id: cursor.sentence_id,
    word_index: cursor.word_index,
    percent: sameSentence ? (previous.percent || 0) : 0,
  });
}

function updateReadingProgress() {
  if (!state.book || !state.chapter) return;
  const sentenceById = new Map(state.sentences().map((sentence) => [sentence.id, sentence]));
  const sentences = reader.order
    .map((sentenceId) => sentenceById.get(sentenceId))
    .filter(Boolean);
  const currentId = state.cursor ? state.cursor.sentence_id : null;
  const metrics = chapterTimeMetrics(sentences, state.timeline, {
    currentId,
    playerSentenceId: player.sentenceId,
    playerPosition: player.position || 0,
  });
  const progress = metrics.total > 0
    ? Math.min(100, Math.round((metrics.elapsed / metrics.total) * 100))
    : 0;
  const elapsedLabel = formatTime(metrics.elapsed);
  const totalLabel = formatTime(metrics.total);
  dom.readingChapterFill.style.width = `${progress}%`;
  dom.readingChapterProgress.setAttribute('aria-valuenow', String(progress));
  dom.playerProgress.style.width = `${progress}%`;
  dom.playerTime.textContent = `${elapsedLabel} / ${totalLabel}`;
  dom.playerTime.title = `本章累计已播 ${elapsedLabel} / 总时长 ${totalLabel}`;
}

const measureProgress = debounce(async () => {
  if (!state.book || !state.cursor) return;
  const { chapter_id: chapterId, sentence_id: sentenceId } = state.cursor;
  try {
    const payload = await api.percent(state.book.book_id, chapterId, sentenceId);
    const prefs = state.prefsFor(state.book.book_id);
    if (!prefs.position || prefs.position.sentence_id !== sentenceId) return;
    state.setPref(state.book.book_id, 'position', {
      ...prefs.position,
      percent: payload.percent,
    });
    updateReadingProgress();
  } catch (error) {
    /* 百分比算不出来不影响阅读 */
  }
}, 400);

/* 提前把音频准备好：打开一章就在后台预热开头几句，
 * 播放时就不用等网络。 */
const warmed = new Set();

function warmAhead(chapterId) {
  if (!state.book || !chapterId || warmed.has(chapterId)) return;
  warmed.add(chapterId);
  api.warmAudio(state.book.book_id, {
    chapter_id: chapterId,
    voice_id: state.settings.voiceId || undefined,
    limit: 12,
  }).catch(() => {
    // 预热失败不影响阅读：播放时照样按需合成。
  });
}

function moveCursor(sentenceId, { scroll = false } = {}) {
  const sentence = state.findSentence(sentenceId);
  if (!sentence) return;
  const chapterId = sentenceId.split('.b')[0];
  const cursor = {
    book_id: state.book.book_id,
    chapter_id: chapterId,
    sentence_id: sentenceId,
    word_index: state.cursor ? state.cursor.word_index : null,
  };
  state.setCursor(cursor, 'move');
  reader.setCurrent(sentenceId, { scroll });
  rememberPosition(cursor);
  measureProgress();
  updateReadingProgress();
}

function onSentenceClick(sentenceId) {
  if (player.playing) {
    player.play(sentenceId);
  } else {
    moveCursor(sentenceId);
    reader.jumpTo(sentenceId);
  }
}

async function onNavigate(node) {
  closeDrawers();
  const chapterId = node.chapter_id;
  if (!chapterId) return;
  if (node.sentence_id) {
    // A search hit: jump straight to the sentence.
    if (chapterId !== (state.chapter && state.chapter.chapter_id)) {
      await loadChapter(chapterId, node.sentence_id);
    } else {
      moveCursor(node.sentence_id);
      reader.jumpTo(node.sentence_id);
    }
    return;
  }
  if (state.chapter && state.chapter.chapter_id === chapterId) {
    if (node.anchor) {
      const sentenceId = reader.sentenceForAnchor(state.chapter, node.anchor);
      if (sentenceId) {
        moveCursor(sentenceId);
        reader.jumpTo(sentenceId);
        return;
      }
    }
    const first = reader.firstSentenceId();
    if (first) reader.jumpTo(first);
    return;
  }
  await loadChapter(chapterId);
  if (node.anchor && state.chapter) {
    const sentenceId = reader.sentenceForAnchor(state.chapter, node.anchor);
    if (sentenceId) {
      moveCursor(sentenceId);
      requestAnimationFrame(() => reader.jumpTo(sentenceId, { smooth: false }));
      return;
    }
  }
  const first = reader.firstSentenceId();
  if (first) {
    moveCursor(first);
    reader.jumpTo(first, { smooth: false });
  }
}

async function gotoChapter(offset) {
  // Switch to the neighbouring chapter and put the cursor at its start.
  // Returns true when there was a chapter to switch to.
  if (!state.chapter) return false;
  const chapters = await chapterIds();
  const index = chapters.indexOf(state.chapter.chapter_id);
  const next = chapters[index + offset];
  if (!next) return false;
  await loadChapter(next);
  const first = reader.firstSentenceId();
  if (first) {
    moveCursor(first);
    reader.jumpTo(first, { smooth: false });
  }
  return true;
}

let chapterIdsCache = null;
let chapterIdsBook = null;

/** The chapters in reading order (the spine order), not the directory order. */
async function chapterIds() {
  if (chapterIdsCache && chapterIdsBook === state.book.book_id) return chapterIdsCache;
  const ids = new Set();
  const count = state.book ? state.book.chapter_count : 0;
  for (let index = 0; index < count; index += 1) ids.add(`c${index}`);
  // 目录里出现过的章节排在前面：那是这本书自己的阅读顺序。
  const ordered = [];
  for (const node of state.toc) {
    if (node.chapter_id && !ordered.includes(node.chapter_id)) {
      ordered.push(node.chapter_id);
    }
  }
  const rest = [...ids]
    .filter((id) => !ordered.includes(id))
    .sort((left, right) => Number(left.slice(1)) - Number(right.slice(1)));
  chapterIdsCache = [...ordered, ...rest];
  chapterIdsBook = state.book.book_id;
  return chapterIdsCache;
}

/* ------------------------------------------------------------------ */
/* 听书                                                                */
/* ------------------------------------------------------------------ */

const refreshTimeline = debounce(() => {
  if (state.chapter) loadTimeline(state.chapter.chapter_id);
}, 1500);

player.onSentence = (sentenceId, words, granularity) => {
  reader.setWords(sentenceId, words, granularity);
  reader.setCurrent(sentenceId);
  reader.locked = true;
  // 当前句可见时不打扰阅读；翻到下一页或被播放器遮住时才滚回可视区。
  reader.ensureSentenceVisible(sentenceId);
  if (state.cursor && state.cursor.sentence_id !== sentenceId) {
    state.setCursor({ ...state.cursor, sentence_id: sentenceId }, 'play');
    rememberPosition(state.cursor);
  }
  // 新合成的句子还没进时间线，拉一次，让进度条和总时长跟上。
  if (!state.timeline.some((item) => item.sentence_id === sentenceId)) {
    refreshTimeline();
  }
  updatePlayerTime();
};

player.onState = (playing, finished) => {
  // 播放时游标归声音管，滚动不再改它；停下来才交还给用户。
  reader.locked = playing;
  dom.btnPlay.setAttribute('aria-label', playing ? '暂停' : '播放');
  dom.btnPlay.innerHTML = playing
    ? '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6 4h3v12H6zM11 4h3v12h-3z"/></svg>'
    : '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6 4l10 6-10 6z"/></svg>';
  if (finished) {
    // 一章读完就接着下一章，听书不该在章节边界断掉。
    gotoChapter(1).then((advanced) => {
      if (advanced) player.play(state.cursor.sentence_id);
      else toast('全书读完');
    });
  }
  updatePlayerTime();
};

player.onTick = () => updatePlayerTime();

player.onError = (message) => {
  toast(message || '播放失败');
  dom.playerStatus.textContent = '';
};

dom.btnPlay.addEventListener('click', () => {
  dom.player.hidden = false;
  player.toggle();
});
dom.btnPrev.addEventListener('click', () => stepSentence(-1));
dom.btnNext.addEventListener('click', () => stepSentence(1));

function setPlayerCollapsed(collapsed) {
  dom.player.classList.toggle('is-collapsed', collapsed);
  dom.playerPanel.toggleAttribute('inert', collapsed);
  dom.playerPanel.setAttribute('aria-hidden', String(collapsed));
  dom.btnPlayerToggle.setAttribute('aria-expanded', String(!collapsed));
  const label = collapsed ? '展开播放控制' : '收起播放控制';
  dom.btnPlayerToggle.setAttribute('aria-label', label);
  dom.btnPlayerToggle.title = label;
  if (collapsed) closeRateMenu();
}

dom.btnPlayerToggle.addEventListener('click', () => {
  setPlayerCollapsed(!dom.player.classList.contains('is-collapsed'));
});
/* 倍速：点一下弹出菜单，而不是一轮轮地转 */
function openRateMenu() {
  const menu = dom.rateMenu;
  for (const button of menu.querySelectorAll('button')) {
    const value = Number(button.dataset.rate);
    button.classList.toggle('is-active', Math.abs(value - state.settings.rate) < 0.01);
  }
  menu.hidden = false;
  dom.btnRate.setAttribute('aria-expanded', 'true');
  (menu.querySelector('.is-active') || menu.querySelector('button')).focus({ preventScroll: true });
}

function closeRateMenu({ restoreFocus = false } = {}) {
  dom.rateMenu.hidden = true;
  dom.btnRate.setAttribute('aria-expanded', 'false');
  if (restoreFocus) dom.btnRate.focus({ preventScroll: true });
}

dom.btnRate.addEventListener('click', (event) => {
  event.stopPropagation();
  if (dom.rateMenu.hidden) openRateMenu();
  else closeRateMenu();
});

dom.btnRate.addEventListener('keydown', (event) => {
  if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
  event.preventDefault();
  event.stopPropagation();
  openRateMenu();
});

dom.rateMenu.addEventListener('keydown', (event) => {
  if (event.key === 'Tab') {
    closeRateMenu({ restoreFocus: true });
    return;
  }
  const buttons = [...dom.rateMenu.querySelectorAll('button')];
  const index = buttons.indexOf(document.activeElement);
  let next;
  if (event.key === 'ArrowDown') next = (index + 1) % buttons.length;
  else if (event.key === 'ArrowUp') next = (index - 1 + buttons.length) % buttons.length;
  else if (event.key === 'Home') next = 0;
  else if (event.key === 'End') next = buttons.length - 1;
  else return;
  event.preventDefault();
  event.stopPropagation();
  buttons[next].focus();
});

dom.rateMenu.parentElement.addEventListener('focusout', (event) => {
  // 触摸浏览器可能先 blur（relatedTarget=null），再产生 click。此时由
  // 外部点击或 Tab 负责关闭，避免按钮在点击前被隐藏。
  if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) closeRateMenu();
});

dom.rateMenu.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-rate]');
  if (!button) return;
  event.stopPropagation();
  const value = Number(button.dataset.rate);
  player.setRate(value);
  applySettings();
  closeRateMenu({ restoreFocus: true });
});

document.addEventListener('click', (event) => {
  if (!dom.rateMenu.hidden && !dom.rateMenu.contains(event.target)) {
    closeRateMenu();
  }
});
dom.btnVoice.addEventListener('click', () => openDrawer('settings'));

$('#btn-share').addEventListener('click', async () => {
  if (!state.book || !state.cursor) {
    toast('还没有位置可以分享');
    return;
  }
  try {
    const payload = await api.createShortCode({
      book_id: state.book.book_id,
      chapter_id: state.cursor.chapter_id,
      sentence_id: state.cursor.sentence_id,
      word_index: state.cursor.word_index ?? null,
    });
    const url = `${window.location.origin}${payload.url}`;
    try {
      await navigator.clipboard.writeText(url);
      toast(`短码已复制：${payload.code}`);
    } catch (error) {
      toast(`短码：${payload.code}（${url}）`);
    }
  } catch (error) {
    toast(error.message || '分享失败');
  }
});

$('#btn-warm').addEventListener('click', async () => {
  if (!state.book || !state.chapter) {
    toast('先打开一本书');
    return;
  }
  toast('正在预生成音频，可以继续阅读');
  try {
    // 不等它结束：预生成是后台工作，读到哪算到哪。
    api.warmAudio(state.book.book_id, {
      chapter_id: state.chapter.chapter_id,
      voice_id: state.settings.voiceId || undefined,
    }).then((payload) => {
      toast(`预生成完成：成功 ${payload.ready}，失败 ${payload.failed}`);
      loadTimeline(state.chapter.chapter_id);
    }).catch((error) => toast(error.message || '预生成失败'));
  } catch (error) {
    toast(error.message || '预生成失败');
  }
});

$('#btn-clear-audio').addEventListener('click', async () => {
  if (!state.book) return;
  try {
    await api.clearAudio(state.book.book_id);
    toast('音频缓存已清除');
  } catch (error) {
    toast(error.message || '清除失败');
  }
});

$('#btn-export-progress').addEventListener('click', async () => {
  if (!state.book) return;
  try {
    // 导出的是这一端本地记的进度，不是服务器上的。
    const position = state.prefsFor(state.book.book_id).position || null;
    const progress = {
      book_id: state.book.book_id,
      cursor: position
        ? {
          chapter_id: position.chapter_id,
          sentence_id: position.sentence_id,
          word_index: position.word_index ?? null,
        }
        : null,
      percent: position ? position.percent || 0 : 0,
      source: 'local',
    };
    const blob = new Blob([JSON.stringify(progress, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${state.book.title}-progress.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast('进度已导出');
  } catch (error) {
    toast(error.message || '导出失败');
  }
});

function stepSentence(offset) {
  const sentences = reader.order;
  if (!sentences.length) return;
  const current = state.cursor ? state.cursor.sentence_id : sentences[0];
  let index = sentences.indexOf(current);
  if (index < 0) index = 0;
  const next = sentences[clamp(index + offset, 0, sentences.length - 1)];
  if (!next) return;
  moveCursor(next);
  reader.jumpTo(next);
  if (player.playing) player.play(next);
}

function updatePlayerTime() {
  updateReadingProgress();
}

/* ------------------------------------------------------------------ */
/* 快捷键                                                              */
/* ------------------------------------------------------------------ */

document.addEventListener('keydown', async (event) => {
  if (isTypingTarget(event.target)) {
    if (event.key === 'Escape') event.target.blur();
    return;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;

  const key = event.key;
  if (key === 'Escape') {
    if (!dom.rateMenu.hidden) { closeRateMenu({ restoreFocus: true }); return; }
    if (drawerOpen()) { closeDrawers(); return; }
    if (document.body.classList.contains('immersive')) {
      document.body.classList.remove('immersive');
      return;
    }
    if (dom.body.classList.contains('view-reader')) { showLibrary(); return; }
    return;
  }
  // Native controls own their activation and navigation keys.
  if (event.target.closest('button, a[href], [role="button"]')
    && [' ', 'Spacebar', 'Enter', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown',
      'Home', 'End', 'PageUp', 'PageDown'].includes(key)) return;
  if (!dom.rateMenu.hidden) return;
  if (key === '?' || (key === '/' && event.shiftKey)) {
    openDrawer('settings');
    event.preventDefault();
    return;
  }
  if (key === '/') {
    event.preventDefault();
    openDrawer('toc');
    return;
  }
  if (key === 't') {
    if (activeDrawer === dom.drawerToc) closeDrawers();
    else openDrawer('toc');
    return;
  }
  if (key === 's') {
    if (activeDrawer === dom.drawerSettings) closeDrawers();
    else openDrawer('settings');
    return;
  }
  if (drawerOpen()) return;
  if (key === 'm') { cycleTheme(); return; }
  if (key === 'f') {
    document.body.classList.toggle('immersive');
    return;
  }
  if (key === '+' || key === '=') {
    state.setSetting('fontSize', clamp(state.settings.fontSize + 1, 14, 26));
    state.setSetting('fontSizeTouched', true);
    applySettings();
    return;
  }
  if (key === '-' || key === '_') {
    state.setSetting('fontSize', clamp(state.settings.fontSize - 1, 14, 26));
    state.setSetting('fontSizeTouched', true);
    applySettings();
    return;
  }
  if (!dom.body.classList.contains('view-reader')) return;

  if (key === 'ArrowLeft') { stepSentence(-1); event.preventDefault(); return; }
  if (key === 'ArrowRight') { stepSentence(1); event.preventDefault(); return; }
  if (key === 'ArrowUp') { reader.scroll.scrollBy({ top: -40 }); event.preventDefault(); return; }
  if (key === 'ArrowDown') { reader.scroll.scrollBy({ top: 40 }); event.preventDefault(); return; }
  if (key === 'PageUp') { reader.scroll.scrollBy({ top: -reader.scroll.clientHeight * 0.9 }); event.preventDefault(); return; }
  if (key === 'PageDown') { reader.scroll.scrollBy({ top: reader.scroll.clientHeight * 0.9 }); event.preventDefault(); return; }
  if (key === 'Home') {
    const first = reader.firstSentenceId();
    if (first) { moveCursor(first); reader.jumpTo(first); }
    event.preventDefault();
    return;
  }
  if (key === 'End') {
    const last = reader.order[reader.order.length - 1];
    if (last) { moveCursor(last); reader.jumpTo(last); }
    event.preventDefault();
    return;
  }
  if (key === '[') { await gotoChapter(-1); return; }
  if (key === ']') { await gotoChapter(1); return; }
  if (key === ' ' || key === 'Spacebar') {
    event.preventDefault();
    // 听书态：播放/暂停。阅读态：翻页。进入听书态的入口是听书条上的播放键。
    if (player.playing || player.sentenceId) {
      player.toggle();
    } else {
      reader.scroll.scrollBy({ top: reader.scroll.clientHeight * 0.9 });
    }
  }
});

/* ------------------------------------------------------------------ */
/* 启动                                                                */
/* ------------------------------------------------------------------ */

/** 书的语言决定能用哪些音色。 */
function languageFamily(language) {
  if (!language) return '';
  const prefix = language.split('-')[0].toLowerCase();
  return ['zh', 'en'].includes(prefix) ? prefix : '';
}

/** 这一本书可以用的音色：同语言的那些。 */
function voicesFor(language) {
  const featured = state.featuredVoices || [];
  const pool = featured.length
    ? state.voices.filter((voice) => featured.includes(voice.voice_id))
    : state.voices;
  const family = languageFamily(language);
  if (!family) return pool;
  const same = pool.filter(
    (voice) => voice.locale.split('-')[0].toLowerCase() === family,
  );
  return same;
}

let voiceRequest = 0;
async function loadVoices() {
  const request = ++voiceRequest;
  const bookId = state.book?.book_id;
  try {
    const payload = await api.voices();
    if (request !== voiceRequest || bookId !== state.book?.book_id) return;
    state.voices = payload.voices || [];
    // 中文书只给中文的声音，英文书只给英文的。
    let shown = voicesFor(state.book ? state.book.language : '');
    const gender = state.settings.voiceGender;
    if (gender && gender !== 'any') {
      const byGender = shown.filter((voice) => voice.gender === gender);
      // 常用音色里没有这个性别时，宁可给全部，也不给空列表。
      if (byGender.length) shown = byGender;
    }
    settings.voice.replaceChildren();
    for (const voice of shown) {
      settings.voice.append(el('option', {
        value: voice.voice_id,
        text: `${voice.name} · ${voice.locale}`,
      }));
    }
    const wanted = state.settings.voiceId
      || (state.book ? matchVoice(state.book.language, state.settings.voiceGender) : '')
      || state.defaultVoice;
    const options = shown;
    if (wanted && options.some((voice) => voice.voice_id === wanted)) {
      settings.voice.value = wanted;
    } else if (options.length) {
      settings.voice.value = options[0].voice_id;
    }
    const previousVoice = state.settings.voiceId;
    state.setSetting('voiceId', settings.voice.value);
    if (previousVoice !== state.settings.voiceId && player.playing && player.sentenceId) {
      void player.play(player.sentenceId);
    }
    dom.btnVoice.textContent = settings.voice.selectedOptions[0]
      ? settings.voice.selectedOptions[0].textContent
      : '—';
  } catch (error) {
    if (request !== voiceRequest || bookId !== state.book?.book_id) return;
    dom.btnVoice.textContent = '不可用';
  }
}

/**
 * The voice for a book: the server decides, by the language of the book.
 *
 * Chinese books are read in Chinese, English books in American English
 * (a male voice); the client only falls back when the server has no opinion.
 */
function matchVoice(language, gender) {
  const wanted = gender && gender !== 'any' ? gender : null;
  // 只在这本书的语言范围里挑。
  const pool = voicesFor(language);
  const fits = (voice) => !wanted || voice.gender === wanted;
  const family = languageFamily(language)
    || (state.defaultVoice || 'zh-CN').split('-')[0].toLowerCase();

  // 先固定到这门语言的默认地区；再按用户选择的性别筛选。
  const byLanguage = (state.defaultVoices || {})[family];
  const defaultVoice = byLanguage
    ? state.voices.find((voice) => voice.voice_id === byLanguage)
    : null;
  if (defaultVoice && fits(defaultVoice)) return defaultVoice.voice_id;

  const locale = defaultVoice ? defaultVoice.locale.toLowerCase() : '';
  const exact = pool.find(
    (voice) => voice.locale.toLowerCase() === locale && fits(voice),
  );
  if (exact) return exact.voice_id;

  const loose = pool.find(fits);
  if (loose) return loose.voice_id;

  const anywhere = state.voices.find(fits);
  return anywhere ? anywhere.voice_id : '';
}

async function handleShareCode() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('s');
  if (!code) return false;
  try {
    const cursor = await api.resolveShortCode(code);
    await openBook(cursor.book_id, {
      chapterId: cursor.chapter_id || null,
      fromRoute: true,
    });
    if (cursor.sentence_id && state.findSentence(cursor.sentence_id)) {
      moveCursor(cursor.sentence_id);
      reader.jumpTo(cursor.sentence_id, { smooth: false });
    }
    return true;
  } catch (error) {
    toast('短码已失效');
    return false;
  }
}

async function start() {
  applySettings();
  try {
    const meta = await fetch(`${window.lectorBase || ''}/api/v1/meta`)
      .then((response) => response.json());
    state.defaultVoice = meta.default_voice || '';
    state.featuredVoices = meta.featured_voices || [];
    state.defaultVoices = meta.default_voices || {};
    state.defaultRates = meta.default_rates || {};
  } catch (error) {
    state.defaultVoice = '';
  }
  await loadVoices();
  await library.refresh();
  const shared = await handleShareCode();
  if (shared) return;
  const route = parseReaderRoute();
  if (route.bookId) {
    await openBook(route.bookId, { chapterId: route.chapterId, fromRoute: true });
    return;
  }
  showLibrary({ fromRoute: true, replace: true });
}

// 调试用：控制台里能摸到当前状态与播放器。
window.lector = { state, player, reader };

window.addEventListener('popstate', async () => {
  const route = parseReaderRoute();
  if (route.bookId) {
    await openBook(route.bookId, { chapterId: route.chapterId, fromRoute: true });
  } else {
    showLibrary({ fromRoute: true });
  }
});

start();
