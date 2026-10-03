const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { chromium } = require(
  process.env.HOURLINK_PLAYWRIGHT ||
    require("node:path").join(require("node:os").homedir(), ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"),
);
const base = process.env.HOURLINK_TEST_URL || "http://127.0.0.1:8003";
const dataDir = process.env.HOURLINK_TEST_DATA || "tmp/recording/data";
const out = "artifacts/browser/recording";
const report = {
  startedAt: new Date().toISOString(),
  base,
  scenarios: [],
  external: [],
  pageErrors: [],
};
fs.mkdirSync(out, { recursive: true });
fs.mkdirSync("tmp/closed-loop/snapshots", { recursive: true });
let browser, current;
async function api(c, p) {
  const r = await c.request.get(base + "/api/v1" + p);
  assert.equal(r.status(), 200, await r.text());
  return r.json();
}
async function action(p, suffix, click, status = 200, method = "POST") {
  const promise = p.waitForResponse(
    (r) =>
      r.url() === base + "/api/v1" + suffix && r.request().method() === method,
  );
  promise.catch(() => {});
  await click();
  const response = await promise;
  const value = await response.json();
  assert.equal(response.status(), status, JSON.stringify(value));
  await p.locator(".busy-line").waitFor({ state: "hidden" });
  current.steps.push({ method, path: suffix, status, code: value.code });
  return value;
}
async function role(p, user) {
  const me = await api(p.context(), "/me");
  if (me.user.id === user) return;
  const profile = (await api(p.context(), "/demo/users")).find(
    (x) => x.id === user,
  );
  await p.getByRole("button", { name: "切換演示身份" }).click();
  await action(p, "/auth/demo-login", () =>
    p
      .locator(".account-menu")
      .getByRole("button", { name: new RegExp(profile.name + "$") })
      .click(),
  );
  assert.equal((await api(p.context(), "/me")).user.id, user);
}
async function scenario(
  name,
  caseId,
  fn,
  viewport = { width: 1440, height: 1000 },
) {
  if (
    process.env.HOURLINK_SCENARIO &&
    !name.includes(process.env.HOURLINK_SCENARIO)
  )
    return;
  current = { name, case: caseId, steps: [], passed: false };
  report.scenarios.push(current);
  const c = await browser.newContext({
    viewport,
    recordVideo: {
      dir: "artifacts/browser/recording/video",
      size: { width: 1280, height: 800 },
    },
    timezoneId: "Asia/Hong_Kong",
  });
  await c.tracing.start({ screenshots: true, snapshots: true, sources: true });
  c.on("page", (p) =>
    p.on("pageerror", (e) =>
      report.pageErrors.push({ name, message: e.message }),
    ),
  );
  await c.route("**/*", (r) => {
    const host = new URL(r.request().url()).hostname;
    if (!["127.0.0.1", "localhost"].includes(host)) {
      report.external.push(r.request().url());
      return r.abort();
    }
    return r.continue();
  });
  for (const user of ["reviewer", "zao"]) {
    const r = await c.request.post(base + "/api/v1/auth/demo-login", {
      data: { username: user, case: caseId },
    });
    assert.equal(r.status(), 200);
    if (user === "reviewer") {
      const reset = await c.request.post(base + "/api/v1/demo/reset", {
        data: {},
      });
      assert.equal(reset.status(), 200);
    }
  }
  const p = await c.newPage();
  current.videoStarted = Date.now();
  p.setDefaultTimeout(12000);
  await p.goto(base);
  await p.getByRole("heading", { name: /你的能力/ }).waitFor();
  try {
    await fn(p, c);
    assert.deepEqual(
      report.pageErrors.filter((e) => e.name === name),
      [],
    );
    current.passed = true;
    await p.screenshot({ path: `${out}/${name}.png`, fullPage: true });
    const snapshot = `tmp/closed-loop/snapshots/${name}.sqlite3`;
    execFileSync("python3", [
      "-c",
      "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close(); s.close()",
      path.join(dataDir, caseId + ".sqlite3"),
      snapshot,
    ]);
    current.database = snapshot;
    console.log("PASS", name);
  } catch (e) {
    current.error = e.stack;
    await p
      .screenshot({ path: `${out}/${name}-failed.png`, fullPage: true })
      .catch(() => {});
    throw e;
  } finally {
    await c.tracing.stop({ path: `${out}/${name}-trace.zip` });
    await c.close();
    fs.writeFileSync(`${out}/result.json`, JSON.stringify(report, null, 2));
  }
}
async function holdTemplates(c) {
  let release, requested;
  const ready = new Promise((resolve) => {
    requested = resolve;
  });
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await c.route(base + "/api/v1/templates", async (route) => {
    requested();
    await gate;
    await route.continue();
  });
  return { ready, release };
}
async function seededProposal(p, c) {
  const q = (await api(c, "/me/proposals"))[0];
  await p.goto(base + "/proposal/" + q.id);
  await p.getByRole("button", { name: "建立雙方協議" }).waitFor();
  return q;
}
async function createAndSign(p) {
  const a = await action(p, "/agreements", () =>
    p.getByRole("button", { name: "建立雙方協議" }).click(),
  );
  await p.waitForURL("**/orders/" + a.id);
  for (const u of ["zao", "lin"]) {
    await role(p, u);
    await action(p, `/agreements/${a.id}/confirm`, () =>
      p.getByRole("button", { name: "我確認此版本協議" }).click(),
    );
  }
  assert.equal(
    (await api(p.context(), "/agreements/" + a.id)).status,
    "ACTIVE",
  );
  return a.id;
}
async function fund(p, id, index) {
  const a = await api(p.context(), "/agreements/" + id);
  const s = a.stages[index];
  if (!s.payment || s.payment.state !== "NEW") return;
  await role(p, s.payment.payer_id);
  await action(p, `/stages/${s.id}/fund`, () =>
    p
      .locator(".stage-card")
      .nth(index)
      .getByRole("button", { name: "模擬預留", exact: true })
      .click(),
  );
}
async function submit(p, ob, minutes = ob.data.minutes) {
  await role(p, ob.provider_id);
  await p
    .locator(".obligation")
    .filter({ has: p.getByText(ob.data.stage_deliverable, { exact: true }) })
    .getByRole("button", { name: "提交交付", exact: true })
    .click();
  const dialog = p.getByRole("dialog");
  await dialog.getByLabel("執行分鐘數").fill(String(minutes));
  await dialog
    .getByRole("textbox")
    .fill("依原驗收清單交付工作表或服務紀錄，閉環實測資料。");
  await action(p, `/obligations/${ob.id}/submit`, () =>
    dialog.getByRole("button", { name: "提交", exact: true }).click(),
  );
  await dialog.waitFor({ state: "hidden" });
}
async function accept(p, ob) {
  await role(p, ob.recipient_id);
  await p
    .locator(".obligation")
    .filter({ has: p.getByText(ob.data.stage_deliverable, { exact: true }) })
    .getByRole("button", { name: "驗收並確認時間", exact: true })
    .click();
  const dialog = p.getByRole("dialog");
  await dialog.getByLabel("正確性", { exact: true }).fill("94");
  await dialog.getByLabel("完整性", { exact: true }).fill("92");
  await dialog.getByLabel("自主完成", { exact: true }).fill("90");
  await action(p, `/obligations/${ob.id}/accept`, () =>
    dialog.getByRole("button", { name: "提交", exact: true }).click(),
  );
  await dialog.waitFor({ state: "hidden" });
}
async function deliver(p, id, index, seq, minutes) {
  let a = await api(p.context(), "/agreements/" + id);
  let ob = a.stages[index].obligations[seq];
  assert.equal(ob.status, "READY");
  await submit(p, ob, minutes);
  a = await api(p.context(), "/agreements/" + id);
  ob = a.stages[index].obligations[seq];
  assert.equal(ob.status, "SUBMITTED");
  await accept(p, ob);
  assert.equal(
    (await api(p.context(), "/agreements/" + id)).stages[index].obligations[seq]
      .status,
    "ACCEPTED",
  );
}
async function finish(p, id, execution) {
  const a = await api(p.context(), "/agreements/" + id);
  for (let i = 0; i < a.stages.length; i++) {
    await fund(p, id, i);
    for (let j = 0; j < a.stages[i].obligations.length; j++)
      await deliver(p, id, i, j, execution?.[i]);
  }
  const end = await api(p.context(), "/agreements/" + id);
  assert.equal(end.status, "COMPLETED");
  assert(
    end.stages.every((s) =>
      s.obligations.every((o) => o.status === "ACCEPTED"),
    ),
  );
  await p.reload();
  await p
    .getByRole("heading", { name: end.data.scope.title, exact: true })
    .waitFor();
  assert.equal(
    (await api(p.context(), "/agreements/" + id)).status,
    "COMPLETED",
  );
  current.order = end;
  return end;
}
async function balances(p, expected) {
  current.accounts = {};
  current.time = {};
  for (const user of Object.keys(expected)) {
    await role(p, user);
    const account = await api(p.context(), "/me/mock-account");
    assert.equal(account.available, expected[user]);
    assert.equal(account.reserved, 0);
    current.accounts[user] = {
      available: account.available,
      reserved: account.reserved,
    };
    current.time[user] = await api(p.context(), "/me/time-summary");
  }
}
async function close(p, id, continueFirst = false) {
  if ((await api(p.context(), "/agreements/" + id)).status !== "CLOSING") {
    await p
      .getByRole("button", { name: "申請退出與結清", exact: true })
      .click();
    const dialog = p.getByRole("dialog");
    await dialog
      .getByRole("textbox")
      .fill("閉環驗證：保留原已確認貢獻，取消尚未開始的後續階段。");
    await action(p, `/agreements/${id}/withdraw`, () =>
      dialog.getByRole("button", { name: "提交", exact: true }).click(),
    );
    await dialog.waitFor({ state: "hidden" });
  }
  await p.getByRole("button", { name: "建立結清方案", exact: true }).click();
  const dialog = p.getByRole("dialog");
  if (continueFirst) {
    await dialog.getByRole("combobox").first().selectOption("CONTINUE");
    await dialog.getByLabel("本筆模擬預留").selectOption("HOLD");
  }
  await dialog
    .getByRole("textbox")
    .fill("逐項保留已獲服務的原回報，後續雙方明確豁免，未履約預留退回付款方。");
  const closeout = await action(p, `/agreements/${id}/closeouts`, () =>
    dialog.getByRole("button", { name: "提交", exact: true }).click(),
  );
  await dialog.waitFor({ state: "hidden" });
  for (const user of ["zao", "lin"]) {
    await role(p, user);
    await action(p, `/closeouts/${closeout.id}/confirm`, () =>
      p.getByRole("button", { name: "確認這份結清方案", exact: true }).click(),
    );
  }
  return api(p.context(), "/agreements/" + id);
}
function local(v) {
  const fields = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Hong_Kong",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(v));
  return fields.replace(" ", "T");
}

let recordedVideo;
const speed = Number(process.env.HOURLINK_RECORD_SPEED || 1);
async function caption(p, title, message) {
  await p.evaluate(
    ({ title, message }) => {
      let el = document.getElementById("record-caption");
      if (!el) {
        el = document.createElement("div");
        el.id = "record-caption";
        document.body.appendChild(el);
      }
      el.style.cssText =
        "position:fixed;left:28px;right:28px;bottom:14px;padding:15px 22px;border-radius:10px;background:rgba(22,78,67,.96);color:white;z-index:9999;pointer-events:none;line-height:1.6;font-family:-apple-system,PingFang TC,sans-serif";
      el.replaceChildren();
      const h = document.createElement("b");
      h.style.cssText = "font-size:19px;display:block";
      h.textContent = title;
      const t = document.createElement("span");
      t.style.cssText = "font-size:14px;color:#deebd8";
      t.textContent = message;
      el.append(h, t);
    },
    { title, message },
  );
  console.log("SCENE", title);
}
async function until(start, seconds) {
  const remaining = (seconds * 1000) / speed - (Date.now() - start);
  if (remaining > 0)
    await new Promise((resolve) => setTimeout(resolve, remaining));
}
async function perspective(p, id, user, value, reason) {
  await role(p, user);
  const form = p.locator(".perspective-form");
  await form
    .getByLabel("收到的整份服務，對我值得多少（HKD）")
    .fill(String(value));
  await form.getByLabel("為什麼我這樣判斷").fill(reason);
  await form.getByRole("checkbox").check();
  await action(
    p,
    `/proposals/${id}/perspectives`,
    () => form.getByRole("button", { name: "保存我的價值判斷" }).click(),
    200,
    "PUT",
  );
}
async function bound(p, id, user, value) {
  await role(p, user);
  if ((await p.locator(".negotiation-panel").getAttribute("open")) === null)
    await p.locator(".negotiation-panel summary").click();
  await p.locator(".inline-form input").fill(String(value));
  await action(
    p,
    `/proposals/${id}/preference`,
    () =>
      p
        .locator(".inline-form")
        .getByRole("button", { name: "保存", exact: true })
        .click(),
    200,
    "PUT",
  );
}
(async () => {
  browser = await chromium.launch({ headless: true });
  await scenario(
    "time-value-story",
    "barter",
    async (p, c) => {
      const q = await seededProposal(p, c);
      recordedVideo = p.video();
      await p.locator(".negotiation-panel summary").click();
      await p.getByLabel("反向服務分鐘數").fill("60");
      await action(p, `/proposals/${q.id}/revise`, () =>
        p.getByRole("button", { name: "保存協商條件" }).click(),
      );
      await p.locator(".proposal-panel").scrollIntoViewIfNeeded();
      const start = Date.now();
      current.storyOffsetSeconds = (start - current.videoStarted) / 1000;
      await caption(
        p,
        "先試一次：一小時換一小時？",
        "60分鐘表格輔導 ↔ 60分鐘英語交流。時間相同，相關能力、投入與對方需要的價值可能不同；全程使用模擬人物與資料。",
      );
      await until(start, 15);
      await perspective(
        p,
        q.id,
        "lin",
        80,
        "我只需要短時口語練習，增加交流時長對我的幫助有限。",
      );
      await perspective(
        p,
        q.id,
        "zao",
        200,
        "這次表格輔導能解決急需的公式問題，對我有較高價值。",
      );
      await p.locator(".perspective-panel").scrollIntoViewIfNeeded();
      await p
        .locator(".perspective-panel .perspective-grid")
        .screenshot({ path: "artifacts/pitch-assets/perspectives.png" });
      await caption(
        p,
        "同一份服務，平台與雙方可以不同意",
        "平台按能力與投入提供參考；本人判斷收到服務是否有用。只有本人勾選分享才對方可見；私人接受底線不公開。",
      );
      await until(start, 34);
      const rec = await action(p, `/proposals/${q.id}/recommend`, () =>
        p.getByRole("button", { name: "重新計算建議" }).click(),
      );
      assert.equal(rec.data.reverse_minutes, 90);
      assert.deepEqual(
        (await api(c, `/proposals/${q.id}/perspectives`)).views,
        [],
      );
      await p.locator(".proposal-panel").scrollIntoViewIfNeeded();
      await caption(
        p,
        "本單參考：60分鐘輔導 ↔ 90分鐘英語",
        "輔導參考HK$150／小時，英語HK$100／小時；不是永久匯率。服務數量改變後，舊的個人價值判斷須重新表達。",
      );
      await until(start, 49);
      await bound(p, q.id, "lin", 90);
      await bound(p, q.id, "zao", 60);
      const refusal = await action(
        p,
        `/proposals/${q.id}/calculate`,
        () => p.getByRole("button", { name: "計算交集" }).click(),
        422,
      );
      assert.equal(refusal.code, "NO_FEASIBLE_PLAN");
      assert.deepEqual(await api(c, "/me/orders"), []);
      await caption(
        p,
        "參考價相等，也不代表雙方願意交換",
        "一方至少要90分鐘回報，另一方最多提供60分鐘：沒有共同可接受方案，不成單、不扣信用；不强迫接受平台比例。",
      );
      await until(start, 64);
      await bound(p, q.id, "zao", 105);
      const options = await action(p, `/proposals/${q.id}/calculate`, () =>
        p.getByRole("button", { name: "計算交集" }).click(),
      );
      assert(options.candidates.includes(90));
      await action(p, `/proposals/${q.id}/select`, () =>
        p.getByRole("button", { name: "選用首個候選" }).click(),
      );
      const id = await createAndSign(p);
      await caption(
        p,
        "重新協商後，雙方確認同一版約定",
        "選用60↔90的具體服務組合，分兩輪30↔45。第二次簽署原子檢查需求、容量與時段，不生成通用時間積分。",
      );
      await until(start, 81);
      await deliver(p, id, 0, 0);
      await caption(
        p,
        "先付出30分鐘，回報還沒有發生",
        "只有提交並被接收者驗收的服務才計入貢獻。這一刻，原45分鐘英語回報仍是清楚的未結義務。",
      );
      await until(start, 98);
      await role(p, "lin");
      const closing = await close(p, id);
      assert.equal(closing.status, "CLOSING");
      await caption(
        p,
        "先履約者退出，原回報不能被清空",
        "雙方逐項確認結清：繼續原45分鐘英語，豁免尚未開始的下一輪。義務未完成前，訂單保持結清中。",
      );
      await until(start, 114);
      await deliver(p, id, 0, 1);
      const end = await api(c, "/agreements/" + id);
      assert.equal(end.status, "CANCELLED");
      current.order = end;
      await balances(p, { zao: 100000, lin: 100000 });
      assert.equal(current.time.lin.provided_minutes, 30);
      assert.equal(current.time.lin.received_service_minutes, 45);
      await p.getByRole("link", { name: "能力與時間", exact: true }).click();
      await caption(
        p,
        "結清保留事實：提供30，收到45",
        "不同服務分鐘不相減，部分履約不冒充整單能力歷史。這條公平規則保護先付出者，也增加雙方的驗收成本。",
      );
      await until(start, 129);
      await p.goto(base + "/mechanism");
      await p
        .getByRole("heading", { name: "公平規則保護誰，讓誰多做了什麼？" })
        .scrollIntoViewIfNeeded();
      await caption(
        p,
        "保護越細，操作越多：公開這個代價",
        "120↔180的演示：30分鐘先行限制需4輪、18次簽署／提交／驗收命令；60分鐘限制需2輪、10次。這是流程計數，不是實測耗時。",
      );
      await until(start, 145);
      const missing = await action(p, "/mechanism/simulate", () =>
        p.getByRole("button", { name: "證據不足", exact: true }).click(),
      );
      assert.equal(missing.failure.code, "INSUFFICIENT_EVIDENCE");
      await p.locator(".mechanism-result").scrollIntoViewIfNeeded();
      await caption(
        p,
        "沒有已確認能力證據，停止確定建議",
        "平台保留模板參考，但不虛構能力溢價或確定交換比例；需要先復核。這也意味着新用戶多了一道進入成本。",
      );
      await until(start, 159);
      const indivisible = await action(p, "/mechanism/simulate", () =>
        p.getByRole("button", { name: "不可合法分輪", exact: true }).click(),
      );
      assert.equal(indivisible.failure.code, "NO_FEASIBLE_PLAN");
      await p.locator(".mechanism-result").scrollIntoViewIfNeeded();
      await caption(
        p,
        "這套規則也會失效",
        "準備投入已超過先行限制時，不能靠切碎服務繞過保護。18組隔離控制實驗公開參數跳幅和失效原因，不宣稱已驗證真實市場定價。",
      );
      await until(start, 174);
      await p.goto(base + "/study");
      await p
        .getByRole("heading", { name: "用一次，再告訴我們是否值得" })
        .waitFor();
      await caption(
        p,
        "下一步：真實使用者能否理解並願意採用？",
        "與時間銀行和付費里程碑平台作官方資料對照，提供匿名試用流程。模擬交易和身份切換不當作真實用戶研究，也不提供真實支付担保。",
      );
      await until(start, 180);
    },
    { width: 1280, height: 800 },
  );
  await recordedVideo.saveAs("artifacts/browser/recording/hourlink-raw.webm");
  fs.writeFileSync(
    "artifacts/browser/recording/metadata.json",
    JSON.stringify(report, null, 2),
  );
  await browser.close();
  console.log("Recorded verified time-exchange story.");
})().catch(async (e) => {
  console.error(e);
  if (browser) await browser.close();
  process.exit(1);
});
