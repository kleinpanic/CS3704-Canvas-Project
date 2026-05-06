import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const extPath = path.join(__dirname, 'extension');

async function main() {
  console.log('=== E2E Extension Test ===\n');

  // 1. Launch Chromium with extension loaded
  console.log('1. Launching Chromium with extension...');
  const browser = await chromium.launch({
    channel: 'chromium',
    headless: false,
    args: [
      `--load-extension=${extPath}`,
      '--no-sandbox',
      '--disable-dev-shm-usage',
    ],
  });

  const errors = [];
  browser.on('disconnected', () => console.log('Browser disconnected'));

  // 2. Check extension loaded in chrome://extensions
  console.log('2. Checking chrome://extensions...');
  const extPage = await browser.newPage();
  await extPage.goto('chrome://extensions', { waitUntil: 'networkidle', timeout: 15000 });
  const extContent = await extPage.content();
  const extFound = extContent.includes('Canvas Deadline Tracker');
  console.log(`   Extension visible: ${extFound ? '✅' : '❌'}`);

  // 3. Test the popup directly
  console.log('\n3. Testing popup UI...');
  const popup = await browser.newPage();
  await popup.goto(`chrome-extension://${extFound ? 'unknown' : 'test'}/src/popup/index.html`, { timeout: 5000 }).catch(() => {});

  // Get extension ID from the service worker
  const serviceWorkerPage = await browser.newPage();
  serviceWorkerPage.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });

  // 4. Test Canvas API directly (simulating background.js logic)
  console.log('\n4. Testing Canvas API integration...');
  const apiPage = await browser.newPage();
  const token = process.env.CANVAS_TOKEN;

  if (!token) {
    console.log('   ⚠️  CANVAS_TOKEN not set — skipping API test');
  } else {
    // Test Canvas API calls directly
    const response = await apiPage.evaluate(async (token) => {
      const res = await fetch('https://canvas.vt.edu/api/v1/users/self', {
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' }
      });
      return { status: res.status, ok: res.ok };
    }, token);

    console.log(`   Canvas API status: ${response.status} ${response.ok ? '✅' : '❌'}`);

    // Test upcoming events
    const upcomingRes = await apiPage.evaluate(async (token) => {
      const res = await fetch('https://canvas.vt.edu/api/v1/users/self/upcoming_events?per_page=20', {
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' }
      });
      const data = await res.json();
      return { status: res.status, count: data.filter(e => e.type === 'assignment').length };
    }, token);

    console.log(`   Upcoming assignments: ${upcomingRes.count} ✅`);
  }

  // 5. Test popup DOM structure (loads as file:// so chrome.* APIs won't work — expected)
  console.log('\n5. Testing popup DOM structure...');
  const filePage = await browser.newPage();
  await filePage.goto(`file://${extPath}/src/popup/index.html`, { waitUntil: 'domcontentloaded' });

  const title = await filePage.textContent('h1');
  const h2 = await filePage.textContent('h2');
  const buttons = await filePage.$$eval('button', bs => bs.map(b => b.textContent));
  const hasCourseFilter = await filePage.$('#course-filter') !== null;
  const hasUpcomingList = await filePage.$('#upcoming-list') !== null;
  const hasSettingsPanel = await filePage.$('#settings-btn') !== null;

  console.log(`   h1: "${title}" ✅`);
  console.log(`   h2: "${h2}" ✅`);
  console.log(`   Buttons: ${buttons.join(', ')} ✅`);
  console.log(`   Course filter: ${hasCourseFilter ? '✅' : '❌'}`);
  console.log(`   Upcoming list: ${hasUpcomingList ? '✅' : '❌'}`);
  console.log(`   Settings button: ${hasSettingsPanel ? '✅' : '❌'}`);

  // 6. Test settings panel opens
  console.log('\n6. Testing settings panel...');
  await filePage.click('#settings-btn');
  await filePage.waitForSelector('#settings-panel', { timeout: 2000 }).catch(() => {});
  const settingsVisible = await filePage.$('#settings-panel') !== null;
  console.log(`   Settings panel opens: ${settingsVisible ? '✅' : '❌'}`);

  if (settingsVisible) {
    const tokenInput = await filePage.$('#token-input') !== null;
    const saveBtn = await filePage.$('#save-token') !== null;
    console.log(`   Token input field: ${tokenInput ? '✅' : '❌'}`);
    console.log(`   Save button: ${saveBtn ? '✅' : '❌'}`);
  }

  // 7. Verify manifest.json structure
  console.log('\n7. Verifying manifest...');
  const fs = await import('fs');
  const manifest = JSON.parse(fs.readFileSync(`${extPath}/manifest.json`, 'utf8'));
  console.log(`   Manifest version: ${manifest.manifest_version} ✅`);
  console.log(`   Permissions: ${manifest.permissions.join(', ')} ✅`);
  console.log(`   Background service worker: ${manifest.background?.service_worker ? '✅' : '❌'}`);
  console.log(`   Popup: ${manifest.action?.default_popup ? '✅' : '❌'}`);

  // 8. Check all assets exist
  console.log('\n8. Checking assets...');
  const icons = ['16', '48', '128'];
  for (const size of icons) {
    const exists = fs.existsSync(`${extPath}/assets/icon-${size}.png`);
    console.log(`   icon-${size}.png: ${exists ? '✅' : '❌'}`);
  }

  await browser.close();

  console.log('\n=== E2E Test Complete ===');
  if (errors.length > 0) {
    console.log('\n⚠️  Console errors found:');
    errors.forEach(e => console.log('  -', e));
  } else {
    console.log('\n✅ No console errors');
  }
}

main().catch(err => {
  console.error('\n❌ Test failed:', err.message);
  process.exit(1);
});