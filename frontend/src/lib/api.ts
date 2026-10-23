/**
 * Cliente de la API de Mavic.
 *
 * Todos los pedidos van a /api/... (mismo origen que la página). El servidor de
 * Next los reenvía al backend (ver next.config.ts). La cookie de sesión viaja
 * sola: el código nunca la lee ni la guarda (es HttpOnly).
 *
 * Errores: el backend siempre responde { detail, code, request_id }. Acá se
 * convierte en un ApiError con esos datos, para que cada pantalla pueda decidir
 * qué mostrar según el `code` (ej. "RULE_OVERLAP") y no según el texto.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly body: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** La sesión venció o no existe: hay que volver a iniciar sesión. */
  get isUnauthorized(): boolean {
    return this.status === 401;
  }
}

type QueryValue = string | number | boolean | null | undefined;
/** Una lista se manda repitiendo la clave: ?invoice_id=a&invoice_id=b */
type QueryParam = QueryValue | readonly string[];

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, QueryParam>;
  json?: unknown;
  formData?: FormData;
  signal?: AbortSignal;
}

const FALLBACK_MESSAGES: Record<number, string> = {
  401: "Tu sesión venció. Volvé a iniciar sesión.",
  403: "Tu rol no tiene permiso para hacer esto.",
  404: "No se encontró lo que buscabas.",
  429: "Demasiados intentos. Esperá unos minutos y volvé a probar.",
};

export function buildUrl(path: string, query?: Record<string, QueryParam>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (Array.isArray(value)) {
      for (const item of value) params.append(key, item);
    } else if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const search = params.toString();
  return `/api${path}${search ? `?${search}` : ""}`;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.formData) {
    body = options.formData; // el navegador arma el Content-Type con el "boundary"
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? "GET",
      headers,
      body,
      credentials: "same-origin",
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "NETWORK_ERROR", "No se pudo conectar con el servidor. ¿Está levantado?");
  }

  if (response.status === 204) return undefined as T;

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data: unknown = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const payload = (isJson && data && typeof data === "object" ? data : {}) as Record<
      string,
      unknown
    >;
    const message =
      (typeof payload.detail === "string" && payload.detail) ||
      FALLBACK_MESSAGES[response.status] ||
      `Error inesperado del servidor (${response.status}).`;
    const code = typeof payload.code === "string" ? payload.code : `HTTP_${response.status}`;
    throw new ApiError(response.status, code, message, payload);
  }
  return data as T;
}

/**
 * ¿Puede andar si se vuelve a intentar? Solo si falló la red o el servidor
 * (5xx). Un 403 o un 404 van a dar lo mismo la próxima vez.
 */
export function isTransient(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status === 0 || error.status >= 500;
}

/** Mensaje para mostrar a la persona, venga de donde venga el error. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Ocurrió un error inesperado.";
}
