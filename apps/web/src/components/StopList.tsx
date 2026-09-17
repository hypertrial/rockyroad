import type { Stop, Trip } from "../lib/types";
import { useUiStore } from "../stores/ui";

type DraftStop = Pick<Stop, "name" | "lon" | "lat" | "place_id"> & { id?: string };

type Props = {
  trip: Trip;
  onChange: (stops: DraftStop[]) => void;
};

export function StopList({ trip, onChange }: Props) {
  const selectedStopId = useUiStore((state) => state.selectedStopId);
  const setSelectedStopId = useUiStore((state) => state.setSelectedStopId);

  const move = (index: number, direction: -1 | 1) => {
    const next = [...trip.stops];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    onChange(
      next.map((stop) => ({
        id: stop.id,
        name: stop.name,
        lon: stop.lon,
        lat: stop.lat,
        place_id: stop.place_id,
      })),
    );
  };

  const remove = (id: string) => {
    onChange(
      trip.stops
        .filter((stop) => stop.id !== id)
        .map((stop) => ({
          id: stop.id,
          name: stop.name,
          lon: stop.lon,
          lat: stop.lat,
          place_id: stop.place_id,
        })),
    );
  };

  return (
    <section className="panel">
      <h2>Stops</h2>
      {trip.stops.length === 0 ? (
        <p className="muted">Search or click the map to add a stop.</p>
      ) : null}
      <ol>
        {trip.stops.map((stop, index) => (
          <li key={stop.id}>
            <div className="stop-item" data-selected={selectedStopId === stop.id} onClick={() => setSelectedStopId(stop.id)}>
              <div>
                <strong>
                  {index + 1}. {stop.name}
                </strong>
                <div className="muted">
                  {stop.lat.toFixed(3)}, {stop.lon.toFixed(3)}
                </div>
              </div>
              <div className="stop-actions">
                <button type="button" className="ghost" onClick={() => move(index, -1)} aria-label={`Move ${stop.name} up`}>
                  Up
                </button>
                <button type="button" className="ghost" onClick={() => move(index, 1)} aria-label={`Move ${stop.name} down`}>
                  Down
                </button>
                <button type="button" className="ghost" onClick={() => remove(stop.id)} aria-label={`Remove ${stop.name}`}>
                  Remove
                </button>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
