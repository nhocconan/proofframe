// Usage: node seek.mjs <baseUrl> <runId> <assertionId> <outPng>
// Clicks a check in the run view and asserts the target <video> currentTime lands inside the
// check's focus interval (from the API report the page renders). Exit 1 on failure.
import * as pw from 'playwright';
const chromium = pw[process.env.BROWSER || 'chromium'];
const [base, runId, aid, out] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 },
  ...(process.env.HTTP_USER ? { httpCredentials: { username: process.env.HTTP_USER, password: process.env.HTTP_PASS } } : {}) });
await page.goto(`${base}/runs/${runId}`, { waitUntil: 'networkidle' });
const video = page.getByTestId('target-video');
await video.waitFor();
await page.waitForFunction(() => {
  const v = document.querySelector('[data-testid="target-video"]'); return v && v.readyState >= 1;
}, null, { timeout: 30000 });
await page.getByTestId(`check-${aid}`).click();
await page.waitForFunction(() => {
  const v = document.querySelector('[data-testid="target-video"]'); return v && !v.seeking && v.currentTime > 0;
}, null, { timeout: 30000 });
const t = await video.evaluate(v => v.currentTime);
const focus = await page.evaluate(async ({ runId, aid }) => {
  const el = document.querySelector(`[data-testid="check-${aid}"]`);
  return { start: Number(el.dataset.focusStartMs), end: Number(el.dataset.focusEndMs) };
}, { runId, aid });
await page.screenshot({ path: out, fullPage: true });
const ok = t * 1000 >= focus.start - 50 && t * 1000 <= focus.end + 50;
console.log(JSON.stringify({ assertion: aid, currentTime_s: t, focus_ms: focus, inside: ok, screenshot: out }));
await browser.close();
process.exit(ok ? 0 : 1);
