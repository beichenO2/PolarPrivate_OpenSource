/**
 * Regression guard: the document-identity sanitize middleware is retired.
 *
 * PolarPrivate is a secret vault + LLM proxy (Agent supply plane). The
 * /api/sanitize/mappings endpoint returns secret keys only, so a client-side
 * sanitize/resolve middleware has no data to work with and must not be shipped.
 */
import { describe, it, expect } from "vitest";

describe("sanitize middleware retired", () => {
  it("is not exported from the package entrypoint", async () => {
    const mod = await import("../src/index.js");
    expect(mod).not.toHaveProperty("PrivPortalMiddleware");
    expect(Object.keys(mod).filter((k) => /middleware/i.test(k))).toEqual([]);
  });

  it("has no middleware module to import", async () => {
    await expect(import("../src/middleware.js")).rejects.toThrow();
  });
});

describe("supply-plane surface retained", () => {
  it("still exports identity-binding and LLM helpers", async () => {
    const mod = await import("../src/index.js");
    for (const name of [
      "resolveUser",
      "listUserBindings",
      "createBinding",
      "chatCompletion",
      "isHealthy",
      "listModels",
    ]) {
      expect(typeof (mod as Record<string, unknown>)[name]).toBe("function");
    }
  });
});
