import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-md px-6 py-24">
      <h1 className="text-xl font-semibold">Esta página no existe</h1>
      <p className="mt-2 text-sm text-muted">Puede que el enlace esté mal escrito o sea viejo.</p>
      <Link href="/" className="mt-6 inline-block text-sm font-semibold text-petrol underline">
        Ir al inicio
      </Link>
    </main>
  );
}
