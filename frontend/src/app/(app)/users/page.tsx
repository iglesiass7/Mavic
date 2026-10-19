"use client";

import { Plus, RefreshCw } from "lucide-react";
import { useState, type FormEvent } from "react";

import { CopyButton } from "@/components/CopyButton";
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Panel,
  QueryError,
  cx,
  inputClass,
} from "@/components/ui";
import { can, useMe } from "@/features/auth";
import {
  checkNewPassword,
  generatePassword,
  looksLikeEmail,
  useCreateUser,
  useUpdateUser,
  useUsers,
} from "@/features/users";
import { errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { ROLE_HINT, ROLE_LABEL } from "@/lib/labels";
import type { CompanyRole, User } from "@/lib/types";

const COMPANY_ROLES: CompanyRole[] = ["operator", "supervisor", "admin"];

// ---------------------------------------------------------------- alta

function NewUserForm({ onClose }: { onClose: () => void }) {
  const create = useCreateUser();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<CompanyRole>("operator");
  const [password, setPassword] = useState(() => generatePassword());
  const [errors, setErrors] = useState<Record<string, string>>({});

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = "Escribí el nombre.";
    if (!looksLikeEmail(email)) next.email = "Escribí un email válido.";
    const passwordProblem = checkNewPassword(password);
    if (passwordProblem) next.password = passwordProblem;
    setErrors(next);
    if (Object.keys(next).length === 0) {
      create.mutate({ name: name.trim(), email: email.trim(), password, role });
    }
  }

  if (create.isSuccess) {
    return (
      <Panel title="Usuario creado">
        <div className="space-y-4 text-sm">
          <p>
            <span className="font-semibold">{create.data.name}</span> ya puede entrar a Mavic con
            estos datos. Pasáselos por un medio privado: la contraseña no se vuelve a mostrar. Después
            la puede cambiar desde <span className="font-medium">Mi cuenta</span>.
          </p>
          <dl className="grid gap-3 rounded-md border border-line bg-paper p-4 sm:grid-cols-[auto_1fr_auto] sm:items-center">
            <dt className="text-muted">Email</dt>
            <dd className="font-medium break-all">{create.data.email}</dd>
            <dd />
            <dt className="text-muted">Contraseña</dt>
            <dd>
              <code className="text-base">{password}</code>
            </dd>
            <dd>
              <CopyButton text={`Email: ${create.data.email}\nContraseña: ${password}`} />
            </dd>
          </dl>
          <Button variant="secondary" onClick={onClose}>
            Listo
          </Button>
        </div>
      </Panel>
    );
  }

  return (
    <Panel title="Nuevo usuario">
      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field id="new-name" label="Nombre" error={errors.name}>
            {(aria) => (
              <input
                {...aria}
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="off"
                className={inputClass(Boolean(errors.name))}
              />
            )}
          </Field>
          <Field id="new-email" label="Email" hint="Con este email va a entrar." error={errors.email}>
            {(aria) => (
              <input
                {...aria}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="off"
                className={inputClass(Boolean(errors.email))}
              />
            )}
          </Field>
        </div>

        <fieldset>
          <legend className="text-sm font-medium">Rol</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            {COMPANY_ROLES.map((value) => (
              <label
                key={value}
                className={cx(
                  "flex cursor-pointer gap-3 rounded-md border p-3 text-sm",
                  role === value ? "border-petrol bg-petrol-soft" : "border-line",
                )}
              >
                <input
                  type="radio"
                  name="role"
                  value={value}
                  checked={role === value}
                  onChange={() => setRole(value)}
                  className="mt-0.5 accent-petrol"
                />
                <span>
                  <span className="font-medium">{ROLE_LABEL[value]}</span>
                  <span className="block text-xs text-muted">{ROLE_HINT[value]}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <Field
          id="new-password"
          label="Contraseña inicial"
          hint="Generada al azar. Podés escribir otra (mínimo 10 caracteres)."
          error={errors.password}
        >
          {(aria) => (
            <div className="flex gap-2">
              <input
                {...aria}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                spellCheck={false}
                className={inputClass(Boolean(errors.password), "font-mono")}
              />
              <Button type="button" variant="secondary" onClick={() => setPassword(generatePassword())}>
                <RefreshCw aria-hidden className="size-4" /> Otra
              </Button>
            </div>
          )}
        </Field>

        {create.isError && <ErrorState message={errorMessage(create.error)} />}

        <div className="flex flex-wrap gap-3">
          <Button type="submit" loading={create.isPending}>
            Crear usuario
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
        </div>
      </form>
    </Panel>
  );
}

// ---------------------------------------------------------------- lista

function UserRow({ user, isMe }: { user: User; isMe: boolean }) {
  const update = useUpdateUser();
  const role = user.role === "platform_admin" ? null : user.role;

  const roleControl =
    role && !isMe ? (
      <select
        aria-label={`Rol de ${user.name}`}
        value={role}
        disabled={update.isPending}
        onChange={(e) => update.mutate({ id: user.id, role: e.target.value as CompanyRole })}
        className={inputClass(false, "w-auto py-1.5")}
      >
        {COMPANY_ROLES.map((value) => (
          <option key={value} value={value}>
            {ROLE_LABEL[value]}
          </option>
        ))}
      </select>
    ) : (
      ROLE_LABEL[user.role]
    );

  // Desactivarse a uno mismo cerraría la sesión en el acto: no se ofrece.
  const activeControl = isMe ? null : (
    <Button
      variant={user.is_active ? "ghost" : "secondary"}
      className="px-2 py-1"
      loading={update.isPending}
      onClick={() => update.mutate({ id: user.id, is_active: !user.is_active })}
    >
      {user.is_active ? "Desactivar" : "Reactivar"}
    </Button>
  );

  return (
    <tr className={cx("border-b border-line align-top last:border-0", !user.is_active && "text-muted")}>
      <td className="px-4 py-3">
        <span className="font-medium">{user.name}</span>
        {isMe && <span className="ml-2 text-xs text-muted">(vos)</span>}
        {!user.is_active && <span className="ml-2 text-xs">Desactivado</span>}
        <span className="block text-xs break-all text-muted">{user.email}</span>
        {/* En el celular no entran las otras columnas: rol y acción van acá abajo. */}
        <div className="mt-2 flex flex-wrap items-center gap-2 sm:hidden">
          {roleControl}
          {activeControl}
        </div>
        {update.isError && (
          <div className="mt-2">
            <ErrorState message={errorMessage(update.error)} />
          </div>
        )}
      </td>
      <td className="hidden px-4 py-3 sm:table-cell">{roleControl}</td>
      <td className="hidden px-4 py-3 whitespace-nowrap md:table-cell">
        {user.last_login_at ? formatDateTime(user.last_login_at) : "Nunca entró"}
      </td>
      <td className="hidden px-4 py-3 text-right sm:table-cell">{activeControl}</td>
    </tr>
  );
}

export default function UsersPage() {
  const me = useMe();
  const allowed = can(me.data, "manage_users");
  const users = useUsers();
  const [adding, setAdding] = useState(false);

  if (!allowed) {
    return (
      <EmptyState title="Tu rol no puede ver los usuarios">
        Los administra alguien con rol de administración.
      </EmptyState>
    );
  }

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight">Usuarios</h1>
          <p className="mt-1 text-sm text-muted">
            Quién puede entrar a Mavic{me.data?.company ? ` en ${me.data.company.name}` : ""} y qué
            puede hacer. Al desactivar a alguien se cierran sus sesiones en el momento.
          </p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden className="size-4" /> Nuevo usuario
          </Button>
        )}
      </div>

      <div className="mt-6 space-y-6">
        {adding && <NewUserForm onClose={() => setAdding(false)} />}

        {users.isPending && <LoadingState label="Cargando usuarios…" />}
        {users.isError && <QueryError error={users.error} retry={users.refetch} />}
        {users.isSuccess && (
          <div className="overflow-x-auto rounded-lg border border-line bg-surface">
            <table className="w-full text-sm">
              <caption className="sr-only">Usuarios de la empresa</caption>
              <thead className="border-b border-line text-left text-xs text-muted">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">Usuario</th>
                  <th scope="col" className="hidden px-4 py-3 font-medium sm:table-cell">Rol</th>
                  <th scope="col" className="hidden px-4 py-3 font-medium md:table-cell">Último ingreso</th>
                  <th scope="col" className="hidden px-4 py-3 text-right font-medium sm:table-cell">
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {users.data.map((user) => (
                  <UserRow key={user.id} user={user} isMe={user.id === me.data?.user.id} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
