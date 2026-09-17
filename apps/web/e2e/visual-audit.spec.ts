import { expect, test } from "@playwright/test";
import { mockRockyRoad } from "./fixtures";

test("capture the manual visual comparison matrix outside Git", async ({ page }, testInfo) => {
  test.skip(!process.env.ROCKYROAD_VISUAL_AUDIT, "Run explicitly when refreshing manual UI evidence.");

  await mockRockyRoad(page, {
    manyStops: true,
    routeReady: true,
    longDirections: true,
    providerMode: "local",
    tripName: "The trans-island slow road with every scenic detour",
  });

  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Plan the long way around." })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("360x800-dashboard.png"), fullPage: true });

  await page.setViewportSize({ width: 768, height: 1024 });
  await page.goto("/trips/trip-1?panel=stops&stop=stop-extra-5");
  await expect(page.getByRole("heading", { name: "Stops" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Interactive trip map" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("768x1024-many-stops-local.png"), fullPage: true });

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/trips/trip-1?panel=directions");
  await expect(page.getByRole("heading", { name: "Directions" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("1280x720-long-directions.png"), fullPage: true });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/trips/trip-1?panel=options");
  await expect(page.getByRole("heading", { name: "Route preferences" })).toBeVisible();
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "200%";
  });
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await page.screenshot({ path: testInfo.outputPath("1440x900-text-200-percent.png"), fullPage: true });
});
