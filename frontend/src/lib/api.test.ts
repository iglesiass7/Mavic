import { ApiError, apiFetch, buildUrl, errorMessage, isTransient } from "./api";

function mockFetch(response: Response | Error) {
  const fn = vi.fn(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("buildUrl", () => {
  it("prefixes /api and skips empty filters", () => {
    expect(buildUrl("/cases", { status: "", sort: "newest", limit: 20, offset: undefined })).toBe(
      "/api/cases?sort=newest&limit=20",
    );
  });
});

describe("apiFetch", () => {
  it("returns the JSON body", async () => {
    mockFetch(json(200, { items: [], total: 0 }));
    await expect(apiFetch("/cases")).resolves.toEqual({ items: [], total: 0 });
  });

  it("sends JSON bodies with the right header and same-origin credentials", async () => {
    const fetchMock = mockFetch(json(200, {}));
    await apiFetch("/auth/login", { method: "POST", json: { email: "a@b.com" } });
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.credentials).toBe("same-origin");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(init.body).toBe('{"email":"a@b.com"}');
  });

  it("turns the backend error format into an ApiError with its code", async () => {
    mockFetch(json(409, { detail: "Se pisa con la regla activa 'X'.", code: "RULE_OVERLAP" }));
    const error = await apiFetch("/negotiation-rules").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "RULE_OVERLAP" });
    expect(errorMessage(error)).toBe("Se pisa con la regla activa 'X'.");
  });

  it("marks expired sessions", async () => {
    mockFetch(json(401, { detail: "Tu sesión expiró.", code: "SESSION_INVALID" }));
    const error = (await apiFetch("/auth/me").catch((e: unknown) => e)) as ApiError;
    expect(error.isUnauthorized).toBe(true);
  });

  it("explains when the server cannot be reached", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    const error = (await apiFetch("/cases").catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("NETWORK_ERROR");
  });

  it("handles 204 No Content", async () => {
    mockFetch(new Response(null, { status: 204 }));
    await expect(apiFetch("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });
});

describe("isTransient (¿sirve reintentar?)", () => {
  it.each([
    [new ApiError(0, "NETWORK_ERROR", "Sin conexión"), true],
    [new ApiError(503, "HTTP_503", "Servicio no disponible"), true],
    [new Error("cualquier otra cosa"), true],
    [new ApiError(404, "CASE_NOT_FOUND", "El caso no existe."), false],
    [new ApiError(403, "FORBIDDEN", "No tenés permiso."), false],
  ])("%s -> %s", (error, expected) => {
    expect(isTransient(error)).toBe(expected);
  });
});
