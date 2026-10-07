/** Cloudflare Free scheduler: all Dhan/Firebase/strategy work stays in Python. */
export function inMarketWindow(timestamp) {
  const ist = new Date(timestamp + 330 * 60_000);
  const day = ist.getUTCDay();
  const minute = ist.getUTCHours() * 60 + ist.getUTCMinutes();
  return day >= 1 && day <= 5 && minute >= 555 && minute <= 930;
}

export async function triggerPaperCycle(event, env, dependencies = {}) {
  const clock = dependencies.clock || Date.now;
  const request = dependencies.fetch || fetch;
  const sleep = dependencies.sleep || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  if (!inMarketWindow(event.scheduledTime)) return;
  const age = clock() - event.scheduledTime;
  if (age > 45_000 || age < -10_000) throw new Error('Stale scheduled event');
  if (!env.PAPER_SCHEDULER_TOKEN) throw new Error('Scheduler secret missing');
  const url = new URL(env.API_BASE_URL);
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) {
    throw new Error('API_BASE_URL must be an HTTPS backend base URL');
  }
  url.pathname = url.pathname.replace(/\/$/, '') + '/algos/run-paper-cycle';
  await sleep(Math.max(0, event.scheduledTime + 5_000 - clock()));
  const response = await request(url.toString(), {
    method: 'POST', redirect: 'manual', signal: AbortSignal.timeout(55_000),
    headers: { 'X-Paper-Scheduler-Token': env.PAPER_SCHEDULER_TOKEN,
               'X-Scheduled-At': new Date(event.scheduledTime).toISOString() },
  });
  await response.body?.cancel();
  // No automatic retries: the backend persists each claimed minute and position.
  if (!response.ok && response.status !== 409) {
    console.error(JSON.stringify({ event: 'paper_cycle_failed', http_status: response.status, scheduled_at: event.scheduledTime }));
    throw new Error(`Paper backend HTTP ${response.status}`);
  }
  console.log(JSON.stringify({ event: response.status === 409 ? 'paper_cycle_busy' : 'paper_cycle_ok', scheduled_at: event.scheduledTime }));
}

export default {
  async scheduled(event, env) {
    await triggerPaperCycle(event, env);
  },
  async fetch() {
    // Public requests never evaluate strategies.
    return Response.json({ service: 'tradebud-paper-scheduler', execution: 'paper_only' });
  },
};
