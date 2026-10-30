import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

describe("Vite Static GitHub Pages config (Phase P7-B)", () => {
  const configPath = path.resolve(__dirname, "../../vite.config.ts");
  const config = fs.readFileSync(configPath, "utf8");

  it("configures relative base for GitHub Pages subpath compatibility", () => {
    expect(config).toContain('base: "./"');
  });

  it("does not proxy to FastAPI 127.0.0.1:8899 (100% static client-side)", () => {
    expect(config).not.toContain("127.0.0.1:8899");
    expect(config).not.toContain("PROXY_PATHS");
  });
});
