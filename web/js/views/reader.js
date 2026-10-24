/* 阅读列：渲染章节、维护游标线、跟随朗读 */

import { state } from '../state.js';
import { el, debounce, scrollIntoBand } from '../util.js';

const BLOCK_TAGS = {
  h1: 'h1', h2: 'h2', h3: 'h3', h4: 'h4', h5: 'h5', h6: 'h6',
  p: 'p', li: 'li', blockquote: 'blockquote', pre: 'pre',
};

export class ReaderView {
  constructor(root, { onCursorMove, onSentenceClick, onScrollEnd }) {
    this.root = root;
    this.scroll = root.querySelector('#reader-scroll');
    this.column = root.querySelector('#column');
    this.onCursorMove = onCursorMove;
    this.onSentenceClick = onSentenceClick;
    this.onScrollEnd = onScrollEnd;

    this.sentenceNodes = new Map();
    this.order = [];
    this.currentElement = null;
    this.follow = true;
    this.userScrolled = false;

    this.settle = debounce(() => this._syncFromScroll(), 150);
    this.scroll.addEventListener('scroll', () => {
      this.settle();
      if (this._programmaticScroll) return;
      this.userScrolled = true;
      this.follow = false;
      if (this.onScrollEnd) this.onScrollEnd(false);
    }, { passive: true });

    for (const type of ['wheel', 'touchmove']) {
      this.scroll.addEventListener(type, () => {
        this.userScrolled = true;
        this.follow = false;
        if (this.onScrollEnd) this.onScrollEnd(false);
      }, { passive: true });
    }
  }

  /** Render a chapter into the column. */
  render(chapter) {
    this.column.replaceChildren();
    this.sentenceNodes.clear();
    this.order = [];
    this.currentElement = null;

    this.column.append(el('h1', { class: 'chapter-title', text: chapter.title }));
    if (!chapter.blocks.length) {
      this.column.append(el('p', { class: 'chapter-empty', text: '本章没有文字内容。' }));
      return;
    }
    const blocks = this.withoutRepeatedTitle(chapter);
    for (let index = 0; index < blocks.length; index += 1) {
      const block = blocks[index];
      if (block.type === 'li') {
        // 列表项要放进同一个列表里，否则项目符号会跑到行外。
        const items = [block];
        while (index + 1 < blocks.length && blocks[index + 1].type === 'li') {
          index += 1;
          items.push(blocks[index]);
        }
        const list = el('ul', { class: 'blk-list' });
        for (const item of items) list.append(this.renderBlock(item));
        this.column.append(list);
        continue;
      }
      this.column.append(this.renderBlock(block));
    }
  }

  /** A heading that repeats the chapter title is shown only once. */
  withoutRepeatedTitle(chapter) {
    const blocks = chapter.blocks || [];
    const first = blocks[0];
    if (!first) return blocks;
    const isHeading = /^h[1-6]$/.test(first.type);
    if (!isHeading) return blocks;
    const text = (first.sentences || []).map((sentence) => sentence.text).join('').trim();
    if (text && text !== (chapter.title || '').trim()) return blocks;
    return blocks.slice(1);
  }

  renderBlock(block) {
    if (block.type === 'img') {
      const figure = el('figure', { class: 'blk blk-img' });
      if (block.src) {
        figure.append(el('img', { src: `/api/v1/books/${state.book.book_id}/media/${block.src}`, alt: block.alt || '' }));
      }
      return figure;
    }
    if (block.type === 'hr') return el('hr', { class: 'blk' });

    const tag = BLOCK_TAGS[block.type] || 'p';
    const node = el(tag, { class: 'blk', dataset: { bid: block.id } });
    for (const sentence of block.sentences) {
      const span = el('span', {
        class: 'sent',
        dataset: { sid: sentence.id },
        text: sentence.text,
      });
      span.addEventListener('click', (event) => {
        event.stopPropagation();
        if (this.onSentenceClick) this.onSentenceClick(sentence.id, event);
      });
      this.sentenceNodes.set(sentence.id, span);
      this.order.push(sentence.id);
      node.append(span);
    }
    return node;
  }

  elementFor(sentenceId) {
    return this.sentenceNodes.get(sentenceId) || null;
  }

  /** Move the cursor line. */
  setCurrent(sentenceId, { scroll = false } = {}) {
    if (this.currentElement) {
      this.currentElement.classList.remove('is-current', 'is-speaking');
    }
    const node = this.elementFor(sentenceId);
    this.currentElement = node;
    if (!node) return;
    node.classList.add('is-current');
    if (scroll) {
      this._programmaticScroll = true;
      scrollIntoBand(node, this.scroll);
      setTimeout(() => { this._programmaticScroll = false; }, 420);
      this.userScrolled = false;
      this.follow = true;
    }
  }

  /** Replace the text of a sentence with timed word spans. */
  setWords(sentenceId, words, granularity) {
    const node = this.elementFor(sentenceId);
    if (!node) return;
    const text = state.findSentence(sentenceId);
    const source = text ? text.text : node.textContent;
    node.replaceChildren();
    if (granularity !== 'word' || !words.length) {
      node.textContent = source;
      return;
    }
    let cursor = 0;
    for (const word of words) {
      const index = source.indexOf(word.text, cursor);
      if (index < 0) continue;
      if (index > cursor) {
        node.append(document.createTextNode(source.slice(cursor, index)));
      }
      const span = el('span', { class: 'w', text: word.text });
      span.dataset.start = word.start;
      span.dataset.end = word.end;
      node.append(span);
      cursor = index + word.text.length;
    }
    if (cursor < source.length) {
      node.append(document.createTextNode(source.slice(cursor)));
    }
  }

  /** Put the plain text back — used when playback stops. */
  clearWords(sentenceId) {
    const node = this.elementFor(sentenceId);
    if (!node) return;
    const sentence = state.findSentence(sentenceId);
    if (!sentence) return;
    node.replaceChildren(document.createTextNode(sentence.text));
  }

  /** Which sentence sits in the reading band right now. */
  sentenceInBand() {
    const band = this.scroll.scrollTop + this.scroll.clientHeight * 0.3;
    let found = null;
    for (const [sentenceId, node] of this.sentenceNodes) {
      const top = node.offsetTop;
      if (top <= band) found = sentenceId;
      else break;
    }
    if (!found && this.order.length) found = this.order[0];
    return found;
  }

  _syncFromScroll() {
    const sentenceId = this.sentenceInBand();
    if (!sentenceId) return;
    if (this.currentElement && this.currentElement.dataset.sid === sentenceId) return;
    if (this.onCursorMove) this.onCursorMove(sentenceId);
  }

  /** Scroll a sentence into the reading band and make it current. */
  jumpTo(sentenceId, { smooth = true } = {}) {
    const node = this.elementFor(sentenceId);
    if (!node) return;
    this._programmaticScroll = true;
    scrollIntoBand(node, this.scroll, smooth);
    setTimeout(() => { this._programmaticScroll = false; }, 420);
    this.userScrolled = false;
    this.follow = true;
    if (this.onCursorMove) this.onCursorMove(sentenceId, { scroll: false });
  }

  /** Find the block that carries an anchor and return its first sentence. */
  sentenceForAnchor(chapter, anchor) {
    if (!anchor) return null;
    for (const block of chapter.blocks) {
      const anchors = block.anchors || [];
      if (anchors.includes(anchor) && block.sentences.length) {
        return block.sentences[0].id;
      }
    }
    return null;
  }

  setFollow(value) {
    this.follow = value;
  }
}
