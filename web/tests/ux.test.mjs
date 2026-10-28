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

async function openPage(t, width = 1280, height = 800, options = {}, catalog = [book]) {
  const context = await browser.newContext({ viewport: { width, height }, ...options });
  t.after(() => context.close());
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  t.after(() => assert.deepEqual(errors, [], 'no browser runtime errors'));
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1', '');
    let payload;
    if (path.endsWith('.mp3')) {
      // Real playable PCM media; no speech service or network involved.
      const samples = 8000 * 12;
      const wav = Buffer.alloc(44 + samples * 2);
      wav.write('RIFF'); wav.writeUInt32LE(36 + samples * 2, 4);
      wav.write('WAVEfmt ', 8); wav.writeUInt32LE(16, 16);
      wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
      wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28);
      wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34);
      wav.write('data', 36); wav.writeUInt32LE(samples * 2, 40);
      await route.fulfill({ body: wav, contentType: 'audio/wav' });
      return;
    }
    if (path.endsWith('.words')) {
      await route.fulfill({ json: { words: [], granularity: 'sentence', duration: 12 } });
      return;
    }
    if (path === '/meta') payload = { default_voice: 'test-voice', default_voices: { zh: 'test-voice', en: 'en-male' } };
    else if (path === '/tts/voices') payload = { voices: [
      { voice_id: 'test-voice', locale: 'zh-CN', name: '测试男声', gender: 'male' },
      { voice_id: 'test-female', locale: 'zh-CN', name: '测试女声', gender: 'female' },
      { voice_id: 'en-male', locale: 'en-US', name: 'American male', gender: 'male' },
      { voice_id: 'en-female', locale: 'en-US', name: 'American female', gender: 'female' },
      { voice_id: 'en-gb-female', locale: 'en-GB', name: 'British female', gender: 'female' },
    ] };
    else if (path === '/books') payload = catalog;
    else if (catalog.some(item => path === `/books/${item.book_id}`)) payload = { book: catalog.find(item => path === `/books/${item.book_id}`) };
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
  await expect(page.locator('.card')).toHaveCount(catalog.length);
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

for (const width of [375, 1280]) {
  test(`book preferences restore independently after switching and reload at ${width}px`, async t => {
    const page = await openPage(t, width, 800, { hasTouch: width === 375 },
      [book, { ...book, book_id: 'second-book', title: 'Second book', language: 'en-US' }]);
    await page.locator('.card').filter({ hasText: book.title }).click();
    await expect(page.locator('.sent')).toHaveCount(30);
    await page.locator('#btn-rate').click();
    await page.locator('#rate-menu button[data-rate="1.5"]').click();
    assert.equal(await page.evaluate(() => window.lector.player.audio.playbackRate), 1.5);
    await page.locator('#btn-settings').click();
    await page.locator('#s-gender button[data-gender="female"]').click();
    await expect(page.locator('#s-voice')).toHaveValue('test-female');
    await page.locator('#btn-settings-close').click();
    await page.locator('#btn-back').click();
    await page.locator('.card').filter({ hasText: 'Second book' }).click();
    await expect(page.locator('.sent')).toHaveCount(30);
    await expect(page.locator('#btn-rate')).toHaveText('1.00×');
    assert.equal(await page.evaluate(() => window.lector.player.audio.playbackRate), 1);
    await page.locator('#btn-settings').click();
    await expect(page.locator('#s-gender button[data-gender="male"]')).toHaveClass(/is-active/);
    await expect(page.locator('#s-voice')).toHaveValue('en-male');
    await page.locator('#s-gender button[data-gender="female"]').click();
    await page.locator('#s-voice').selectOption('en-gb-female');
    await page.locator('#btn-settings-close').click();
    await page.locator('#btn-back').click();
    await page.locator('.card').filter({ hasText: book.title }).click();
    await expect(page.locator('#btn-rate')).toHaveText('1.50×');
    await page.reload();
    await expect(page.locator('#btn-rate')).toHaveText('1.50×');
    await page.locator('#btn-settings').click();
    await expect(page.locator('#s-gender button[data-gender="female"]')).toHaveClass(/is-active/);
    await expect(page.locator('#s-voice')).toHaveValue('test-female');
    await page.locator('#btn-settings-close').click();
    await page.locator('#btn-back').click();
    await page.locator('.card').filter({ hasText: 'Second book' }).click();
    await page.locator('#btn-settings').click();
    await expect(page.locator('#s-voice')).toHaveValue('en-gb-female');
    await expect(page.locator('#s-rate')).toHaveValue('1');

  });
}

