// CI-only: connects to this run's isolated WebView2 debug endpoint. Never imports credentials.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

try {
  let browser;
  for (let attempt = 0; attempt < 40; attempt++) {
    try { browser = await chromium.connectOverCDP('http://127.0.0.1:9222'); break; }
    catch { await new Promise(resolve => setTimeout(resolve, 500)); }
  }
  if (!browser) throw new Error('Native WebView2 debug connection unavailable');
  let page;
  for (let attempt = 0; attempt < 40; attempt++) {
    page = browser.contexts().flatMap(context => context.pages()).find(p => /tauri\.localhost|tauri:\/\//.test(p.url()));
    if (page) break;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  if (!page) throw new Error('Installed application did not open its native frontend');
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await expect(page.getByRole('heading', {name: '3D Trading Floor', exact: true})).toBeVisible();
  await expect(page.getByText('LOCAL ENGINE CONNECTED', {exact: false})).toBeVisible();
  await expect(page.locator('canvas')).toBeVisible();
  const graphics = await page.locator('canvas').evaluate(canvas => {
    const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
    return {width:canvas.width,height:canvas.height,context:!!gl,lost:gl ? gl.isContextLost() : true};
  });
  if (!graphics.context || graphics.lost || graphics.width < 100 || graphics.height < 100) {
    throw new Error('Native WebGL canvas failed to initialize');
  }
  await mkdir('artifacts', {recursive:true});
  await page.screenshot({path:'artifacts/windows-office.png',fullPage:true});
  await page.getByRole('button',{name:'Live Trading',exact:false}).click();
  await expect(page.getByRole('heading',{name:'Link your personal account'})).toBeVisible();
  await expect(page.getByLabel('Coinbase key JSON export')).toBeEnabled();
  await expect(page.getByRole('button',{name:'Enable individually approved live orders'})).toBeDisabled();
  await page.screenshot({path:'artifacts/windows-account-link.png',fullPage:true});
  if (errors.length) throw new Error('Native frontend JavaScript errors: '+errors.join('; '));
  console.log('Installed native WebView, WebGL office, loopback engine and inactive account-link workflow passed. No credentials or live orders used.');
  // Do not send Browser.close to the embedded WebView. The PowerShell harness closes the app normally.
  process.exit(0);
} catch (error) {
  console.error('::error title=Native WebView smoke::' + String(error.message).replace(/%/g,'%25').replace(/\r?\n/g,'%0A'));
  console.error(error);
  process.exit(1);
}
