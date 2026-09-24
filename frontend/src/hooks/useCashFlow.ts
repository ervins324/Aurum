import { useQuery } from "@tanstack/react-query";
import { fetchCashFlow } from "@/api/cashFlow";

export function useCashFlow(startDate?: string, endDate?: string, excludeTransfers?: boolean) {
  return useQuery({
    queryKey: ["cash-flow", startDate, endDate, excludeTransfers],
    queryFn: () => fetchCashFlow(startDate, endDate, excludeTransfers),
  });
}
