import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('./util.js', import.meta.url), 'utf8');
const util = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('formatTime uses mm:ss and hh:mm:ss', () => {
  assert.equal(util.formatTime(0), '00:00');
  assert.equal(util.formatTime(59), '00:59');
  assert.equal(util.formatTime(60), '01:00');
  assert.equal(util.formatTime(61), '01:01');
  assert.equal(util.formatTime(666), '11:06');
  assert.equal(util.formatTime(3600), '01:00:00');
  assert.equal(util.formatTime(3601), '01:00:01');
  assert.equal(util.formatTime(3661), '01:01:01');
  assert.equal(util.formatTime(7325), '02:02:05');
});

test('formatTime clamps invalid and fractional values', () => {
  assert.equal(util.formatTime(-1), '00:00');
  assert.equal(util.formatTime(Number.NaN), '00:00');
  assert.equal(util.formatTime(59.9), '00:59');
});

test('chapterTimeMetrics covers the whole chapter and cumulative play time', () => {
  const sentences = [
    { id: 's0', text: '第一句。' },
    { id: 's1', text: '第二句。' },
    { id: 's2', text: '第三句。' },
  ];
  const timeline = [
    { sentence_id: 's0', start: 0, end: 2 },
    { sentence_id: 's1', start: 2, end: 5 },
  ];
  const metrics = util.chapterTimeMetrics(sentences, timeline, {
    currentId: 's1',
    playerSentenceId: 's1',
    playerPosition: 1.5,
  });

  assert.equal(metrics.elapsed, 3.5);
  assert.ok(metrics.total > 5, 'unsynthesised sentences must contribute to total time');
});

test('chapterTimeMetrics starts at zero before a current sentence exists', () => {
  const metrics = util.chapterTimeMetrics(
    [{ id: 's0', text: '第一句。' }],
    [],
  );
  assert.equal(metrics.elapsed, 0);
  assert.ok(metrics.total > 0);
});

test('stale cursor from another chapter does not mark the new chapter fully read', () => {
  const metrics = util.chapterTimeMetrics([{ id: 'c2.b0.s0', text: '新章节。' }], [], { currentId: 'c1.b0.s0' });
  assert.equal(metrics.elapsed, 0);
  assert.ok(metrics.total > 0);
});

test('chapterSections honours nested TOC anchors and preserves preface and trailing sections', () => {
  const chapter = { chapter_id: 'c4', title: '出版说明', blocks: [
    { id: 'c4.b0', sentences: [] },
    { id: 'c4.b1', anchor: 'one', sentences: [] },
    { id: 'c4.b2', anchors: ['two'], sentences: [] },
    { id: 'c4.b3', sentences: [] },
  ] };
  const sections = util.chapterSections(chapter, [{ chapter_id: 'c4', title: '出版说明', children: [
    { chapter_id: 'c4', title: '第一回', anchor: 'one' },
    { chapter_id: 'c4', title: '失效链接', anchor: 'missing' },
    { chapter_id: 'c4', title: '第二回', anchor: 'two' },
  ] }]);
  assert.deepEqual(sections, [
    { title: '出版说明', start: 0, end: 1 },
    { title: '第一回', start: 1, end: 2 },
    { title: '第二回', start: 2, end: 4 },
  ]);
});
