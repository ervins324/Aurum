import { useQuery } from "@tanstack/react-query";
import { fetchDashboardSummary } from "@/api/dashboard";

export function useDashboardSummary(year: number, month: number, excludeTransfers?: boolean) {
  return useQuery({
    queryKey: ["dashboard-summary", year, month, excludeTransfers],
    queryFn: () => fetchDashboardSummary(year, month, excludeTransfers),
  });
}
