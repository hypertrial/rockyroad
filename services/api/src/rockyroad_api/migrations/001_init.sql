CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS trip_stops (
    id UUID PRIMARY KEY,
    trip_id UUID NOT NULL,
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    lon DOUBLE NOT NULL,
    lat DOUBLE NOT NULL,
    place_id TEXT,
    created_at TIMESTAMP NOT NULL,
    UNIQUE (trip_id, position)
);

CREATE TABLE IF NOT EXISTS trip_settings (
    trip_id UUID PRIMARY KEY,
    avoid_tolls BOOLEAN NOT NULL DEFAULT FALSE,
    avoid_highways BOOLEAN NOT NULL DEFAULT FALSE,
    avoid_ferries BOOLEAN NOT NULL DEFAULT FALSE,
    costing TEXT NOT NULL DEFAULT 'auto',
    optimize BOOLEAN NOT NULL DEFAULT FALSE,
    selected_alternative INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS route_legs (
    id UUID PRIMARY KEY,
    trip_id UUID NOT NULL,
    cache_key TEXT NOT NULL,
    data_version TEXT NOT NULL,
    alternative_index INTEGER NOT NULL DEFAULT 0,
    geometry JSON NOT NULL,
    distance_m DOUBLE NOT NULL,
    duration_s DOUBLE NOT NULL,
    maneuvers JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_places (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    lon DOUBLE NOT NULL,
    lat DOUBLE NOT NULL,
    place_id TEXT,
    notes TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS recent_searches (
    id UUID PRIMARY KEY,
    query TEXT NOT NULL,
    result_place_id TEXT,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS geo_meta (
    dataset TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    imported_at TIMESTAMP NOT NULL,
    row_count BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS geo_features (
    id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    search_text TEXT NOT NULL,
    feature_type TEXT NOT NULL,
    lon DOUBLE NOT NULL,
    lat DOUBLE NOT NULL,
    population BIGINT,
    population_score DOUBLE NOT NULL,
    importance DOUBLE NOT NULL,
    type_prior DOUBLE NOT NULL,
    admin_level TEXT
);

CREATE INDEX IF NOT EXISTS trip_stops_trip_id ON trip_stops(trip_id);
CREATE INDEX IF NOT EXISTS route_legs_trip_id ON route_legs(trip_id);
