"use client";

import Link from "next/link";

import SymptomSearch from "@/components/SymptomSearch";
import { useAuth } from "@/lib/auth";

export default function SymptomsPage() {
  const { user, loading } = useAuth();

  if (loading) {
    return <p className="text-gray-500">Loading…</p>;
  }

  if (!user) {
    return (
      <div className="rounded-md border border-yellow-300 bg-yellow-100 px-4 py-3 text-sm text-yellow-900">
        Symptom search requires an account.{" "}
        <Link href="/login" className="font-semibold underline">
          Log in
        </Link>{" "}
        or{" "}
        <Link href="/register" className="font-semibold underline">
          create one
        </Link>{" "}
        to continue.
      </div>
    );
  }

  return (
    <div>
      <p className="mb-4 text-gray-600">
        Describe your symptoms to get suggested over-the-counter medicines. This is not a diagnosis.
      </p>
      <SymptomSearch />
    </div>
  );
}
