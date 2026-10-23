import { useEffect, useState } from "react";

/**
 * El valor, pero recién cuando dejó de cambiar por `delay` ms. Sirve para los
 * buscadores: se le pide al backend una vez cuando la persona termina de
 * escribir, no una vez por letra.
 */
export function useDebounced<T>(value: T, delay = 300): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}
