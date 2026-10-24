/* 书架：卡片网格 */

import { api } from '../api.js';
import { state } from '../state.js';
import { el } from '../util.js';

export class LibraryView {
  constructor(root, { onOpen, onToast }) {
    this.root = root;
    this.onOpen = onOpen;
    this.onToast = onToast;
    this.grid = root.querySelector('#book-grid');
    this.empty = root.querySelector('#library-empty');
    this.dropzone = root.querySelector('#dropzone');
    this.fileInput = root.querySelector('#file-input');
    this.importButton = root.querySelector('#btn-import');

    this.importButton.addEventListener('click', () => this.fileInput.click());
    this.fileInput.addEventListener('change', () => {
      const file = this.fileInput.files && this.fileInput.files[0];
      if (file) this.upload(file);
      this.fileInput.value = '';
    });

    let depth = 0;
    window.addEventListener('dragenter', (event) => {
      event.preventDefault();
      depth += 1;
      this.dropzone.classList.add('is-dragging');
    });
    window.addEventListener('dragover', (event) => event.preventDefault());
    window.addEventListener('dragleave', () => {
      depth = Math.max(0, depth - 1);
      if (depth === 0) this.dropzone.classList.remove('is-dragging');
    });
    window.addEventListener('drop', (event) => {
      event.preventDefault();
      depth = 0;
      this.dropzone.classList.remove('is-dragging');
      const file = event.dataTransfer && event.dataTransfer.files[0];
      if (file) this.upload(file);
    });
  }

  async upload(file) {
    if (!/\.epub$/i.test(file.name)) {
      this.onToast('只支持 EPUB 文件');
      return;
    }
    this.importButton.disabled = true;
    this.importButton.textContent = '上传中…';
    try {
      const payload = await api.uploadBook(file);
      this.onToast(payload.duplicate ? '这本书已经在书架上了' : '已加入书架');
      await this.refresh();
    } catch (error) {
      this.onToast(error.message || '上传失败');
    } finally {
      this.importButton.disabled = false;
      this.importButton.textContent = '导入 EPUB';
    }
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

    const coverBox = el('div', { class: 'card-cover' }, [cover]);
    coverBox.append(el('button', {
      class: 'card-delete',
      title: '删除',
      'aria-label': `删除 ${book.title}`,
      text: '×',
      onclick: (event) => {
        event.stopPropagation();
        this.remove(book);
      },
    }));

    return el('button', {
      class: 'card',
      title: book.title,
      onclick: () => this.onOpen(book),
    }, [
      coverBox,
      el('span', { class: 'card-title', text: book.title }),
      el('span', { class: 'card-author', text: book.author || '未知作者' }),
      el('span', { class: 'card-progress' }, [
        el('span', { class: 'card-progress-fill', style: `width:${Math.round((book.progress || 0) * 100)}%` }),
      ]),
    ]);
  }

  async remove(book) {
    if (!window.confirm(`删除《${book.title}》？`)) return;
    try {
      await api.deleteBook(book.book_id);
      this.onToast('已删除');
      await this.refresh();
    } catch (error) {
      this.onToast(error.message || '删除失败');
    }
  }
}
