import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Sheet } from "./Sheet";

describe("Sheet", () => {
  it("si la pantalla de atrás se redibuja, el foco se queda donde estaba", async () => {
    const { rerender } = render(
      <Sheet title="Invitar miembro" open onClose={() => {}}>
        <input aria-label="Nombre" />
      </Sheet>,
    );
    await userEvent.click(screen.getByLabelText("Nombre"));
    // Un padre que se redibuja pasa una función nueva cada vez.
    rerender(
      <Sheet title="Invitar miembro" open onClose={() => {}}>
        <input aria-label="Nombre" />
      </Sheet>,
    );
    expect(screen.getByLabelText("Nombre")).toHaveFocus();
  });

  it("Escape cierra con la última función recibida", async () => {
    const first = vi.fn();
    const latest = vi.fn();
    const { rerender } = render(
      <Sheet title="Detalle" open onClose={first}>
        contenido
      </Sheet>,
    );
    rerender(
      <Sheet title="Detalle" open onClose={latest}>
        contenido
      </Sheet>,
    );
    await userEvent.keyboard("{Escape}");
    expect(latest).toHaveBeenCalledOnce();
    expect(first).not.toHaveBeenCalled();
  });
});
