import { api } from "@/api/client";
import type {
  BybitIntegrationInput,
  IntegrationStatus,
  IntegrationSyncResult,
  MonobankIntegrationInput,
  MonobankSyncRequest,
} from "@/types";

/** Fetch masked status for all providers (monobank + bybit). */
export function fetchIntegrations() {
  return api.get<IntegrationStatus[]>("/integrations");
}

/** Save or update Monobank credentials. */
export function setMonobankIntegration(input: MonobankIntegrationInput) {
  return api.put<IntegrationStatus>("/integrations/monobank", input);
}

/** Save or update Bybit credentials. */
export function setBybitIntegration(input: BybitIntegrationInput) {
  return api.put<IntegrationStatus>("/integrations/bybit", input);
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
