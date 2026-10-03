const fs=require('node:fs');const path=require('node:path');
const {chromium}=require(process.env.HOURLINK_PLAYWRIGHT || '/Users/pomelo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1280,height:800},timezoneId:'Asia/Hong_Kong'});
 await context.request.post('http://127.0.0.1:8000/api/v1/auth/demo-login',{data:{username:'reviewer',case:'cash'}});
 await context.request.post('http://127.0.0.1:8000/api/v1/demo/reset',{data:{}});
 await context.request.post('http://127.0.0.1:8000/api/v1/auth/demo-login',{data:{username:'zao',case:'cash'}});
 // Record a fresh context with the prepared demo session.
 const state=await context.storageState();await context.close();
 const recording=await browser.newContext({viewport:{width:1280,height:800},timezoneId:'Asia/Hong_Kong',storageState:state,recordVideo:{dir:'artifacts/browser/video',size:{width:1280,height:800}}});
 const page=await recording.newPage();const started=Date.now();
 async function caption(title,text){await page.evaluate(({title,text})=>{let el=document.getElementById('record-caption');if(!el){el=document.createElement('div');el.id='record-caption';el.style.cssText='position:fixed;left:40px;right:40px;bottom:18px;padding:17px 22px;border-radius:10px;background:rgba(22,78,67,.95);color:white;z-index:9999;pointer-events:none;box-shadow:0 5px 20px #173a3420;line-height:1.6;font-family:-apple-system,PingFang TC,sans-serif';document.body.appendChild(el)}el.innerHTML='';const h=document.createElement('b');h.style.cssText='font-size:18px;display:block;margin-bottom:5px';h.textContent=title;const p=document.createElement('span');p.style.cssText='font-size:14px;color:#deebd8';p.textContent=text;el.append(h,p)}, {title,text})}
 async function until(seconds){const wait=seconds*1000-(Date.now()-started);if(wait>0)await page.waitForTimeout(wait)}
 async function role(name){await page.getByRole('button',{name:'切換演示身份'}).click();await page.locator('.account-menu').getByRole('button',{name}).click();await page.waitForTimeout(450)}
 await page.goto('http://127.0.0.1:8000');await page.getByRole('heading',{name:/你的能力/}).waitFor();
 await caption('Hourlink 時間有價','平臺分析相關能力與投入，讓非標準服務有清楚的交換約定。所有資料與資金均為演示。');await until(15);
 await page.getByRole('link',{name:/整理一份散亂/}).click();await page.getByRole('heading',{name:'誰適合這次需求？'}).waitFor();
 await caption('先選適合本單的人','平臺先檢查技能、時段與容量，再比較能力證據、預計工時和參考總價。');await page.locator('.candidate-card').first().scrollIntoViewIfNeeded();await until(32);
 await page.getByRole('button',{name:'查看評估依據'}).first().click();await caption('推薦有可核對的依據','同類履約、復核作品與測評進入評估。品質影響時薪，歷史耗時影響工時，不把交易次數當成能力。');await until(48);
 await page.getByRole('button',{name:'關閉',exact:true}).click();await page.getByRole('button',{name:'選擇並生成方案'}).first().click();await page.getByRole('button',{name:'建立雙方協議'}).waitFor();
 await caption('平臺先生成默認方案','時薪 HK$300 的服務者預計只需 30 分鐘，本單 HK$150。雙方仍可協商，參考價不是市場行情。');await until(64);
 await page.getByRole('button',{name:'建立雙方協議'}).click();await page.getByRole('button',{name:'我確認此版本協議'}).click();await role('知 林知行');await page.getByRole('button',{name:'我確認此版本協議'}).click();
 await caption('同一版本，雙方確認','第二次確認在同一事務中檢查需求鎖、雙方容量和可用時段。不能只靠前端宣告成單。');await until(80);
 await role('予 周予安');await page.getByRole('button',{name:'模擬預留'}).click();await role('知 林知行');await page.getByRole('button',{name:'提交交付',exact:true}).click();await page.getByRole('dialog').getByRole('textbox').fill('依驗收樣本完成第一階段工作表與修改說明。');await page.getByRole('dialog').getByRole('button',{name:'提交',exact:true}).click();
 await caption('先預留，再交付','資金僅爲模擬。提供者提交成果和時間明細，接收者驗收前，不計入已確認貢獻。');await until(99);
 await role('予 周予安');await page.getByRole('button',{name:'驗收並確認時間'}).click();await page.getByRole('dialog').getByRole('button',{name:'提交',exact:true}).click();await caption('驗收、資金釋放與階段推進一起完成','實際時間獨立保存，不會自動改寫已籤價格。重複點擊不重複記賬，刷新後狀態仍然保留。');await until(115);
 await page.getByRole('link',{name:'演示模式',exact:true}).click();await page.getByRole('button',{name:/時間互換/}).click();await page.getByRole('link',{name:'我的交換',exact:true}).click();await page.locator('.order-row').last().click();await page.getByRole('button',{name:'建立雙方協議'}).waitFor();await caption('不同能力的一小時，有不同的本單價值','表格輔導參考 HK$150／小時，英語交流 HK$100／小時。平臺建議 60 分鐘換 90 分鐘，按兩輪 30↔45 履約。');await until(133);
 await page.getByRole('link',{name:'演示模式',exact:true}).click();await page.getByRole('button',{name:/部分履約後退出/}).click();await page.getByRole('link',{name:'我的交換',exact:true}).click();await page.locator('.order-row').first().click();await page.getByRole('button',{name:'申請退出與結清'}).click();await page.getByRole('dialog').getByRole('textbox').fill('雙方同意取消尚未開始的第二階段服務。');await page.getByRole('dialog').getByRole('button',{name:'提交',exact:true}).click();await page.getByRole('button',{name:'建立結清方案'}).click();await page.getByRole('dialog').getByRole('textbox').fill('保留已驗收 HK$60，取消第二階段並退回原付款方 HK$90。');await page.getByRole('dialog').getByRole('button',{name:'提交',exact:true}).click();
 await caption('退出，不會抹掉已經付出的時間','本案例第一階段 HK$60 已釋放，第二階段 HK$90 仍預留。結清逐項列出原義務和資金，不自動清空。');await until(150);
 await page.getByRole('button',{name:'確認這份結清方案'}).click();await role('知 林知行');await page.getByRole('button',{name:'確認這份結清方案'}).click();await caption('雙方確認後，才執行結清','服務者保留已獲得的 HK$60，未開始階段退回 HK$90。時間互換退出則保留原回報服務，不把不同服務分鐘數相減。');await until(167);
 await page.getByRole('link',{name:'能力與時間',exact:true}).click();await caption('記錄貢獻，也保留平臺的邊界','分階段保護先履約者，同時增加驗收操作。核心流程不依賴 AI 或外網，平臺不承諾真實支付擔保或追回線下損失。');await until(180);
 const video=page.video();await page.close();await recording.close();await video.saveAs('artifacts/hourlink-demo.webm');await browser.close();
 console.log('Recorded 3-minute demo:',path.resolve('artifacts/hourlink-demo.webm'));
})().catch(e=>{console.error(e);process.exit(1)});
