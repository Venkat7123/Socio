"use client";

import { useState, useEffect, use } from "react";
import { useCases } from "@/lib/useCases";
import TranscriptPanel from "@/components/TranscriptPanel";
import { MapPin, Image as ImageIcon, AlertCircle } from "lucide-react";

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

export default function CaseDetail({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const { cases, isLoaded } = useCases();
  const [caseData, setCaseData] = useState<any>(null);

  useEffect(() => {
    if (isLoaded) {
      const found = cases.find((c: any) => c.case_id === resolvedParams.id);
      if (found) setCaseData(found);
    }
  }, [resolvedParams.id, cases, isLoaded]);

  if (!isLoaded || !caseData) return <div className="container" style={{ padding: "4rem", textAlign: "center", color: "#64748b" }}>Loading Case Details...</div>;

  return (
    <main className="container" style={{ maxWidth: "1400px", marginTop: "1rem" }}>
      <header className="flex-between" style={{ marginBottom: "2rem" }}>
        <div>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center", marginBottom: "8px" }}>
            <h1 style={{ fontSize: "2rem", color: "#0f172a" }}>Case {caseData.case_id}</h1>
            <span className={statusClass(caseData.state)}>
              {caseData.state}
            </span>
          </div>
          <p className="subtext">Reported via {caseData.channel} by {caseData.citizen.id} • {new Date(caseData.created_at).toLocaleString()}</p>
        </div>
      </header>

      <div className="grid-layout" style={{ gridTemplateColumns: "1fr 1fr", alignItems: "start" }}>
        
        {/* Left Column: Details & Photos */}
        <div className="flex-column" style={{ gap: "2rem" }}>
          <div className="glass-panel flex-column" style={{ gap: "1rem" }}>
            <h3 style={{ borderBottom: "1px solid #e2e8f0", paddingBottom: "0.5rem", color: "#0f172a" }}>Report Summary</h3>
            <div style={{ marginBottom: "0.5rem" }}>
              <span className="subtext">Subject</span>
              <h4 style={{ fontSize: "1.15rem", color: "#0f172a", marginTop: "2px" }}>{caseData.report.subject || "No subject provided"}</h4>
            </div>
            
            <div style={{ background: "#f0f9ff", padding: "14px 16px", borderRadius: "10px", borderLeft: "4px solid #0284c7", borderTop: "1px solid #bae6fd", borderRight: "1px solid #bae6fd", borderBottom: "1px solid #bae6fd" }}>
              <p style={{ fontSize: "0.95rem", color: "#0369a1", whiteSpace: "pre-wrap" }}>&ldquo;{caseData.report.text}&rdquo;</p>
            </div>
            
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", marginTop: "1rem" }}>
              <div>
                <span className="subtext" style={{ display: "flex", alignItems: "center", gap: "4px", marginBottom: "4px" }}><AlertCircle size={14} color="#0284c7" /> Classification</span>
                <p style={{ textTransform: "capitalize", fontWeight: "700", color: "#0f172a" }}>{caseData.grievance_type || "Issue"} / {caseData.category}</p>
              </div>
              <div>
                <span className="subtext" style={{ display: "flex", alignItems: "center", gap: "4px", marginBottom: "4px" }}><MapPin size={14} color="#0284c7" /> Location</span>
                <p style={{ fontWeight: "700", color: "#0f172a" }}>{caseData.location.ward} - {caseData.location.street || "Unknown Street"}</p>
                <p className="subtext" style={{ fontSize: "0.8rem" }}>{caseData.location.address_hint}</p>
              </div>
            </div>

            <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid #e2e8f0" }}>
               <span className="subtext" style={{ display: "block", marginBottom: "4px" }}>Citizen Details</span>
               <p style={{ color: "#0f172a" }}><strong>{caseData.citizen.name || "Anonymous"}</strong> • {caseData.citizen.mobile || "No Mobile"}</p>
            </div>

            {caseData.report.photos && caseData.report.photos.length > 0 && (
              <div style={{ marginTop: "1rem" }}>
                <span className="subtext" style={{ display: "flex", alignItems: "center", gap: "4px", marginBottom: "8px" }}><ImageIcon size={14} color="#0284c7" /> Attachments</span>
                <img src={caseData.report.photos[0]} alt="Report" style={{ width: "100%", height: "200px", objectFit: "cover", borderRadius: "10px", border: "1px solid #cbd5e1" }} />
              </div>
            )}
            
            {caseData.report.voice_note && (
              <div style={{ marginTop: "1rem", padding: "12px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: "8px", color: "#059669", fontWeight: "700", display: "flex", alignItems: "center", gap: "8px" }}>
                🎙️ Voice Note Attached
              </div>
            )}
          </div>

          <div className="glass-panel flex-column" style={{ gap: "1rem" }}>
             <h3 style={{ borderBottom: "1px solid #e2e8f0", paddingBottom: "0.5rem", color: "#0f172a" }}>Task Ownership</h3>
             {caseData.owners.length === 0 ? (
               <p className="subtext" style={{ fontStyle: "italic" }}>Ownership pending Socio Engine assignment.</p>
             ) : (
               caseData.owners.map((owner: any, idx: number) => (
                 <div key={idx} style={{ display: "flex", justifyContent: "space-between", background: "#f8fafc", padding: "12px 14px", borderRadius: "10px", border: "1px solid #e2e8f0" }}>
                   <div>
                     <p style={{ fontWeight: "700", textTransform: "capitalize", color: "#0284c7" }}>{owner.department}</p>
                     <p className="subtext">{owner.task}</p>
                   </div>
                   <span className="status-badge status-assigned" style={{ alignSelf: "center" }}>{owner.status}</span>
                 </div>
               ))
             )}
          </div>
        </div>

        {/* Right Column: Dispute Transcript Panel */}
        <div>
          <TranscriptPanel caseData={caseData} />
        </div>

      </div>
    </main>
  );
}
