import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteIntegration,
  fetchIntegrations,
  setBybitIntegration,
  setMonobankIntegration,
  syncIntegration,
} from "@/api/integrations";
import type { BybitIntegrationInput, MonobankIntegrationInput, MonobankSyncRequest } from "@/types";

const QUERY_KEY = ["integrations"];

export function useIntegrations() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: fetchIntegrations,
    refetchInterval: (query) => {
      const isAnySyncing = query.state.data?.some((i) => i.is_syncing);
      return isAnySyncing ? 1000 : false;
    },
  });
}

export function useSetMonobankIntegration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: MonobankIntegrationInput) => setMonobankIntegration(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });
}

export function useSetBybitIntegration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: BybitIntegrationInput) => setBybitIntegration(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });
}

export function useDeleteIntegration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (provider: string) => deleteIntegration(provider),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEY }),
  });
}

export function useSyncIntegration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, body }: { provider: string; body?: MonobankSyncRequest }) =>
      syncIntegration(provider, body),
    // Invalidate transactions list after a sync so new data shows up immediately
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
    },
  });
}
