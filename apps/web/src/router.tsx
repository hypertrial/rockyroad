import { createRootRoute, createRoute, createRouter, lazyRouteComponent } from "@tanstack/react-router";
import { AppShell } from "./components/AppShell";
import { validatePlannerSearch } from "./lib/searchParams";
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
  component: lazyRouteComponent(() => import("./pages/PlannerPage"), "PlannerPage"),
  pendingComponent: () => (
    <main id="main-content" className="planner-loading" aria-label="Loading planner" tabIndex={-1}>
      <div className="planner-loading-panel">
        <span className="skeleton skeleton-title" />
        <span className="skeleton skeleton-line" />
      </div>
      <div className="planner-loading-map" />
    </main>
  ),
});

const routeTree = rootRoute.addChildren([indexRoute, tripRoute]);

export const router = createRouter({ routeTree });
export { tripRoute };

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
