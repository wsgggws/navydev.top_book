/* Lector — the browser application. */

import { api, getToken, setToken } from './api.js';
import { state } from './state.js';
import { Player } from './player.js';
import { LibraryView } from './views/library.js';
import { ReaderView } from './views/reader.js';
import { TocDrawer } from './views/toc.js';
import { clamp, debounce, el, formatTime, isTypingTarget } from './util.js';

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
  drawerToc: $('#drawer-toc'),
  drawerSettings: $('#drawer-settings'),
  overlay: $('#overlay'),
  toast: $('#toast'),
  player: $('#player'),
  playerChapter: $('#player-chapter'),
  playerProgress: $('#player-progress'),
  playerTime: $('#player-time'),
  playerStatus: $('#player-status'),
  btnPlay: $('#btn-play'),
  btnPrev: $('#btn-prev'),
  btnNext: $('#btn-next'),
  btnRate: $('#btn-rate'),
  btnVoice: $('#btn-voice'),
  btnPlayerClose: $('#btn-player-close'),
  btnFollow: $('#btn-follow'),
  followDot: $('#follow-dot'),
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

let hideTimer = null;

function openDrawer(name) {
  closeDrawers();
  if (hideTimer) clearTimeout(hideTimer);
  const drawer = name === 'toc' ? dom.drawerToc : dom.drawerSettings;
  drawer.hidden = false;
  requestAnimationFrame(() => drawer.classList.add('is-open'));
  dom.overlay.hidden = false;
}

function closeDrawers() {
  for (const drawer of [dom.drawerToc, dom.drawerSettings]) {
    drawer.classList.remove('is-open');
  }
  dom.overlay.hidden = true;
  // Wait for the slide-out before hiding, but let a new drawer cancel it.
  if (hideTimer) clearTimeout(hideTimer);
  hideTimer = setTimeout(() => {
    for (const drawer of [dom.drawerToc, dom.drawerSettings]) {
      if (!drawer.classList.contains('is-open')) drawer.hidden = true;
    }
    hideTimer = null;
  }, 240);
}

function drawerOpen() {
  return dom.drawerToc.classList.contains('is-open')
    || dom.drawerSettings.classList.contains('is-open');
}

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
settings.gender.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-gender]');
  if (!button) return;
  state.setSetting('voiceGender', button.dataset.gender);
  // 换了性别，之前挑的音色就不作数了，让它按语言与性别重新挑。
  state.setSetting('voiceId', '');
  state.setSetting('voiceTouched', false);
  applySettings();
  loadVoices();
});

