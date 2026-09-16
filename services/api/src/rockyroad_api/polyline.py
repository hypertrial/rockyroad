from __future__ import annotations


def decode_polyline(encoded: str, precision: int = 6) -> list[list[float]]:
    coordinates: list[list[float]] = []
    index = 0
    lat = 0
    lng = 0
    factor = 10**precision
    while index < len(encoded):
        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        result = 0
        shift = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        coordinates.append([lng / factor, lat / factor])
    return coordinates
