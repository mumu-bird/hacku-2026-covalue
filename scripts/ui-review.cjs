/* Read-only UI review against a dedicated demo database, never reset the live app. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(
  process.env.HOURLINK_PLAYWRIGHT ||
    path.join(
      require("node:os").homedir(),
      ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright",
    ),
);
const base = process.env.HOURLINK_UI_URL || "http://127.0.0.1:8004";
const out = "artifacts/browser/ui-review";
const report = {
  startedAt: new Date().toISOString(),
  pages: [],
  pageErrors: [],
  external: [],
};
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    for (const width of [1440, 390]) {
      const c = await browser.newContext({
        viewport: { width, height: 1000 },
        timezoneId: "Asia/Hong_Kong",
        reducedMotion: "reduce",
      });
      await c.route("**/*", (route) => {
        if (
          !["127.0.0.1", "localhost"].includes(
            new URL(route.request().url()).hostname,
          )
        ) {
          report.external.push(route.request().url());
          return route.abort();
        }
        return route.continue();
      });
      const login = await c.request.post(base + "/api/v1/auth/demo-login", {
        data: { username: "zao", case: "cash" },
      });
      assert.equal(login.status(), 200);
      const p = await c.newPage();
      p.setDefaultTimeout(12000);
      p.on("pageerror", (e) => report.pageErrors.push(e.message));
      const proposals = await (
        await c.request.get(base + "/api/v1/me/proposals")
      ).json();
      const routes = [
        ["market", "/"],
        ["publish", "/publish"],
        ["listing", "/listing/request-main"],
        ["edit", "/listing/request-main/edit"],
        ["proposal", "/proposal/" + proposals[0].id],
        ["orders", "/orders"],
        ["profile", "/me"],
        ["value-model", "/value-model"],
        ["mechanism", "/mechanism"],
        ["study", "/study"],
        ["demo", "/demo"],
      ];
      await c.request.post(base + "/api/v1/auth/demo-login", {
        data: { username: "zao", case: "withdrawal" },
      });
      const orders = await (
        await c.request.get(base + "/api/v1/me/orders")
      ).json();
      assert(orders.length);
      await c.request.post(base + "/api/v1/auth/demo-login", {
        data: { username: "zao", case: "cash" },
      });
      for (const [name, url] of [
        ...routes,
        ["order", "/orders/" + orders[0].id],
      ]) {
        if (name === "order")
          await c.request.post(base + "/api/v1/auth/demo-login", {
            data: { username: "zao", case: "withdrawal" },
          });
        await p.goto(base + url);
        await p.locator("main h1").waitFor();
        await p.waitForFunction(() => !document.querySelector(".loading"));
        await p.evaluate(() => document.fonts.ready);
        assert.equal(
          await p.evaluate(
            () => document.documentElement.scrollWidth > innerWidth,
          ),
          false,
          `${name}/${width} overflow`,
        );
        await p.screenshot({
          path: `${out}/${name}-${width}.png`,
          fullPage: true,
        });
        report.pages.push({ name, width, passed: true });
      }
      await c.request.post(base + "/api/v1/auth/demo-login", {
        data: { username: "zao", case: "cash" },
      });
      await c.route(base + "/api/v1/me/orders", (route) =>
        route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            code: "TEMPORARY",
            message: "暫時無法讀取訂單，請重試",
          }),
        }),
      );
      await p.goto(base + "/orders");
      await p
        .getByRole("alert")
        .filter({ hasText: "暫時無法讀取訂單" })
        .waitFor();
      await c.unroute(base + "/api/v1/me/orders");
      await p.getByRole("button", { name: "重新讀取", exact: true }).click();
      await p.getByRole("alert").waitFor({ state: "hidden" });
      report.pages.push({ name: "error-and-retry", width, passed: true });
      await c.close();
    }
    assert.deepEqual(report.pageErrors, []);
    assert.deepEqual(report.external, []);
    report.passed = true;
    report.completedAt = new Date().toISOString();
    console.log(
      JSON.stringify({
        passed: true,
        pages: report.pages.length,
        widths: [1440, 390],
      }),
    );
  } finally {
    fs.writeFileSync(out + "/result.json", JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
