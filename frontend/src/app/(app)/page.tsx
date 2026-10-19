"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { NAV_ITEMS } from "@/components/AppShell";
import { EmptyState, LoadingState } from "@/components/ui";
import { can, useMe } from "@/features/auth";

/** Inicio: lleva a la primera pantalla que el rol puede ver. */
export default function HomePage() {
  const router = useRouter();
  const me = useMe();
  const first = NAV_ITEMS.find((item) => can(me.data, item.permission));

  useEffect(() => {
    if (first) router.replace(first.href);
  }, [first, router]);

  if (me.isPending || first) return <LoadingState />;
  return (
    <EmptyState title={`Hola, ${me.data?.user.name ?? ""}`}>
      Tu rol todavía no tiene pantallas en esta versión de Mavic. Mientras tanto, podés usar la
      API desde{" "}
      <a className="text-petrol underline" href="http://localhost:8000/docs">
        la documentación (Swagger)
      </a>
      .
    </EmptyState>
  );
}
