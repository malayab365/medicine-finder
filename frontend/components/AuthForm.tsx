"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ErrorBox } from "@/components/Disclaimer";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Mode = "login" | "register";

export default function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const { login, register } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const isRegister = mode === "register";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (isRegister && password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      if (isRegister) {
        await register(username, password);
      } else {
        await login(username, password);
      }
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="max-w-sm">
      <h1 className="text-xl font-bold">{isRegister ? "Create an account" : "Log in"}</h1>
      {error ? <ErrorBox title={error} /> : null}
      <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3" autoComplete="off">
        <label className="flex flex-col gap-1 text-sm">
          Username
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            minLength={isRegister ? 3 : undefined}
            maxLength={64}
            className="rounded border border-gray-300 px-3 py-2 text-base"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={isRegister ? 8 : undefined}
            maxLength={128}
            className="rounded border border-gray-300 px-3 py-2 text-base"
          />
        </label>
        {isRegister ? (
          <label className="flex flex-col gap-1 text-sm">
            Confirm password
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              minLength={8}
              maxLength={128}
              className="rounded border border-gray-300 px-3 py-2 text-base"
            />
          </label>
        ) : null}
        <button
          type="submit"
          disabled={loading}
          className="self-start rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-60"
        >
          {loading ? "Please wait…" : isRegister ? "Register" : "Log in"}
        </button>
      </form>
      <p className="mt-4 text-sm">
        {isRegister ? (
          <>
            Already have an account? <Link href="/login" className="text-blue-600 hover:underline">Log in</Link>.
          </>
        ) : (
          <>
            No account? <Link href="/register" className="text-blue-600 hover:underline">Register</Link>.
          </>
        )}
      </p>
    </section>
  );
}
