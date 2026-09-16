import { describe, expect, it } from "vitest";
import { CONTINENT_CENTER, CONTINENT_ZOOM, initialMapCamera } from "./mapCamera";

const pei = [-64.45, 45.9, -61.9, 47.1];

describe("initialMapCamera", () => {
  it("fits a small extract even when the URL is a continental overview", () => {
    const camera = initialMapCamera({ lat: 47.85, lng: -101.64, z: 3.42 }, pei);
    expect(camera).toEqual({
      kind: "bounds",
      bounds: [
        [-64.45, 45.9],
        [-61.9, 47.1],
      ],
    });
  });

  it("keeps a zoomed URL when the extract is continental", () => {
    const camera = initialMapCamera({ lat: 46.24, lng: -63.13, z: 9 }, [-168, 24, -52, 83.5]);
    expect(camera).toEqual({ kind: "center", center: [-63.13, 46.24], zoom: 9 });
  });

  it("falls back to North America when no bounds or URL exist", () => {
    expect(initialMapCamera({}, null)).toEqual({
      kind: "center",
      center: CONTINENT_CENTER,
      zoom: CONTINENT_ZOOM,
    });
  });
});
