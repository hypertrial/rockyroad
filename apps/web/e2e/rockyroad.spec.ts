import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { mockRockyRoad } from "./fixtures";

let browserErrors: string[] = [];
let expectedResourceErrors = 0;

test.beforeEach(async ({ page }) => {
  browserErrors = [];
  expectedResourceErrors = 0;
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => browserErrors.push(error.message));
});

test.afterEach(() => {
  const resourceErrors = browserErrors.filter((message) => message.startsWith("Failed to load resource:"));
  const unexpectedErrors = browserErrors.filter((message) => !message.startsWith("Failed to load resource:"));
  expect(unexpectedErrors).toEqual([]);
  expect(resourceErrors).toHaveLength(expectedResourceErrors);
});

async function expectNoSeriousAxeViolations(page: Parameters<typeof mockRockyRoad>[0]) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((violation) => violation.impact === "serious" || violation.impact === "critical")).toEqual([]);
}

async function expectNoHorizontalOverflow(page: Parameters<typeof mockRockyRoad>[0]) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

async function expectPlannerLockedToViewport(page: Parameters<typeof mockRockyRoad>[0]) {
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).toBe(true);
}

test("dashboard is responsive, accessible, and supports safe trip deletion", async ({ page }) => {
  expectedResourceErrors = 1;
  await page.setViewportSize({ width: 360, height: 800 });
  const state = await mockRockyRoad(page, { deleteFailureCount: 1 });
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Plan the long way around." })).toBeVisible();
  await expect(page.getByRole("link", { name: /Island slow road/ })).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await expectNoSeriousAxeViolations(page);

  await page.getByRole("button", { name: "Actions for Island slow road" }).click();
  const deleteButton = page.getByRole("button", { name: "Delete Island slow road" });
  await deleteButton.focus();
  await deleteButton.click();
  const dialog = page.getByRole("dialog", { name: "Delete this trip?" });
  await expect(dialog).toContainText("Island slow road");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(deleteButton).toBeFocused();

  await deleteButton.click();
  await dialog.getByRole("button", { name: "Delete trip" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Trip could not be deleted.");
  await expect(page.getByRole("link", { name: /Island slow road/ })).toBeVisible();
  expect(state.isDeleted()).toBe(false);

  await dialog.getByRole("button", { name: "Delete trip" }).click();
  await expect(page.getByText("Your first route starts here")).toBeVisible();
  expect(state.isDeleted()).toBe(true);
});

test("mobile planner keeps the map mounted through search, add, collapse, and route build", async ({ page }) => {
  expectedResourceErrors = 1;
  await page.setViewportSize({ width: 768, height: 1024 });
  const state = await mockRockyRoad(page, { routeFailureCount: 1 });
  await page.goto("/trips/trip-1?panel=stops&stop=stop-a&lat=46.8&lng=-62.5&z=7");

  const map = page.getByRole("region", { name: "Interactive trip map" });
  await expect(map).toBeVisible();
  await page.waitForTimeout(700);
  expect(Number(new URL(page.url()).searchParams.get("lat"))).toBeCloseTo(46.8, 2);
  expect(Number(new URL(page.url()).searchParams.get("lng"))).toBeCloseTo(-62.5, 2);
  const mapIdentity = await map.evaluate((element) => {
    element.setAttribute("data-e2e-persistent", "true");
    return element.getAttribute("data-e2e-persistent");
  });
  expect(mapIdentity).toBe("true");
  for (const selector of [".maplibregl-ctrl-zoom-in", ".maplibregl-ctrl-attrib-button"]) {
    const locator = page.locator(selector);
    await expect(locator).toBeAttached();
    const control = await locator.evaluate((element) => ({
      width: parseFloat(getComputedStyle(element).width),
      height: parseFloat(getComputedStyle(element).height),
    }));
    expect(control.width).toBeGreaterThanOrEqual(44);
    expect(control.height).toBeGreaterThanOrEqual(44);
  }
  await expect(page.locator(".maplibregl-ctrl-attrib-button")).toBeVisible();
  const attributionBox = await page.locator(".maplibregl-ctrl-attrib-button").boundingBox();
  const expandedSheetBox = await page.locator(".planner-panel").boundingBox();
  expect(attributionBox && expandedSheetBox && attributionBox.y + attributionBox.height <= expandedSheetBox.y).toBe(true);
  expect(await page.locator(".planner-actions").evaluate((element) => parseFloat(getComputedStyle(element).paddingBottom))).toBeGreaterThanOrEqual(13);

  const sheetToggle = page.getByRole("button", { name: "Collapse planner" });
  await expect(sheetToggle).toHaveAttribute("aria-expanded", "true");
  await sheetToggle.click();
  await expect(page.getByRole("button", { name: "Expand planner" })).toHaveAttribute("aria-expanded", "false");
  await page.getByRole("button", { name: "Expand planner" }).click();

  await page.getByRole("button", { name: "Remove Summerside" }).click();
  await expect(page.getByText("Summerside removed.")).toBeVisible();
  expect(state.getTrip().stops).toHaveLength(1);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("Summerside restored.")).toBeVisible();
  expect(state.getTrip().stops).toHaveLength(2);

  const moveSummersideEarlier = page.getByRole("button", { name: "Move Summerside up" });
  await moveSummersideEarlier.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => state.getTrip().stops[0]?.id).toBe("stop-b");
  const moveSummersideLater = page.getByRole("button", { name: "Move Summerside down" });
  await expect(moveSummersideLater).toBeEnabled();
  await moveSummersideLater.focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => state.getTrip().stops[0]?.id).toBe("stop-a");

  await page.getByRole("button", { name: "Change location for Charlottetown" }).click();
  await expect(page.getByRole("heading", { name: "Move Charlottetown" })).toBeVisible();
  await page.getByRole("searchbox", { name: "Search places" }).fill("Cavendish");
  await page.locator(".search-results > button", { hasText: "Cavendish National Park" }).click();
  await expect(page.getByRole("button", { name: "Expand planner" })).toBeFocused();
  expect(state.getTrip().stops).toHaveLength(2);
  expect(state.getTrip().stops[0]?.name).toBe("Cavendish National Park");
  await page.getByRole("button", { name: "Expand planner" }).click();

  const stopsTab = page.getByRole("tab", { name: "Stops" });
  await stopsTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Route" })).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "Search" }).click();
  await page.getByRole("searchbox", { name: "Search places" }).fill("Cavendish");
  await page.locator(".search-results > button", { hasText: "Cavendish National Park" }).click();
  await expect(page.getByRole("button", { name: "Expand planner" })).toBeFocused();
  expect(state.getTrip().stops).toHaveLength(3);

  await page.getByRole("button", { name: "Expand planner" }).click();
  await page.getByRole("button", { name: "Build route" }).click();
  await expect(page.getByRole("alert")).toContainText("Routing provider unavailable.");
  await expect(page.getByRole("button", { name: "Collapse planner" })).toBeVisible();
  await page.getByRole("button", { name: "Build route" }).click();
  await expect(page.getByRole("button", { name: "Expand planner" })).toBeVisible();
  await page.getByRole("button", { name: "Expand planner" }).click();
  await expect(page.getByRole("heading", { name: "Directions" })).toBeVisible();
  await expect(page.getByText("Head west on Water Street")).toBeVisible();
  await expect(map).toHaveAttribute("data-e2e-persistent", "true");
  await expectNoHorizontalOverflow(page);
  await expectPlannerLockedToViewport(page);
  await expectNoSeriousAxeViolations(page);
});

