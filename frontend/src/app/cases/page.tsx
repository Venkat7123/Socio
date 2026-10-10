"use client";

import { useCases } from "@/lib/useCases";
import Link from "next/link";
import { Search, Filter, Clock } from "lucide-react";

function statusClass(state: string) {
  switch (state) {
    case "ROUTED": return "status-badge status-routed";
    case "ASSIGNED": return "status-badge status-assigned";
    case "DISPUTE": return "status-badge status-dispute";
    case "ESCALATED": return "status-badge status-escalated";
    case "NEEDS_INFO": return "status-badge status-needs_info";
    case "ERROR": return "status-badge status-error";
    case "SPLIT": return "status-badge status-split";
    case "DUPLICATE_LINKED": return "status-badge status-duplicate_linked";
    case "NEW": return "status-badge status-routed";
    default: return "status-badge status-pending";
  }
}

export default function CaseList() {
  const { cases, isLoaded } = useCases();

  if (!isLoaded) return null;

  return (
    <main className="container flex-column" style={{ maxWidth: "1200px", marginTop: "1rem", gap: "2rem" }}>
      <header className="flex-between">
        <div>
          <h1 style={{ fontSize: "2rem", color: "#0f172a" }}>Officer Dashboard — All Cases</h1>
          <p className="subtext">View and manage civic cases routed by the Socio Engine.</p>
        </div>
      </header>

      <div className="glass-panel" style={{ padding: "1rem 1.5rem" }}>
        <div className="flex-between">
          <div style={{ display: "flex", gap: "1rem", flex: 1, marginRight: "2rem" }}>
            <div style={{ position: "relative", flex: 1 }}>
              <Search size={18} color="#64748b" style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)" }} />
              <input type="text" className="glass-input" placeholder="Search Case ID or keyword..." style={{ paddingLeft: "40px" }} />
            </div>
          </div>
          <div style={{ display: "flex", gap: "1rem" }}>
            <button className="glass-button secondary flex-between" style={{ gap: "8px", padding: "8px 16px" }}>
              <Filter size={16} /> Status
            </button>
            <button className="glass-button secondary flex-between" style={{ gap: "8px", padding: "8px 16px" }}>
              <Filter size={16} /> Ward
            </button>
          </div>
        </div>
      </div>

      <div className="glass-panel" style={{ padding: 0, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #e2e8f0", background: "#f8fafc" }}>
              <th style={{ padding: "1rem", color: "#475569", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Case ID</th>
              <th style={{ padding: "1rem", color: "#475569", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Category</th>
              <th style={{ padding: "1rem", color: "#475569", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Location</th>
              <th style={{ padding: "1rem", color: "#475569", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Status</th>
              <th style={{ padding: "1rem", color: "#475569", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>SLA Deadline</th>
              <th style={{ padding: "1rem", color: "#475569", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.04em" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => {
              const isBreached = new Date(c.sla.deadline) < new Date();
              
              return (
                <tr key={c.case_id} style={{ borderBottom: "1px solid #f1f5f9", transition: "background 0.2s" }} className="table-row-hover">
                  <td style={{ padding: "1rem", fontWeight: "700", color: "#0f172a" }}>{c.case_id}</td>
                  <td style={{ padding: "1rem", textTransform: "capitalize", color: "#475569" }}>{c.category}</td>
                  <td style={{ padding: "1rem", color: "#475569" }}>{c.location.ward}</td>
                  <td style={{ padding: "1rem" }}>
                    <span className={statusClass(c.state)}>
                      {c.state}
                    </span>
                  </td>
                  <td style={{ padding: "1rem" }}>
                    <div style={{ display: "flex", gap: "6px", alignItems: "center", color: isBreached ? "#dc2626" : "#059669", fontWeight: isBreached ? 700 : 500 }}>
                      <Clock size={14} />
                      <span style={{ fontSize: "0.9rem" }}>
                        {new Date(c.sla.deadline).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: "1rem" }}>
                    <Link href={`/cases/${c.case_id}`} style={{ color: "#0284c7", textDecoration: "none", fontWeight: "700", fontSize: "0.88rem" }}>
                      View Details →
                    </Link>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </main>
  );
}
