import { useQuery } from "@tanstack/react-query";
import { Link, Outlet } from "@tanstack/react-router";
import { api } from "../lib/api";

export function AppShell() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: false });
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <strong>RockyRoad</strong>
          <span>{health.data?.provider_mode === "hosted" ? "Canada + USA" : "Canada + USA, offline"}</span>
        </Link>
        <div className="health-pill" role="status">
          {health.data?.detail ?? (health.data?.status === "ok" ? "Ready" : "Checking local data")}
        </div>
      </header>
      <Outlet />
    </div>
  );
}
