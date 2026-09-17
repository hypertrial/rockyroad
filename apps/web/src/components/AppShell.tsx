import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "@tanstack/react-router";
import { CircleCheck, Cloud, CloudOff, Mountain, TriangleAlert } from "lucide-react";
import { api } from "../lib/api";

export function AppShell() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  const hosted = health.data?.provider_mode === "hosted";
  const degraded = health.isError || health.data?.status === "degraded";
  const statusLabel = health.isPending
    ? "Checking services"
    : degraded
      ? "Needs attention"
      : hosted
        ? "Services ready"
        : "Offline data ready";

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <header className="app-header">
        <Link to="/" className="brand" aria-label="RockyRoad trips">
          <span className="brand-mark" aria-hidden="true">
            <Mountain size={23} strokeWidth={2.25} />
          </span>
          <span className="brand-copy">
            <strong>RockyRoad</strong>
            <span>{hosted ? "Canada + USA" : "Local road-trip planner"}</span>
          </span>
        </Link>
        <div className={`service-status${degraded ? " service-status-warning" : ""}`} role="status">
          {degraded ? (
            <TriangleAlert aria-hidden="true" size={17} />
          ) : health.isPending ? (
            <Cloud aria-hidden="true" size={17} />
          ) : (
            <CircleCheck aria-hidden="true" size={17} />
          )}
          <span>{statusLabel}</span>
        </div>
      </header>
      {degraded ? (
        <div className="service-banner" role="alert">
          <CloudOff aria-hidden="true" size={18} />
          <span>{health.data?.detail ?? "RockyRoad cannot reach its local API. Some planning tools are unavailable."}</span>
          <button type="button" disabled={health.isFetching} onClick={() => void health.refetch()}>
            {health.isFetching ? "Checking…" : "Check again"}
          </button>
        </div>
      ) : null}
      <Outlet />
    </div>
  );
}
