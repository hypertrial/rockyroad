export const EMPTY_MAP_STYLE = {
  version: 8 as const,
  name: "RockyRoad Empty",
  sources: {},
  layers: [
    {
      id: "background",
      type: "background" as const,
      paint: { "background-color": "#efe7d6" },
    },
  ],
};

export const LOCAL_TILE_STYLE = "/map/style.json";

export function plannerMapStyle(mapsAvailable: boolean) {
  return mapsAvailable ? LOCAL_TILE_STYLE : EMPTY_MAP_STYLE;
}
