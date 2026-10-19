"use client";

import { CheckCircle2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { Button, ErrorState, Fact, Field, Panel, inputClass } from "@/components/ui";
import { useMe } from "@/features/auth";
import { PASSWORD_MIN_LENGTH, checkNewPassword, useChangePassword } from "@/features/users";
import { errorMessage } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/labels";

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
    <Panel title="Cambiar contraseña">
      <form onSubmit={handleSubmit} noValidate className="max-w-md space-y-4">
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
            Listo, cambiaste tu contraseña. Si tenías Mavic abierto en otra computadora o navegador,
            ahí se cerró la sesión.
          </p>
        )}

        <Button type="submit" loading={change.isPending}>
          Cambiar contraseña
        </Button>
      </form>
    </Panel>
  );
}

export default function AccountPage() {
  const me = useMe();
  const user = me.data?.user;

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Mi cuenta</h1>
      <div className="mt-6 space-y-6">
        {user && (
          <Panel>
            <dl className="grid gap-4 sm:grid-cols-4">
              <Fact label="Nombre">{user.name}</Fact>
              <Fact label="Email">
                <span className="break-all">{user.email}</span>
              </Fact>
              <Fact label="Rol">{ROLE_LABEL[user.role]}</Fact>
              <Fact label="Empresa">{me.data?.company?.name ?? "—"}</Fact>
            </dl>
          </Panel>
        )}
        <ChangePassword />
      </div>
    </>
  );
}
