import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { QueryError } from "./ui";
import { ApiError } from "@/lib/api";

describe("QueryError", () => {
  it("si el caso no existe, lo dice y no ofrece reintentar", () => {
    const error = new ApiError(404, "CASE_NOT_FOUND", "El caso no existe.");
    render(<QueryError error={error} retry={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent("El caso no existe.");
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  });

  it("si se cortó la conexión, ofrece reintentar", async () => {
    const retry = vi.fn();
    const error = new ApiError(0, "NETWORK_ERROR", "Sin conexión.");
    render(<QueryError error={error} retry={retry} />);

    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
