import {chromium} from '/Users/kavishanwee/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1.5,reducedMotion:"reduce"});await page.goto('http://127.0.0.1:5174',{waitUntil:'domcontentloaded'});await page.waitForTimeout(7000);
await page.locator('.intro').screenshot({path:'tmp/presentation/assets/hero.png'});
await page.locator('.workspace').screenshot({path:'tmp/presentation/assets/explorer.png'});
await page.locator('.calendar-panel').screenshot({path:'tmp/presentation/assets/calendar.png'});
await page.locator('.comparison-lab').scrollIntoViewIfNeeded();await page.waitForTimeout(2500);await page.locator('.comparison-lab').screenshot({path:'tmp/presentation/assets/comparison.png'});
await page.locator('.investigation-desk').scrollIntoViewIfNeeded();await page.waitForTimeout(500);await page.locator('.investigation-desk').screenshot({path:'tmp/presentation/assets/investigation.png'});
await browser.close();
