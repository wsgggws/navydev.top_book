/* 书架：卡片网格 */

import { api } from '../api.js';
import { state } from '../state.js';
import { el } from '../util.js';

/** 这本书在本浏览器里读到百分之多少。 */
function localPercent(book) {
  const prefs = state.bookPrefs[book.book_id];
  return (prefs && prefs.position && prefs.position.percent) || 0;
}

function languageGroup(book) {
  const family = (book.language || '').split('-')[0].toLowerCase();
  if (family === 'en') return 'en';
  if (family === 'zh') return 'zh';
  return 'other';
}

function lastOpened(book) {
  const value = state.bookPrefs[book.book_id]?.lastOpened;
  return Number.isFinite(value) ? value : 0;
}

function compareBooks(left, right) {
  const opened = lastOpened(right) - lastOpened(left);
  if (opened) return opened;
  return (left.title || '').localeCompare(right.title || '', 'zh-CN');
}

export class LibraryView {
  constructor(root, { onOpen }) {
    this.root = root;
    this.onOpen = onOpen;
    this.grid = root.querySelector('#book-grid');
    this.empty = root.querySelector('#library-empty');
  }

  async refresh() {
    this.grid.replaceChildren(el('p', { class: 'is-loading', text: '加载中…' }));
    try {
      const books = await api.listBooks();
      state.books = books;
      this.render(books);
    } catch (error) {
      this.grid.replaceChildren(el('p', { class: 'is-loading', text: error.message }));
    }
  }

  render(books) {
    this.grid.replaceChildren();
    this.empty.hidden = books.length > 0;
    const groups = [
      ['en', '英文'],
      ['zh', '中文'],
      ['other', '其他'],
    ];
    for (const [key, label] of groups) {
      const items = books.filter((book) => languageGroup(book) === key).sort(compareBooks);
      if (!items.length) continue;
      this.grid.append(el('section', { class: 'book-section' }, [
        el('h2', { class: 'book-section-title', text: label }),
        el('div', { class: 'grid' }, items.map((book) => this.card(book))),
      ]));
    }
  }

  card(book) {
    const cover = book.cover_url
      ? el('img', { src: book.cover_url, alt: '', loading: 'lazy' })
      : el('span', { class: 'placeholder', text: (book.title || '?').trim().charAt(0) });

    return el('button', {
      class: 'card',
      title: book.title,
      onclick: () => this.onOpen(book),
    }, [
      el('div', { class: 'card-cover' }, [cover]),
      el('span', { class: 'card-title', text: book.title }),
      el('span', { class: 'card-author', text: book.author || '未知作者' }),
      el('span', { class: 'card-progress' }, [
        el('span', {
          class: 'card-progress-fill',
          // 进度是这一端自己记的，不和服务端也不和终端共享。
          style: `width:${Math.round(localPercent(book) * 100)}%`,
        }),
      ]),
    ]);
  }

}
