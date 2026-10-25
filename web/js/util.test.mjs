import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('./util.js', import.meta.url), 'utf8');
const util = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

test('formatDuration uses human-readable Chinese units', () => {
  assert.equal(util.formatDuration(0), '0秒');
  assert.equal(util.formatDuration(59), '59秒');
  assert.equal(util.formatDuration(60), '1分钟');
  assert.equal(util.formatDuration(61), '1分钟1秒');
  assert.equal(util.formatDuration(666), '11分钟6秒');
  assert.equal(util.formatDuration(3600), '1小时');
  assert.equal(util.formatDuration(3601), '1小时1秒');
  assert.equal(util.formatDuration(3661), '1小时1分钟1秒');
  assert.equal(util.formatDuration(7325), '2小时2分钟5秒');
});

test('formatDuration clamps invalid and fractional values', () => {
  assert.equal(util.formatDuration(-1), '0秒');
  assert.equal(util.formatDuration(Number.NaN), '0秒');
  assert.equal(util.formatDuration(59.9), '59秒');
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
