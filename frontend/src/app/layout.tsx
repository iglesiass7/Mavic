import "@fontsource-variable/public-sans";
import "./globals.css";

import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "Mavic", template: "%s · Mavic" },
  description: "Gestión de cobranzas con un agente de voz.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="es-AR">
      <body className="min-h-screen font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