test('touch selection survives button blur before the synthesized click', async t => {
  const page = await openPage(t, 375, 800, { hasTouch: true });
  await openBook(page);
  await page.locator('#btn-rate').tap();
  // Safari may blur the focused menu item without focusing the tapped button.
  await page.locator('#rate-menu button[data-rate="1"]').evaluate(node => node.blur());
  await page.locator('#rate-menu button[data-rate="1.5"]').tap({ timeout: 1200 });
  await expect(page.locator('#btn-rate')).toHaveText('1.50×');
  assert.equal(await page.evaluate(() => window.lector.player.audio.playbackRate), 1.5);
});

for (const width of [375, 1280]) {
  test(`native audio keeps selected speed while playing, resuming and changing sentences at ${width}px`, async t => {
    const page = await openPage(t, width, 800, { hasTouch: width === 375 });
    await openBook(page);
    await page.locator('#btn-play').click();
    await page.waitForFunction(() => window.lector.player.playing && !window.lector.player.audio.paused);
    if (width === 375) await page.locator('#btn-rate').tap();
    else await page.locator('#btn-rate').click();
    await page.locator('#rate-menu button[data-rate="1.75"]').click();
    const checkRate = async () => {
      assert.deepEqual(await page.evaluate(() => {
        const a = window.lector.player.audio;
        return [a.playbackRate, a.defaultPlaybackRate, a.paused];
      }), [1.75, 1.75, false]);
    };
    await checkRate();
    const audioSeconds = await page.evaluate(() => window.lector.player.audio.currentTime);
    await page.waitForTimeout(400);
    const elapsed = await page.evaluate(() => window.lector.player.audio.currentTime);
    assert.ok(elapsed - audioSeconds > 0.5, 'native audio clock advances faster than wall time');
    await page.locator('#btn-play').click();
    await page.waitForFunction(() => !window.lector.player.playing);
    await page.locator('#btn-play').click();
    await page.waitForFunction(() => window.lector.player.playing && !window.lector.player.audio.paused);
    await checkRate();
    await page.locator('#btn-next').click();
    await page.waitForFunction(() => window.lector.player.sentenceId === 'c0.b1.s0' && window.lector.player.playing && !window.lector.player.audio.paused && window.lector.player.audio.readyState >= 2);
    await checkRate();
  });
}

test('existing per-book voice and speed restore without legacy global selection flags', async t => {
  const page = await openPage(t);
  await page.evaluate(() => {
    localStorage.setItem('lector.settings', JSON.stringify({ rate: 2, voiceGender: 'male', voiceTouched: false }));
    localStorage.setItem('lector.books', JSON.stringify({
      'test-book': { rate: 1.25, gender: 'female', voiceId: 'test-female' },
    }));
  });
  await page.reload();
  await openBook(page);
  await expect(page.locator('#btn-rate')).toHaveText('1.25×');
  await page.locator('#btn-settings').click();
  await expect(page.locator('#s-voice')).toHaveValue('test-female');
  await expect(page.locator('#s-gender button[data-gender="female"]')).toHaveClass(/is-active/);
});

