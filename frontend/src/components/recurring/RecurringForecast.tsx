import { useState, useMemo } from "react";
import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Coins,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { formatCurrency, getIntlLocale } from "@/lib/format";
import { useTranslation, type TranslationKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { RecurringTransaction, RecurringFrequency } from "@/types";

// ---------------------------------------------------------------------------
// Client-side advance logic — mirrors backend services/recurring_service._advance
// ---------------------------------------------------------------------------

export function advanceDate(d: Date, frequency: RecurringFrequency): Date {
  const result = new Date(d);
  if (frequency === "weekly") {
    result.setDate(result.getDate() + 7);
  } else if (frequency === "monthly") {
    const day = result.getDate();
    result.setMonth(result.getMonth() + 1, 1);
    const lastDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate();
    result.setDate(Math.min(day, lastDay));
  } else {
    // yearly
    const day = result.getDate();
    const month = result.getMonth();
    const nextYear = result.getFullYear() + 1;
    const lastDay = new Date(nextYear, month + 1, 0).getDate();
    result.setFullYear(nextYear, month, Math.min(day, lastDay));
  }
  return result;
}

/** Compute all occurrence dates for a recurring item within [today, cutoffDate]. */
export function getOccurrences(item: RecurringTransaction, cutoffDate: Date): Date[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  let current = new Date(`${item.next_due_date}T00:00:00`);
  const occurrences: Date[] = [];

  while (current <= cutoffDate) {
    if (current >= today) {
      occurrences.push(new Date(current));
    }
    current = advanceDate(current, item.frequency);
  }

  return occurrences;
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

const intlLocale = getIntlLocale();

function formatMonthHeading(date: Date): string {
  return new Intl.DateTimeFormat(intlLocale, { month: "long", year: "numeric" }).format(date);
}

function formatDay(date: Date): string {
  return new Intl.DateTimeFormat(intlLocale, { day: "numeric", month: "short" }).format(date);
}

// ---------------------------------------------------------------------------
// Data structures & aggregation
// ---------------------------------------------------------------------------

export interface ForecastEntry {
  item: RecurringTransaction;
  date: Date;
}

export interface MonthGroup {
  key: string;
  heading: string;
  totalIncome: number;
  totalExpense: number;
  net: number;
  entries: ForecastEntry[];
}

export function buildForecast(items: RecurringTransaction[], months: number): MonthGroup[] {
  const cutoff = new Date();
  cutoff.setHours(0, 0, 0, 0);
  cutoff.setMonth(cutoff.getMonth() + months);

  const allEntries: ForecastEntry[] = [];

  for (const item of items) {
    if (!item.is_active) continue;
    const occurrences = getOccurrences(item, cutoff);
    for (const date of occurrences) {
      allEntries.push({ item, date });
    }
  }

  allEntries.sort((a, b) => a.date.getTime() - b.date.getTime());

  const groups = new Map<string, MonthGroup>();
  for (const entry of allEntries) {
    const year = entry.date.getFullYear();
    const month = entry.date.getMonth();
    const key = `${year}-${String(month + 1).padStart(2, "0")}`;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        heading: formatMonthHeading(entry.date),
        totalIncome: 0,
        totalExpense: 0,
        net: 0,
        entries: [],
      });
    }

    const group = groups.get(key)!;
    group.entries.push(entry);

    const amount = Number(entry.item.amount) || 0;
    if (entry.item.type === "income") {
      group.totalIncome += amount;
      group.net += amount;
    } else if (entry.item.type === "expense") {
      group.totalExpense += amount;
      group.net -= amount;
    }
  }

  return Array.from(groups.values());
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface RecurringForecastProps {
  items: RecurringTransaction[];
}

const MIN_MONTHS = 1;
const MAX_MONTHS = 24;
const DEFAULT_MONTHS = 3;
const PRESET_HORIZONS = [1, 3, 6, 12];

