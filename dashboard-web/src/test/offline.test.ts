// @vitest-environment node
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("static and mobile delivery", () => {
  it("contains phone and tablet responsive breakpoints", () => {
    const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");
    expect(css).toContain("@media (max-width: 900px)");
    expect(css).toContain("@media (max-width: 620px)");
    expect(css).toContain(".page-widgets");
    expect(css).toContain("overflow-wrap: anywhere");
  });

  it("generates an offline single-file dashboard for the Xiaopeng run", () => {
    const snapshot = resolve(process.cwd(), "../outputs/20260806_182326_小鹏进入德国乘用车市场/dashboard/dashboard.html");
    expect(existsSync(snapshot)).toBe(true);
    const html = readFileSync(snapshot, "utf8");
    expect(html).toContain("dashboard-embedded-data");
    expect(html).not.toMatch(/<script[^>]+src=/i);
    expect(html).not.toMatch(/<link[^>]+rel=["']stylesheet/i);
  });
});
