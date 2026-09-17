import { BadgeDollarSign, Route, Ship } from "lucide-react";
import type { Trip } from "../lib/types";
import { StatusNotice } from "./StatusNotice";

type Props = {
  trip: Trip;
  disabled?: boolean;
  pending?: boolean;
  error?: string | null;
  onToggle: (key: "avoid_tolls" | "avoid_highways" | "avoid_ferries") => void;
};

export function RouteOptions({ trip, disabled = false, pending = false, error, onToggle }: Props) {
  return (
    <section className="planner-tool" aria-labelledby="route-options-heading">
      <div className="tool-heading">
        <span className="eyebrow">Shape the drive</span>
        <h2 id="route-options-heading">Route preferences</h2>
        <p className="muted">Choose what RockyRoad should avoid when it builds the route.</p>
      </div>
      <div className="settings-list">
        <label className="setting-row">
          <span className="setting-icon"><BadgeDollarSign aria-hidden="true" size={19} /></span>
          <span><strong>Avoid tolls</strong><small>Prefer roads without toll charges.</small></span>
          <input type="checkbox" checked={trip.settings.avoid_tolls} disabled={disabled} onChange={() => onToggle("avoid_tolls")} />
        </label>
        <label className="setting-row">
          <span className="setting-icon"><Route aria-hidden="true" size={19} /></span>
          <span><strong>Avoid highways</strong><small>Favor secondary and local roads.</small></span>
          <input type="checkbox" checked={trip.settings.avoid_highways} disabled={disabled} onChange={() => onToggle("avoid_highways")} />
        </label>
        <label className="setting-row">
          <span className="setting-icon"><Ship aria-hidden="true" size={19} /></span>
          <span><strong>Avoid ferries</strong><small>Keep the route on connected roads.</small></span>
          <input type="checkbox" checked={trip.settings.avoid_ferries} disabled={disabled} onChange={() => onToggle("avoid_ferries")} />
        </label>
      </div>
      <div className="mutation-status" aria-live="polite">{pending ? "Saving route preferences…" : ""}</div>
      {error ? <StatusNotice variant="error">{error}</StatusNotice> : null}
    </section>
  );
}
