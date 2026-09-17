import { Clock3, Navigation, Route as RouteIcon } from "lucide-react";
import { formatDistance, formatDuration } from "../lib/format";
import type { Trip } from "../lib/types";
import { StatusNotice } from "./StatusNotice";

type Props = {
  trip: Trip;
  disabled?: boolean;
  pending?: boolean;
  error?: string | null;
  onSelectAlternative: (index: number) => void;
};

export function Directions({ trip, disabled = false, pending = false, error, onSelectAlternative }: Props) {
  const alternatives = trip.route?.alternatives ?? [];
  const selected = alternatives[trip.settings.selected_alternative] ?? alternatives[0];

  if (!selected) {
    return (
      <section className="planner-tool directions-empty" aria-labelledby="directions-heading">
        <span className="empty-state-icon" aria-hidden="true"><Navigation size={26} /></span>
        <h2 id="directions-heading">Directions will appear here</h2>
        <p className="muted">Add at least two stops, then build a route for turn-by-turn guidance.</p>
      </section>
    );
  }

  return (
    <section className="planner-tool" aria-labelledby="directions-heading">
      <div className="tool-heading">
        <span className="eyebrow">On the road</span>
        <h2 id="directions-heading">Directions</h2>
      </div>
      {alternatives.length > 1 ? (
        <div className="route-alternatives" aria-label="Route alternatives">
          {alternatives.map((item) => (
            <button
              key={item.index}
              type="button"
              className="route-alternative"
              aria-pressed={item.index === selected.index}
              disabled={disabled}
              onClick={() => onSelectAlternative(item.index)}
            >
              <span>Route {item.index + 1}</span>
              <strong>{formatDuration(item.duration_s)}</strong>
              <small>{formatDistance(item.distance_m)}</small>
            </button>
          ))}
        </div>
      ) : null}
      <div className="route-summary-card">
        <span><RouteIcon aria-hidden="true" size={18} /> {formatDistance(selected.distance_m)}</span>
        <span><Clock3 aria-hidden="true" size={18} /> {formatDuration(selected.duration_s)}</span>
      </div>
      <ol className="maneuver-list">
        {selected.maneuvers.map((maneuver, index) => (
          <li key={`${maneuver.begin_shape_index}-${index}`} className="maneuver">
            <span className="maneuver-number" aria-hidden="true">{index + 1}</span>
            <span className="maneuver-copy">{maneuver.instruction}</span>
            <span className="maneuver-distance">{formatDistance(maneuver.distance_m)}</span>
          </li>
        ))}
      </ol>
      <div className="mutation-status" aria-live="polite">{pending ? "Saving route choice…" : ""}</div>
      {error ? <StatusNotice variant="error">{error}</StatusNotice> : null}
    </section>
  );
}
