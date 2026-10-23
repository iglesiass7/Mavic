import { describe, expect, it } from "vitest";

import { callFiltersQuery, callOutcome, readCallFilters } from "./conversations";
import type { Conversation } from "@/lib/types";

const DONE: Conversation = {
  id: "c1",
  provider_conversation_id: "conv_1",
  origin: "OUTBOUND",
  status: "DONE",
  failure_reason: null,
  review_reason: null,
  started_at: "2026-10-22T15:00:00Z",
  identity_verified: null,
  offered: [],
  result: "ACUERDO",
  unknown_count: null,
  agreement: null,
  summary: null,
  call_duration_secs: 60,
  transcript: [],
};

describe("filtros de conversaciones en la dirección", () => {
  it("ida y vuelta: lo que se escribe en la URL se vuelve a leer igual", () => {
    const filters = { search: "#12", outcome: "DESCONOCIMIENTO" as const, day: "2026-10-22", page: 2 };
    const text = callFiltersQuery(filters, "abc");
    expect(text).toBe("q=%2312&estado=no-reconoce&fecha=2026-10-22&pagina=2&llamada=abc");
    expect(readCallFilters(new URLSearchParams(text))).toEqual(filters);
  });

  it("ignora valores inventados", () => {
    expect(readCallFilters(new URLSearchParams("estado=cualquiera&fecha=ayer&pagina=-3"))).toEqual({
      search: "",
      outcome: "",
      day: "",
      page: 1,
    });
  });

  it("sin filtros, la dirección queda limpia", () => {
    expect(callFiltersQuery({ search: "  ", outcome: "", day: "", page: 1 }, null)).toBe("");
  });
});

describe("callOutcome", () => {
  it("el estado de la llamada gana sobre el resultado", () => {
    expect(callOutcome({ ...DONE, status: "IN_PROGRESS", result: null }).label).toBe("En curso");
    expect(callOutcome({ ...DONE, status: "FAILED", result: null }).label).toBe("No se pudo llamar");
    expect(callOutcome({ ...DONE, status: "NEEDS_REVIEW" }).label).toBe("Para revisar");
  });

  it("si terminó bien, muestra el resultado con el color del estado de caso", () => {
    expect(callOutcome(DONE)).toEqual({ label: "Acuerdo", tone: "agreement" });
    expect(callOutcome({ ...DONE, result: "DESCONOCIMIENTO" })).toEqual({ label: "No reconoce", tone: "disputed" });
  });
});
