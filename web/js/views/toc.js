/* 目录抽屉与搜索 */

import { api } from '../api.js';
import { state } from '../state.js';
import { el, escapeHtml } from '../util.js';

export class TocDrawer {
  constructor(root, { onNavigate, onToast }) {
    this.root = root;
    this.onNavigate = onNavigate;
    this.onToast = onToast;
    this.list = root.querySelector('#toc');
    this.results = root.querySelector('#search-results');
    this.searchInput = root.querySelector('#search-input');
    this.searchTimer = null;

    this.searchInput.addEventListener('input', () => {
      clearTimeout(this.searchTimer);
      const query = this.searchInput.value.trim();
      if (!query) {
        this.results.hidden = true;
        this.list.hidden = false;
        return;
      }
      this.searchTimer = setTimeout(() => this.search(query), 260);
    });

    this.searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        this.searchInput.value = '';
        this.results.hidden = true;
        this.list.hidden = false;
        this.searchInput.blur();
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        const query = this.searchInput.value.trim();
        if (query) this.search(query);
      }
    });
  }

  setToc(nodes) {
    state.toc = nodes || [];
    this.list.replaceChildren();
    for (const node of state.toc) this.list.append(this.node(node));
    this.list.hidden = false;
    this.results.hidden = true;
  }

  node(item, depth = 0) {
    const children = el('div', { class: 'toc-children' });
    const row = el('button', {
      class: `toc-item toc-depth-${Math.min(depth, 3)}`,
      title: item.title,
      onclick: () => this.onNavigate(item),
    }, [el('span', { class: 'toc-title', text: item.title })]);

    const wrapper = el('div', { class: 'toc-node' }, [row]);
    if (item.children && item.children.length) {
      for (const child of item.children) children.append(this.node(child, depth + 1));
      wrapper.append(children);
    }
    return wrapper;
  }

  async search(query) {
    if (!state.book) return;
    try {
      const payload = await api.search(state.book.book_id, query, 50);
      this.list.hidden = true;
      this.results.hidden = false;
      this.results.replaceChildren();
      if (!payload.results.length) {
        this.results.append(el('p', { class: 'is-loading', text: '没有找到' }));
        return;
      }
      this.results.append(el('p', {
        class: 'search-count',
        text: `找到 ${payload.total} 处`,
      }));
      for (const result of payload.results) {
        this.results.append(el('button', {
          class: 'search-item',
          onclick: () => this.onNavigate({
            chapter_id: result.chapter_id,
            anchor: null,
            sentence_id: result.sentence_id,
          }),
        }, [
          el('span', { class: 'search-chapter', text: result.chapter_title }),
          el('span', { class: 'search-snippet', html: escapeHtml(result.snippet).replace(/&lt;em&gt;/g, '<em>').replace(/&lt;\/em&gt;/g, '</em>') }),
        ]));
      }
    } catch (error) {
      this.onToast(error.message || '搜索失败');
    }
  }
}
