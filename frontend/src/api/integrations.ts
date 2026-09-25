import { api } from "@/api/client";
import type {
  IntegrationStatus,
  IntegrationSyncResult,
  MonobankIntegrationInput,
  MonobankSyncRequest,
} from "@/types";

/** Fetch masked status for configured providers (Monobank). */
export function fetchIntegrations() {
  return api.get<IntegrationStatus[]>("/integrations");
}

/** Save or update Monobank credentials. */
export function setMonobankIntegration(input: MonobankIntegrationInput) {
  return api.put<IntegrationStatus>("/integrations/monobank", input);
}

/** Remove stored credentials for a provider. */
export function deleteIntegration(provider: string) {
  return api.delete<void>(`/integrations/${provider}`);
}

/** Trigger a sync for a provider. Returns a result summary.
 *  For Monobank, an optional body with sync_from / sync_to narrows the window. */
export function syncIntegration(provider: string, body?: MonobankSyncRequest) {
  return api.post<IntegrationSyncResult>(`/integrations/${provider}/sync`, body ?? {});
}
