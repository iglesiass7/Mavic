import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("muestra el estado con palabras, no solo con un color", () => {
    render(<StatusBadge status="disputed" />);

    const badge = screen.getByText("En disputa");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("title");
  });
});
