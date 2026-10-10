import React from 'react';
import { ShieldAlert, Split, CheckCircle2, XCircle, Clock, AlertTriangle } from 'lucide-react';

export default function TranscriptPanel({ caseData }: { caseData: any }) {
  const { messages, state, sla } = caseData;

  const isBreached = new Date(sla.deadline) < new Date();

  return (
    <div className="glass-panel flex-column" style={{ padding: "1.5rem", gap: "1.5rem" }}>
      <div className="flex-between" style={{ borderBottom: "1px solid #e2e8f0", paddingBottom: "1rem" }}>
        <div>
          <h2 style={{ fontSize: "1.25rem", marginBottom: "4px", color: "#0f172a" }}>Dispute Transcript</h2>
          <p className="subtext">Evidence-backed departmental referral protocol</p>
        </div>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <div style={{ background: isBreached ? "#fee2e2" : "#dcfce7", padding: "6px 12px", borderRadius: "8px", display: "flex", gap: "8px", alignItems: "center", border: `1px solid ${isBreached ? "#fca5a5" : "#bbf7d0"}` }}>
            <Clock size={16} color={isBreached ? "#b91c1c" : "#15803d"} />
            <span style={{ fontSize: "0.85rem", fontWeight: "700", color: isBreached ? "#b91c1c" : "#15803d" }}>
              {isBreached ? "SLA Breached" : "SLA Running"}
            </span>
          </div>
        </div>
      </div>

      <div className="flex-column" style={{ gap: "1.25rem" }}>
        {messages.map((msg: any, index: number) => (
          <div key={msg.id} style={{ display: "flex", gap: "1rem" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <div style={{ width: "26px", height: "26px", borderRadius: "50%", background: "#e0f2fe", border: "1px solid #bae6fd", color: "#0369a1", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "0.78rem", fontWeight: "bold" }}>
                {msg.hop}
              </div>
              {index !== messages.length - 1 && <div style={{ width: "2px", flex: 1, background: "#cbd5e1", margin: "4px 0" }}></div>}
            </div>
            
            <div style={{ flex: 1, background: "#f8fafc", borderRadius: "12px", border: "1px solid #e2e8f0", padding: "1.1rem" }}>
              <div className="flex-between" style={{ marginBottom: "0.85rem" }}>
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <strong style={{ textTransform: "capitalize", color: "#0284c7" }}>{msg.from.replace('_agent', '')}</strong>
                  <span className="subtext">→</span>
                  <span className="subtext" style={{ fontWeight: 600, color: "#475569" }}>Engine</span>
                </div>
                
                <span className="status-badge" style={{ 
                  background: msg.type === 'reject' ? '#fee2e2' : msg.type === 'split' ? '#f3e8ff' : '#dcfce7',
                  color: msg.type === 'reject' ? '#b91c1c' : msg.type === 'split' ? '#6b21a8' : '#15803d',
                  border: `1px solid ${msg.type === 'reject' ? '#fca5a5' : msg.type === 'split' ? '#e9d5ff' : '#bbf7d0'}`,
                  display: "flex", gap: "4px", alignItems: "center", fontWeight: 700
                }}>
                  {msg.type === 'reject' && <XCircle size={14} />}
                  {msg.type === 'split' && <Split size={14} />}
                  {msg.type === 'accept' && <CheckCircle2 size={14} />}
                  {msg.type.toUpperCase()}
                </span>
              </div>

              {msg.target && (
                <p style={{ fontSize: "0.9rem", marginBottom: "0.85rem", color: "#0f172a" }}>
                  Proposed routing to <strong style={{ color: "#6d28d9", textTransform: "capitalize" }}>{msg.target.replace('_agent', '')}</strong>.
                </p>
              )}

              {msg.sub_tasks && (
                <div style={{ background: "#f5f3ff", padding: "12px", borderRadius: "8px", marginBottom: "0.85rem", border: "1px solid #ddd6fe" }}>
                  <p style={{ fontSize: "0.85rem", fontWeight: "700", marginBottom: "8px", color: "#6d28d9" }}>Proposed Split:</p>
                  <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "8px" }}>
                    {msg.sub_tasks.map((task: any, i: number) => (
                      <li key={i} style={{ fontSize: "0.85rem", display: "flex", gap: "8px" }}>
                        <span style={{ color: "#0284c7", fontWeight: 700, textTransform: "capitalize" }}>{task.department}:</span>
                        <span style={{ color: "#475569" }}>{task.rationale}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div style={{ background: "#ffffff", padding: "12px", borderRadius: "8px", border: "1px solid #e2e8f0" }}>
                <p style={{ fontSize: "0.85rem", fontWeight: "700", marginBottom: "8px", display: "flex", alignItems: "center", gap: "6px", color: "#0284c7" }}>
                  <ShieldAlert size={15} color="#0284c7" /> Evidence Provided (Confidence: {Math.round(msg.confidence * 100)}%)
                </p>
                <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "8px" }}>
                  {msg.evidence.map((ev: any, i: number) => (
                    <li key={i} style={{ fontSize: "0.85rem" }}>
                      <span style={{ color: "#0f172a" }}>&ldquo;{ev.finding}&rdquo;</span>
                      <span className="subtext" style={{ marginLeft: "8px", fontSize: "0.78rem" }}>(Source: {ev.source} / ref: {ev.ref})</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        ))}
      </div>

      {state === "ESCALATED" && (
        <div style={{ background: "#fef2f2", padding: "1rem", borderRadius: "10px", border: "1px solid #fca5a5", display: "flex", gap: "12px", alignItems: "flex-start" }}>
          <AlertTriangle color="#dc2626" size={20} />
          <div>
            <h4 style={{ color: "#b91c1c", marginBottom: "4px", fontWeight: 700 }}>Escalated to Zonal Officer</h4>
            <p style={{ fontSize: "0.85rem", color: "#475569" }}>Transfer cap reached. Automated routing paused pending human adjudication.</p>
          </div>
        </div>
      )}
      
      <p style={{ textAlign: "center", fontSize: "0.75rem", color: "#64748b", marginTop: "0.5rem" }}>
        * Multi-agent decision history and confidence telemetry generated by Socio Engine.
      </p>
    </div>
  );
}
