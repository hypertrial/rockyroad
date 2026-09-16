import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router";
import { AppShell } from "./components/AppShell";
import { validatePlannerSearch } from "./lib/searchParams";
import { PlannerPage } from "./pages/PlannerPage";
import { TripListPage } from "./pages/TripListPage";

const rootRoute = createRootRoute({
  component: AppShell,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: TripListPage,
});

const tripRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/trips/$tripId",
  validateSearch: validatePlannerSearch,
  component: PlannerPage,
});

const routeTree = rootRoute.addChildren([indexRoute, tripRoute]);

export const router = createRouter({ routeTree });
export { tripRoute };

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
