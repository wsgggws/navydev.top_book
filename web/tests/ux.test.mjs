// Run with Node's test runner and Playwright available through NODE_PATH.
// BROWSER_CHANNEL defaults to the locally installed Chrome; no app dependencies.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { after, before, test } from 'node:test';

const { chromium, expect } = createRequire(import.meta.url)('playwright/test');
const webRoot = new URL('../', import.meta.url);
const book = {
  book_id: 'test-book', title: '用于检查手机与桌面布局的很长很长的电子书标题',
  author: '测试作者', language: 'zh-CN', chapter_count: 1, open_count: 1,
};
const chapter = {
  chapter_id: 'c0', index: 0, title: '第一章：用于检查控件的章节',
  blocks: Array.from({ length: 30 }, (_, index) => ({
    id: `c0.b${index}`, type: 'p',
    sentences: [{ id: `c0.b${index}.s0`, text: '这是一段供阅读和播放控件测试使用的文字。'.repeat(3) }],
  })),
};
let server;
let browser;
let origin;

before(async () => {
  server = createServer(async (req, res) => {
    const path = new URL(req.url, 'http://localhost').pathname;
    const asset = path.match(/\.(?:js|css|png)$/) ? path.slice(1) : 'index.html';
    try {
      let body = await readFile(new URL(asset, webRoot));
      if (asset === 'index.html') body = body.toString().replace('<head>', '<head><base href="/">');
      const type = asset.endsWith('.js') ? 'text/javascript' : asset.endsWith('.css')
        ? 'text/css' : asset.endsWith('.png') ? 'image/png' : 'text/html';
      res.writeHead(200, { 'Content-Type': type });
      res.end(body);
    } catch {
      res.writeHead(404).end();
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'chrome' });
});

after(async () => {
  await browser?.close();
  await new Promise(resolve => server?.close(resolve));
});

async function openPage(t, width = 1280, height = 800, options = {}) {
  const context = await browser.newContext({ viewport: { width, height }, ...options });
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  t.after(() => assert.deepEqual(errors, [], 'no browser runtime errors'));
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
    let payload;
    if (path === '/meta') payload = { default_voice: 'test-voice', default_voices: { zh: 'test-voice' } };
    else if (path === '/tts/voices') payload = { voices: [{ voice_id: 'test-voice', locale: 'zh-CN', name: '测试音色', gender: 'male' }] };
    else if (path === '/books') payload = [book];
    else if (path === '/books/test-book') payload = { book };
    else if (path.endsWith('/toc')) payload = { toc: [{ id: 'toc0', title: chapter.title, chapter_id: 'c0', children: [] }] };
    else if (path.endsWith('/chapters/c0')) payload = { chapter };
    else if (path.endsWith('/timeline')) payload = { sentences: [] };
    else if (path.endsWith('/open')) payload = { open_count: 2 };
    else if (path.endsWith('/warm')) payload = { ready: 0, failed: 0 };
    else if (path.endsWith('/percent')) payload = { percent: 0 };
    else if (path.endsWith('/search')) payload = { results: [], total: 0 };
    else throw new Error(`Unexpected API request: ${path}`);
    await route.fulfill({ json: payload });
  });
  await page.goto(origin);
  await expect(page.locator('.card')).toHaveCount(1);
  return page;
}

async function openBook(page) {
  await page.locator('.card').click();
  await expect(page.locator('.sent')).toHaveCount(30);
  await expect(page.locator('#player')).toBeVisible();
}

async function assertHitTarget(page, selector) {
  assert.equal(await page.locator(selector).evaluate(node => {
    const rect = node.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return node === hit || node.contains(hit);
  }), true, `${selector} must be visible and receive pointer input`);
}

test('browser title stays navy\'s ebook on shelf, reader, reload and back', async t => {
  const page = await openPage(t);
  await expect(page).toHaveTitle("navy's ebook");
  await openBook(page);
  await expect(page).toHaveTitle("navy's ebook");
  await page.reload();
  await expect(page.locator('.sent')).toHaveCount(30);
  await expect(page).toHaveTitle("navy's ebook");
  await page.locator('#btn-back').click();
  await expect(page.locator('#library')).toBeVisible();
  await expect(page).toHaveTitle("navy's ebook");
});

for (const width of [320, 375, 768, 1920]) {
  test(`long titles and playback controls fit at ${width}px`, async t => {
    const page = await openPage(t, width);
    await openBook(page);
    for (const selector of ['#btn-menu', '#btn-back', '#btn-theme', '#btn-font', '#btn-settings',
      '#btn-prev', '#btn-play', '#btn-next', '#btn-rate', '#btn-player-toggle']) {
      const box = await page.locator(selector).boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= width, `${selector} fits viewport: ${JSON.stringify(box)}`);
      await assertHitTarget(page, selector);
      if (width < 640) assert.ok(box.width >= 44 && box.height >= 44, `${selector} has a 44px touch target`);
    }
    await page.locator('#btn-rate').click();
    await assertHitTarget(page, '#rate-menu button[data-rate="2"]');
    await page.locator('#rate-menu button[data-rate="2"]').click({ timeout: 1500 });
    await expect(page.locator('#btn-rate')).toHaveText('2.00×');
    await page.locator('#btn-rate').click();
    await page.locator('#btn-player-toggle').click();
    await expect(page.locator('#rate-menu')).toBeHidden();
    await expect(page.locator('#player-panel')).toHaveAttribute('inert', '');
    await page.locator('#btn-player-toggle').click();
    await expect(page.locator('#btn-rate')).toHaveText('2.00×');
  });
}

