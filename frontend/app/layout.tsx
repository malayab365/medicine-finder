import type { Metadata } from "next";

import Nav from "@/components/Nav";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "Medicine Search",
  description: "Look up medicines by name or symptom. Informational only — not medical advice.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <div className="mx-auto max-w-3xl px-4 py-8">
            <Nav />
            <main className="mt-6">{children}</main>
            <footer className="mt-12 border-t border-gray-200 pt-4 text-sm text-gray-500">
              Informational only. Not medical advice. Consult a healthcare provider.
            </footer>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
