import { describe, expect, it } from "vitest";

import { eventsToCsv } from "./audit";
import type { AuditEvent } from "@/lib/types";

const EVENT: AuditEvent = {
  id: "e1",
  occurred_at: "2026-10-23T09:55:00Z",
  actor_kind: "user",
  actor_name: "Laura Gómez",
  action: "RULE_UPDATED",
  level: "critical",
  subject_kind: "rule",
  subject_id: "r1",
  subject_label: "Regla 'Mora alta'",
  summary: 'Cambió la regla "Mora alta": descuento (%).',
  details: {},
};

describe("eventsToCsv", () => {
  it("arma un CSV que Excel en castellano abre bien", () => {
    const csv = eventsToCsv([EVENT], () => "23/10/2026, 06:55");
    const [header, row] = csv.replace("﻿", "").trim().split("\r\n");

    expect(csv.startsWith("﻿")).toBe(true);
    expect(header).toBe('"Fecha y hora";"Quién";"Evento";"Sobre";"Detalle";"Nivel";"Id"');
    // Las comillas del texto se duplican, como pide el formato.
    expect(row).toContain('"Cambió la regla ""Mora alta"": descuento (%)."');
    expect(row).toContain('"Cambio de regla"');
  });
});