test("phone planner keeps every map control clear of the expanded sheet", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await mockRockyRoad(page);
  await page.goto("/trips/trip-1?panel=stops");

  await expect(page.getByRole("region", { name: "Interactive trip map" })).toBeVisible();
  const helpBox = await page.getByRole("button", { name: "Map help" }).boundingBox();
  const attribution = page.locator(".maplibregl-ctrl-attrib-button");
  await expect(attribution).toBeVisible();
  const attributionBox = await attribution.boundingBox();
  const zoomBox = await page.locator(".maplibregl-ctrl-zoom-in").boundingBox();
  const sheetBox = await page.locator(".planner-panel").boundingBox();

  expect(attributionBox?.width).toBeGreaterThanOrEqual(44);
  expect(attributionBox?.height).toBeGreaterThanOrEqual(44);
  expect(helpBox && attributionBox && helpBox.x + helpBox.width <= attributionBox.x).toBe(true);
  expect(attributionBox && zoomBox && attributionBox.x + attributionBox.width <= zoomBox.x).toBe(true);
  expect(attributionBox && sheetBox && attributionBox.y + attributionBox.height <= sheetBox.y).toBe(true);
  await expectNoHorizontalOverflow(page);
  await expectPlannerLockedToViewport(page);
});

test("planner survives invalid camera links and explains fatal map failures", async ({ page }) => {
  expectedResourceErrors = 1;
  const state = await mockRockyRoad(page, { mapStyleStatus: 500 });
  await page.goto("/trips/trip-1?lat=999&lng=-63&z=7");

  const map = page.getByRole("region", { name: "Interactive trip map" });
  await expect(map).toBeVisible();
  const banner = page.locator(".map-banner");
  await expect(banner).toContainText("map source is temporarily unavailable");
  await map.click({ position: { x: 140, y: 140 } });
  await page.waitForTimeout(300);
  await expect(banner).toContainText("map source is temporarily unavailable");
  expect(state.getStopReplacementRequestCount()).toBe(0);
  expect(state.getTrip().stops).toHaveLength(2);
  expect(browserErrors.some((message) => message.includes("Invalid LngLat"))).toBe(false);
});

