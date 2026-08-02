import type { KnowledgeDoc } from "../../lib/api";

export function strField(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === "string" ? v : "";
}

export function evidenceItems(payload: Record<string, unknown>): { item: string; source: string }[] {
  const ev = payload["evidence"];
  if (!Array.isArray(ev)) return [];
  const out: { item: string; source: string }[] = [];
  for (const e of ev) {
    if (typeof e !== "object" || e === null) continue;
    const o = e as Record<string, unknown>;
    out.push({
      item: typeof o.item === "string" ? o.item : "",
      source: typeof o.source === "string" ? o.source : "",
    });
  }
  return out;
}

export function statusClass(statusVal: string): string {
  return statusVal === "activated" ? "ok" : statusVal === "proposed" ? "pending" : "bad";
}

export function statusTagClass(statusVal: string): string {
  return `tag ${statusClass(statusVal)}`;
}

export function fmtTs(ts: string | null): string {
  if (!ts) return "—";
  return ts.replace("T", " ").replace(/\.\d+Z$/, "Z");
}

export type KnowledgeViewState = {
  hit: import("../../lib/api").KnowledgeSearchHit;
  doc: KnowledgeDoc | null;
  activating: boolean;
  onSelect: (docId: string) => void;
  onActivate: () => void;
};
