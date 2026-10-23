"use client";

/**
 * Configuración > Mi cuenta, con el diseño de Rynx: dos tarjetas.
 *
 *   Cuenta personal (nombre, email, rol, empresa)  |  Seguridad (cambiar contraseña)
 *
 * El nombre y el email no se editan acá: el backend no tiene ese cambio todavía
 * (los corrige administración). Rynx también muestra "Autenticación en dos
 * pasos"; Mavic no la tiene, así que no se muestra un botón que no hace nada.
 */
import { CheckCircle2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useMe } from "@/features/auth";
import { PASSWORD_MIN_LENGTH, checkNewPassword, useChangePassword } from "@/features/users";
import { errorMessage } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/labels";

import { Button, ErrorState, Field, Panel, inputClass } from "../ui";

function ReadOnly({ id, label, value }: { id: string; label: string; value: string }) {
  return (
    <Field id={id} label={label}>
      {(aria) => (
        <input {...aria} value={value} readOnly className={inputClass(false, "bg-sunken/60 text-muted")} />
      )}
    </Field>
  );
}

function PersonalAccount() {
  const me = useMe();
  const user = me.data?.user;
  if (!user) return null;
  return (
    <Panel title="Cuenta personal" description="Tus datos para entrar a Mavic.">
      <div className="space-y-4">
        <ReadOnly id="me-name" label="Nombre" value={user.name} />
        <ReadOnly id="me-email" label="Email" value={user.email} />
        <div className="grid gap-4 sm:grid-cols-2">
          <ReadOnly id="me-role" label="Rol" value={ROLE_LABEL[user.role]} />
          <ReadOnly id="me-company" label="Empresa" value={me.data?.company?.name ?? "—"} />
        </div>
        <p className="text-xs text-muted">
          Para cambiar el nombre o el email, pedíselo a alguien con rol de administración.
        </p>
      </div>
    </Panel>
  );
}

function ChangePassword() {
  const change = useChangePassword();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!current) found.current = "Escribí tu contraseña actual.";
    const problem = checkNewPassword(next);
    if (problem) found.next = problem;
    else if (next === current) found.next = "Tiene que ser distinta de la actual.";
    if (!found.next && repeat !== next) found.repeat = "No coincide con la nueva.";
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent("");
          setNext("");
          setRepeat("");
        },
      },
    );
  }

  return (
    <Panel
      title="Seguridad"
      description="Cambiá tu contraseña cuando quieras. Al cambiarla se cierran tus otras sesiones."
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {/* Para que el gestor de contraseñas del navegador sepa de qué cuenta es. */}
        <input type="hidden" autoComplete="username" />
        <Field id="current" label="Contraseña actual" error={errors.current}>
          {(aria) => (
            <input
              {...aria}
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className={inputClass(Boolean(errors.current))}
            />
          )}
        </Field>
        <Field
          id="next"
          label="Contraseña nueva"
          hint={`Al menos ${PASSWORD_MIN_LENGTH} caracteres. Una frase es más segura y más fácil de recordar que símbolos raros.`}
          error={errors.next}
        >
          {(aria) => (
            <input
              {...aria}
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className={inputClass(Boolean(errors.next))}
            />
          )}
        </Field>
        <Field id="repeat" label="Repetí la contraseña nueva" error={errors.repeat}>
          {(aria) => (
            <input
              {...aria}
              type="password"
              autoComplete="new-password"
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              className={inputClass(Boolean(errors.repeat))}
            />
          )}
        </Field>

        {change.isError && <ErrorState message={errorMessage(change.error)} />}
        {change.isSuccess && (
          <p role="status" className="flex items-start gap-2 text-sm">
            <CheckCircle2 aria-hidden className="mt-0.5 size-4 shrink-0 text-status-agreement" />
            Listo, cambiaste tu contraseña. Si tenías Mavic abierto en otra computadora o navegador, ahí se
            cerró la sesión.
          </p>
        )}

        <Button type="submit" loading={change.isPending}>
          Cambiar contraseña
        </Button>
      </form>
    </Panel>
  );
}

export function AccountSettings() {
  return (
    <div className="grid items-start gap-6 lg:grid-cols-2">
      <PersonalAccount />
      <ChangePassword />
    </div>
  );
}
