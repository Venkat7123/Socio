"use client";

import { useState } from "react";
import { useRole } from "@/lib/useRole";
import { useCases } from "@/lib/useCases";
import Link from "next/link";
import {
  Activity, BarChart2, Clock, AlertTriangle, CheckCircle2,
  GitBranch, Search, Filter, ChevronRight, Layers,
} from "lucide-react";

/* ─── helpers ──────────────────────────────────────────────── */
const ALL_STATES = [
  "NEW", "ROUTED", "DISPUTE", "ASSIGNED", "NEEDS_INFO", "ESCALATED", "SPLIT", "VERIFIED", "ERROR",
];

function statusPalette(state: string) {
  switch (state) {
    case "ROUTED": case "NEW": return { bg: "#e0f2fe", col: "#0369a1", border: "#bae6fd" };
    case "ASSIGNED":           return { bg: "#dcfce7", col: "#15803d", border: "#bbf7d0" };
    case "DISPUTE":            return { bg: "#fef3c7", col: "#b45309", border: "#fde68a" };
    case "ESCALATED": case "ERROR": return { bg: "#fee2e2", col: "#b91c1c", border: "#fca5a5" };
    case "NEEDS_INFO":         return { bg: "#f3e8ff", col: "#6b21a8", border: "#e9d5ff" };
    case "VERIFIED":           return { bg: "#dcfce7", col: "#15803d", border: "#bbf7d0" };
    default:                   return { bg: "#f1f5f9", col: "#475569", border: "#e2e8f0" };
  }
}

