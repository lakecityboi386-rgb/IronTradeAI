import { test, expect } from "@playwright/test";
test("office renders eight workstations; sections and safe paper preview work", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "3D Trading Floor", exact: true }),
  ).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible();
  await expect(
    page.getByText("LOCAL ENGINE CONNECTED", { exact: false }),
  ).toBeVisible();
  await page.waitForTimeout(2500);
  await page.screenshot({
    path: "test-results/nightshift-office.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Bot Team", exact: false })
    .first()
    .click();
  for (const name of [
    "Market Scout",
    "Technical Analyst",
    "Wallet Tracker",
    "Liquidity Analyst",
    "Risk Officer",
    "Execution Specialist",
    "Momentum Maverick",
    "Mean Reversion Quant",
  ])
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  await page
    .getByRole("button", { name: "Manual Trading", exact: false })
    .click();
  await page.getByRole("button", { name: "Preview paper buy" }).click();
  await expect(page.getByRole("heading", { name: /BTC-USD/ })).toBeVisible();
  await expect(page.getByText("Confidence: uncalibrated")).toBeVisible();
  await page
    .getByRole("button", { name: "Live Trading", exact: false })
    .click();
  await expect(
    page.getByText("ACTIVATION LOCKED", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Live trading unavailable" }),
  ).toBeDisabled();
  expect(errors).toEqual([]);
});
test("kill switch persists and can be resumed", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByText("LOCAL ENGINE CONNECTED", { exact: false }),
  ).toBeVisible();
  const stop = page.getByRole("button", {
    name: "Emergency stop",
    exact: false,
  });
  if (await stop.count()) await stop.click();
  await expect(
    page.getByRole("button", { name: "Resume entries" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Resume entries" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Resume entries" }).click();
  await expect(
    page.getByRole("button", { name: "Emergency stop", exact: false }),
  ).toBeVisible();
});

test("research comparison displays holdout evidence without promotion controls", async ({
  page,
}) => {
  // Explicit mocked research result: never shown in the actual application without this test route.
  await page.route("**/api/research", (route) =>
    route.fulfill({
      json: {
        bot: "Market Scout",
        status: "Research comparison only. No promotion.",
        training_candles: 210,
        holdout_candles: 90,
        assumptions: "Test fixture: fees and slippage included",
        results: {
          champion: {
            training: { trades: 10, net: 1 },
            holdout: { trades: 3, net: -0.2 },
          },
          challenger: {
            training: { trades: 4, net: 0.2 },
            holdout: { trades: 1, net: -0.1 },
          },
        },
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByText("LOCAL ENGINE CONNECTED", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Bot Leaderboard", exact: false })
    .click();
  await expect(
    page.getByRole("heading", { name: "Champion / challenger research" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Market Scout", exact: true }).click();
  await expect(
    page.getByText("3 holdout trades", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("Research comparison only. No promotion.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /promote/i })).toHaveCount(0);
});
