import { t, type TranslationKey } from "@/lib/i18n";

// Maps the exact seeded English category name (backend/app/db/seed.py) to
// its translation key, so the fixed default set reads in the user's chosen
// language regardless of what the DB literally stores. Categories created
// through the category-management UI (CategoriesPage) aren't in this map —
// their name is whatever the user typed and is shown as-is.
const DEFAULT_CATEGORY_KEYS: Record<string, TranslationKey> = {
  "Housing & Utilities": "category.housingUtilities",
  Groceries: "category.groceries",
  "Dining Out": "category.diningOut",
  Transportation: "category.transportation",
  "Health & Fitness": "category.healthFitness",
  Shopping: "category.shopping",
  Entertainment: "category.entertainment",
  Subscriptions: "category.subscriptions",
  Salary: "category.salary",
  Freelance: "category.freelance",
  Investments: "category.investments",
  Gifts: "category.gifts",
  "Business Income": "category.businessIncome",
  "Rental Income": "category.rentalIncome",
  Benefits: "category.benefits",
  "Item Sales": "category.itemSales",
  "Money Transfers": "category.moneyTransfers",
  "Other Income": "category.otherIncome",
};

export function translateCategoryName(name: string): string {
  const key = DEFAULT_CATEGORY_KEYS[name];
  return key ? t(key) : name;
}

/** A category's full path for display — "Groceries" alone reads as if it
 * were a top-level category even when it's actually a subcategory; showing
 * "Groceries · Sweets" makes the parent unambiguous everywhere a bare
 * category name used to be shown (transaction rows, filters). `categories`
 * is the full list (any kind, any order) to resolve the parent's own name
 * from `category.parent_id` — subcategories are one level deep only, so a
 * single lookup is enough. */
export function categoryPath(
  category: { name: string; parent_id: number | null },
  categories: { id: number; name: string }[] | undefined
): string {
  if (category.parent_id == null) return translateCategoryName(category.name);
  const parent = categories?.find((c) => c.id === category.parent_id);
  if (!parent) return translateCategoryName(category.name);
  return `${translateCategoryName(parent.name)} · ${translateCategoryName(category.name)}`;
}

/** Orders a category list for display in a dropdown: alphabetical by
 * translated name, with each subcategory placed directly under its own
 * parent (not scattered by name) and flagged `indented` so callers can
 * prefix it visually (e.g. "  ↳ "). Shared by every category picker
 * (TransactionFormModal, the Transactions/Reports filters) so they all
 * read the same way. */
export function buildHierarchicalCategories<C extends { id: number; parent_id: number | null; name: string }>(
  categories: C[],
  language: string
): (C & { indented: boolean })[] {
  const sorted = [...categories].sort((a, b) =>
    translateCategoryName(a.name).localeCompare(translateCategoryName(b.name), language)
  );
  const result: (C & { indented: boolean })[] = [];
  for (const parent of sorted.filter((category) => category.parent_id === null)) {
    result.push({ ...parent, indented: false });
    for (const child of sorted.filter((category) => category.parent_id === parent.id)) {
      result.push({ ...child, indented: true });
    }
  }
  return result;
}
