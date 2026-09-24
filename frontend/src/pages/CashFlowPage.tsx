import { useState } from "react";
import { PillSelector } from "@/components/layout/PillSelector";
import { YearRangeSelector } from "@/components/layout/YearSelector";
import { CashFlowChart } from "@/components/cashflow/CashFlowChart";
import { useCashFlow } from "@/hooks/useCashFlow";
import { useTransactionYears } from "@/hooks/useTransactions";
import { computeRange, type CustomYearRange, type RangePreset } from "@/lib/dateRange";
import { useTranslation } from "@/lib/i18n";

import { useExcludeTransfers } from "@/hooks/useExcludeTransfers";

export function CashFlowPage() {
  const { t } = useTranslation();
  const now = new Date();
  const { data: years } = useTransactionYears();
  const [range, setRange] = useState<RangePreset>("this_year");
  const [customRange, setCustomRange] = useState<CustomYearRange>({
    fromYear: now.getFullYear(),
    toYear: now.getFullYear(),
  });
  const [excludeTransfers, setExcludeTransfers] = useExcludeTransfers();

  const RANGE_OPTIONS: Array<{ value: RangePreset; label: string }> = [
    { value: "all", label: t("reports.rangeAll") },
    { value: "this_year", label: t("reports.rangeThisYear") },
    { value: "5y", label: t("reports.range5y") },
    { value: "custom", label: t("reports.rangeCustom") },
  ];

  const { startDate, endDate } = computeRange(range, customRange);
  const { data: cashFlow, isLoading } = useCashFlow(startDate, endDate, excludeTransfers);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 cursor-pointer text-sm text-text-secondary select-none">
          <input
            type="checkbox"
            checked={excludeTransfers}
            onChange={(e) => setExcludeTransfers(e.target.checked)}
            className="rounded border-gridline text-primary focus:ring-primary h-4 w-4"
          />
          <span title={t("cashFlow.excludeTransfersHint")}>
            {t("cashFlow.excludeTransfers")}
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <PillSelector options={RANGE_OPTIONS} value={range} onChange={setRange} />
          {range === "custom" && (
            <YearRangeSelector
              years={years ?? [now.getFullYear()]}
              fromYear={customRange.fromYear}
              toYear={customRange.toYear}
              onChange={setCustomRange}
            />
          )}
        </div>
      </div>

      <CashFlowChart cashFlow={cashFlow} isLoading={isLoading} />
    </div>
  );
}
