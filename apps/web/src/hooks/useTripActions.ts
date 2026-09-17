import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { api } from "../lib/api";
import type { RouteResponse, Stop, Trip, TripSettings, TripSummary } from "../lib/types";
import type { StopDraft } from "../lib/mapInteraction";

type MutationContext = { previous?: Trip };
type EditableSettings = Pick<
  TripSettings,
  "avoid_tolls" | "avoid_highways" | "avoid_ferries" | "costing" | "optimize" | "selected_alternative"
>;

function editableSettings(settings: TripSettings, patch: Partial<EditableSettings> = {}): EditableSettings {
  return {
    avoid_tolls: settings.avoid_tolls,
    avoid_highways: settings.avoid_highways,
    avoid_ferries: settings.avoid_ferries,
    costing: settings.costing,
    optimize: settings.optimize,
    selected_alternative: settings.selected_alternative,
    ...patch,
  };
}

function optimisticStops(trip: Trip, drafts: StopDraft[]): Stop[] {
  const currentById = new Map(trip.stops.map((stop) => [stop.id, stop]));
  const createdAt = new Date().toISOString();
  return drafts.map((draft, position) => {
    const id = draft.id ?? crypto.randomUUID();
    const current = currentById.get(id);
    return {
      id,
      trip_id: trip.id,
      position,
      name: draft.name,
      lon: draft.lon,
      lat: draft.lat,
      place_id: draft.place_id,
      created_at: current?.created_at ?? createdAt,
    };
  });
}

export function useTripActions(tripId: string) {
  const queryClient = useQueryClient();
  const key = ["trip", tripId] as const;
  const stopWriteQueueRef = useRef<Promise<unknown>>(Promise.resolve());

  const currentTrip = () => {
    const trip = queryClient.getQueryData<Trip>(key);
    if (!trip) throw new Error("Trip data is not ready yet.");
    return trip;
  };

  const updateLists = () => void queryClient.invalidateQueries({ queryKey: ["trips"] });

  const stops = useMutation<Trip, Error, StopDraft[], MutationContext>({
    mutationFn: (next) => {
      const write = stopWriteQueueRef.current
        .catch(() => undefined)
        .then(() => api.replaceStops(tripId, next));
      stopWriteQueueRef.current = write;
      return write;
    },
    onMutate: async (next) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<Trip>(key);
      if (previous) {
        queryClient.setQueryData<Trip>(key, {
          ...previous,
          stops: optimisticStops(previous, next),
          route: null,
          updated_at: new Date().toISOString(),
        });
      }
      return { previous };
    },
    onError: (_error, _next, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSuccess: (trip) => {
      queryClient.setQueryData(key, trip);
      updateLists();
    },
  });

  const settings = useMutation<Trip, Error, Partial<EditableSettings>, MutationContext>({
    mutationFn: (patch) => {
      const trip = currentTrip();
      return api.updateTrip(tripId, { settings: editableSettings(trip.settings, patch) });
    },
    onMutate: async (patch) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<Trip>(key);
      if (previous) {
        queryClient.setQueryData<Trip>(key, {
          ...previous,
          settings: { ...previous.settings, ...patch, updated_at: new Date().toISOString() },
          route: patch.selected_alternative === undefined ? null : previous.route,
          updated_at: new Date().toISOString(),
        });
      }
      return { previous };
    },
    onError: (_error, _patch, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSuccess: (trip) => {
      queryClient.setQueryData(key, trip);
      updateLists();
    },
  });

  const name = useMutation<Trip, Error, string, MutationContext>({
    mutationFn: (nextName) => api.updateTrip(tripId, { name: nextName }),
    onMutate: async (nextName) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<Trip>(key);
      if (previous) queryClient.setQueryData<Trip>(key, { ...previous, name: nextName });
      return { previous };
    },
    onError: (_error, _nextName, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSuccess: (trip) => {
      queryClient.setQueryData(key, trip);
      updateLists();
    },
  });

  const route = useMutation<RouteResponse, Error, void>({
    mutationFn: () => api.routeTrip(tripId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: key });
      updateLists();
    },
  });

  const optimize = useMutation<RouteResponse, Error, void>({
    mutationFn: () => api.optimizeTrip(tripId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: key });
      updateLists();
    },
  });

  const remove = useMutation<void, Error, void>({
    mutationFn: () => api.deleteTrip(tripId),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: key });
      queryClient.setQueryData<TripSummary[]>(["trips"], (current) => current?.filter((trip) => trip.id !== tripId));
    },
  });

  const busy = stops.isPending || settings.isPending || name.isPending || route.isPending || optimize.isPending || remove.isPending;

  return {
    replaceStops: stops.mutateAsync,
    updateSettings: settings.mutateAsync,
    rename: name.mutateAsync,
    buildRoute: route.mutateAsync,
    optimizeRoute: optimize.mutateAsync,
    deleteTrip: remove.mutateAsync,
    busy,
    stopBusy: stops.isPending,
    settingsBusy: settings.isPending,
    nameBusy: name.isPending,
    routeBusy: route.isPending,
    optimizeBusy: optimize.isPending,
    deleteBusy: remove.isPending,
    stopError: stops.error,
    settingsError: settings.error,
    nameError: name.error,
    routeError: route.error,
    optimizeError: optimize.error,
    deleteError: remove.error,
    resetDelete: remove.reset,
  };
}
