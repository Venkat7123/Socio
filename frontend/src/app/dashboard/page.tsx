"use client";

import { useState } from "react";

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState("routing");

  const cases = [
    { id: "TKT-8940", dept: "Water Board", status: "Field Crew Assigned", time: "10 mins ago", hops: 1, hazard: "Medium" },
    { id: "TKT-8941", dept: "Electricity", status: "Pending Verification", time: "45 mins ago", hops: 2, hazard: "High" },
    { id: "TKT-8942", dept: "Corporation", status: "SLA Breach Alert", time: "3 hrs ago", hops: 3, hazard: "Low" },
  ];

  return (
    <main className="container flex-column" style={{ maxWidth: "1400px", marginTop: "1rem", gap: "2rem" }}>
      <header className="flex-between">
        <div>
          <h1 style={{ fontSize: "2rem" }}>Command Center</h1>
          <p className="subtext">Live view of the Socio Engine department agent network &amp; field execution.</p>
        </div>
        <div style={{ display: "flex", gap: "1rem" }}>
          <button 
            className={`glass-button ${activeTab !== "routing" ? "secondary" : ""}`}
            onClick={() => setActiveTab("routing")}
            style={{ padding: "8px 16px", fontSize: "0.9rem" }}
          >
            Agent Routing
          </button>
          <button 
            className={`glass-button ${activeTab !== "analytics" ? "secondary" : ""}`}
            onClick={() => setActiveTab("analytics")}
            style={{ padding: "8px 16px", fontSize: "0.9rem" }}
          >
            Hotspot Analytics
          </button>
        </div>
      </header>

      {activeTab === "routing" ? (
        <div className="grid-layout">
          {/* Active Cases Panel */}
          <div className="glass-panel flex-column" style={{ gridColumn: "span 2", gap: "1.5rem" }}>
            <div className="flex-between">
              <h3>Live Case Engine</h3>
              <span className="status-badge status-active">System Healthy</span>
            </div>
            
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--panel-border)" }}>
                    <th style={{ padding: "12px", color: "var(--text-secondary)" }}>Ticket ID</th>
                    <th style={{ padding: "12px", color: "var(--text-secondary)" }}>Routed Dept</th>
                    <th style={{ padding: "12px", color: "var(--text-secondary)" }}>Status</th>
                    <th style={{ padding: "12px", color: "var(--text-secondary)" }}>Hops</th>
                    <th style={{ padding: "12px", color: "var(--text-secondary)" }}>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                      <td style={{ padding: "16px 12px", fontWeight: "bold" }}>{c.id}</td>
                      <td style={{ padding: "16px 12px" }}>
                        <span style={{ color: c.dept === "Water Board" ? "var(--accent-cyan)" : "var(--accent-purple)" }}>
                          {c.dept}
                        </span>
                      </td>
                      <td style={{ padding: "16px 12px" }}>
                        <span className={`status-badge ${c.status.includes('SLA') ? 'status-pending' : 'status-active'}`} style={{ 
                          borderColor: c.status.includes('SLA') ? 'var(--accent-red)' : '',
                          color: c.status.includes('SLA') ? '#fca5a5' : '',
                          background: c.status.includes('SLA') ? 'rgba(239, 68, 68, 0.2)' : ''
                        }}>
                          {c.status}
                        </span>
                      </td>
                      <td style={{ padding: "16px 12px" }}>
                        <span style={{ color: c.hops >= 3 ? "var(--accent-red)" : "inherit" }}>
                          {c.hops}/2 Max
                        </span>
                      </td>
                      <td style={{ padding: "16px 12px", color: "var(--text-secondary)", fontSize: "0.9rem" }}>{c.time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Verification Stream Panel */}
          <div className="glass-panel flex-column" style={{ gap: "1rem" }}>
            <h3>Verification Stream</h3>
            <p className="subtext">Waiting on citizen confirmation.</p>
            
            <div className="flex-column" style={{ gap: "1rem", marginTop: "1rem" }}>
              <div style={{ background: "rgba(0,0,0,0.3)", borderRadius: "8px", padding: "12px", border: "1px solid var(--panel-border)" }}>
                <div className="flex-between" style={{ marginBottom: "8px" }}>
                  <span style={{ fontWeight: "bold", fontSize: "0.9rem" }}>TKT-8938 (Pothole)</span>
                  <span style={{ fontSize: "0.8rem", color: "var(--accent-green)" }}>Photo + GPS Matched</span>
                </div>
                <div style={{ height: "100px", background: "url('https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?auto=format&fit=crop&q=80&w=400') center/cover", borderRadius: "4px", marginBottom: "12px" }}></div>
                <div className="flex-between">
                  <span className="status-badge" style={{ background: "rgba(255,255,255,0.1)", border: "none" }}>Citizen Pending</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="glass-panel" style={{ height: "600px", position: "relative", overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
          {/* Simulated WebGL Map Background */}
          <div style={{ 
            position: "absolute", inset: 0, opacity: 0.4,
            backgroundImage: "radial-gradient(circle at 50% 50%, transparent 20%, #0b0f19 80%), url('https://images.unsplash.com/photo-1524661135-423995f22d0b?auto=format&fit=crop&q=80&w=1600')",
            backgroundSize: "cover", backgroundPosition: "center", filter: "blur(2px) sepia(1) hue-rotate(180deg) saturate(3)"
          }}></div>
          
          <div style={{ position: "relative", zIndex: 1, textAlign: "center", background: "rgba(0,0,0,0.7)", padding: "2rem", borderRadius: "16px", border: "1px solid var(--accent-cyan)" }}>
            <h2 className="text-gradient" style={{ fontSize: "2.5rem", marginBottom: "1rem" }}>Ward 42 Hotspot</h2>
            <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }}>High frequency of repeat disputes detected for Water Board assets.</p>
            <div className="flex-between" style={{ gap: "2rem" }}>
              <div className="flex-column">
                <span style={{ fontSize: "2rem", fontWeight: "bold", color: "var(--accent-red)" }}>14</span>
                <span className="subtext">Repeat Disputes</span>
              </div>
              <div className="flex-column">
                <span style={{ fontSize: "2rem", fontWeight: "bold", color: "var(--accent-cyan)" }}>98%</span>
                <span className="subtext">AI Correlation</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