settings.theme.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-theme]');
  if (!button) return;
  state.setSetting('theme', button.dataset.theme);
  applySettings();
});
settings.rate.addEventListener('input', () => {
  state.setSetting('rate', Number(settings.rate.value));
  player.setRate(state.settings.rate);
  applySettings();
});
settings.gap.addEventListener('input', () => {
  state.setSetting('gap', Number(settings.gap.value));
  applySettings();
});
settings.voice.addEventListener('change', () => {
  state.setSetting('voiceId', settings.voice.value);
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
  const order = ['paper', 'sepia', 'night'];
  const index = order.indexOf(state.settings.theme);
  const next = index < 0 ? 0 : (index + 1) % order.length;
  state.setSetting('theme', order[next]);
  applySettings();
}

/* ------------------------------------------------------------------ */
/* 书架与阅读                                                          */
/* ------------------------------------------------------------------ */

const library = new LibraryView(dom.library, {
  onOpen: (book) => openBook(book.book_id),
  onToast: toast,
});

const reader = new ReaderView(dom.reader, {
  onCursorMove: (sentenceId, options) => moveCursor(sentenceId, options),
  onSentenceClick: (sentenceId) => onSentenceClick(sentenceId),
  onScrollEnd: (following) => updateFollowHint(following),
});

const toc = new TocDrawer(dom.drawerToc, {
  onNavigate: (node) => onNavigate(node),
  onToast: toast,
});

function showLibrary() {
  dom.body.classList.remove('view-reader');
  dom.body.classList.add('view-library');
  dom.library.hidden = false;
  dom.reader.hidden = true;
  dom.btnBack.hidden = true;
  dom.topbarBook.textContent = 'Lector';
  dom.topbarChapter.textContent = '';
  dom.player.hidden = true;
  player.release();
  library.refresh();
}

async function openBook(bookId) {
  try {
    const payload = await api.getBook(bookId);
    // 换书就换书：上一本的音频要停掉，缓存也要清掉。
    if (state.book && state.book.book_id !== bookId) {
      player.release();
      if (state.cursor) reader.clearWords(state.cursor.sentence_id);
    }
    state.book = payload.book;
    state.rememberBook(bookId);
    dom.body.classList.remove('view-library');
    dom.body.classList.add('view-reader');
    dom.library.hidden = true;
    dom.reader.hidden = false;
    dom.player.hidden = false;
    dom.btnBack.hidden = false;
    dom.topbarBook.textContent = payload.book.title;
    await loadToc();
    await loadVoices();
    // 音色跟着书的语言走：中文书用中文，英文书用美式男声。
    if (!state.settings.voiceTouched && state.book.language) {
      const wanted = matchVoice(state.book.language, state.settings.voiceGender);
      if (wanted) {
        state.setSetting('voiceId', wanted);
        settings.voice.value = wanted;
        dom.btnVoice.textContent = settings.voice.selectedOptions[0]
          ? settings.voice.selectedOptions[0].textContent
          : '—';
      }
    }
    const progress = payload.progress;
    const target = progress && progress.cursor ? progress.cursor : null;
    if (target) {
      await loadChapter(target.chapter_id, target.sentence_id);
    } else {
      await openFirstReadableChapter();
    }
    if (target && target.word_index !== null && target.word_index !== undefined) {
      state.setCursor({ ...target, book_id: bookId }, 'restore');
    }
    if (!target) {
      const first = state.sentences()[0];
      if (first) moveCursor(first.id);
    }
  } catch (error) {
    toast(error.message || '打开失败');
  }
}

/**
 * Open the first chapter that has words.
 *
 * Books often start with cover and copyright pages that carry no text at all;
 * dropping the reader into an empty chapter is a bad first impression.
 */
async function openFirstReadableChapter() {
  const ids = await chapterIds();
  const limit = Math.min(ids.length, 6);
  let lastChapter = null;
  for (let index = 0; index < limit; index += 1) {
    const chapterId = ids[index];
    const payload = await api.getChapter(state.book.book_id, chapterId);
    lastChapter = payload.chapter;
    if (payload.chapter.sentence_count > 0) {
      await loadChapter(chapterId);
      const first = state.sentences()[0];
      if (first) {
        moveCursor(first.id);
        reader.jumpTo(first.id, { smooth: false });
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
    await loadTimeline(chapterId);
    warmAhead(chapterId);
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

const writeProgress = debounce(async () => {
  if (!state.book || !state.cursor) return;
  const { chapter_id: chapterId, sentence_id: sentenceId, word_index: wordIndex } = state.cursor;
  try {
    await api.setProgress(state.book.book_id, {
      chapter_id: chapterId,
      sentence_id: sentenceId,
      word_index: wordIndex ?? null,
    });
  } catch (error) {
    /* 进度写失败不影响阅读 */
  }
}, 600);

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

/* 跨端接力：网页与终端读写同一份进度。
 * 终端停下 1.2 秒就推一次，网页每 5 秒拉一次；谁先动谁说了算，
 * 另一端在没有本地操作时跟随过去。 */
let lastLocalMove = 0;

const pullRemoteProgress = setInterval(async () => {
  if (!state.book || !state.chapter) return;
  if (document.hidden) return;
  if (!dom.body.classList.contains('view-reader')) return;
  if (Date.now() - lastLocalMove < 3000) return;
  let progress;
  try {
    progress = await api.getProgress(state.book.book_id);
  } catch (error) {
    return;
  }
  const remote = progress && progress.cursor;
  if (!remote) return;
  if (state.cursor
      && remote.chapter_id === state.cursor.chapter_id
      && remote.sentence_id === state.cursor.sentence_id) return;
  await followRemote(remote);
}, 5000);

async function followRemote(remote) {
  toast('已跟随另一端的进度');
  if (remote.chapter_id !== (state.chapter && state.chapter.chapter_id)) {
    await loadChapter(remote.chapter_id, remote.sentence_id);
    return;
  }
  lastLocalMove = Date.now();
  moveCursor(remote.sentence_id);
  reader.jumpTo(remote.sentence_id, { smooth: false });
}

function moveCursor(sentenceId, { scroll = false } = {}) {
  const sentence = state.findSentence(sentenceId);
  if (!sentence) return;
  lastLocalMove = Date.now();
  const chapterId = sentenceId.split('.b')[0];
  const cursor = {
    book_id: state.book.book_id,
    chapter_id: chapterId,
    sentence_id: sentenceId,
    word_index: state.cursor ? state.cursor.word_index : null,
  };
  state.setCursor(cursor, 'move');
  reader.setCurrent(sentenceId, { scroll });
  writeProgress();
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
    reader.jumpTo(state.sentences()[0].id);
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
  const first = state.sentences()[0];
  if (first) {
    moveCursor(first.id);
    reader.jumpTo(first.id, { smooth: false });
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
  const first = state.sentences()[0];
  if (first) {
    moveCursor(first.id);
    reader.jumpTo(first.id, { smooth: false });
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
  for (const node of state.toc) {
    if (node.chapter_id) ids.add(node.chapter_id);
  }
  chapterIdsCache = [...ids].sort(
    (left, right) => Number(left.slice(1)) - Number(right.slice(1)),
  );
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
  reader.setCurrent(sentenceId, { scroll: reader.follow });
  if (state.cursor && state.cursor.sentence_id !== sentenceId) {
    state.setCursor({ ...state.cursor, sentence_id: sentenceId }, 'play');
    writeProgress();
  }
  // 新合成的句子还没进时间线，拉一次，让进度条和总时长跟上。
  if (!state.timeline.some((item) => item.sentence_id === sentenceId)) {
    refreshTimeline();
  }
  updatePlayerTime();
};

player.onState = (playing, finished) => {
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
dom.btnPlayerClose.addEventListener('click', () => {
  player.stop();
  dom.player.hidden = true;
  if (state.cursor) reader.clearWords(state.cursor.sentence_id);
});
dom.btnRate.addEventListener('click', () => {
  const steps = [0.75, 1, 1.25, 1.5, 1.75, 2];
  const index = steps.findIndex((value) => value >= state.settings.rate - 0.01);
  const next = steps[(index + 1) % steps.length];
  state.setSetting('rate', next);
  player.setRate(next);
  applySettings();
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
    const progress = await api.getProgress(state.book.book_id);
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
  const sentences = state.sentences();
  if (!sentences.length) return;
  const current = state.cursor ? state.cursor.sentence_id : sentences[0].id;
  let index = sentences.findIndex((sentence) => sentence.id === current);
  if (index < 0) index = 0;
  const next = sentences[clamp(index + offset, 0, sentences.length - 1)];
  if (!next) return;
  moveCursor(next.id);
  reader.jumpTo(next.id);
  if (player.playing) player.play(next.id);
}

function updatePlayerTime() {
  const total = state.timeline.length
    ? state.timeline[state.timeline.length - 1].end
    : 0;
  const current = player.sentenceId;
  const entry = state.timeline.find((item) => item.sentence_id === current);
  const elapsed = entry ? entry.start + (player.position || 0) : (player.position || 0);
  dom.playerTime.textContent = `${formatTime(elapsed)} / ${formatTime(total)}`;
  const progress = player.chapterProgress();
  dom.playerProgress.style.width = `${Math.round(progress * 100)}%`;
}

function updateFollowHint(following) {
  if (!state.book) return;
  dom.playerStatus.textContent = following ? '' : '跟随已暂停';
  dom.btnFollow.classList.toggle('is-active', following);
  dom.followDot.hidden = following;
}

dom.btnFollow.addEventListener('click', () => {
  reader.setFollow(!reader.follow);
  updateFollowHint(reader.follow);
  if (reader.follow && state.cursor) {
    reader.jumpTo(state.cursor.sentence_id);
  }
});

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
    if (drawerOpen()) { closeDrawers(); return; }
    if (document.body.classList.contains('immersive')) {
      document.body.classList.remove('immersive');
      return;
    }
    if (dom.body.classList.contains('view-reader')) { showLibrary(); return; }
    return;
  }
  if (key === '?' || (key === '/' && event.shiftKey)) {
    openDrawer('settings');
    event.preventDefault();
    return;
  }
  if (key === '/') {
    event.preventDefault();
    openDrawer('toc');
    setTimeout(() => $('#search-input').focus(), 60);
    return;
  }
  if (key === 't') {
    if (dom.drawerToc.classList.contains('is-open')) closeDrawers();
    else openDrawer('toc');
    return;
  }
  if (key === 's') {
    if (dom.drawerSettings.classList.contains('is-open')) closeDrawers();
    else openDrawer('settings');
    return;
  }
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
    const first = state.sentences()[0];
    if (first) { moveCursor(first.id); reader.jumpTo(first.id); }
    event.preventDefault();
    return;
  }
  if (key === 'End') {
    const sentences = state.sentences();
    const last = sentences[sentences.length - 1];
    if (last) { moveCursor(last.id); reader.jumpTo(last.id); }
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

async function loadVoices() {
  try {
    const payload = await api.voices();
    state.voices = payload.voices || [];
    // 引擎有三百多个音色，界面上只给常用的那些。
    const featured = state.featuredVoices || [];
    let shown = featured.length
      ? state.voices.filter((voice) => featured.includes(voice.voice_id))
      : state.voices;
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
    const options = shown.length ? shown : state.voices;
    if (wanted && options.some((voice) => voice.voice_id === wanted)) {
      settings.voice.value = wanted;
    } else if (options.length) {
      settings.voice.value = options[0].voice_id;
    }
    state.setSetting('voiceId', settings.voice.value);
    dom.btnVoice.textContent = settings.voice.selectedOptions[0]
      ? settings.voice.selectedOptions[0].textContent
      : '—';
  } catch (error) {
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
  // 语言不明（EPUB 里写的是 und）时，按服务端默认音色的语言来。
  const unknown = !language || ['und', 'zxx', 'none'].includes(language.toLowerCase());
  const fallbackLocale = (state.defaultVoice || 'zh-CN').split('-')[0].toLowerCase();
  const prefix = unknown ? fallbackLocale : language.split('-')[0].toLowerCase();
  const wanted = gender && gender !== 'any' ? gender : null;
  const featured = state.featuredVoices || [];
  const pool = featured.length
    ? state.voices.filter((voice) => featured.includes(voice.voice_id))
    : state.voices;
  const fits = (voice) => !wanted || voice.gender === wanted;

  // 这门语言的默认音色；英文的默认是美式，所以女声也留在美式里挑。
  const byLanguage = (state.defaultVoices || {})[prefix];
  const defaultVoice = byLanguage
    ? state.voices.find((voice) => voice.voice_id === byLanguage)
    : null;
  if (defaultVoice && fits(defaultVoice)) return defaultVoice.voice_id;

  const locale = defaultVoice
    ? defaultVoice.locale.toLowerCase()
    : (unknown ? '' : language.toLowerCase());
  const exact = pool.find(
    (voice) => voice.locale.toLowerCase() === locale && fits(voice),
  );
  if (exact) return exact.voice_id;

  const loose = pool.find(
    (voice) => voice.locale.split('-')[0].toLowerCase() === prefix && fits(voice),
  );
  if (loose) return loose.voice_id;

  const any = state.voices.find(
    (voice) => voice.locale.split('-')[0].toLowerCase() === prefix && fits(voice),
  );
  if (any) return any.voice_id;

  const anywhere = pool.find(fits) || state.voices.find(fits);
  return anywhere ? anywhere.voice_id : '';
}

async function handleShareCode() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get('s');
  if (!code) return false;
  try {
    const cursor = await api.resolveShortCode(code);
    await openBook(cursor.book_id);
    if (cursor.chapter_id && cursor.chapter_id !== (state.chapter && state.chapter.chapter_id)) {
      await loadChapter(cursor.chapter_id, cursor.sentence_id);
    } else if (cursor.sentence_id) {
      moveCursor(cursor.sentence_id);
      reader.jumpTo(cursor.sentence_id, { smooth: false });
    }
    window.history.replaceState({}, '', window.location.pathname);
    return true;
  } catch (error) {
    toast('短码已失效');
    return false;
  }
}

async function start() {
  applySettings();
  try {
    const meta = await fetch('/api/v1/meta').then((response) => response.json());
    state.defaultVoice = meta.default_voice || '';
    state.featuredVoices = meta.featured_voices || [];
    state.defaultVoices = meta.default_voices || {};
  } catch (error) {
    state.defaultVoice = '';
  }
  await loadVoices();
  await library.refresh();
  const shared = await handleShareCode();
  if (shared) return;
  // 接着上次读的那本：位置在服务器上，不该因为刷新丢掉。
  const lastId = state.lastBookId();
  if (!lastId) return;
  try {
    await openBook(lastId);
  } catch (error) {
    state.rememberBook('');
  }
}

start();