test('rate menu supports Space, arrows, Home/End, selection and Escape', async t => {
  const page = await openPage(t);
  await openBook(page);
  await page.locator('#btn-rate').focus();
  await page.keyboard.press('Space');
  await expect(page.locator('#rate-menu')).toBeVisible();
  await expect(page.locator('#rate-menu button[data-rate="1"]')).toBeFocused();
  await page.keyboard.press('ArrowDown');
  await expect(page.locator('#rate-menu button[data-rate="1.25"]')).toBeFocused();
  await page.keyboard.press('End');
  await expect(page.locator('#rate-menu button[data-rate="2"]')).toBeFocused();
  await page.keyboard.press('Home');
  await expect(page.locator('#rate-menu button[data-rate="0.75"]')).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#btn-rate')).toHaveText('0.75×');
  await expect(page.locator('#btn-rate')).toBeFocused();
  await page.keyboard.press('ArrowUp');
  await expect(page.locator('#rate-menu')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.locator('#rate-menu')).toBeHidden();
  await expect(page.locator('#btn-rate')).toBeFocused();
  await expect(page.locator('#reader')).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page.locator('#rate-menu')).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.locator('#rate-menu')).toBeHidden();
  await page.locator('#btn-rate').click();
  await page.locator('#column').click({ position: { x: 20, y: 20 } });
  await expect(page.locator('#rate-menu')).toBeHidden();
});

for (const width of [375, 1280]) {
  test(`drawers contain focus and Escape restores trigger at ${width}px`, async t => {
    const page = await openPage(t, width);
    await openBook(page);
    await page.locator('#btn-settings').click();
    await expect(page.locator('#btn-settings')).toHaveAttribute('aria-expanded', 'true');
    await expect(page.locator('#btn-settings-close')).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(page.locator('#btn-export-progress')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.locator('#btn-settings-close')).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.locator('#drawer-settings')).toBeHidden();
    await expect(page.locator('#btn-settings')).toBeFocused();
    await expect(page.locator('#btn-settings')).toHaveAttribute('aria-expanded', 'false');
    await page.locator('#btn-menu').click();
    await expect(page.locator('#search-input')).toBeFocused();
    await page.locator('#search-input').fill('测试');
    await page.keyboard.press('Escape');
    await expect(page.locator('#drawer-toc')).toBeHidden();
    await expect(page.locator('#btn-menu')).toBeFocused();
    await expect(page.locator('#reader')).toBeVisible();
    assert.equal(await page.locator('#topbar').evaluate(node => node.inert), false);
    await page.locator('#btn-settings').click();
    assert.equal(await page.locator('#topbar').evaluate(node => node.inert), true);
    assert.equal(await page.locator('.stage').evaluate(node => node.inert), true);
    const cursor = await page.evaluate(() => window.lector.state.cursor.sentence_id);
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('f');
    assert.equal(await page.evaluate(() => window.lector.state.cursor.sentence_id), cursor);
    await expect(page.locator('body')).not.toHaveClass(/immersive/);
    await page.keyboard.press('Escape');
    await page.keyboard.press('f');
    await expect(page.locator('body')).toHaveClass(/immersive/);
    await page.keyboard.press('s');
    await expect(page.locator('#drawer-settings')).toBeVisible();
    await expect(page.locator('#btn-settings-close')).toBeFocused();
    await page.keyboard.press('s');
    await expect(page.locator('#drawer-settings')).toBeHidden();
  });
}

test('rapid drawer switching leaves one usable modal', async t => {
  const page = await openPage(t);
  await openBook(page);
  await page.locator('#btn-settings').click();
  await page.keyboard.press('t');
  await expect(page.locator('#search-input')).toBeFocused();
  await expect(page.locator('#drawer-settings')).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(page.locator('#drawer-toc')).toBeHidden();
  await expect(page.locator('#btn-settings')).toBeFocused();
});

test('short landscape viewport keeps settings scrollable and hour times fit on mobile', async t => {
  const page = await openPage(t, 320, 480, { reducedMotion: 'reduce', hasTouch: true });
  await openBook(page);
  await page.locator('#player-time').evaluate(node => { node.textContent = '123:45:56 / 999:59:59'; });
  for (const selector of ['#player-time', '#btn-rate', '#btn-player-toggle']) {
    const box = await page.locator(selector).boundingBox();
    assert.ok(box.x >= 0 && box.x + box.width <= 320, `${selector} fits with long durations`);
    await assertHitTarget(page, selector);
  }
  await page.setViewportSize({ width: 844, height: 390 });
  await page.locator('#btn-settings').click();
  await page.locator('#btn-export-progress').scrollIntoViewIfNeeded();
  await assertHitTarget(page, '#btn-export-progress');
  await assertHitTarget(page, '#btn-settings-close');
  await page.locator('#btn-settings-close').click();
  await expect(page.locator('#drawer-settings')).toBeHidden();
});
