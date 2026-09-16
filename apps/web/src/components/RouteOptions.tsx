import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Trip } from "../lib/types";

type Props = {
  trip: Trip;
};

export function RouteOptions({ trip }: Props) {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (settings: Partial<Trip["settings"]>) => api.updateTrip(trip.id, { settings }),
    onSuccess: (next) => queryClient.setQueryData(["trip", trip.id], next),
  });

  const toggle = (key: "avoid_tolls" | "avoid_highways" | "avoid_ferries") => {
    update.mutate({
      avoid_tolls: trip.settings.avoid_tolls,
      avoid_highways: trip.settings.avoid_highways,
      avoid_ferries: trip.settings.avoid_ferries,
      costing: trip.settings.costing,
      optimize: trip.settings.optimize,
      selected_alternative: trip.settings.selected_alternative,
      [key]: !trip.settings[key],
    });
  };

  return (
    <section className="panel">
      <h2>Route options</h2>
      <label className="checkbox">
        <input type="checkbox" checked={trip.settings.avoid_tolls} onChange={() => toggle("avoid_tolls")} />
        Avoid tolls
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={trip.settings.avoid_highways} onChange={() => toggle("avoid_highways")} />
        Avoid highways
      </label>
      <label className="checkbox">
        <input type="checkbox" checked={trip.settings.avoid_ferries} onChange={() => toggle("avoid_ferries")} />
        Avoid ferries
      </label>
    </section>
  );
}
