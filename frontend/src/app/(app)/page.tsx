"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { NAV_ITEMS } from "@/components/AppShell";
import { LoadingState } from "@/components/ui";
import { can, useMe } from "@/features/auth";

/** La raíz lleva a la primera pantalla del menú que el rol puede ver. */
export default function HomePage() {
  const router = useRouter();
  const me = useMe();
  const first = NAV_ITEMS.find((item) => item.permission === null || can(me.data, item.permission));

  useEffect(() => {
    if (me.isSuccess && first) router.replace(first.href);
  }, [me.isSuccess, first, router]);

  return <LoadingState />;
}
