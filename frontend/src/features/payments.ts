/** Seguimiento de pagos de los acuerdos (ADR-037): cuotas, registrar y anular pagos. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { AgreementStatus, AgreementTracking, IsoDate } from "@/lib/types";

export const AGREEMENT_STATUS_LABEL: Record<AgreementStatus, string> = {
  active: "Al día",
  fulfilled: "Cumplido",
  late: "Atrasado",
};

export function useCaseAgreements(caseId: string) {
  return useQuery({
    queryKey: ["agreements", caseId],
    queryFn: ({ signal }) => apiFetch<AgreementTracking[]>(`/cases/${caseId}/agreements`, { signal }),
  });
}

/** Al registrar o anular un pago puede cambiar el estado del caso (cerrado): se refresca todo. */
function useRefreshAfterPayment(caseId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      [["agreements", caseId], ["case", caseId], ["cases"], ["dashboard"]].map((queryKey) =>
        queryClient.invalidateQueries({ queryKey }),
      ),
    );
}

export function useRecordPayment(caseId: string) {
  const refresh = useRefreshAfterPayment(caseId);
  return useMutation({
    mutationFn: (input: { agreementId: string; number: number; paidOn: IsoDate; note: string }) =>
      apiFetch<AgreementTracking>(`/agreements/${input.agreementId}/installments/${input.number}/payment`, {
        method: "POST",
        json: { paid_on: input.paidOn, note: input.note.trim() || null },
      }),
    onSuccess: refresh,
  });
}

export function useUndoPayment(caseId: string) {
  const refresh = useRefreshAfterPayment(caseId);
  return useMutation({
    mutationFn: (input: { agreementId: string; number: number; reason: string }) =>
      apiFetch<AgreementTracking>(
        `/agreements/${input.agreementId}/installments/${input.number}/undo-payment`,
        { method: "POST", json: { reason: input.reason } },
      ),
    onSuccess: refresh,
  });
}
