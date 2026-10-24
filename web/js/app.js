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
  rateMenu: $('#rate-menu'),
  btnVoice: $('#btn-voice'),
  btnPlayerClose: $('#btn-player-close'),
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
settings.gender.addEventListener('click', async (event) => {
  const button = event.target.closest('button[data-gender]');
  if (!button) return;
  state.setSetting('voiceGender', button.dataset.gender);
  // 换了性别，之前挑的音色就不作数了，让它按语言与性别重新挑。
  state.setSetting('voiceId', '');
  state.setSetting('voiceTouched', false);
  if (state.book) {
    state.setPref(state.book.book_id, 'gender', button.dataset.gender);
    state.setPref(state.book.book_id, 'voiceId', '');
  }
  applySettings();
  // 等音色列表刷新完再记：这时才知道挑中了哪一个。
  await loadVoices();
  rememberVoiceChoice();
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
  if (state.book) state.setPref(state.book.book_id, 'rate', state.settings.rate);
  applySettings();
});
settings.gap.addEventListener('input', () => {
  state.setSetting('gap', Number(settings.gap.value));
  applySettings();
});
settings.voice.addEventListener('change', () => {
  state.setSetting('voiceId', settings.voice.value);
  state.setSetting('voiceTouched', true);
  if (state.book) state.setPref(state.book.book_id, 'voiceId', settings.voice.value);
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

    // 这本书自己的音色与倍速：换到别的书再切回来时还在。
    const prefs = state.prefsFor(bookId);
    if (prefs.gender) state.settings.voiceGender = prefs.gender;
    if (typeof prefs.rate === 'number') state.settings.rate = prefs.rate;
    player.setRate(state.settings.rate);
    const family = languageFamily(state.book.language);
    const saved = state.voices.find((voice) => voice.voice_id === prefs.voiceId);
    const savedFits = saved
      && (!family || saved.locale.split('-')[0].toLowerCase() === family);
    // 记住的音色得是这本书这个语言的；不是就按语言与性别重新挑（空着让
    // loadVoices 按语言挑，列表与选中项才对得上）。
    state.settings.voiceId = savedFits ? saved.voice_id : '';
    await loadVoices();
    rememberVoiceChoice();
    const progress = payload.progress;
    // 服务器上没有进度就用本地记的（换了设备或服务端还没写进去时）。
    const local = state.prefsFor(bookId).position;
    const target = progress && progress.cursor
      ? progress.cursor
      : (local ? { chapter_id: local.chapter_id, sentence_id: local.sentence_id, word_index: local.word_index } : null);
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
  // 本地也记一份：换设备、服务端暂时连不上时不至于从头开始。
  if (state.book) {
    state.setPref(state.book.book_id, 'position', {
      chapter_id: cursor.chapter_id,
      sentence_id: cursor.sentence_id,
      word_index: cursor.word_index,
    });
  }
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
  // 只高亮，不滚动：文字停在哪由人决定，声音走到哪就高亮哪。
  reader.setCurrent(sentenceId);
  reader.locked = true;
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
dom.btnPlayerClose.addEventListener('click', () => {
  player.stop();
  dom.player.hidden = true;
  if (state.cursor) reader.clearWords(state.cursor.sentence_id);
});
/* 倍速：点一下弹出菜单，而不是一轮轮地转 */
const RATE_STEPS = [0.75, 1, 1.25, 1.5, 1.75, 2];

function openRateMenu() {
  const menu = dom.rateMenu;
  for (const button of menu.querySelectorAll('button')) {
    const value = Number(button.dataset.rate);
    button.classList.toggle('is-active', Math.abs(value - state.settings.rate) < 0.01);
  }
  menu.hidden = false;
  dom.btnRate.setAttribute('aria-expanded', 'true');
}

function closeRateMenu() {
  dom.rateMenu.hidden = true;
  dom.btnRate.setAttribute('aria-expanded', 'false');
}

dom.btnRate.addEventListener('click', (event) => {
  event.stopPropagation();
  if (dom.rateMenu.hidden) openRateMenu();
  else closeRateMenu();
});

dom.rateMenu.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-rate]');
  if (!button) return;
  event.stopPropagation();
  const value = Number(button.dataset.rate);
  state.setSetting('rate', value);
  player.setRate(value);
  // 倍速也是这本书自己的：换书再切回来还是这个速度。
  if (state.book) state.setPref(state.book.book_id, 'rate', value);
  applySettings();
  closeRateMenu();
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
    if (!dom.rateMenu.hidden) { closeRateMenu(); return; }
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

/** 把当前挑中的音色记到这本书名下。 */
function rememberVoiceChoice() {
  if (!state.book || !state.settings.voiceId) return;
  state.setPref(state.book.book_id, 'voiceId', state.settings.voiceId);
}

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
  // 没有同语言的就退回全部，总比给不出声音强。
  return same.length ? same : pool;
}

async function loadVoices() {
  try {
    const payload = await api.voices();
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
    const options = shown.length ? shown : state.voices;
    if (wanted && options.some((voice) => voice.voice_id === wanted)) {
      settings.voice.value = wanted;
    } else if (options.length) {
      settings.voice.value = options[0].voice_id;
    }
    state.settings.voiceId = settings.voice.value;
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
  const wanted = gender && gender !== 'any' ? gender : null;
  // 只在这本书的语言范围里挑。
  const pool = voicesFor(language);
  const fits = (voice) => !wanted || voice.gender === wanted;
  const family = languageFamily(language)
    || (state.defaultVoice || 'zh-CN').split('-')[0].toLowerCase();

  // 这门语言的默认音色；英文的默认是美式，所以女声也留在美式里挑。
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
    const meta = await fetch(`${window.lectorBase || ''}/api/v1/meta`)
      .then((response) => response.json());
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

// 调试用：控制台里能摸到当前状态与播放器。
window.lector = { state, player, reader };

start();
