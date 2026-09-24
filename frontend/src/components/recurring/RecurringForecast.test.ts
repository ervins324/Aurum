import { describe, it, expect } from "vitest";
import { advanceDate, getOccurrences, buildForecast } from "./RecurringForecast";
import type { RecurringTransaction } from "@/types";

describe("RecurringForecast", () => {
  describe("advanceDate", () => {
    it("advances weekly by exactly 7 days", () => {
      const start = new Date(2026, 8, 1); // 2026-09-01
      const next = advanceDate(start, "weekly");
      expect(next.getDate()).toBe(8);
      expect(next.getMonth()).toBe(8);
    });

    it("advances monthly clamping to month end", () => {
      const jan31 = new Date(2026, 0, 31); // Jan 31
      const feb = advanceDate(jan31, "monthly");
      expect(feb.getMonth()).toBe(1); // Feb
      expect(feb.getDate()).toBe(28); // 2026 is not leap year
    });

    it("advances yearly handling leap day", () => {
      const leapDay = new Date(2024, 1, 29); // Feb 29, 2024
      const nextYear = advanceDate(leapDay, "yearly");
      expect(nextYear.getFullYear()).toBe(2025);
      expect(nextYear.getMonth()).toBe(1); // Feb
      expect(nextYear.getDate()).toBe(28); // clamped
    });
  });

  describe("getOccurrences", () => {
    it("generates expected future occurrences within window", () => {
      const futureStart = new Date();
      futureStart.setDate(futureStart.getDate() + 5);
      const isoStart = futureStart.toISOString().slice(0, 10);

      const mockItem: RecurringTransaction = {
        id: 1,
        account_id: 1,
        account_name: "Checking",
        category_id: null,
        category_name: null,
        category_color: null,
        category_icon: null,
        transfer_account_id: null,
        transfer_account_name: null,
        type: "expense",
        amount: "50.00",
        description: "Netflix",
        merchant: null,
        notes: null,
        frequency: "monthly",
        anchor_date: isoStart,
        last_posted_date: null,
        is_active: true,
        next_due_date: isoStart,
        is_due: false,
        days_until_due: 5,
      };

      const cutoff = new Date();
      cutoff.setMonth(cutoff.getMonth() + 3);

      const occurrences = getOccurrences(mockItem, cutoff);
      expect(occurrences.length).toBeGreaterThanOrEqual(2);
      expect(occurrences.length).toBeLessThanOrEqual(4);
    });
  });

  describe("buildForecast", () => {
    it("ignores inactive recurring items", () => {
      const mockItem: RecurringTransaction = {
        id: 1,
        account_id: 1,
        account_name: "Checking",
        category_id: null,
        category_name: null,
        category_color: null,
        category_icon: null,
        transfer_account_id: null,
        transfer_account_name: null,
        type: "expense",
        amount: "50.00",
        description: "Gym",
        merchant: null,
        notes: null,
        frequency: "monthly",
        anchor_date: "2026-09-01",
        last_posted_date: null,
        is_active: false,
        next_due_date: "2026-10-01",
        is_due: false,
        days_until_due: 10,
      };

      const result = buildForecast([mockItem], 3);
      expect(result).toHaveLength(0);
    });

    it("correctly aggregates totalIncome, totalExpense, and net", () => {
      const futureStart = new Date();
      futureStart.setDate(futureStart.getDate() + 2);
      const isoStart = futureStart.toISOString().slice(0, 10);

      const incomeItem: RecurringTransaction = {
        id: 1,
        account_id: 1,
        account_name: "Checking",
        category_id: null,
        category_name: null,
        category_color: null,
        category_icon: null,
        transfer_account_id: null,
        transfer_account_name: null,
        type: "income",
        amount: "2000.00",
        description: "Salary",
        merchant: null,
        notes: null,
        frequency: "monthly",
        anchor_date: isoStart,
        last_posted_date: null,
        is_active: true,
        next_due_date: isoStart,
        is_due: false,
        days_until_due: 2,
      };

      const expenseItem: RecurringTransaction = {
        id: 2,
        account_id: 1,
        account_name: "Checking",
        category_id: null,
        category_name: null,
        category_color: null,
        category_icon: null,
        transfer_account_id: null,
        transfer_account_name: null,
        type: "expense",
        amount: "500.00",
        description: "Rent",
        merchant: null,
        notes: null,
        frequency: "monthly",
        anchor_date: isoStart,
        last_posted_date: null,
        is_active: true,
        next_due_date: isoStart,
        is_due: false,
        days_until_due: 2,
      };

      const result = buildForecast([incomeItem, expenseItem], 1);
      expect(result.length).toBeGreaterThanOrEqual(1);
      expect(result[0].totalIncome).toBe(2000);
      expect(result[0].totalExpense).toBe(500);
      expect(result[0].net).toBe(1500);
    });
  });
});