test('changing gender during playback fetches matching media and word timings instead of reusing old voice', async t => {
  const page = await openPage(t, 375, 800, { hasTouch: true });
  const media = [];
  page.on('request', request => {
    if (/\/audio\/c0\.b0\.s0\.(mp3|words)/.test(request.url())) media.push(new URL(request.url()));
  });
  await openBook(page);
  await page.locator('#btn-play').click();
  await page.waitForFunction(() => window.lector.player.playing && !window.lector.player.audio.paused);
  const originalSrc = await page.evaluate(() => window.lector.player.audio.src);
  await page.locator('#btn-settings').click();
  await page.locator('#s-gender button[data-gender="female"]').click();
  await expect(page.locator('#s-voice')).toHaveValue('test-female');
  await page.waitForFunction(old => window.lector.player.audio.src !== old && !window.lector.player.audio.paused,
    originalSrc);
  for (const ext of ['.mp3', '.words']) {
    assert.ok(media.some(url => url.pathname.endsWith(ext) && url.searchParams.get('voice_id') === 'test-female'),
      `${ext} requested with the selected female voice`);
  }
});

test('QingShan theme persists across shelf, reader and reload and participates in cycling', async t => {
  for (const width of [320, 1280]) {
    const page = await openPage(t, width);
    await page.locator('#btn-settings').click();
    const choice = page.locator('#s-theme [data-theme="qingshan"]');
    await choice.click();
    await expect(choice).toHaveClass('is-active');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'qingshan');
    assert.equal(await page.locator('html').evaluate(el => getComputedStyle(el).getPropertyValue('--bg').trim()), '#1D3229');
    assert.equal(await choice.evaluate(el => {
      const rect = el.getBoundingClientRect();
      return rect.left >= 0 && rect.right <= innerWidth;
    }), true, 'theme choice fits the settings drawer');
    await page.keyboard.press('Escape');
    await openBook(page);
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'qingshan');
    await page.reload();
    await expect(page.locator('.sent')).toHaveCount(30);
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'qingshan');
    await page.locator('#btn-back').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'qingshan');
    await page.locator('#btn-theme').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'huangpao');
    await page.locator('#btn-theme').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'paper');
    await page.locator('#btn-theme').click();
    await page.locator('#btn-theme').click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'night');
    await page.keyboard.press('m');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'qingshan');
  }
});

test('TOC sections sharing one EPUB file show the selected title and section time', async t => {
  const page = await openPage(t);
  const titles = ['出版说明', '第一回', '第二回'];
  const sections = {
    ...chapter, title: titles[0],
    blocks: titles.flatMap((title, index) => [
      { type: 'h1', id: `c0.b${index * 2}`, anchor: index ? `section-${index}` : null, anchors: index ? [`section-${index}`] : [],
        sentences: [{ id: `c0.b${index * 2}.s0`, text: title }] },
      { type: 'p', id: `c0.b${index * 2 + 1}`,
        sentences: [{ id: `c0.b${index * 2 + 1}.s0`, text: `${title}的正文。` }] },
    ]),
  };
  await page.route('**/books/test-book/toc', route => route.fulfill({ json: {
    toc: titles.map((title, index) => ({ id: `t${index}`, title, chapter_id: 'c0',
      anchor: index ? `section-${index}` : null, children: [] })),
  } }));
  await page.route('**/books/test-book/chapters/c0', route => route.fulfill({ json: { chapter: sections } }));
  await page.route('**/chapters/c0/timeline', route => route.fulfill({ json: {
    sentences: sections.blocks.map((block, index) => ({ sentence_id: block.sentences[0].id,
      start: index * 10, end: index * 10 + 10 })),
  } }));
  await page.locator('.card').click();
  await expect(page.locator('.sent')).toHaveCount(5);
  await page.locator('#btn-menu').click();
  await page.getByRole('button', { name: '第一回', exact: true }).click();
  await expect(page.locator('#player-chapter')).toHaveText('第一回');
  await expect(page.locator('#player-time')).toHaveText('00:00 / 00:20');
  await page.locator('#btn-menu').click();
  await page.getByRole('button', { name: '第二回', exact: true }).click();
  await expect(page.locator('#player-chapter')).toHaveText('第二回');
  await expect(page.locator('#player-time')).toHaveText('00:00 / 00:20');
  await page.reload();
  await expect(page.locator('#player-chapter')).toHaveText('第二回');
  await expect(page.locator('#player-time')).toHaveText('00:00 / 00:20');
  await page.keyboard.press('[');
  await expect(page.locator('#player-chapter')).toHaveText('第一回');
  await expect(page.locator('#player-time')).toHaveText('00:00 / 00:20');
  await page.keyboard.press('[');
  await expect(page.locator('#player-chapter')).toHaveText('出版说明');
  await expect(page.locator('#player-time')).toHaveText('00:00 / 00:10');
});

