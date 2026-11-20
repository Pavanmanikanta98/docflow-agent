// Records the DocFlow walkthrough against the real local stack (real model).
// Usage: node record_demo.js <out_dir> <samples_dir>
// Writes <out_dir>/raw.webm, <out_dir>/events.json (caption + speed-up marks)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const OUT = process.argv[2], SAMPLES = process.argv[3];
const BASE = 'http://localhost:3100';
const SESSION = 'ses_demovideo0000a3';

const INIT = `
(() => {
  const css = (e, s) => Object.assign(e.style, s);
  window.__demo = {
    caption(text) {
      let e = document.getElementById('demo-cap');
      if (!text) { if (e) e.remove(); return; }
      if (!e) {
        e = document.createElement('div'); e.id = 'demo-cap';
        css(e, { position: 'fixed', left: '50%', bottom: '38px', transform: 'translateX(-50%)', maxWidth: '1060px',
          padding: '14px 28px', background: 'rgba(15,23,42,.93)', color: '#fff', textAlign: 'center',
          font: '600 27px/1.32 Inter, system-ui, sans-serif', borderRadius: '14px', zIndex: 2147483646,
          boxShadow: '0 10px 34px rgba(0,0,0,.4)', pointerEvents: 'none' });
        document.documentElement.appendChild(e);
      }
      e.textContent = text;
    },
    card(lines, mono) {
      let e = document.getElementById('demo-card');
      if (!lines) { if (e) e.remove(); return; }
      if (!e) {
        e = document.createElement('div'); e.id = 'demo-card';
        css(e, { position: 'fixed', inset: '0', background: 'linear-gradient(135deg,#0f172a,#1e293b 60%,#312e81)', color: '#fff',
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '22px',
          padding: '60px 90px', textAlign: 'center', zIndex: 2147483647, font: '700 46px/1.25 Inter, system-ui, sans-serif' });
        document.documentElement.appendChild(e);
      }
      e.replaceChildren();
      lines.forEach((l, i) => {
        const d = document.createElement(mono ? 'pre' : 'div');
        d.textContent = l.t;
        css(d, { margin: 0, font: l.f || (i === 0 ? '700 50px/1.25 Inter, system-ui, sans-serif' : '500 32px/1.4 Inter, system-ui, sans-serif'),
          color: l.c || (i === 0 ? '#fff' : '#cbd5e1'), whiteSpace: 'pre-wrap', textAlign: l.align || 'center', maxWidth: '1060px' });
        e.appendChild(d);
      });
    },
  };
  // a visible cursor, because headless video does not draw one
  window.addEventListener('DOMContentLoaded', () => {
    const c = document.createElement('div');
    css(c, { position: 'fixed', width: '22px', height: '22px', borderRadius: '50%', background: 'rgba(245,158,11,.85)',
      border: '2px solid #fff', boxShadow: '0 2px 8px rgba(0,0,0,.4)', zIndex: 2147483645, pointerEvents: 'none',
      left: '-50px', top: '-50px', transform: 'translate(-50%,-50%)', transition: 'left .03s linear, top .03s linear' });
    document.documentElement.appendChild(c);
    window.addEventListener('mousemove', (ev) => { c.style.left = ev.clientX + 'px'; c.style.top = ev.clientY + 'px'; }, true);
  });
  localStorage.setItem('docflow_session_id', '${SESSION}');
})();
`;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 }, acceptDownloads: true,
    recordVideo: { dir: OUT, size: { width: 1280, height: 720 } },
  });
  await ctx.addInitScript(INIT);
  const page = await ctx.newPage();
  const t0 = Date.now();
  const events = [];
  const now = () => Date.now() - t0;
  const say = async (text) => { events.push({ t: now(), type: 'caption', text }); await page.evaluate((x) => window.__demo.caption(x), text); };
  const clear = async () => { events.push({ t: now(), type: 'caption', text: '' }); await page.evaluate(() => window.__demo.caption('')); };
  const card = async (lines, mono) => { events.push({ t: now(), type: 'card', text: lines.map((l) => l.t).join(' / ') }); await page.evaluate(([l, m]) => window.__demo.card(l, m), [lines, !!mono]); };
  const mark = (name) => events.push({ t: now(), type: 'mark', name });
  const wait = (ms) => page.waitForTimeout(ms);
  const glide = async (locator) => {
    await locator.scrollIntoViewIfNeeded();
    const b = await locator.boundingBox();
    await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 28 });
    await wait(350);
    await locator.click();
  };
  const waitStatus = async (re, label) => {
    await page.waitForFunction((src) => new RegExp(src, 'i').test(document.body.innerText), re, { timeout: 180000, polling: 500 });
  };

  // ---- 1. hook: problem first, no logo, no greeting
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await card([
    { t: 'This invoice says the total is $1,439.20.' },
    { t: 'The line items add up to $1,339.20.' },
    { t: 'Would your system notice?', c: '#fbbf24', f: '700 40px/1.3 Inter, system-ui, sans-serif' },
  ]);
  await wait(4800);
  await page.evaluate(() => window.__demo.card(null));
  events.push({ t: now(), type: 'card', text: '' });

  // ---- 2. upload the wrong-total PDF
  await say('DocFlow: upload the invoice.');
  await wait(1800);
  await page.locator('input[type=file]').first().setInputFiles(path.join(SAMPLES, 'invoice_wrong_total.jpg'));
  await page.waitForURL('**/documents', { timeout: 20000 });
  await say('OCR, a queue, a worker and a model: all in the background.');
  await wait(2200);
  const alreadyDone = await page.evaluate(() => /AWAITING REVIEW/i.test(document.body.innerText));
  if (!alreadyDone) await say('Real model, real wait: sped up');
  mark('fast-start');
  await waitStatus('AWAITING REVIEW');
  mark('fast-end');
  await wait(600);
  await say('Held for review. Not silently approved.');
  await wait(2600);

  // ---- 3. review screen
  await glide(page.getByRole('button', { name: /review/i }).first());
  await page.waitForLoadState('networkidle');
  await wait(1500);
  await say('The reason is written on the screen.');
  await wait(3600);
  await say('While it waits for review, the original file stays beside the values.');
  await wait(4200);

  // ---- 4. reject with a reason
  await say('Reject it, with a reason.');
  await glide(page.getByRole('button', { name: /reject/i }).first());
  await wait(900);
  await page.locator('.ant-modal textarea').click();
  await page.keyboard.type('Total does not match the line items', { delay: 55 });
  await wait(700);
  await page.locator('.ant-modal-footer button').last().click();
  await page.waitForURL('**/documents', { timeout: 20000 });
  await wait(1200);
  await say('Rejected, and the list says so.');
  await wait(3000);

  // ---- 5. a scanned photo
  await say('Now a regular PDF from another vendor.');
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await wait(2000);
  await page.locator('input[type=file]').first().setInputFiles(path.join(SAMPLES, 'invoice_ok.pdf'));
  await page.waitForURL('**/documents', { timeout: 20000 });
  await say('The same checks run on it.');
  await wait(2200);
  await say('Real model, real wait: sped up');
  mark('fast2-start');
  await page.waitForFunction(() => {
    const row = Array.from(document.querySelectorAll('tr')).find((r) => /invoice_ok/.test(r.innerText));
    return row && /COMPLETED|AWAITING REVIEW|FAILED/i.test(row.innerText);
  }, null, { timeout: 180000, polling: 500 });
  mark('fast2-end');
  await wait(500);
  await say('The numbers add up, so it completes without review.');
  await wait(3200);

  // ---- 6. open it and export
  await glide(page.locator('tr', { hasText: 'invoice_ok' }).getByRole('button', { name: /review/i }));
  await page.waitForLoadState('networkidle');
  await wait(1800);
  await say('Completed documents export as JSON or CSV.');
  await wait(1500);
  const dlPromise = page.waitForEvent('download', { timeout: 15000 });
  await glide(page.getByRole('button', { name: /json/i }).first());
  const dl = await dlPromise;
  const jsonPath = path.join(OUT, 'export.json');
  await dl.saveAs(jsonPath);
  await wait(1200);
  const exported = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
  const keep = ['vendor_name', 'invoice_number', 'invoice_date', 'due_date', 'subtotal', 'tax_amount', 'total_amount', 'currency'];
  const snippet = '{\n' + keep.filter((k) => k in exported).map((k) => `  "${k}": ${JSON.stringify(exported[k])}`).join(',\n') + '\n}';
  await clear();
  await card([
    { t: 'export.json  (from the PDF)', f: '600 30px/1.3 Inter, system-ui, sans-serif', c: '#94a3b8' },
    { t: snippet, f: '500 34px/1.5 "DejaVu Sans Mono", monospace', c: '#a7f3d0', align: 'left' },
  ], false);
  await wait(5200);
  await page.evaluate(() => window.__demo.card(null));
  events.push({ t: now(), type: 'card', text: '' });

  // ---- 7. the guided tour
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await wait(1500);
  await say('A guided tour walks through every screen.');
  await wait(1500);
  await glide(page.getByRole('button', { name: /start tour/i }).first());
  await wait(2600);
  for (let i = 0; i < 2; i++) {
    await page.locator('.reactour__popover button[aria-label="Go to next step"]').first().click();
    await wait(2300);
  }
  await page.keyboard.press('Escape');
  await clear();

  // ---- 8. closing card: only numbers that exist in a committed file
  await card([
    { t: '262 of 274 field checks correct' },
    { t: '32 hand-labelled documents (20 clean, 12 adversarial)\ngpt-oss-20b · one run · 18 Sep 2026', f: '500 30px/1.4 Inter, system-ui, sans-serif' },
    { t: 'Open source: github.com/Pavanmanikanta98/docflow-agent\nLive demo: docflow-agent.vercel.app', c: '#fbbf24', f: '600 30px/1.5 Inter, system-ui, sans-serif' },
  ]);
  await wait(6500);

  const videoPath = await page.video().path();
  events.push({ t: now(), type: 'end' });
  await ctx.close();
  await browser.close();
  fs.renameSync(videoPath, path.join(OUT, 'raw.webm'));
  fs.writeFileSync(path.join(OUT, 'events.json'), JSON.stringify(events, null, 2));
  console.log('recorded', events.filter((e) => e.type === 'caption' && e.text).length, 'captions;', (now() / 1000).toFixed(1), 's raw');
})().catch((e) => { console.error('FAILED:', e.message.split('\n').slice(0, 3).join(' | ')); process.exit(1); });
