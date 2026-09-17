import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { ChevronDown, ChevronUp, GripVertical, LocateFixed, PencilLine, Trash2 } from "lucide-react";
import type { CSSProperties } from "react";
import type { Stop, Trip } from "../lib/types";

export type DraftStop = Pick<Stop, "name" | "lon" | "lat" | "place_id"> & { id?: string };

type Props = {
  trip: Trip;
  selectedStopId: string | null;
  disabled?: boolean;
  onChange: (stops: DraftStop[]) => void;
  onSelect: (id: string) => void;
  onReplace: (id: string) => void;
  onRemove: (id: string) => void;
};

function toDrafts(stops: Stop[]): DraftStop[] {
  return stops.map(({ id, name, lon, lat, place_id }) => ({ id, name, lon, lat, place_id }));
}

type SortableStopProps = {
  stop: Stop;
  index: number;
  total: number;
  selected: boolean;
  disabled: boolean;
  onMove: (index: number, direction: -1 | 1) => void;
  onSelect: (id: string) => void;
  onReplace: (id: string) => void;
  onRemove: (id: string) => void;
};

function SortableStop({
  stop,
  index,
  total,
  selected,
  disabled,
  onMove,
  onSelect,
  onReplace,
  onRemove,
}: SortableStopProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: stop.id,
    disabled,
  });
  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className="stop-card"
      data-selected={selected}
      data-dragging={isDragging}
    >
      <button
        type="button"
        className="stop-drag-handle"
        aria-label={`Reorder ${stop.name}`}
        disabled={disabled}
        {...attributes}
        {...listeners}
      >
        <GripVertical aria-hidden="true" size={20} />
      </button>
      <button type="button" className="stop-main" onClick={() => onSelect(stop.id)} aria-pressed={selected}>
        <span className="stop-index" aria-hidden="true">{index + 1}</span>
        <span className="stop-copy">
          <strong>{stop.name}</strong>
          <span>{stop.lat.toFixed(3)}, {stop.lon.toFixed(3)}</span>
        </span>
        <LocateFixed aria-hidden="true" size={18} />
      </button>
      <div className="stop-actions" aria-label={`Actions for ${stop.name}`}>
        <button type="button" className="icon-button" aria-label={`Move ${stop.name} up`} disabled={disabled || index === 0} onClick={() => onMove(index, -1)}>
          <ChevronUp aria-hidden="true" size={18} />
        </button>
        <button type="button" className="icon-button" aria-label={`Move ${stop.name} down`} disabled={disabled || index === total - 1} onClick={() => onMove(index, 1)}>
          <ChevronDown aria-hidden="true" size={18} />
        </button>
        <button type="button" className="icon-button" aria-label={`Change location for ${stop.name}`} disabled={disabled} onClick={() => onReplace(stop.id)}>
          <PencilLine aria-hidden="true" size={17} />
        </button>
        <button type="button" className="icon-button stop-remove" aria-label={`Remove ${stop.name}`} disabled={disabled} onClick={() => onRemove(stop.id)}>
          <Trash2 aria-hidden="true" size={17} />
        </button>
      </div>
    </li>
  );
}

export function StopList({
  trip,
  selectedStopId,
  disabled = false,
  onChange,
  onSelect,
  onReplace,
  onRemove,
}: Props) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= trip.stops.length) return;
    onChange(arrayMove(toDrafts(trip.stops), index, target));
  };

  const onDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = trip.stops.findIndex((stop) => stop.id === active.id);
    const to = trip.stops.findIndex((stop) => stop.id === over.id);
    if (from < 0 || to < 0) return;
    onChange(arrayMove(toDrafts(trip.stops), from, to));
  };

  return (
    <section className="planner-tool" aria-labelledby="stops-heading">
      <div className="tool-heading tool-heading-with-count">
        <div>
          <span className="eyebrow">Your itinerary</span>
          <h2 id="stops-heading">Stops</h2>
        </div>
        <span className="count-badge" aria-label={`${trip.stops.length} stops`}>{trip.stops.length}</span>
      </div>
      {trip.stops.length === 0 ? (
        <div className="mini-empty-state">
          <LocateFixed aria-hidden="true" size={22} />
          <div>
            <strong>Add your first stop</strong>
            <span>Search for a place or click anywhere inside the map coverage.</span>
          </div>
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={trip.stops.map((stop) => stop.id)} strategy={verticalListSortingStrategy}>
            <ol className="stop-list">
              {trip.stops.map((stop, index) => (
                <SortableStop
                  key={stop.id}
                  stop={stop}
                  index={index}
                  total={trip.stops.length}
                  selected={selectedStopId === stop.id}
                  disabled={disabled}
                  onMove={move}
                  onSelect={onSelect}
                  onReplace={onReplace}
                  onRemove={onRemove}
                />
              ))}
            </ol>
          </SortableContext>
        </DndContext>
      )}
    </section>
  );
}
