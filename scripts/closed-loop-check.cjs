const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const { chromium } = require(
  process.env.HOURLINK_PLAYWRIGHT ||
    require("node:path").join(
      require("node:os").homedir(),
      ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright",
    ),
);
const base = process.env.HOURLINK_TEST_URL || "http://127.0.0.1:8001";
const dataDir = process.env.HOURLINK_TEST_DATA || "tmp/closed-loop/data";
const out = "artifacts/browser/closed-loop";
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
(async () => {
  browser = await chromium.launch({ headless: true });
  await scenario("paid-publish-complete", "cash", async (p, c) => {
    const template = await api(c, "/listings/request-main");
    await p.getByRole("link", { name: "發佈我的需求", exact: true }).click();
    await p.getByLabel("用一句話說明").fill("閉環測試：整理社群活動表格");
    await p
      .getByLabel("需求情境")
      .fill("清理重複資料並核對公式，完成後要交付清單及修改說明。");
    await p
      .getByLabel("可用時段開始（本地時間）")
      .fill(local(template.data.start));
    await p
      .getByLabel("可用時段結束（本地時間）")
      .fill(local(template.data.end));
    const listing = await action(p, "/listings", () =>
      p.getByRole("button", { name: "發佈並分析" }).click(),
    );
    await p.waitForURL("**/listing/" + listing.id);
    const analysis = await action(p, `/listings/${listing.id}/analyze`, () =>
      p.getByRole("button", { name: "分析需求", exact: true }).click(),
    );
    assert.deepEqual(analysis.missing_fields, []);
    const matches = await api(c, `/listings/${listing.id}/matches`);
    assert.equal(matches.recommended_id, "lin");
    assert.deepEqual(
      matches.candidates.map((c) => c.total_amount),
      [15000, 25000, 30000],
    );
    await p.getByRole("button", { name: "查看評估依據" }).first().click();
    await p
      .getByRole("dialog")
      .getByText(/歷史中位數/)
      .waitFor();
    await p.getByRole("button", { name: "關閉", exact: true }).click();
    const recResponse = p.waitForResponse(
      (r) =>
        r.url().endsWith("/proposals/recommended") &&
        r.request().method() === "POST",
    );
    await p.getByRole("button", { name: "選擇並生成方案" }).first().click();
    assert.equal((await recResponse).status(), 200);
    await p.getByRole("button", { name: "建立雙方協議" }).waitFor();
    let q = await api(c, "/proposals/" + p.url().split("/").pop());
    await p.locator(".negotiation-panel summary").click();
    await p.getByLabel("協商金額（HKD）").fill("160");
    q = await action(p, `/proposals/${q.id}/revise`, () =>
      p.getByRole("button", { name: "保存協商條件" }).click(),
    );
    assert.equal(q.data.amount, 16000);
    const id = await createAndSign(p);
    await finish(p, id, [12, 17]);
    await balances(p, { zao: 84000, lin: 116000 });
    assert.equal(current.time.lin.provided_minutes, 29);
    await role(p, "lin");
    const evidence = await api(c, "/me/evidence");
    const history = evidence.filter((e) => e.agreement_id === id);
    assert.equal(history.length, 1);
    assert.equal(history[0].data.confirmed_minutes, 29);
    current.feedback = { evidence_id: history[0].id, confirmed_minutes: 29 };
  });
  await scenario("barter-complete", "barter", async (p, c) => {
    const q = await seededProposal(p, c);
    assert.equal(q.data.reverse_minutes, 90);
    const id = await createAndSign(p);
    await finish(p, id);
    await balances(p, { zao: 100000, lin: 100000 });
    assert.equal(current.time.lin.provided_minutes, 60);
    assert.equal(current.time.lin.received_service_minutes, 90);
    assert.equal(current.time.zao.provided_minutes, 90);
  });
  await scenario("hybrid-complete", "hybrid", async (p, c) => {
    await seededProposal(p, c);
    const id = await createAndSign(p);
    const end = await finish(p, id);
    assert.equal(
      end.stages.reduce((n, s) => n + s.payment.released, 0),
      5000,
    );
    await balances(p, { zao: 95000, lin: 105000 });
    assert.equal(current.time.lin.received_service_minutes, 60);
  });
  await scenario("barter-exit-remediation", "barter", async (p, c) => {
    await seededProposal(p, c);
    const id = await createAndSign(p);
    await deliver(p, id, 0, 0);
    await role(p, "zao");
    let end = await close(p, id);
    assert.equal(end.status, "CLOSING");
    assert.equal(end.stages[0].obligations[1].data.minutes, 45);
    assert.equal(end.stages[0].obligations[1].status, "READY");
    assert(end.stages[1].obligations.every((o) => o.status === "WAIVED"));
    await deliver(p, id, 0, 1);
    end = await api(c, "/agreements/" + id);
    assert.equal(end.status, "CANCELLED");
    current.order = end;
    await balances(p, { zao: 100000, lin: 100000 });
    assert.equal(current.time.lin.provided_minutes, 30);
    assert.equal(current.time.lin.received_service_minutes, 45);
    assert.equal(current.time.lin.pending.length, 0);
  });
  await scenario("paid-exit-refund", "withdrawal", async (p, c) => {
    const id = (await api(c, "/me/orders"))[0].id;
    await p.goto(base + "/orders/" + id);
    await p.getByRole("button", { name: "申請退出與結清" }).waitFor();
    const end = await close(p, id);
    assert.equal(end.status, "CANCELLED");
    assert.equal(end.stages[0].payment.released, 6000);
    assert.equal(end.stages[1].payment.refunded, 9000);
    current.order = end;
    await balances(p, { zao: 94000, lin: 106000 });
    assert.equal(current.time.lin.provided_minutes, 12);
  });
  await scenario("hybrid-exit-hold-remediation", "hybrid", async (p, c) => {
    await seededProposal(p, c);
    const id = await createAndSign(p);
    await fund(p, id, 0);
    await deliver(p, id, 0, 0);
    await role(p, "zao");
    let end = await close(p, id);
    assert.equal(end.status, "CLOSING");
    assert.equal(end.stages[0].payment.reserved, 2500);
    assert.equal(end.stages[0].payment.released, 0);
    assert.equal(end.stages[0].payment.refunded, 0);
    await deliver(p, id, 0, 1);
    end = await api(c, "/agreements/" + id);
    assert.equal(end.status, "CANCELLED");
    assert.equal(end.stages[0].payment.released, 2500);
    current.order = end;
    await balances(p, { zao: 97500, lin: 102500 });
  });
  await scenario("no-feasible-no-transaction", "no_deal", async (p, c) => {
    const q = await seededProposal(p, c);
    await p.locator(".negotiation-panel summary").click();
    const result = await action(
      p,
      `/proposals/${q.id}/calculate`,
      () => p.getByRole("button", { name: "計算交集" }).click(),
      422,
    );
    assert.equal(result.code, "NO_FEASIBLE_PLAN");
    const rejectedDraft = await action(
      p,
      "/agreements",
      () => p.getByRole("button", { name: "建立雙方協議" }).click(),
      422,
    );
    assert.equal(rejectedDraft.code, "NO_FEASIBLE_PLAN");
    assert.deepEqual(await api(c, "/me/orders"), []);
    assert.equal((await api(c, "/users/zao/credit")).policy.blocked, false);
    assert.equal((await api(c, "/users/lin/credit")).policy.blocked, false);
    await balances(p, { zao: 100000, lin: 100000 });
    current.rejection = result;
  });
  await scenario("assisted-candidate-complete", "no_deal", async (p, c) => {
    const q = await seededProposal(p, c);
    await p.locator(".negotiation-panel summary").click();
    for (const [user, value] of [
      ["lin", "180"],
      ["zao", "220"],
    ]) {
      await role(p, user);
      if ((await p.locator(".negotiation-panel").getAttribute("open")) === null)
        await p.locator(".negotiation-panel summary").click();
      await p.locator(".inline-form input").fill(value);
      await action(
        p,
        `/proposals/${q.id}/preference`,
        () =>
          p
            .locator(".inline-form")
            .getByRole("button", { name: "保存", exact: true })
            .click(),
        200,
        "PUT",
      );
    }
    const options = await action(p, `/proposals/${q.id}/calculate`, () =>
      p.getByRole("button", { name: "計算交集" }).click(),
    );
    assert.deepEqual(options.candidates, [20000]);
    const selected = await action(p, `/proposals/${q.id}/select`, () =>
      p.getByRole("button", { name: "選用首個候選" }).click(),
    );
    assert.equal(selected.data.amount, 20000);
    const own = await api(c, `/proposals/${q.id}/preference`);
    assert.equal(own.value, 22000);
    assert.equal(own.scope_version, selected.scope_version);
    const id = await createAndSign(p);
    const end = await finish(p, id);
    assert.equal(end.data.amount, 20000);
    assert.equal(end.data.recommendation.amount, 15000);
    await balances(p, { zao: 80000, lin: 120000 });
  });
  await scenario("hybrid-repriced-zero-complete", "hybrid", async (p, c) => {
    const q = await seededProposal(p, c);
    await p.locator(".negotiation-panel summary").click();
    await p.getByLabel("反向服務分鐘數").fill("90");
    await action(p, `/proposals/${q.id}/revise`, () =>
      p.getByRole("button", { name: "保存協商條件" }).click(),
    );
    const revised = await action(p, `/proposals/${q.id}/recommend`, () =>
      p.getByRole("button", { name: "重新計算建議" }).click(),
    );
    assert.equal(revised.data.amount, 0);
    assert.equal(revised.data.recommendation.reverse.total_amount, 15000);
    const id = await createAndSign(p);
    await finish(p, id);
    await balances(p, { zao: 100000, lin: 100000 });
  });
  await scenario("dispute-redo-complete", "cash", async (p, c) => {
    await seededProposal(p, c);
    const id = await createAndSign(p);
    await fund(p, id, 0);
    let ob = (await api(c, "/agreements/" + id)).stages[0].obligations[0];
    await submit(p, ob, 20);
    await role(p, "zao");
    await p.getByRole("button", { name: "提出異議", exact: true }).click();
    let dialog = p.getByRole("dialog");
    await dialog
      .getByRole("textbox")
      .fill("公式不符合原驗收樣本，要求對照原條款重交。");
    const dispute = await action(p, `/agreements/${id}/disputes`, () =>
      dialog.getByRole("button", { name: "提交", exact: true }).click(),
    );
    await dialog.waitFor({ state: "hidden" });
    assert.equal((await api(c, "/agreements/" + id)).status, "DISPUTED");
    assert.equal((await api(c, "/users/lin/credit")).policy.blocked, false);
    await role(p, "reviewer");
    await p.getByRole("link", { name: "演示模式", exact: true }).click();
    await p.getByRole("button", { name: "記錄復核結果", exact: true }).click();
    dialog = p.getByRole("dialog");
    await dialog.getByLabel("復核處理").selectOption("REDO");
    await dialog
      .getByLabel("復核依據")
      .fill("對照原工作表驗收樣本，原義務退回重做，未判定全域違約。");
    await action(p, `/disputes/${dispute.id}/review`, () =>
      dialog.getByRole("button", { name: "保存復核結果" }).click(),
    );
    await dialog.waitFor({ state: "hidden" });
    await role(p, "lin");
    await p.goto(base + "/orders/" + id);
    await deliver(p, id, 0, 0, 18);
    await fund(p, id, 1);
    await deliver(p, id, 1, 0, 12);
    const end = await api(c, "/agreements/" + id);
    assert.equal(end.status, "COMPLETED");
    assert.equal(end.disputes[0].status, "REVIEWED");
    assert.equal(
      end.stages[0].obligations[0].time_entries.find(
        (t) => t.component === "EXECUTION",
      ).minutes,
      18,
    );
    current.order = end;
    await balances(p, { zao: 85000, lin: 115000 });
    assert.equal(current.time.lin.provided_minutes, 30);
  });
  await scenario("evidence-review-new-recommendation", "cash", async (p, c) => {
    let before = await api(c, "/listings/request-extra-1/matches");
    assert.equal(before.recommended_id, "zao");
    const templates = await holdTemplates(c);
    await p.getByRole("link", { name: "能力與時間", exact: true }).click();
    await templates.ready;
    const form = p.locator("aside form");
    try {
      assert.equal(await form.getByLabel("服務類別").isDisabled(), true);
    } finally {
      templates.release();
    }
    await form.getByLabel("服務類別").selectOption("english");
    await form.getByLabel("作品或測評名稱").fill("英語交流新測評：閉環實測");
    await form
      .getByLabel("材料與完成說明")
      .fill("根據模板完成對話、口語回饋與自主教學的結構化能力測評。");
    const e = await action(p, "/capability-evidence", () =>
      form.getByRole("button", { name: "提交能力證據" }).click(),
    );
    assert.equal(e.status, "PENDING");
    assert.equal(
      (await api(c, "/listings/request-extra-1/matches")).candidates.find(
        (x) => x.user_id === "zao",
      ).hourly_rate,
      10000,
    );
    await role(p, "reviewer");
    await p.getByRole("link", { name: "演示模式", exact: true }).click();
    await p.getByRole("button", { name: "查看並復核", exact: true }).click();
    const dialog = p.getByRole("dialog");
    for (const name of ["正確性", "完整性", "自主完成"])
      await dialog.getByLabel(name, { exact: true }).fill("98");
    await dialog
      .getByLabel("復核依據")
      .fill("按三項模板核對英語對話、回饋完整度與自主引導，均為98分。");
    await action(p, `/capability-evidence/${e.id}/review`, () =>
      dialog.getByRole("button", { name: "保存復核結果" }).click(),
    );
    await dialog.waitFor({ state: "hidden" });
    await role(p, "zao");
    const after = await api(c, "/listings/request-extra-1/matches");
    const candidate = after.candidates.find((x) => x.user_id === "zao");
    assert.equal(candidate.quality, 86);
    assert.equal(candidate.hourly_rate, 12500);
    assert.equal(candidate.evidence_count, 2);
    await p.getByRole("link", { name: "能力與時間", exact: true }).click();
    const rejectedForm = p.locator("aside form");
    await rejectedForm.getByLabel("服務類別").selectOption("english");
    await rejectedForm
      .getByLabel("作品或測評名稱")
      .fill("未通過作品：不計入能力");
    await rejectedForm
      .getByLabel("材料與完成說明")
      .fill("材料尚未提供可核對的對話與回饋內容，需要補充後再提交。");
    const rejected = await action(p, "/capability-evidence", () =>
      rejectedForm.getByRole("button", { name: "提交能力證據" }).click(),
    );
    await role(p, "reviewer");
    await p.getByRole("link", { name: "演示模式", exact: true }).click();
    await p.getByRole("button", { name: "查看並復核", exact: true }).click();
    const rejectDialog = p.getByRole("dialog");
    await rejectDialog
      .getByText("材料尚未提供可核對的對話與回饋內容，需要補充後再提交。", {
        exact: true,
      })
      .waitFor();
    await rejectDialog.getByLabel("材料復核結果").selectOption("reject");
    await rejectDialog
      .getByLabel("復核依據")
      .fill("缺少可核對作品，不納入相關能力評估；可補充材料後重新提交。");
    await action(p, `/capability-evidence/${rejected.id}/review`, () =>
      rejectDialog.getByRole("button", { name: "保存復核結果" }).click(),
    );
    await rejectDialog.waitFor({ state: "hidden" });
    const afterReject = (
      await api(c, "/listings/request-extra-1/matches")
    ).candidates.find((x) => x.user_id === "zao");
    assert.equal(afterReject.quality, 86);
    assert.equal(afterReject.evidence_count, 2);
    current.feedback = {
      before_hourly: 10000,
      after_hourly: 12500,
      quality: 86,
      evidence_id: e.id,
    };
  });
  await scenario("dispute-exit-review-remediation", "cash", async (p, c) => {
    await seededProposal(p, c);
    const id = await createAndSign(p);
    await fund(p, id, 0);
    const ob = (await api(c, "/agreements/" + id)).stages[0].obligations[0];
    await submit(p, ob, 20);
    await role(p, "zao");
    await p.getByRole("button", { name: "提出異議", exact: true }).click();
    let dialog = p.getByRole("dialog");
    await dialog
      .getByRole("textbox")
      .fill("原公式與驗收樣本不符，請按原義務重交。");
    const dispute = await action(p, `/agreements/${id}/disputes`, () =>
      dialog.getByRole("button", { name: "提交", exact: true }).click(),
    );
    await dialog.waitFor({ state: "hidden" });
    await p.getByRole("button", { name: "申請退出與結清" }).click();
    dialog = p.getByRole("dialog");
    await dialog
      .getByRole("textbox")
      .fill("等待復核時申請退出，但保留第一阶段原義務。");
    await action(p, `/agreements/${id}/withdraw`, () =>
      dialog.getByRole("button", { name: "提交", exact: true }).click(),
    );
    await dialog.waitFor({ state: "hidden" });
    await role(p, "reviewer");
    await p.getByRole("link", { name: "演示模式", exact: true }).click();
    await p.getByRole("button", { name: "記錄復核結果" }).click();
    dialog = p.getByRole("dialog");
    await dialog.getByLabel("復核處理").selectOption("REDO");
    await dialog.locator("summary").click();
    await dialog.getByLabel("已確認需補救的當事人").selectOption("lin");
    await dialog
      .getByLabel("復核依據")
      .fill("原交付返回重做，期間退出申請仍然有效，不能恢復下一階段。");
    await action(p, `/disputes/${dispute.id}/review`, () =>
      dialog.getByRole("button", { name: "保存復核結果" }).click(),
    );
    await dialog.waitFor({ state: "hidden" });
    assert((await api(c, "/users/lin/credit")).policy.blocked);
    await role(p, "lin");
    await p.goto(base + "/orders/" + id);
    assert.equal((await api(c, "/agreements/" + id)).status, "CLOSING");
    assert.equal(
      await p.getByRole("button", { name: "提交交付", exact: true }).count(),
      0,
    );
    await close(p, id, true);
    await deliver(p, id, 0, 0, 15);
    const end = await api(c, "/agreements/" + id);
    assert.equal(end.status, "CANCELLED");
    current.order = end;
    await balances(p, { zao: 94000, lin: 106000 });
    await role(p, "reviewer");
    await p.goto(base + "/orders/" + id);
    await p.getByRole("button", { name: "記錄完成補救", exact: true }).click();
    dialog = p.getByRole("dialog");
    await dialog
      .getByLabel("說明與依據")
      .fill("原義務已按驗收標準補做並確認，剩餘事項已由雙方明確結清。");
    await action(p, `/disputes/${dispute.id}/remedy`, () =>
      dialog.getByRole("button", { name: "提交", exact: true }).click(),
    );
    await dialog.waitFor({ state: "hidden" });
    assert.equal((await api(c, "/users/lin/credit")).policy.blocked, false);
  });
  await scenario("prepared-barter-six-rounds", "barter", async (p, c) => {
    const template = await api(c, "/listings/request-main");
    const templates = await holdTemplates(c);
    await p.getByRole("link", { name: "發佈我的需求", exact: true }).click();
    await templates.ready;
    try {
      assert.equal(await p.getByLabel("服務類別").isDisabled(), true);
    } finally {
      templates.release();
    }
    await p.getByLabel("服務類別").selectOption("tutoring");
    assert.equal(
      await p.getByLabel("交付與驗收標準").inputValue(),
      "約定時長的輔導與練習回饋",
    );
    await p.getByLabel("用一句話說明").fill("含準備投入的表格輔導閉環");
    await p
      .getByLabel("需求情境")
      .fill("約定60分鐘輔導，並事前納入20分鐘準備投入。");
    await p
      .getByLabel("可用時段開始（本地時間）")
      .fill(local(template.data.start));
    await p
      .getByLabel("可用時段結束（本地時間）")
      .fill(local(template.data.end));
    const prep = p.locator("label").filter({ hasText: "預計準備時間" });
    await prep.getByRole("spinbutton").fill("20");
    await prep.getByRole("checkbox").check();
    const listing = await action(p, "/listings", () =>
      p.getByRole("button", { name: "發佈並分析" }).click(),
    );
    await p.waitForURL("**/listing/" + listing.id);
    await p
      .locator(".mode-options")
      .getByRole("button", { name: "時間互換", exact: true })
      .click();
    const recPromise = p.waitForResponse(
      (r) =>
        r.url().endsWith("/proposals/recommended") &&
        r.request().method() === "POST",
    );
    await p.getByRole("button", { name: "選擇並生成方案" }).first().click();
    const proposal = await (await recPromise).json();
    assert.equal(proposal.data.recommendation.rounds, 6);
    assert.equal(proposal.data.reverse_minutes, 120);
    await p.getByRole("button", { name: "建立雙方協議" }).waitFor();
    assert.equal(await p.getByLabel("可獨立驗收的階段數").inputValue(), "6");
    const id = await createAndSign(p);
    await finish(p, id);
    await balances(p, { zao: 100000, lin: 100000 });
    assert.equal(current.time.lin.provided_minutes, 80);
    assert.equal(current.time.lin.received_service_minutes, 120);
  });
  await scenario(
    "mobile-paid-complete",
    "cash",
    async (p, c) => {
      await seededProposal(p, c);
      const id = await createAndSign(p);
      await finish(p, id);
      assert(
        await p.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
        "mobile order horizontal overflow",
      );
      await balances(p, { zao: 85000, lin: 115000 });
    },
    { width: 390, height: 844 },
  );
  assert.deepEqual(report.external, []);
  await scenario(
    "subjective-values-consent-and-completion",
    "barter",
    async (p, c) => {
      const q = await seededProposal(p, c);
      const original = await api(c, `/proposals/${q.id}`);
      const initial = await api(c, `/proposals/${q.id}/perspectives`);
      assert.equal(initial.views.length, 0);
      assert.equal(initial.estimates.length, 2);
      await p
        .getByRole("heading", { name: "平台先估算這份時間的價值" })
        .waitFor();
      await p
        .locator('.algorithm-estimate[data-recipient="zao"]')
        .getByText("算法建議", { exact: true })
        .waitFor();
      const adoptionForm = p.locator(".perspective-form");
      await adoptionForm.getByRole("button", { name: "採用平台估值" }).click();
      assert.equal(
        await adoptionForm
          .getByLabel("收到的整份服務，對我值得多少（HKD）")
          .inputValue(),
        "150",
      );
      assert(
        (
          await adoptionForm.getByLabel("為什麼我這樣判斷").inputValue()
        ).includes("平台本單估值"),
      );
      assert.equal(await adoptionForm.getByRole("checkbox").isChecked(), false);
      await action(
        p,
        `/proposals/${q.id}/perspectives`,
        () =>
          adoptionForm
            .getByRole("button", { name: "保存我的價值判斷" })
            .click(),
        200,
        "PUT",
      );
      assert.equal(
        (await api(c, `/proposals/${q.id}/perspectives`)).views[0]
          .received_value,
        15000,
      );
      await role(p, "lin");
      assert.equal(
        (await api(c, `/proposals/${q.id}/perspectives`)).views.length,
        0,
      );
      for (const [user, value, reason, shared] of [
        ["lin", "80", "我只需短時口語練習，額外時長對我幫助有限。", false],
        ["zao", "200", "這次辅導能解決急需的公式問題，對我價值較高。", true],
      ]) {
        await role(p, user);
        const form = p.locator(".perspective-form");
        await form
          .getByLabel("收到的整份服務，對我值得多少（HKD）")
          .fill(value);
        await form.getByLabel("為什麼我這樣判斷").fill(reason);
        if (shared) await form.getByRole("checkbox").check();
        await action(
          p,
          `/proposals/${q.id}/perspectives`,
          () => form.getByRole("button", { name: "保存我的價值判斷" }).click(),
          200,
          "PUT",
        );
      }
      let views = (await api(c, `/proposals/${q.id}/perspectives`)).views;
      assert.equal(views.length, 1);
      assert.equal(views[0].received_value, 20000);
      await role(p, "lin");
      assert.equal(
        (await api(c, `/proposals/${q.id}/perspectives`)).views.length,
        2,
      );
      const form = p.locator(".perspective-form");
      await form.getByLabel("收到的整份服務，對我值得多少（HKD）").fill("80");
      await form
        .getByLabel("為什麼我這樣判斷")
        .fill("我只需短時口語練習，願意分享與平台參考的差異。");
      await form.getByRole("checkbox").check();
      await action(
        p,
        `/proposals/${q.id}/perspectives`,
        () => form.getByRole("button", { name: "保存我的價值判斷" }).click(),
        200,
        "PUT",
      );
      await role(p, "zao");
      views = (await api(c, `/proposals/${q.id}/perspectives`)).views;
      assert.equal(views.length, 2);
      assert.equal(
        (await api(c, `/proposals/${q.id}`)).data.amount,
        original.data.amount,
      );
      const id = await createAndSign(p);
      await finish(p, id);
      await balances(p, { zao: 100000, lin: 100000 });
    },
  );
  await scenario(
    "mechanism-failures-and-mobile-study",
    "barter",
    async (p, c) => {
      await p.goto(base + "/mechanism");
      await p
        .getByRole("heading", { name: "一小時的價值，如何改變？" })
        .waitFor();
      for (const [button, code] of [
        ["證據不足", "INSUFFICIENT_EVIDENCE"],
        ["雙方價值無交集", "NO_FEASIBLE_PLAN"],
        ["不可合法分輪", "NO_FEASIBLE_PLAN"],
      ]) {
        const result = await action(p, "/mechanism/simulate", () =>
          p.getByRole("button", { name: button, exact: true }).click(),
        );
        assert.equal(result.failure.code, code);
        await p
          .locator(".mechanism-result")
          .getByText(code, { exact: true })
          .waitFor();
      }
      assert.deepEqual(await api(c, "/me/orders"), []);
      const report = await api(c, "/mechanism");
      assert.equal(report.experiments.length, 18);
      assert(
        report.tradeoffs[0].workflow_commands >
          report.tradeoffs[1].workflow_commands,
      );
      assert(
        await p.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      await p.getByRole("link", { name: "進入匿名試用與回饋 →" }).click();
      await p
        .getByRole("heading", { name: "用一次，再告訴我們是否值得" })
        .waitFor();
      assert(
        await p.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      current.note =
        "Study page inspection only; automation is not a real participant and submits no feedback.";
    },
    { width: 390, height: 844 },
  );
  await scenario(
    "goal-aware-value-plan-and-complete",
    "barter",
    async (p, c) => {
      const q = await seededProposal(p, c);
      await p.goto(base + "/value-model");
      await p
        .getByRole("heading", { name: "把難量化的幫助，拆成可說明的價值" })
        .waitFor();
      await p.getByLabel("本次目標分鐘").fill("120");
      const experiment = await action(p, "/value-model/simulate", () =>
        p.getByRole("button", { name: "分析時間與受益" }).click(),
      );
      assert.equal(experiment.benefit.score, 84.6);
      assert.equal(experiment.reference.reference_amount, 15000);
      await p.locator(".value-model-result").waitFor();
      assert(
        await p.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      await p.goto(base + "/proposal/" + q.id);
      await role(p, "lin");
      await p
        .locator(".benefit-panel")
        .getByText("確認我的目標與偏好（僅本人可見）", { exact: true })
        .click();
      await p.getByLabel("目標練習時長（分鐘）").fill("60");
      await action(
        p,
        `/proposals/${q.id}/value-context`,
        () =>
          p
            .getByRole("button", { name: "確認目標與偏好", exact: true })
            .click(),
        200,
        "PUT",
      );
      assert.deepEqual((await api(c, `/proposals/${q.id}`)).data, q.data);
      const values = await api(c, `/proposals/${q.id}/perspectives`);
      assert.equal(values.goal_plan.amount, 5000);
      assert.equal(values.goal_plan.reverse_minutes, 60);
      const changed = await action(
        p,
        `/proposals/${q.id}/apply-value-plan`,
        () => p.getByRole("button", { name: "確認目標並帶入方案" }).click(),
      );
      assert.equal(changed.mode, "HYBRID");
      assert.equal(changed.data.payer_id, "zao");
      assert(
        await p.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      );
      await p.screenshot({
        path: `${out}/goal-value-proposal-mobile.png`,
        fullPage: true,
      });
      const id = await createAndSign(p);
      await finish(p, id);
      await balances(p, { zao: 95000, lin: 105000 });
    },
    { width: 390, height: 844 },
  );
  await scenario(
    "listing-edit-close-reopen-and-complete",
    "cash",
    async (p, c) => {
      await p.goto(base + "/listing/request-main");
      await p.getByRole("checkbox", { name: "比較林知行" }).check();
      await p.getByRole("checkbox", { name: "比較陳思維" }).check();
      const compareButton = p.getByRole("button", {
        name: "比較候選",
        exact: true,
      });
      await compareButton.click();
      const comparison = p.getByRole("dialog");
      await comparison.getByRole("heading", { name: "比較本單候選" }).waitFor();
      await p.keyboard.press("Tab");
      assert(
        await comparison.evaluate((el) => el.contains(document.activeElement)),
      );
      await p.keyboard.press("Escape");
      await comparison.waitFor({ state: "hidden" });
      assert(
        await compareButton.evaluate((el) => el === document.activeElement),
      );
      await p.getByRole("link", { name: "編輯刊登", exact: true }).click();
      await p.getByLabel("用一句話說明").fill("完整流程：編輯後的社群表格需求");
      const changed = await action(
        p,
        "/listings/request-main",
        () => p.getByRole("button", { name: "保存刊登" }).click(),
        200,
        "PATCH",
      );
      assert(changed.version > 1);
      await p.waitForURL("**/listing/request-main");
      await p.getByRole("button", { name: "撤回刊登", exact: true }).click();
      await action(p, "/listings/request-main/close", () =>
        p
          .getByRole("dialog")
          .getByRole("button", { name: "確認撤回", exact: true })
          .click(),
      );
      assert(
        !(await api(c, "/listings?status=OPEN")).some(
          (x) => x.id === "request-main",
        ),
      );
      await p.goto(base + "/orders");
      await p.getByRole("heading", { name: "我的刊登", exact: true }).waitFor();
      await p.locator(".order-row").filter({ hasText: changed.title }).click();
      await action(p, "/listings/request-main/reopen", () =>
        p.getByRole("button", { name: "重新公開" }).click(),
      );
      await action(p, "/proposals/recommended", () =>
        p.getByRole("button", { name: "選擇並生成方案" }).first().click(),
      );
      const id = await createAndSign(p);
      await p.getByRole("region", { name: "目前下一步" }).waitFor();
      await finish(p, id);
      await p.getByRole("heading", { name: "每份承諾已完成" }).waitFor();
      await balances(p, { zao: 85000, lin: 115000 });
    },
  );
  await scenario(
    "unsigned-cancel-recreate-complete",
    "cash",
    async (p, c) => {
      const q = await seededProposal(p, c);
      const old = await action(p, "/agreements", () =>
        p.getByRole("button", { name: "建立雙方協議" }).click(),
      );
      await p.waitForURL("**/orders/" + old.id);
      await action(p, `/agreements/${old.id}/confirm`, () =>
        p.getByRole("button", { name: "我確認此版本協議" }).click(),
      );
      await p.getByRole("button", { name: "撤回未生效協議" }).click();
      await action(p, `/agreements/${old.id}/cancel-draft`, () =>
        p
          .getByRole("dialog")
          .getByRole("button", { name: "提交", exact: true })
          .click(),
      );
      assert.equal((await api(c, "/agreements/" + old.id)).status, "CANCELLED");
      assert.equal((await api(c, "/me/mock-account")).reserved, 0);
      await p.getByRole("link", { name: "返回提案重新協商" }).click();
      assert.equal((await api(c, "/proposals/" + q.id)).agreement, null);
      const id = await createAndSign(p);
      await finish(p, id);
      await balances(p, { zao: 85000, lin: 115000 });
    },
    { width: 390, height: 844 },
  );
  assert.deepEqual(report.external, []);
  assert.deepEqual(report.pageErrors, []);
  report.completedAt = new Date().toISOString();
  report.passed = report.scenarios.every((s) => s.passed);
  fs.writeFileSync(`${out}/result.json`, JSON.stringify(report, null, 2));
  await browser.close();
  console.log("All", report.scenarios.length, "closed-loop scenarios passed");
})().catch(async (e) => {
  report.passed = false;
  report.error = e.stack;
  fs.writeFileSync(`${out}/result.json`, JSON.stringify(report, null, 2));
  console.error(e);
  if (browser) await browser.close();
  process.exit(1);
});