test("planner renders initial markers when health resolves after the first render", async ({ page }) => {
  await mockRockyRoad(page, { healthDelayMs: 250 });
  await page.goto("/trips/trip-1?panel=stops");

  await expect(page.getByRole("region", { name: "Interactive trip map" })).toBeVisible();
  await expect(page.locator(".trip-marker")).toHaveCount(2);
});

test("desktop planner saves titles, exposes route failures, and keeps keyboard focus visible", async ({ page }) => {
  expectedResourceErrors = 1;
  await page.setViewportSize({ width: 1280, height: 720 });
  await mockRockyRoad(page, { routeSettingsFailure: true });
  await page.goto("/trips/trip-1?panel=options");

  const title = page.getByRole("textbox", { name: "Trip name" });
  await title.fill("A very long island road trip name that still fits the planning rail");
  await title.press("Enter");
  await expect(title).toHaveValue("A very long island road trip name that still fits the planning rail");
  await title.fill("   ");
  await title.press("Enter");
  await expect(title).toHaveValue("A very long island road trip name that still fits the planning rail");

  await page.getByRole("checkbox", { name: /Avoid tolls/ }).click();
  await expect(page.getByRole("alert")).toContainText("Route settings could not be saved.");

  await page.getByRole("tab", { name: "Route" }).focus();
  await page.keyboard.press("End");
  await expect(page.getByRole("tab", { name: "Directions" })).toBeFocused();
  await expect(page.getByRole("tab", { name: "Directions" })).toHaveCSS("outline-style", "solid");
  await expectNoHorizontalOverflow(page);
  await expectPlannerLockedToViewport(page);
  await expectNoSeriousAxeViolations(page);
});

test("degraded and empty dashboard states remain actionable", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockRockyRoad(page, { degraded: true, empty: true });
  await page.goto("/");

  await expect(page.getByRole("alert")).toContainText("Routing is unavailable");
  await expect(page.getByText("Your first route starts here")).toBeVisible();
  await page.getByLabel("Trip name").fill("Autumn coast");
  await page.getByRole("button", { name: "Create trip" }).click();
  await expect(page).toHaveURL(/\/trips\/trip-1/);
  await expect(page.getByRole("heading", { name: "Find a place" })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});

test("dashboard loading and API failure states resolve without layout replacement", async ({ page }) => {
  expectedResourceErrors = 2;
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1280, height: 720 });
  await mockRockyRoad(page, { tripListDelayMs: 250, tripListFailureCount: 2 });
  await page.goto("/");

  await expect(page.getByLabel("Loading trips")).toBeVisible();
  expect(
    await page.locator(".trip-card-skeleton").first().evaluate((element) =>
      parseFloat(getComputedStyle(element).animationDuration),
    ),
  ).toBeLessThanOrEqual(0.00001);
  await expect(page.getByRole("alert")).toContainText("Saved trips are temporarily unavailable.");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("link", { name: /Island slow road/ })).toBeVisible();
  await expectNoHorizontalOverflow(page);
});
