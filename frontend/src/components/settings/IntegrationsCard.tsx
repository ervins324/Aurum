import { useState } from "react";
import { RefreshCw, Trash2, ChevronDown, ChevronUp, CheckCircle2, XCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label, Select } from "@/components/ui/Input";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  useIntegrations,
  useSetMonobankIntegration,
  useSetBybitIntegration,
  useDeleteIntegration,
  useSyncIntegration,
} from "@/hooks/useIntegrations";
import { useAccounts } from "@/hooks/useAccounts";
import type { IntegrationSyncResult } from "@/types";

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ isConfigured }: { isConfigured: boolean }) {
  const { t } = useTranslation();
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        isConfigured
          ? "bg-success/10 text-success"
          : "bg-surface-2 text-text-muted"
      )}
    >
      {isConfigured ? (
        <CheckCircle2 size={11} />
      ) : (
        <XCircle size={11} />
      )}
      {isConfigured
        ? t("settings.integrations.configured")
        : t("settings.integrations.notConfigured")}
    </span>
  );
}

function SyncResultBanner({ result }: { result: IntegrationSyncResult }) {
  const { t } = useTranslation();
  const hasError = !!result.error;
  return (
    <div
      className={cn(
        "rounded-md px-3 py-2 text-sm",
        hasError ? "bg-danger/10 text-danger" : "bg-success/10 text-success"
      )}
    >
      {hasError ? (
        <span>{t("settings.integrations.syncError", { error: result.error! })}</span>
      ) : (
        <span>
          {t("settings.integrations.syncSuccess", {
            synced: result.synced_count,
            skipped: result.skipped_count,
          })}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Monobank section
// ---------------------------------------------------------------------------

/** Format an ISO datetime or date string to YYYY-MM-DD for input[type=date]. */
function toDateInput(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  return value.slice(0, 10);
}

function MonobankSection() {
  const { t } = useTranslation();
  const { data: integrations } = useIntegrations();
  const { data: accounts } = useAccounts();
  const setMono = useSetMonobankIntegration();
  const deleteMono = useDeleteIntegration();
  const syncMono = useSyncIntegration();

  const status = integrations?.find((i) => i.provider === "monobank");

  const [expanded, setExpanded] = useState(false);
  const [token, setToken] = useState("");
  const [accountId, setAccountId] = useState("");
  const [lastResult, setLastResult] = useState<IntegrationSyncResult | null>(null);

  // Sync period defaults: from last sync (or 30 days ago) to today
  const today = new Date().toISOString().slice(0, 10);
  const defaultFrom = status?.last_synced_at
    ? toDateInput(status.last_synced_at, today)
    : new Date(Date.now() - 30 * 86_400_000).toISOString().slice(0, 10);
  const [syncFrom, setSyncFrom] = useState("");
  const [syncTo, setSyncTo] = useState("");

  // Recompute defaults when status changes (e.g. after first load)
  const effectiveFrom = syncFrom || defaultFrom;
  const effectiveTo = syncTo || today;

  async function handleSave() {
    if (!token.trim() || !accountId) return;
    await setMono.mutateAsync({ token: token.trim(), account_id: Number(accountId) });
    setToken("");
    setExpanded(false);
  }

  async function handleSync() {
    setLastResult(null);
    const result = await syncMono.mutateAsync({
      provider: "monobank",
      body: { sync_from: effectiveFrom, sync_to: effectiveTo },
    });
    setLastResult(result);
  }

  async function handleDelete() {
    if (!window.confirm(t("settings.integrations.confirmRemove", { provider: "Monobank" }))) return;
    setLastResult(null);
    await deleteMono.mutateAsync("monobank");
  }

  const isConfigured = status?.is_configured ?? false;
  const isSyncing = syncMono.isPending;
  const isSaving = setMono.isPending;

  return (
    <div className="border-b border-gridline pb-4 last:border-0 last:pb-0">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {/* Header row */}
        <div className="flex items-center gap-2">
          {/* Monobank logo placeholder — coloured circle */}
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#1b1f3b] text-xs font-bold text-white">
            M
          </span>
          <div>
            <p className="text-sm font-medium text-text-primary">Monobank</p>
            {isConfigured && status?.token_preview && (
              <p className="text-xs text-text-muted font-mono">{status.token_preview}</p>
            )}
          </div>
          <StatusBadge isConfigured={isConfigured} />
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          {isConfigured && (
            <>
              <Button
                variant="secondary"
                disabled={isSyncing}
                onClick={handleSync}
                className="gap-1.5 text-xs"
              >
                <RefreshCw size={13} className={isSyncing ? "animate-spin" : ""} />
                {isSyncing
                  ? t("settings.integrations.syncing")
                  : t("settings.integrations.syncNow")}
              </Button>
              <button
                type="button"
                onClick={handleDelete}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                aria-label={t("settings.integrations.remove")}
              >
                <Trash2 size={14} />
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
            aria-label={expanded ? t("common.collapse") : t("common.expand")}
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Sync period picker — always visible when configured */}
      {isConfigured && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:gap-3">
          <div className="flex-1">
            <Label htmlFor="mono-sync-from">{t("settings.integrations.monobank.syncFrom")}</Label>
            <Input
              id="mono-sync-from"
              type="date"
              value={effectiveFrom}
              onChange={(e) => setSyncFrom(e.target.value)}
            />
          </div>
          <div className="flex-1">
            <Label htmlFor="mono-sync-to">{t("settings.integrations.monobank.syncTo")}</Label>
            <Input
              id="mono-sync-to"
              type="date"
              value={effectiveTo}
              onChange={(e) => setSyncTo(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Sync result */}
      {lastResult && (
        <div className="mt-2">
          <SyncResultBanner result={lastResult} />
        </div>
      )}

      {/* Monobank note about sync duration */}
      {isSyncing && (
        <p className="mt-2 text-xs text-text-muted">
          {t("settings.integrations.monobank.syncNote")}
        </p>
      )}

      {/* Credential form */}
      {expanded && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="mono-token">{t("settings.integrations.monobank.tokenLabel")}</Label>
            <Input
              id="mono-token"
              type="password"
              placeholder={t("settings.integrations.monobank.tokenPlaceholder")}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              autoComplete="off"
            />
            <p className="mt-1 text-xs text-text-muted">
              {t("settings.integrations.monobank.tokenHint")}
            </p>
          </div>
          <div>
            <Label htmlFor="mono-account">{t("settings.integrations.accountLabel")}</Label>
            <Select
              id="mono-account"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              <option value="">{t("settings.integrations.selectAccount")}</option>
              {accounts?.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex items-end gap-2 sm:col-span-2">
            <Button
              onClick={handleSave}
              disabled={!token.trim() || !accountId || isSaving}
            >
              {isSaving ? t("common.saving") : t("common.save")}
            </Button>
            <Button variant="secondary" onClick={() => setExpanded(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bybit section
// ---------------------------------------------------------------------------

function BybitSection() {
  const { t } = useTranslation();
  const { data: integrations } = useIntegrations();
  const { data: accounts } = useAccounts();
  const setBybit = useSetBybitIntegration();
  const deleteBybit = useDeleteIntegration();
  const syncBybit = useSyncIntegration();

  const status = integrations?.find((i) => i.provider === "bybit");

  const [expanded, setExpanded] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [accountId, setAccountId] = useState("");
  const [lastResult, setLastResult] = useState<IntegrationSyncResult | null>(null);

  async function handleSave() {
    if (!apiKey.trim() || !apiSecret.trim() || !accountId) return;
    await setBybit.mutateAsync({
      api_key: apiKey.trim(),
      api_secret: apiSecret.trim(),
      account_id: Number(accountId),
    });
    setApiKey("");
    setApiSecret("");
    setExpanded(false);
  }

  async function handleSync() {
    setLastResult(null);
    const result = await syncBybit.mutateAsync({ provider: "bybit" });
    setLastResult(result);
  }

  async function handleDelete() {
    if (!window.confirm(t("settings.integrations.confirmRemove", { provider: "Bybit Card" }))) return;
    setLastResult(null);
    await deleteBybit.mutateAsync("bybit");
  }

  const isConfigured = status?.is_configured ?? false;
  const isSyncing = syncBybit.isPending;
  const isSaving = setBybit.isPending;

  return (
    <div className="pb-4 last:pb-0">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {/* Header row */}
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#f7a600] text-xs font-bold text-black">
            B
          </span>
          <div>
            <p className="text-sm font-medium text-text-primary">Bybit Card</p>
            {isConfigured && status?.key_preview && (
              <p className="text-xs text-text-muted font-mono">{status.key_preview}</p>
            )}
          </div>
          <StatusBadge isConfigured={isConfigured} />
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          {isConfigured && (
            <>
              <Button
                variant="secondary"
                disabled={isSyncing}
                onClick={handleSync}
                className="gap-1.5 text-xs"
              >
                <RefreshCw size={13} className={isSyncing ? "animate-spin" : ""} />
                {isSyncing
                  ? t("settings.integrations.syncing")
                  : t("settings.integrations.syncNow")}
              </Button>
              <button
                type="button"
                onClick={handleDelete}
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-danger"
                aria-label={t("settings.integrations.remove")}
              >
                <Trash2 size={14} />
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="rounded-md p-1.5 text-text-muted hover:bg-surface-2 hover:text-text-primary"
            aria-label={expanded ? t("common.collapse") : t("common.expand")}
          >
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>
      </div>

      {/* Sync result */}
      {lastResult && (
        <div className="mt-2">
          <SyncResultBanner result={lastResult} />
        </div>
      )}

      {/* Credential form */}
      {expanded && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="bybit-key">{t("settings.integrations.bybit.keyLabel")}</Label>
            <Input
              id="bybit-key"
              type="password"
              placeholder={t("settings.integrations.bybit.keyPlaceholder")}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div>
            <Label htmlFor="bybit-secret">{t("settings.integrations.bybit.secretLabel")}</Label>
            <Input
              id="bybit-secret"
              type="password"
              placeholder={t("settings.integrations.bybit.secretPlaceholder")}
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div>
            <Label htmlFor="bybit-account">{t("settings.integrations.accountLabel")}</Label>
            <Select
              id="bybit-account"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              <option value="">{t("settings.integrations.selectAccount")}</option>
              {accounts?.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.name}
                </option>
              ))}
            </Select>
          </div>
          <p className="text-xs text-text-muted self-end sm:col-span-2">
            {t("settings.integrations.bybit.hint")}
          </p>
          <div className="flex items-center gap-2 sm:col-span-2">
            <Button
              onClick={handleSave}
              disabled={!apiKey.trim() || !apiSecret.trim() || !accountId || isSaving}
            >
              {isSaving ? t("common.saving") : t("common.save")}
            </Button>
            <Button variant="secondary" onClick={() => setExpanded(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main card
// ---------------------------------------------------------------------------

export function IntegrationsCard() {
  const { t } = useTranslation();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("settings.integrationsTitle")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-text-secondary">{t("settings.integrationsHint")}</p>
        <MonobankSection />
        <BybitSection />
      </CardContent>
    </Card>
  );
}
