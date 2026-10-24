/* 书架：卡片网格 */

import { api } from '../api.js';
import { state } from '../state.js';
import { el } from '../util.js';

/** 这本书在本浏览器里读到百分之多少。 */
function localPercent(book) {
  const prefs = state.bookPrefs[book.book_id];
  return (prefs && prefs.position && prefs.position.percent) || 0;
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
    for (const book of books) {
      this.grid.append(this.card(book));
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