test('new chapter selection stops old audio and stale requests cannot overwrite it', async t => {
  const page = await openPage(t);
  let releaseOld;
  const oldResponse = new Promise(resolve => { releaseOld = resolve; });
  t.after(releaseOld);
  const makeChapter = (id, title) => ({ ...chapter, chapter_id: id, title,
    blocks: [{ id: `${id}.b0`, type: 'p', sentences: [{ id: `${id}.b0.s0`, text: title }] }],
  });
  await page.route('**/books/test-book/toc', route => route.fulfill({ json: { toc: [
    { id: 't0', title: chapter.title, chapter_id: 'c0', children: [] },
    { id: 't1', title: '慢章节', chapter_id: 'c1', children: [] },
    { id: 't2', title: '最新章节', chapter_id: 'c2', children: [] },
  ] } }));
  await page.route('**/chapters/c0', route => route.fulfill({ json: { chapter: { ...chapter, sentence_count: 30 } } }));
  await page.route('**/chapters/c1', async route => {
    await oldResponse;
    await route.fulfill({ json: { chapter: makeChapter('c1', '慢章节') } });
  });
  await page.route('**/chapters/c2', route => route.fulfill({ json: { chapter: makeChapter('c2', '最新章节') } }));
  await openBook(page);
  await page.locator('#btn-play').click();
  await page.waitForFunction(() => window.lector.player.playing);
  await page.locator('#btn-menu').click();
  await page.getByRole('button', { name: '慢章节', exact: true }).click();
  await page.locator('#btn-menu').click();
  await page.getByRole('button', { name: '最新章节', exact: true }).click();
  await expect(page.locator('#player-chapter')).toHaveText('最新章节');
  const stale = page.waitForResponse(response => response.url().endsWith('/chapters/c1'));
  releaseOld();
  await stale;
  await page.waitForTimeout(100);
  await expect(page.locator('#player-chapter')).toHaveText('最新章节');
  assert.equal(await page.evaluate(() => window.lector.player.playing), false);
  await expect(page).toHaveURL(/\/test-book\/c2$/);
});

test('HuangPao theme persists and gender only offers male and female, migrating old any preferences', async t => {
  const page = await openPage(t, 375);
  await page.evaluate(() => localStorage.setItem('lector.books', JSON.stringify({
    'test-book': { gender: 'any', voiceId: 'test-female' },
  })));
  await page.reload();
  await openBook(page);
  await page.locator('#btn-settings').click();
  assert.deepEqual(await page.locator('#s-gender button').evaluateAll(buttons => buttons.map(button => button.dataset.gender)), ['female', 'male']);
  await expect(page.locator('#s-gender [data-gender="male"]')).toHaveClass('is-active');
  await expect(page.locator('#s-voice')).toHaveValue('test-voice');
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('lector.books'))['test-book'].gender), 'male');
  await page.locator('#s-theme [data-theme="huangpao"]').click();
  await page.keyboard.press('Escape');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'huangpao');
  assert.equal(await page.locator('html').evaluate(el => getComputedStyle(el).getPropertyValue('--bg').trim()), '#cdb06a');
  await page.locator('#btn-settings').click();
  await page.locator('#s-gender [data-gender="female"]').click();
  await expect(page.locator('#s-voice')).toHaveValue('test-female');
  await page.keyboard.press('Escape');
  await page.reload();
  await page.locator('#btn-settings').click();
  await expect(page.locator('#s-gender [data-gender="female"]')).toHaveClass('is-active');
  await expect(page.locator('#s-voice')).toHaveValue('test-female');
});
