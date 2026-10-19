import { describe, expect, it } from "vitest";

import { checkNewPassword, generatePassword, looksLikeEmail } from "./users";

describe("checkNewPassword (la misma política que el backend)", () => {
  it("pide al menos 10 caracteres y no solo espacios", () => {
    expect(checkNewPassword("corta")).toMatch(/al menos 10/);
    expect(checkNewPassword("          ")).toMatch(/espacios/);
    expect(checkNewPassword("una frase larga")).toBeNull();
    expect(checkNewPassword("x".repeat(129))).toMatch(/128/);
  });
});

describe("generatePassword", () => {
  it("arma 3 grupos de 4, sin letras que se confunden", () => {
    for (let i = 0; i < 50; i++) {
      const password = generatePassword();
      expect(password).toMatch(/^[A-Za-z2-9]{4}-[A-Za-z2-9]{4}-[A-Za-z2-9]{4}$/);
      expect(password).not.toMatch(/[lIoO01]/);
      expect(checkNewPassword(password)).toBeNull(); // la acepta el backend
    }
  });

  it("no repite", () => {
    const seen = new Set(Array.from({ length: 200 }, () => generatePassword()));
    expect(seen.size).toBe(200);
  });
});

describe("looksLikeEmail", () => {
  it.each([
    ["sofia@fibrasur.com", true],
    [" sofia@fibrasur.com ", true],
    ["sofia@fibrasur", false],
    ["sofia fibrasur.com", false],
    ["", false],
  ])("%j -> %s", (email, expected) => {
    expect(looksLikeEmail(email)).toBe(expected);
  });
});