export function RecurringForecast({ items }: RecurringForecastProps) {
  const { t } = useTranslation();
  const [months, setMonths] = useState<number>(DEFAULT_MONTHS);
  const [expandedMonths, setExpandedMonths] = useState<Record<string, boolean>>({});

  const activeItems = useMemo(() => items.filter((i) => i.is_active), [items]);
  const groups = useMemo(() => buildForecast(activeItems, months), [activeItems, months]);

  const totals = useMemo(() => {
    let income = 0;
    let expense = 0;
    for (const g of groups) {
      income += g.totalIncome;
      expense += g.totalExpense;
    }
    return {
      income,
      expense,
      net: income - expense,
      monthlyAvgNet: months > 0 ? (income - expense) / months : 0,
    };
  }, [groups, months]);

  if (activeItems.length === 0) {
    return null;
  }

  function toggleMonth(key: string) {
    setExpandedMonths((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <Card className="overflow-hidden border border-gridline bg-surface-1 shadow-sm">
      <CardHeader className="border-b border-gridline bg-surface-2/40 pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Coins size={18} />
            </span>
            <div>
              <CardTitle className="text-base font-semibold text-text-primary">
                {t("recurring.forecast.title")}
              </CardTitle>
              <p className="text-xs text-text-muted">
                {t("recurring.forecast.transactionsCount", { count: activeItems.length })}
              </p>
            </div>
          </div>

          {/* Horizon Presets + Custom Input */}
          <div className="flex items-center gap-1.5 self-start sm:self-auto">
            <div className="flex rounded-lg border border-gridline bg-surface-1 p-0.5">
              {PRESET_HORIZONS.map((h) => (
                <button
                  key={h}
                  type="button"
                  onClick={() => setMonths(h)}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                    months === h
                      ? "bg-primary text-white shadow-sm"
                      : "text-text-muted hover:text-text-primary"
                  )}
                >
                  {h}M
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1 pl-1">
              <Input
                id="forecast-months"
                type="number"
                min={MIN_MONTHS}
                max={MAX_MONTHS}
                step={1}
                value={months}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  if (val >= MIN_MONTHS && val <= MAX_MONTHS) {
                    setMonths(val);
                  }
                }}
                className="h-8 w-14 px-1.5 py-1 text-center text-xs font-semibold"
                aria-label={t("recurring.forecast.monthsLabel")}
              />
              <span className="text-xs text-text-muted">mo</span>
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6 pt-5">
        {/* Top Highlight Summary Cards: Money Added, Outflow & Net */}
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {/* Total Inflow / Added */}
          <div className="rounded-xl border border-success/20 bg-success/5 p-3.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-success">
                {t("recurring.forecast.totalIncome")}
              </span>
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-success/15 text-success">
                <ArrowDownLeft size={14} />
              </span>
            </div>
            <p className="mt-2 text-xl font-bold tracking-tight text-success">
              +{formatCurrency(totals.income)}
            </p>
          </div>

          {/* Total Outflow */}
          <div className="rounded-xl border border-gridline bg-surface-2/40 p-3.5 transition-all">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
                {t("recurring.forecast.totalExpense")}
              </span>
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-surface-2 text-text-muted">
                <ArrowUpRight size={14} />
              </span>
            </div>
            <p className="mt-2 text-xl font-bold tracking-tight text-text-primary">
              −{formatCurrency(totals.expense)}
            </p>
          </div>

          {/* Net Forecast */}
          <div
            className={cn(
              "rounded-xl border p-3.5 transition-all",
              totals.net >= 0
                ? "border-primary/20 bg-primary/5 text-primary"
                : "border-danger/20 bg-danger/5 text-danger"
            )}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wider">
                {t("recurring.forecast.net")}
              </span>
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full",
                  totals.net >= 0 ? "bg-primary/15 text-primary" : "bg-danger/15 text-danger"
                )}
              >
                {totals.net >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              </span>
            </div>
            <p className="mt-2 text-xl font-bold tracking-tight">
              {totals.net >= 0 ? "+" : "−"}
              {formatCurrency(Math.abs(totals.net))}
            </p>
          </div>
        </div>

        {/* Monthly Breakdown: Shows Amount of Money Added / Net per Month */}
        {groups.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-muted">
            {t("recurring.forecast.empty")}
          </p>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                {t("recurring.forecast.monthlyAvg")}:{" "}
                <span className={totals.monthlyAvgNet >= 0 ? "text-success" : "text-danger"}>
                  {totals.monthlyAvgNet >= 0 ? "+" : "−"}
                  {formatCurrency(Math.abs(totals.monthlyAvgNet))}
                  /mo
                </span>
              </h3>
            </div>

            <div className="grid grid-cols-1 gap-2.5">
              {groups.map((group) => {
                const isExpanded = !!expandedMonths[group.key];
                return (
                  <div
                    key={group.key}
                    className="overflow-hidden rounded-lg border border-gridline bg-surface-2/25 transition-colors hover:border-gridline/80 hover:bg-surface-2/40"
                  >
                    {/* Month Summary Bar */}
                    <div
                      className="flex cursor-pointer flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between"
                      onClick={() => toggleMonth(group.key)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          toggleMonth(group.key);
                        }
                      }}
                    >
                      {/* Left: Month title + badge */}
                      <div className="flex items-center gap-2">
                        <span className="font-semibold capitalize text-text-primary">
                          {group.heading}
                        </span>
                        <span className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-text-muted">
                          {group.entries.length}
                        </span>
                      </div>

                      {/* Right: Aggregated Amounts */}
                      <div className="flex items-center gap-3 self-end sm:self-auto">
                        {group.totalIncome > 0 && (
                          <span className="text-xs font-semibold text-success tabular-nums">
                            +{formatCurrency(group.totalIncome)}
                          </span>
                        )}
                        {group.totalExpense > 0 && (
                          <span className="text-xs font-semibold text-text-muted tabular-nums">
                            −{formatCurrency(group.totalExpense)}
                          </span>
                        )}
                        <span
                          className={cn(
                            "rounded-md px-2 py-0.5 text-xs font-bold tabular-nums",
                            group.net >= 0
                              ? "bg-success/15 text-success"
                              : "bg-danger/10 text-danger"
                          )}
                        >
                          {group.net >= 0 ? "+" : "−"}
                          {formatCurrency(Math.abs(group.net))}
                        </span>

                        <span className="text-text-muted">
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </span>
                      </div>
                    </div>

                    {/* Collapsible itemized transactions breakdown */}
                    {isExpanded && (
                      <div className="border-t border-gridline/60 bg-surface-1/70 px-3 py-2">
                        <ul className="divide-y divide-gridline/40">
                          {group.entries.map(({ item, date }, idx) => {
                            const isExpense = item.type === "expense";
                            const isTransfer = item.type === "transfer";
                            const amountColor = isTransfer
                              ? "text-text-muted"
                              : isExpense
                                ? "text-text-primary"
                                : "text-success";
                            const prefix = isTransfer ? "" : isExpense ? "−" : "+";

                            return (
                              <li
                                key={`${item.id}-${idx}`}
                                className="flex items-center justify-between py-1.5 text-xs"
                              >
                                <div className="min-w-0 flex-1">
                                  <p className="truncate font-medium text-text-primary">
                                    {item.description}
                                  </p>
                                  <p className="text-text-muted">
                                    {formatDay(date)}
                                    {" · "}
                                    {t(`recurring.frequency.${item.frequency}` as TranslationKey)}
                                    {item.account_name && ` · ${item.account_name}`}
                                  </p>
                                </div>
                                <span className={`font-semibold tabular-nums ${amountColor}`}>
                                  {prefix}
                                  {formatCurrency(item.amount)}
                                </span>
                              </li>
                            );
                          })}
                        </ul>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
