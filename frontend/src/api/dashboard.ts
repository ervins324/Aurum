import { api } from "@/api/client";
import type { DashboardSummary } from "@/types";

export function fetchDashboardSummary(year: number, month: number, excludeTransfers?: boolean) {
  const query = excludeTransfers ? `&exclude_transfers=true` : "";
  return api.get<DashboardSummary>(`/dashboard/summary?year=${year}&month=${month}${query}`);
}
