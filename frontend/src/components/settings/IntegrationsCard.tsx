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
  useDeleteIntegration,
  useSyncIntegration,
} from "@/hooks/useIntegrations";
import { useAccounts, useCreateAccount } from "@/hooks/useAccounts";
import type { AccountType, IntegrationSyncResult } from "@/types";

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

function SyncProgressBanner({ statusMessage }: { statusMessage?: string | null }) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 rounded-md border border-primary/20 bg-primary/10 px-3 py-2 text-sm text-primary font-medium animate-pulse">
      <RefreshCw size={14} className="animate-spin shrink-0 text-primary" />
      <span>{statusMessage || t("settings.integrations.syncing")}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// AccountSelector — dropdown with inline "Create new account" option
// ---------------------------------------------------------------------------

const SENTINEL_CREATE = "__create__";

/** Account type options available for new account creation. */
const ACCOUNT_TYPE_OPTIONS: AccountType[] = [
  "debit_card",
  "checking",
  "savings",
  "credit_card",
  "cash",
  "other",
];

interface AccountSelectorProps {
  id: string;
  value: string;
  onChange: (accountId: string) => void;
}

function AccountSelector({ id, value, onChange }: AccountSelectorProps) {
  const { t } = useTranslation();
  const { data: accounts, refetch } = useAccounts();
  const createAccount = useCreateAccount();

  // Inline create-new-account form state
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<AccountType>("debit_card");
  const [creating, setCreating] = useState(false);

  function handleSelectChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const val = e.target.value;
    if (val === SENTINEL_CREATE) {
      // Show the inline creation form instead of passing the sentinel upward
      setIsCreating(true);
      setNewName("");
      setNewType("debit_card");
    } else {
      setIsCreating(false);
      onChange(val);
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      const created = await createAccount.mutateAsync({ name: newName.trim(), type: newType });
      // Refresh the accounts list, then auto-select the newly created account
      await refetch();
      onChange(String(created.id));
      setIsCreating(false);
    } catch {
      // Error state is surfaced by the disabled Create button — nothing else to show here
    } finally {
      setCreating(false);
    }
  }

  function handleCancelCreate() {
    setIsCreating(false);
    // Keep the previously selected account (don't reset value)
  }

  return (
    <div className="flex flex-col gap-2">
      <Select id={id} value={isCreating ? SENTINEL_CREATE : value} onChange={handleSelectChange}>
        <option value="">{t("settings.integrations.selectAccount")}</option>
        {accounts?.map((acc) => (
          <option key={acc.id} value={acc.id}>
            {acc.name}
          </option>
        ))}
        {/* Always-visible sentinel that opens the inline creation form */}
        <option value={SENTINEL_CREATE}>{t("settings.integrations.createNewAccount")}</option>
      </Select>

      {/* Inline creation form — shown only when the sentinel is selected */}
      {isCreating && (
        <div className="rounded-md border border-gridline bg-surface-1 p-3 flex flex-col gap-2">
          <div>
            <Label htmlFor={`${id}-new-name`}>{t("settings.integrations.newAccountName")}</Label>
            <Input
              id={`${id}-new-name`}
              type="text"
              placeholder={t("settings.integrations.newAccountNamePlaceholder")}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              autoFocus
            />
          </div>
          <div>
            <Label htmlFor={`${id}-new-type`}>{t("settings.integrations.newAccountType")}</Label>
            <Select
              id={`${id}-new-type`}
              value={newType}
              onChange={(e) => setNewType(e.target.value as AccountType)}
            >
              {ACCOUNT_TYPE_OPTIONS.map((type) => (
                <option key={type} value={type}>
                  {t(`account.type.${type}` as Parameters<typeof t>[0])}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex gap-2">
            <Button
              onClick={handleCreate}
              disabled={!newName.trim() || creating}
              className="text-xs py-1.5"
            >
              {creating ? t("common.saving") : t("settings.integrations.createAccountButton")}
            </Button>
            <Button variant="secondary" onClick={handleCancelCreate} className="text-xs py-1.5">
              {t("common.cancel")}
            </Button>
          </div>
        </div>
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
  const isSyncing = Boolean(status?.is_syncing) || syncMono.isPending;
  const isSaving = setMono.isPending;
  const displayResult = lastResult || status?.last_sync_result;

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

      {/* Live sync stage */}
      {isSyncing && (
        <div className="mt-2">
          <SyncProgressBanner statusMessage={status?.sync_status} />
        </div>
      )}

      {/* Sync result */}
      {!isSyncing && displayResult && (
        <div className="mt-2">
          <SyncResultBanner result={displayResult} />
        </div>
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
            <AccountSelector
              id="mono-account"
              value={accountId}
              onChange={setAccountId}
            />
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
      </CardContent>
    </Card>
  );
}
