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

  it("prepares a portable offline dashboard bundle from the versioned sample", () => {
    const catalogPath = resolve(process.cwd(), "public/data/index.json");
    expect(existsSync(catalogPath)).toBe(true);
    const catalog = JSON.parse(readFileSync(catalogPath, "utf8"));
    const demo = catalog.reports.find((item: { run_id: string }) => item.run_id === "public_fixture_company_strategy");
    expect(demo).toBeTruthy();
    const bundlePath = resolve(process.cwd(), "public/data", demo.data_url.split("/").at(-1));
    expect(existsSync(bundlePath)).toBe(true);
    const bundle = JSON.parse(readFileSync(bundlePath, "utf8"));
    expect(bundle.dashboard.report_data.scope.topic).toContain("Example Group");
    expect(bundle.dashboard.meta.is_test_fixture).toBe(true);
  });

  it("prepares the professional market-entry example without outputs", () => {
    const catalog = JSON.parse(readFileSync(resolve(process.cwd(), "public/data/index.json"), "utf8"));
    const example = catalog.reports.find((item: { run_id: string }) => item.run_id === "public_fixture_professional_market_entry");
    expect(example).toBeTruthy();
    const bundle = JSON.parse(readFileSync(resolve(process.cwd(), "public/data", example.data_url.split("/").at(-1)), "utf8"));
    expect(bundle.dashboard.meta.is_test_fixture).toBe(true);
    expect(bundle.dashboard.report_data.recommendations[0].label).toContain("伙伴");
    expect(bundle.dashboard.report_data.data_gaps).toHaveLength(1);
    expect(bundle.dashboard.metrics[0].verification_status).toBe("SUPPORTED");
    expect(bundle.dashboard.metrics[2].verification_status).toBe("PARTIAL");
  });
});