/* ─── Analytics Panel ──────────────────────────────────────── */
function AnalyticsPanel({ cases }: { cases: any[] }) {
  const catMap: Record<string, number> = {};
  const wardMap: Record<string, number> = {};
  const stateMap: Record<string, number> = {};

  cases.forEach((c) => {
    catMap[c.category || "general"] = (catMap[c.category || "general"] || 0) + 1;
    wardMap[c.location?.ward || "Unknown"] = (wardMap[c.location?.ward || "Unknown"] || 0) + 1;
    stateMap[c.state] = (stateMap[c.state] || 0) + 1;
  });

  const maxCat = Math.max(...Object.values(catMap), 1);
  const maxWard = Math.max(...Object.values(wardMap), 1);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.5rem" }}>
      {/* By Category */}
      <div className="glass-panel flex-column" style={{ gap: "1rem" }}>
        <h3 style={{ fontSize: "1.05rem", borderBottom: "1px solid var(--panel-border)", paddingBottom: "0.55rem" }}>Cases by Category</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {Object.entries(catMap).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
            <div key={cat}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginBottom: "4px" }}>
                <span style={{ textTransform: "capitalize", color: "var(--text-secondary)", fontWeight: 500 }}>{cat}</span>
                <span style={{ fontWeight: 700, color: "#0f172a" }}>{count}</span>
              </div>
              <div style={{ height: "7px", borderRadius: "4px", background: "#f1f5f9" }}>
                <div style={{ height: "100%", width: `${(count / maxCat) * 100}%`, borderRadius: "4px", background: "linear-gradient(90deg, #0284c7, #6d28d9)", transition: "width 0.6s ease" }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* By Ward */}
      <div className="glass-panel flex-column" style={{ gap: "1rem" }}>
        <h3 style={{ fontSize: "1.05rem", borderBottom: "1px solid var(--panel-border)", paddingBottom: "0.55rem" }}>Cases by Ward</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {Object.entries(wardMap).sort((a, b) => b[1] - a[1]).map(([ward, count]) => (
            <div key={ward}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem", marginBottom: "4px" }}>
                <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{ward}</span>
                <span style={{ fontWeight: 700, color: "#0f172a" }}>{count}</span>
              </div>
              <div style={{ height: "7px", borderRadius: "4px", background: "#f1f5f9" }}>
                <div style={{ height: "100%", width: `${(count / maxWard) * 100}%`, borderRadius: "4px", background: "linear-gradient(90deg, #6d28d9, #059669)", transition: "width 0.6s ease" }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* By Status */}
      <div className="glass-panel flex-column" style={{ gap: "1rem" }}>
        <h3 style={{ fontSize: "1.05rem", borderBottom: "1px solid var(--panel-border)", paddingBottom: "0.55rem" }}>Pipeline Distribution</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {Object.entries(stateMap).sort((a, b) => b[1] - a[1]).map(([state, count]) => {
            const { bg, col, border } = statusPalette(state);
            return (
              <div key={state} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", borderRadius: "10px", background: bg, border: `1px solid ${border}` }}>
                <span style={{ fontSize: "0.8rem", fontWeight: 700, color: col }}>{state}</span>
                <span style={{ fontSize: "0.95rem", fontWeight: 800, color: col }}>{count}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ─── Kanban Panel ──────────────────────────────────────── */
const KANBAN_COLS = [
  { states: ["NEW", "ROUTED"], label: "Queued", color: "#0284c7", bg: "#f0f9ff" },
  { states: ["DISPUTE", "NEEDS_INFO"], label: "Pending Action", color: "#d97706", bg: "#fffbeb" },
  { states: ["ASSIGNED", "SPLIT"], label: "In Progress", color: "#059669", bg: "#f0fdf4" },
  { states: ["ESCALATED", "ERROR"], label: "Escalated", color: "#dc2626", bg: "#fef2f2" },
  { states: ["VERIFIED"], label: "Resolved", color: "#6d28d9", bg: "#f5f3ff" },
];

function KanbanPanel({ cases }: { cases: any[] }) {
  return (
    <div style={{ overflowX: "auto", paddingBottom: "0.5rem" }}>
      <div style={{ display: "flex", gap: "1rem", minWidth: "960px" }}>
        {KANBAN_COLS.map((col) => {
          const colCases = cases.filter((c) => col.states.includes(c.state));
          return (
            <div key={col.label} style={{ flex: 1, minWidth: "210px", background: "#f8fafc", padding: "12px", borderRadius: "14px", border: "1px solid #e2e8f0" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px", paddingBottom: "8px", borderBottom: "1px solid #e2e8f0" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: col.color }} />
                  <span style={{ fontWeight: 700, fontSize: "0.8rem", color: "#475569", textTransform: "uppercase", letterSpacing: "0.04em" }}>{col.label}</span>
                </div>
                <span style={{ fontSize: "0.75rem", fontWeight: 700, padding: "2px 8px", borderRadius: "12px", background: col.bg, color: col.color, border: `1px solid ${col.color}30` }}>{colCases.length}</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {colCases.length === 0 ? (
                  <div style={{ padding: "1.5rem 1rem", borderRadius: "10px", border: "1px dashed #cbd5e1", textAlign: "center", color: "#94a3b8", fontSize: "0.8rem" }}>No cases</div>
                ) : (
                  colCases.map((c: any) => {
                    const { bg, col: txtCol, border } = statusPalette(c.state);
                    return (
                      <Link key={c.case_id} href={`/cases/${c.case_id}`} style={{ textDecoration: "none" }}>
                        <div style={{ padding: "12px 14px", borderRadius: "10px", background: "#ffffff", border: "1px solid #e2e8f0", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", transition: "all 0.2s ease", cursor: "pointer", borderLeft: `4px solid ${col.color}` }}
                          onMouseEnter={(e) => {
                            (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
                            (e.currentTarget as HTMLElement).style.boxShadow = "0 6px 16px rgba(0,0,0,0.06)";
                          }}
                          onMouseLeave={(e) => {
                            (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
                            (e.currentTarget as HTMLElement).style.boxShadow = "0 1px 3px rgba(0,0,0,0.04)";
                          }}
                        >
                          <div style={{ fontSize: "0.82rem", fontWeight: 700, color: "#0f172a", marginBottom: "4px" }}>{c.case_id}</div>
                          <div style={{ fontSize: "0.8rem", color: "#475569", textTransform: "capitalize", marginBottom: "8px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.category || "general"}</div>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: "0.75rem", color: "#64748b" }}>{c.location?.ward || "—"}</span>
                            <span style={{ fontSize: "0.68rem", padding: "2px 6px", borderRadius: "6px", background: bg, color: txtCol, fontWeight: 700 }}>{c.state}</span>
                          </div>
                        </div>
                      </Link>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Cases Table ──────────────────────────────────────── */
function CasesTable({ cases }: { cases: any[] }) {
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("");

  const filtered = cases.filter((c) => {
    const matchSearch = !search || c.case_id.toLowerCase().includes(search.toLowerCase()) || (c.category || "").toLowerCase().includes(search.toLowerCase()) || (c.location?.ward || "").toLowerCase().includes(search.toLowerCase());
    const matchStatus = !filterStatus || c.state === filterStatus;
    return matchSearch && matchStatus;
  });

  return (
    <div>
      {/* Filters */}
      <div style={{ display: "flex", gap: "1rem", marginBottom: "1rem", flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: 1, minWidth: "220px" }}>
          <Search size={16} color="#64748b" style={{ position: "absolute", left: "14px", top: "50%", transform: "translateY(-50%)" }} />
          <input className="glass-input" type="text" placeholder="Search case ID, category, ward..." style={{ paddingLeft: "40px" }} value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select
          className="glass-input"
          style={{ width: "190px" }}
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
        >
          <option value="">All Statuses</option>
          {ALL_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      <div className="glass-panel" style={{ padding: 0, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #e2e8f0", background: "#f8fafc" }}>
              {["Case ID", "Category", "Ward", "Status", "Hops", "SLA Deadline", ""].map((h) => (
                <th key={h} style={{ padding: "12px 18px", color: "#475569", fontSize: "0.78rem", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => {
              const { bg, col, border } = statusPalette(c.state);
              const isBreached = new Date(c.sla?.deadline) < new Date();
              return (
                <tr key={c.case_id} style={{ borderBottom: "1px solid #f1f5f9" }} className="table-row-hover">
                  <td style={{ padding: "14px 18px", fontWeight: 700, fontSize: "0.9rem", color: "#0f172a" }}>{c.case_id}</td>
                  <td style={{ padding: "14px 18px", textTransform: "capitalize", color: "#475569", fontSize: "0.88rem" }}>{c.category}</td>
                  <td style={{ padding: "14px 18px", color: "#475569", fontSize: "0.88rem" }}>{c.location?.ward}</td>
                  <td style={{ padding: "14px 18px" }}>
                    <span style={{ fontSize: "0.72rem", padding: "4px 10px", borderRadius: "20px", background: bg, color: col, border: `1px solid ${border}`, fontWeight: 700 }}>{c.state}</span>
                  </td>
                  <td style={{ padding: "14px 18px", color: c.hop_count >= 3 ? "#dc2626" : "#475569", fontSize: "0.88rem", fontWeight: c.hop_count >= 3 ? 700 : 400 }}>{c.hop_count ?? 0}</td>
                  <td style={{ padding: "14px 18px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px", color: isBreached ? "#dc2626" : "#059669", fontSize: "0.85rem", fontWeight: isBreached ? 700 : 500 }}>
                      <Clock size={14} />
                      {c.sla ? new Date(c.sla.deadline).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}
                    </div>
                  </td>
                  <td style={{ padding: "14px 18px" }}>
                    <Link href={`/cases/${c.case_id}`} style={{ color: "#0284c7", textDecoration: "none", fontWeight: 700, fontSize: "0.85rem", display: "inline-flex", alignItems: "center", gap: "4px" }}>
                      View <ChevronRight size={14} />
                    </Link>
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={7} style={{ padding: "3rem", textAlign: "center", color: "#64748b" }}>No matching cases found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ─── Main Page ──────────────────────────────────────────── */
type Tab = "overview" | "kanban" | "table" | "analytics";

export default function OfficerDashboard() {
  const { role, ready } = useRole(["officer", "field"]);
  const { cases, isLoaded } = useCases();
  const [tab, setTab] = useState<Tab>("overview");

  if (!ready || !isLoaded) return null;
  if (!role) return null;

  const breached = cases.filter((c) => c.sla?.breached || new Date(c.sla?.deadline) < new Date()).length;

  const summaryCards = [
    { label: "Total Cases", value: cases.length, icon: <Layers size={20} />, color: "#0284c7", bg: "#f0f9ff", border: "#bae6fd" },
    { label: "Active Disputes", value: cases.filter((c) => c.state === "DISPUTE").length, icon: <GitBranch size={20} />, color: "#d97706", bg: "#fffbeb", border: "#fde68a" },
    { label: "Escalated", value: cases.filter((c) => c.state === "ESCALATED").length, icon: <AlertTriangle size={20} />, color: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
    { label: "SLA Breaches", value: breached, icon: <Clock size={20} />, color: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
    { label: "Assigned", value: cases.filter((c) => c.state === "ASSIGNED").length, icon: <CheckCircle2 size={20} />, color: "#059669", bg: "#f0fdf4", border: "#bbf7d0" },
    { label: "Avg Hops", value: cases.length ? (cases.reduce((a, c) => a + (c.hop_count || 0), 0) / cases.length).toFixed(1) : "0", icon: <Activity size={20} />, color: "#6d28d9", bg: "#f5f3ff", border: "#ddd6fe" },
  ];

  const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "overview", label: "Overview", icon: <BarChart2 size={16} /> },
    { id: "kanban", label: "Kanban Board", icon: <Layers size={16} /> },
    { id: "table", label: "All Cases Table", icon: <Filter size={16} /> },
    { id: "analytics", label: "Analytics", icon: <Activity size={16} /> },
  ];

  return (
    <main style={{ maxWidth: "1400px", margin: "0 auto", padding: "2.5rem 1.5rem" }}>
      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "2.1rem", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: "6px", color: "#0f172a" }}>
          Monitoring Dashboard
        </h1>
        <p style={{ color: "#64748b", fontSize: "0.95rem" }}>
          Live view of the Socio Engine — case pipeline, department routing, and SLAs.
        </p>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        {summaryCards.map((s) => (
          <div key={s.label} style={{ background: s.bg, border: `1px solid ${s.border}`, borderRadius: "14px", padding: "1.15rem", boxShadow: "0 1px 3px rgba(0,0,0,0.02)" }}>
            <div style={{ color: s.color, marginBottom: "8px" }}>{s.icon}</div>
            <div style={{ fontSize: "1.9rem", fontWeight: 800, color: s.color, lineHeight: 1.1 }}>{s.value}</div>
            <div style={{ fontSize: "0.78rem", color: "#475569", marginTop: "4px", fontWeight: 600 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "6px", background: "#f1f5f9", borderRadius: "12px", padding: "5px", marginBottom: "2rem", width: "fit-content", border: "1px solid #cbd5e1" }}>
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              display: "flex", alignItems: "center", gap: "8px",
              padding: "9px 18px", borderRadius: "8px", border: "none", cursor: "pointer",
              fontWeight: 600, fontSize: "0.88rem", transition: "all 0.2s ease",
              background: tab === t.id ? "#ffffff" : "transparent",
              color: tab === t.id ? "#0284c7" : "#475569",
              boxShadow: tab === t.id ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
            }}
          >
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "overview" && (
        <div className="flex-column" style={{ gap: "2rem" }}>
          <div className="glass-panel">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
              <h3 style={{ fontSize: "1.15rem", color: "#0f172a" }}>Live Case Pipeline (Kanban)</h3>
              <span className="status-badge status-active">Socio Engine Active</span>
            </div>
            <KanbanPanel cases={cases} />
          </div>
          <div className="glass-panel" style={{ padding: "1.5rem" }}>
            <h3 style={{ fontSize: "1.15rem", color: "#0f172a", marginBottom: "1rem" }}>Recent Cases</h3>
            <CasesTable cases={cases.slice(0, 6)} />
          </div>
        </div>
      )}

      {tab === "kanban" && (
        <div className="glass-panel">
          <h3 style={{ marginBottom: "1.5rem", color: "#0f172a" }}>Full Kanban Board</h3>
          <KanbanPanel cases={cases} />
        </div>
      )}

      {tab === "table" && <CasesTable cases={cases} />}

      {tab === "analytics" && <AnalyticsPanel cases={cases} />}
    </main>
  );
}
