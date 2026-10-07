import { test } from 'node:test';
import assert from 'node:assert/strict';
import { inMarketWindow, triggerPaperCycle } from './index.mjs';

const at = Date.parse('2026-10-07T04:45:00Z');
const env = { API_BASE_URL: 'https://api.example.com', PAPER_SCHEDULER_TOKEN: 'test-secret' };
test('IST window covers open/close and excludes weekend', () => {
  assert.equal(inMarketWindow(Date.parse('2026-10-07T03:44:00Z')), false);
  assert.equal(inMarketWindow(Date.parse('2026-10-07T03:45:00Z')), true);
  assert.equal(inMarketWindow(Date.parse('2026-10-07T10:00:00Z')), true);
  assert.equal(inMarketWindow(Date.parse('2026-10-07T10:01:00Z')), false);
  assert.equal(inMarketWindow(Date.parse('2026-10-10T04:45:00Z')), false);
});
test('one protected request, five-second publication delay, no redirects', async () => {
  const calls = [];
  await triggerPaperCycle({ scheduledTime: at }, env, {
    clock: () => at, sleep: async ms => calls.push(ms),
    fetch: async (url, options) => { calls.push([url, options]); return new Response('{}'); },
  });
  assert.equal(calls[0], 5000);
  assert.equal(calls[1][0], 'https://api.example.com/algos/run-paper-cycle');
  assert.equal(calls[1][1].headers['X-Paper-Scheduler-Token'], 'test-secret');
  assert.equal(calls[1][1].redirect, 'manual');
  assert.equal(calls.length, 2);
});
test('closed session makes no request; delayed events and failures are explicit', async () => {
  await triggerPaperCycle({ scheduledTime: Date.parse('2026-10-10T04:45:00Z') }, {}, { fetch: () => assert.fail('closed market called API') });
  await assert.rejects(triggerPaperCycle({ scheduledTime: at }, env, { clock: () => at + 90_000 }), /Stale/);
  await assert.rejects(triggerPaperCycle({ scheduledTime: at }, { ...env, API_BASE_URL: 'http://localhost' }, { clock: () => at }), /HTTPS/);
  let count = 0;
  await assert.rejects(triggerPaperCycle({ scheduledTime: at }, env, { clock: () => at + 5_000,
    sleep: async () => {}, fetch: async () => { count++; return new Response('', { status: 503 }); } }), /HTTP 503/);
  assert.equal(count, 1);
});
