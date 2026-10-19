import type { ReactNode } from "react";

import { AppShell } from "@/components/AppShell";

// Todas las pantallas dentro de (app) requieren sesión. El paréntesis en el
// nombre de la carpeta hace que NO aparezca en la URL: /cases, no /app/cases.
export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
