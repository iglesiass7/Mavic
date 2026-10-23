"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { BrandLogo, PoweredBy } from "@/components/Brand";
import { Button, ErrorState } from "@/components/ui";
import { login, ME_QUERY_KEY, safeNextPath } from "@/features/auth";
import { errorMessage } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const mutation = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: (me) => {
      // Ya sabemos quién es: se guarda para no volver a pedirlo.
      queryClient.setQueryData(ME_QUERY_KEY, me);
      router.replace(safeNextPath(searchParams.get("next")));
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  const field =
    "w-full rounded-xl border border-gray-400 bg-white px-4 py-3 text-sm outline-none placeholder:text-gray-400 focus:border-rynx-primary focus:ring-2 focus:ring-rynx-primary/15";

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <div>
        <label htmlFor="email" className="ml-1 text-xs font-semibold tracking-wide text-ink">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          placeholder="usuario@empresa.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={`mt-1.5 ${field}`}
        />
      </div>
      <div>
        <label htmlFor="password" className="ml-1 text-xs font-semibold tracking-wide text-ink">
          Contraseña
        </label>
        <div className="relative mt-1.5">
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={`${field} pr-12`}
          />
          <button
            type="button"
            onClick={() => setShowPassword((shown) => !shown)}
            aria-label={showPassword ? "Ocultar la contraseña" : "Mostrar la contraseña"}
            aria-pressed={showPassword}
            className="absolute inset-y-0 right-0 flex items-center px-4 text-gray-500 hover:text-ink"
          >
            {showPassword ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
          </button>
        </div>
      </div>

      {mutation.isError && <ErrorState message={errorMessage(mutation.error)} />}

      <Button
        type="submit"
        loading={mutation.isPending}
        disabled={!email || !password}
        className="w-full py-4 font-bold"
      >
        Ingresar
      </Button>
    </form>
  );
}

/**
 * El login, con el diseño de Rynx: una tarjeta al centro con el logo.
 * Rynx tiene además "Recuérdame", "¿Olvidaste tu contraseña?" y links a
 * Términos y Privacidad; Mavic no tiene esas funciones (ni esos textos), así que
 * no se muestran botones que no hacen nada.
 */
export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f2f2f2] p-4 sm:p-6">
      <div className="w-full max-w-[480px] rounded-xl border border-ink bg-white px-6 py-10 shadow-[0_20px_50px_rgba(0,0,0,0.25)] sm:px-10 sm:py-12">
        <div className="mb-8 flex flex-col items-center text-center">
          <BrandLogo className="h-9 w-auto" />
          <h1 className="mt-6 text-lg font-bold text-ink">Bienvenido al panel de gestión de deuda con IA</h1>
          <p className="mt-1 text-sm text-muted">Ingresá con el email y la contraseña de tu empresa.</p>
        </div>
        <Suspense>
          <LoginForm />
        </Suspense>
        <div className="mt-10">
          <PoweredBy />
        </div>
      </div>
    </main>
  );
}
