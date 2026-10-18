// Renders every <section class="s" id="..."> of a carousel HTML file to PNG at 2x (1080 -> 2160 px).
// Usage: NODE_PATH=$(npm root -g) node render.js <carousel.html> <out-dir>
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
(async () => {
  const [file, outDir] = process.argv.slice(2).map((p) => path.resolve(p));
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
  const page = await browser.newPage({ viewport: { width: 1200, height: 1200 }, deviceScaleFactor: 2 });
  await page.goto('file://' + file);
  await page.evaluate(() => document.fonts.ready);
  const ids = await page.$$eval('section.s', (els) => els.map((e) => e.id));
  const base = path.basename(file, '.html');
  for (const [i, id] of ids.entries()) {
    await page.locator('#' + id).screenshot({ path: path.join(outDir, `${base}_${String(i + 1).padStart(2, '0')}.png`) });
  }
  await browser.close();
})();
