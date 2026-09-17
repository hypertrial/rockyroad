import { ListOrdered, Route as RouteIcon, Search, Signpost } from "lucide-react";
import type { KeyboardEvent } from "react";
import type { PlannerSearch } from "../lib/types";

export type PlannerPanel = NonNullable<PlannerSearch["panel"]>;

const items: Array<{
  value: PlannerPanel;
  label: string;
  Icon: typeof Search;
}> = [
  { value: "search", label: "Search", Icon: Search },
  { value: "stops", label: "Stops", Icon: ListOrdered },
  { value: "options", label: "Route", Icon: RouteIcon },
  { value: "directions", label: "Directions", Icon: Signpost },
];

type Props = {
  active: PlannerPanel;
  onChange: (panel: PlannerPanel) => void;
};

export function PlannerTabs({ active, onChange }: Props) {
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % items.length;
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + items.length) % items.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = items.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const next = items[nextIndex];
    onChange(next.value);
    document.getElementById(`planner-tab-${next.value}`)?.focus();
  };

  return (
    <div className="planner-tabs" role="tablist" aria-label="Trip planning tools">
      {items.map(({ value, label, Icon }, index) => (
        <button
          key={value}
          id={`planner-tab-${value}`}
          type="button"
          role="tab"
          aria-selected={active === value}
          aria-controls="planner-tabpanel"
          tabIndex={active === value ? 0 : -1}
          onClick={() => onChange(value)}
          onKeyDown={(event) => onKeyDown(event, index)}
        >
          <Icon aria-hidden="true" size={18} />
          <span>{label}</span>
        </button>
      ))}
    </div>
  );
}
