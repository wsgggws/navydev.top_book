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

/** The index of the word that contains `time`, or -1. */
export function wordAt(words, time) {
  for (let i = 0; i < words.length; i += 1) {
    if (time >= words[i].start && time < words[i].end) return i;
  }
  if (words.length && time >= words[words.length - 1].end) return words.length - 1;
  return -1;
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
