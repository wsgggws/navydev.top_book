/* Pure helpers — no DOM, no state. */

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === 'dataset') {
      Object.assign(node.dataset, value);
    } else {
      node.setAttribute(key, value === true ? '' : String(value));
    }
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function debounce(fn, wait) {
  let timer = null;
  const wrapped = (...args) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...args);
    }, wait);
  };
  wrapped.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  wrapped.flush = (...args) => {
    if (timer) clearTimeout(timer);
    timer = null;
    fn(...args);
  };
  return wrapped;
}

export function formatTime(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  const hours = Math.floor(minutes / 60);
  if (hours > 0) {
    return `${hours}:${String(minutes % 60).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

/** Format a duration in Chinese, omitting zero-valued leading units. */
export function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  const parts = [];
  if (hours > 0) parts.push(`${hours}小时`);
  if (minutes > 0) parts.push(`${minutes}分钟`);
  if (rest > 0 || parts.length === 0) parts.push(`${rest}秒`);
  return parts.join('');
}

/** Estimate narration duration from the chapter text. */
export function estimatedSentenceSeconds(sentence) {
  if (!sentence) return 0;
  let cjk = 0;
  let latin = 0;
  for (const [start, end] of splitWords(sentence.text || '')) {
    const token = sentence.text.slice(start, end);
    if (/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u.test(token)) {
      cjk += 1;
    } else {
      latin += 1;
    }
  }
  return cjk * 0.24 + latin * 0.33;
}

/**
 * Chapter playback metrics.
 *
 * Synthesised sentences use their measured audio duration. Everything else is
 * estimated from text, so the total covers the whole chapter before all audio
 * has been generated.
 */
export function chapterTimeMetrics(
  sentences,
  timeline,
  { currentId = null, playerSentenceId = null, playerPosition = 0 } = {},
) {
  const measured = new Map(
    timeline.map((entry) => [
      entry.sentence_id,
      Math.max(0, entry.end - entry.start),
    ]),
  );
  let elapsed = 0;
  let total = 0;
  let foundCurrent = !currentId;
  for (const sentence of sentences) {
    const duration = measured.has(sentence.id)
      ? measured.get(sentence.id)
      : estimatedSentenceSeconds(sentence);
    total += duration;
    if (sentence.id === currentId) {
      foundCurrent = true;
      if (playerSentenceId === sentence.id) {
        elapsed += clamp(playerPosition, 0, duration);
      }
      continue;
    }
    if (!foundCurrent) elapsed += duration;
  }
  return { elapsed: Math.min(elapsed, total), total };
}

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[char]);
}

/** Split a sentence into word spans using the same rules as the parser. */
export function splitWords(text) {
  const spans = [];
  let index = 0;
  const isCjk = (ch) => {
    const code = ch.codePointAt(0);
    return (code >= 0x3400 && code <= 0x4dbf)
      || (code >= 0x4e00 && code <= 0x9fff)
      || (code >= 0xf900 && code <= 0xfaff)
      || (code >= 0x3040 && code <= 0x30ff)
      || (code >= 0xac00 && code <= 0xd7af);
  };
  while (index < text.length) {
    const ch = text[index];
    if (isCjk(ch)) {
      spans.push([index, index + 1]);
      index += 1;
      continue;
    }
    if (/[\p{L}\p{N}]/u.test(ch)) {
      let end = index;
      while (end < text.length && /[\p{L}\p{N}]/u.test(text[end]) && !isCjk(text[end])) end += 1;
      spans.push([index, end]);
      index = end;
      continue;
    }
    index += 1;
  }
  return spans;
}

/**
 * The index of the word being spoken at `time`.
 *
 * Words are separated by short silences.  Inside such a gap the previous
 * word is still the one being read, so it keeps the highlight instead of
 * going dark for a moment.
 */
export function wordAt(words, time) {
  if (!words.length) return -1;
  let candidate = -1;
  for (let i = 0; i < words.length; i += 1) {
    if (time < words[i].start) break;
    candidate = i;
    if (time < words[i].end) return i;
  }
  return candidate;
}

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

/** Scroll `node` into the reading band (30% of the viewport height). */
export function scrollIntoBand(node, container, smooth = true) {
  if (!node) return;
  const containerRect = container.getBoundingClientRect();
  const nodeRect = node.getBoundingClientRect();
  const target = container.scrollTop
    + (nodeRect.top - containerRect.top)
    - (container.clientHeight * 0.3)
    + (nodeRect.height / 2);
  container.scrollTo({ top: Math.max(0, target), behavior: smooth ? 'smooth' : 'auto' });
}

export function isTypingTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
}
