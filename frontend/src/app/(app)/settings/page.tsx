"use client";

/**
 * Configuración, con el diseño de Rynx: pestañas arriba.
 *
 *   [Mi cuenta] [Organización]
 *
 * "Organización" (el equipo) aparece solo si el rol puede administrar usuarios.
 * La pestaña vive en la dirección (?pestana=organizacion) para poder volver o
 * compartir el link. Rynx tiene además "Preferencias" (idioma, avisos): Mavic
 * todavía no guarda preferencias, así que esa pestaña no se muestra.
 */
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AccountSettings } from "@/components/settings/AccountSettings";
import { TeamSettings } from "@/components/settings/TeamSettings";
import { PageHeader, Tabs } from "@/components/ui";
import { can, useMe } from "@/features/auth";

type Tab = "cuenta" | "organizacion";

function SettingsScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const me = useMe();
  const canManageTeam = can(me.data, "manage_users");

  const tabs: { value: Tab; label: string }[] = [{ value: "cuenta", label: "Mi cuenta" }];
  if (canManageTeam) tabs.push({ value: "organizacion", label: "Organización" });
  const tab: Tab = params.get("pestana") === "organizacion" && canManageTeam ? "organizacion" : "cuenta";

  return (
    <>
      <PageHeader
        title="Configuración"
        subtitle={
          canManageTeam
            ? "Tu cuenta, tu contraseña y los accesos de tu equipo."
            : "Tu cuenta y tu contraseña."
        }
      />
      {tabs.length > 1 && (
        <div className="mb-6">
          <Tabs
            label="Secciones de configuración"
            tabs={tabs}
            value={tab}
            onChange={(next) =>
              router.push(next === "cuenta" ? pathname : `${pathname}?pestana=${next}`, { scroll: false })
            }
          />
        </div>
      )}
      <div role="tabpanel" aria-label={tabs.find((t) => t.value === tab)?.label}>
        {tab === "cuenta" ? <AccountSettings /> : <TeamSettings />}
      </div>
    </>
  );
}

export default function SettingsPage() {
  // useSearchParams necesita un Suspense alrededor (regla de Next.js).
  return (
    <Suspense>
      <SettingsScreen />
    </Suspense>
  );
}
