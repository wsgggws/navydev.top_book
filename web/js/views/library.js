/* 书架：卡片网格 */

import { api } from '../api.js';
import { state } from '../state.js';
import { el } from '../util.js';

const PAGE_SIZE = 12;

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

function normalizeSearch(value) {
  return String(value || '')
    .normalize('NFKC')
    .toLocaleLowerCase()
    .replace(/[\s\p{P}\p{S}]+/gu, '');
}

function fuzzyTitleMatch(title, query) {
  const haystack = normalizeSearch(title);
  const needle = Array.from(normalizeSearch(query));
  if (!needle.length) return true;
  if (haystack.includes(needle.join(''))) return true;

  let matched = 0;
  for (const char of haystack) {
    if (char === needle[matched]) matched += 1;
    if (matched === needle.length) return true;
  }
  return false;
}

export class LibraryView {
  constructor(root, { onOpen }) {
    this.root = root;
    this.onOpen = onOpen;
    this.grid = root.querySelector('#book-grid');
    this.empty = root.querySelector('#library-empty');
    this.emptyTitle = root.querySelector('#library-empty-title');
    this.pagination = root.querySelector('#library-pagination');
    this.search = root.querySelector('#library-search-input');
    this.query = '';
    this.page = 1;
    this.books = [];

    this.search.addEventListener('input', () => {
      this.query = this.search.value;
      this.page = 1;
      this.render(this.books);
    });
  }

  async refresh() {
    this.empty.hidden = true;
    this.pagination.hidden = true;
    this.grid.replaceChildren(el('p', { class: 'is-loading', text: '加载中…' }));
    try {
      const books = await api.listBooks();
      state.books = books;
      this.books = books;
      this.render(books);
    } catch (error) {
      this.grid.replaceChildren(el('p', { class: 'is-loading', text: error.message }));
    }
  }

  render(books) {
    this.books = books;
    this.grid.replaceChildren();
    const groups = [
      ['en', '英文'],
      ['zh', '中文'],
      ['other', '其他'],
    ];
    const ordered = groups.flatMap(([key]) =>
      books
        .filter((book) => languageGroup(book) === key)
        .sort(compareBooks),
    );
    const matches = this.query.trim()
      ? ordered.filter((book) => fuzzyTitleMatch(book.title, this.query))
      : ordered;
    const totalPages = Math.max(1, Math.ceil(matches.length / PAGE_SIZE));
    this.page = Math.min(this.page, totalPages);
    const start = (this.page - 1) * PAGE_SIZE;
    const visible = matches.slice(start, start + PAGE_SIZE);

    this.empty.hidden = matches.length > 0;
    this.emptyTitle.textContent = this.query.trim()
      ? '没有找到匹配的图书'
      : '书架暂时没有书';

    for (const [key, label] of groups) {
      const items = visible.filter((book) => languageGroup(book) === key);
      if (!items.length) continue;
      this.grid.append(el('section', { class: 'book-section' }, [
        el('h2', { class: 'book-section-title', text: label }),
        el('div', { class: 'grid' }, items.map((book) => this.card(book))),
      ]));
    }
    this.renderPagination(totalPages, matches.length);
  }

  renderPagination(totalPages, totalBooks) {
    this.pagination.replaceChildren();
    this.pagination.hidden = totalPages <= 1;
    if (totalPages <= 1) return;

    const previous = el('button', {
      type: 'button',
      class: 'pagination-button',
      text: '上一页',
      disabled: this.page === 1,
      onclick: () => this.goToPage(this.page - 1),
    });
    const next = el('button', {
      type: 'button',
      class: 'pagination-button',
      text: '下一页',
      disabled: this.page === totalPages,
      onclick: () => this.goToPage(this.page + 1),
    });
    this.pagination.append(
      previous,
      el('span', {
        class: 'pagination-status',
        text: `第 ${this.page} / ${totalPages} 页 · 共 ${totalBooks} 本`,
      }),
      next,
    );
  }

  goToPage(page) {
    this.page = page;
    this.render(this.books);
    this.root.scrollTo({ top: 0, behavior: 'smooth' });
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
