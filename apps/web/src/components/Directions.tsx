import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatDistance, formatDuration } from "../lib/format";
import type { Trip } from "../lib/types";
import { useUiStore } from "../stores/ui";

type Props = {
  trip: Trip;
};

export function Directions({ trip }: Props) {
  const queryClient = useQueryClient();
  const setHovered = useUiStore((state) => state.setHoveredManeuverIndex);
  const update = useMutation({
    mutationFn: (index: number) =>
      api.updateTrip(trip.id, {
        settings: { ...trip.settings, selected_alternative: index },
      }),
    onSuccess: (next) => queryClient.setQueryData(["trip", trip.id], next),
  });

  const alternatives = trip.route?.alternatives ?? [];
  const selected = alternatives[trip.settings.selected_alternative] ?? alternatives[0];

  if (!selected) {
    return (
      <section className="panel">
        <h2>Directions</h2>
        <p className="muted">Build a route to see turn-by-turn instructions.</p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>Directions</h2>
      {alternatives.length > 1 ? (
        <div className="stack">
          {alternatives.map((item) => (
            <button
              key={item.index}
              type="button"
              className={item.index === selected.index ? undefined : "secondary"}
              onClick={() => update.mutate(item.index)}
            >
              Alt {item.index + 1}: {formatDuration(item.duration_s)}
            </button>
          ))}
        </div>
      ) : null}
      <p>
        {formatDistance(selected.distance_m)} · {formatDuration(selected.duration_s)}
      </p>
      <ol>
        {selected.maneuvers.map((maneuver, index) => (
          <li
            key={`${maneuver.begin_shape_index}-${index}`}
            className="maneuver"
            onMouseEnter={() => setHovered(index)}
            onMouseLeave={() => setHovered(null)}
          >
            <span>{maneuver.instruction}</span>
            <span className="muted">{formatDistance(maneuver.distance_m)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
