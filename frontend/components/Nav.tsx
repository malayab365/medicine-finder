"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";

export default function Nav() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const tab = (href: string, label: string) => (
    <Link
      href={href}
      className={`rounded px-3 py-1.5 text-sm ${
        pathname === href
          ? "bg-blue-600 text-white"
          : "border border-gray-300 bg-gray-100 text-gray-700 hover:bg-gray-200"
      }`}
    >
      {label}
    </Link>
  );

  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <Link href="/" className="text-xl font-bold">
          Medicine Search
        </Link>
        <nav className="flex gap-1">
          {tab("/", "By name")}
          {tab("/symptoms", "By symptoms")}
        </nav>
      </div>
      <div className="flex items-center gap-3 text-sm">
        {loading ? null : user ? (
          <>
            <span className="font-semibold">{user.username}</span>
            <button
              type="button"
              className="text-blue-600 hover:underline"
              onClick={async () => {
                await logout();
                router.push("/");
              }}
            >
              Log out
            </button>
          </>
        ) : (
          <>
            <Link href="/login" className="text-blue-600 hover:underline">
              Log in
            </Link>
            <Link href="/register" className="text-blue-600 hover:underline">
              Register
            </Link>
          </>
        )}
      </div>
    </header>
  );
}
