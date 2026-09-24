import { useQuery } from "@tanstack/react-query";
import { fetchCategoryRanking, fetchCategorySpendingReport } from "@/api/reports";
import type { CategoryKind } from "@/types";

export function useCategorySpendingReport(categoryId: number | null, startDate?: string, endDate?: string) {
  return useQuery({
    queryKey: ["category-spending-report", categoryId, startDate, endDate],
    queryFn: () => fetchCategorySpendingReport(categoryId as number, startDate, endDate),
    enabled: categoryId !== null,
  });
}

export function useCategoryRanking(kind: CategoryKind, startDate?: string, endDate?: string, excludeTransfers?: boolean) {
  return useQuery({
    queryKey: ["category-ranking", kind, startDate, endDate, excludeTransfers],
    queryFn: () => fetchCategoryRanking(kind, startDate, endDate, excludeTransfers),
  });
}
