"use client";

import { useState } from "react";
import { useRole } from "@/lib/useRole";
import { useCases } from "@/lib/useCases";
import {
  Plus, Mic, FileText, CheckCircle2, Clock, AlertTriangle,
  ChevronDown, ChevronUp, X, MapPin, Paperclip, Activity,
  Timer, BarChart2,
} from "lucide-react";

/* ─── helpers ──────────────────────────────────────────────── */
function statusColor(state: string) {
  switch (state) {
    case "ROUTED": case "NEW":       return { bg: "#e0f2fe", col: "#0369a1", border: "#bae6fd" };
    case "ASSIGNED":                  return { bg: "#dcfce7", col: "#15803d", border: "#bbf7d0" };
    case "DISPUTE":                   return { bg: "#fef3c7", col: "#b45309", border: "#fde68a" };
    case "ESCALATED":                 return { bg: "#fee2e2", col: "#b91c1c", border: "#fca5a5" };
    case "NEEDS_INFO":                return { bg: "#f3e8ff", col: "#6b21a8", border: "#e9d5ff" };
    case "VERIFIED":                  return { bg: "#dcfce7", col: "#15803d", border: "#bbf7d0" };
    default:                          return { bg: "#f1f5f9", col: "#475569", border: "#e2e8f0" };
  }
}

function etaLabel(sla: any) {
  const ms = new Date(sla.deadline).getTime() - Date.now();
  if (ms < 0) return "⚠ SLA Breached";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return `≈ ${h}h ${m}m remaining`;
}

/* ─── Complaint Modal ──────────────────────────────────────── */
function ComplaintModal({ onClose, onSubmit }: { onClose: () => void; onSubmit: (c: any) => void }) {
  const [step, setStep] = useState<"choose" | "voice" | "text">("choose");
  const [description, setDescription] = useState("");
  const [subject, setSubject] = useState("");
  const [category, setCategory] = useState("");
  const [ward, setWard] = useState("");
  const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null);
  const [isLocating, setIsLocating] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceNote, setVoiceNote] = useState(false);
  const [recTime, setRecTime] = useState(0);
  const [hasAttachment, setHasAttachment] = useState(false);

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "10px 14px", borderRadius: "10px",
    border: "1px solid #cbd5e1", background: "#f8fafc",
    color: "#0f172a", fontSize: "0.92rem", fontFamily: "inherit",
    boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
  };
  const labelStyle: React.CSSProperties = {
    display: "block", fontSize: "0.82rem", fontWeight: 600,
    color: "#475569", marginBottom: "6px", letterSpacing: "0.02em",
  };

  const handleVoiceRecord = () => {
    if (isRecording) return;
    setIsRecording(true); setVoiceNote(false); setDescription("");
    let t = 0;
    const interval = setInterval(() => {
      t += 1; setRecTime(t);
      if (t >= 4) {
        clearInterval(interval);
        setIsRecording(false); setVoiceNote(true); setRecTime(0);
        setDescription("Voice complaint recorded — streetlight is broken near the park.");
      }
    }, 1000);
  };

  const handleGps = () => {
    setIsLocating(true);
    navigator.geolocation?.getCurrentPosition(
      (pos) => { setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude }); setIsLocating(false); },
      () => { setGps({ lat: 13.082, lng: 80.27 }); setIsLocating(false); }
    );
  };

  const handleSubmit = () => {
    if (!ward || !description) return alert("Please fill Ward and description.");
    const newCase = {
      case_id: `SCO-${new Date().getFullYear()}-${Math.floor(Math.random() * 10000).toString().padStart(4, "0")}`,
      created_at: new Date().toISOString(),
      channel: step === "voice" ? "voice" : "web",
      citizen: { id: `citizen-${Math.floor(Math.random() * 1000)}`, language: "en", name: "You", mobile: "N/A" },
      report: {
        subject: step === "voice" ? "Voice Complaint" : subject || "Complaint",
        text: description,
        photos: hasAttachment ? ["https://images.unsplash.com/photo-1515162816999-a0c47dc192f7?w=400"] : [],
        voice_note: voiceNote ? "true" : null,
      },
      category: category || "general",
      grievance_type: "civic",
      severity: "medium",
      location: { lat: gps?.lat ?? 13.0, lng: gps?.lng ?? 80.0, ward, street: "N/A", address_hint: "N/A" },
      state: "NEW",
      sla: { deadline: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(), breached: false },
      owners: [], hop_count: 0, rejected_by: [], duplicate_of: null, messages: [],
    };
    onSubmit(newCase);
  };

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 1000,
        background: "rgba(15, 23, 42, 0.4)", backdropFilter: "blur(6px)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        style={{
          background: "#ffffff", border: "1px solid #e2e8f0",
          borderRadius: "20px", padding: "2rem", width: "100%", maxWidth: "520px",
          boxShadow: "0 20px 40px -10px rgba(15,23,42,0.15)", position: "relative",
          animation: "fadeIn 0.25s ease",
        }}
      >
        <button onClick={onClose} style={{ position: "absolute", top: "18px", right: "18px", background: "none", border: "none", cursor: "pointer", color: "#64748b" }}>
          <X size={20} />
        </button>

        {step === "choose" && (
          <>
            <h2 style={{ fontSize: "1.4rem", marginBottom: "0.4rem", color: "#0f172a" }}>Raise a Complaint</h2>
            <p style={{ color: "#64748b", marginBottom: "1.75rem", fontSize: "0.9rem" }}>
              Choose your preferred method to submit your issue to Socio Engine.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
              {[
                {
                  id: "voice", icon: <Mic size={26} />, title: "Voice Complaint",
                  desc: "Record your complaint in spoken words — English or Tamil",
                  gradient: "linear-gradient(135deg,#0284c7,#2563eb)", bg: "#f0f9ff", border: "#bae6fd",
                },
                {
                  id: "text", icon: <FileText size={26} />, title: "Text Complaint",
                  desc: "Fill in category, description & location details manually",
                  gradient: "linear-gradient(135deg,#6d28d9,#4f46e5)", bg: "#f5f3ff", border: "#ddd6fe",
                },
              ].map((opt) => (
                <button
                  key={opt.id}
                  onClick={() => setStep(opt.id as any)}
                  style={{
                    all: "unset", cursor: "pointer", display: "flex", flexDirection: "column",
                    gap: "0.75rem", padding: "1.5rem", borderRadius: "14px",
                    border: `1px solid ${opt.border}`, background: opt.bg,
                    transition: "all 0.2s ease", boxSizing: "border-box",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
                    (e.currentTarget as HTMLElement).style.boxShadow = "0 8px 20px rgba(0,0,0,0.06)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
                    (e.currentTarget as HTMLElement).style.boxShadow = "none";
                  }}
                >
                  <div style={{ width: "48px", height: "48px", borderRadius: "12px", background: opt.gradient, display: "flex", alignItems: "center", justifyContent: "center", color: "#fff" }}>
                    {opt.icon}
                  </div>
                  <div>
                    <p style={{ fontWeight: 700, marginBottom: "4px", color: "#0f172a" }}>{opt.title}</p>
                    <p style={{ fontSize: "0.78rem", color: "#64748b", lineHeight: 1.5 }}>{opt.desc}</p>
                  </div>
                </button>
              ))}
            </div>
          </>
        )}

        {step === "voice" && (
          <>
            <button onClick={() => setStep("choose")} style={{ background: "none", border: "none", cursor: "pointer", color: "#0284c7", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "4px", fontSize: "0.85rem", fontWeight: 600 }}>← Back</button>
            <h2 style={{ fontSize: "1.3rem", marginBottom: "0.4rem", color: "#0f172a" }}>Voice Complaint</h2>
            <p style={{ color: "#64748b", fontSize: "0.85rem", marginBottom: "1.75rem" }}>Tap the microphone button to start recording.</p>

            <div style={{ display: "flex", justifyContent: "center", marginBottom: "1.25rem" }}>
              <button
                onClick={handleVoiceRecord}
                style={{
                  width: "84px", height: "84px", borderRadius: "50%",
                  background: isRecording ? "#dc2626" : "linear-gradient(135deg,#0284c7,#2563eb)",
                  border: "none", cursor: "pointer", color: "#fff",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  boxShadow: isRecording ? "0 0 0 10px rgba(220,38,38,0.2)" : "0 8px 24px rgba(2,132,199,0.3)",
                  transition: "all 0.3s ease",
                  animation: isRecording ? "pulse 1.5s infinite" : "none",
                }}
              >
                {isRecording ? <div style={{ width: "24px", height: "24px", background: "#fff", borderRadius: "4px" }} /> : <Mic size={34} />}
              </button>
            </div>
            <p style={{ textAlign: "center", color: "#475569", fontSize: "0.88rem", fontWeight: 600, marginBottom: "1.5rem" }}>
              {isRecording ? `Recording... 0:0${recTime}` : voiceNote ? "✓ Voice recorded successfully" : "Tap to speak your issue"}
            </p>

            {description && (
              <div style={{ marginBottom: "1rem" }}>
                <label style={labelStyle}>Recognized Transcript</label>
                <textarea
                  style={{ ...inputStyle, minHeight: "80px", resize: "vertical" }}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.25rem" }}>
              <div>
                <label style={labelStyle}>Ward *</label>
                <select style={inputStyle} value={ward} onChange={(e) => setWard(e.target.value)}>
                  <option value="" disabled>Select ward</option>
                  <option value="Ward 34">Ward 34</option>
                  <option value="Ward 35">Ward 35</option>
                  <option value="Ward 36">Ward 36</option>
                </select>
              </div>
              <div>
                <label style={labelStyle}>GPS Location</label>
                <button type="button" onClick={handleGps} style={{ width: "100%", ...inputStyle, display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", justifyContent: "center" }}>
                  <MapPin size={14} color="#0284c7" />
                  {isLocating ? "Locating..." : gps ? "GPS Set ✓" : "Use Location"}
                </button>
              </div>
            </div>

            <button onClick={handleSubmit} className="glass-button" style={{ width: "100%" }}>
              Submit Voice Complaint
            </button>
          </>
        )}

        {step === "text" && (
          <>
            <button onClick={() => setStep("choose")} style={{ background: "none", border: "none", cursor: "pointer", color: "#0284c7", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "4px", fontSize: "0.85rem", fontWeight: 600 }}>← Back</button>
            <h2 style={{ fontSize: "1.3rem", marginBottom: "0.4rem", color: "#0f172a" }}>Text Complaint</h2>
            <p style={{ color: "#64748b", fontSize: "0.85rem", marginBottom: "1.5rem" }}>Provide complaint details below.</p>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                <div>
                  <label style={labelStyle}>Category *</label>
                  <select style={inputStyle} value={category} onChange={(e) => setCategory(e.target.value)}>
                    <option value="" disabled>Select category</option>
                    <option value="waterlogging">Waterlogging / Leak</option>
                    <option value="streetlight">Streetlight Out</option>
                    <option value="pothole">Potholes</option>
                    <option value="garbage">Garbage Pile</option>
                    <option value="general">Other</option>
                  </select>
                </div>
                <div>
                  <label style={labelStyle}>Ward *</label>
                  <select style={inputStyle} value={ward} onChange={(e) => setWard(e.target.value)}>
                    <option value="" disabled>Select ward</option>
                    <option value="Ward 34">Ward 34</option>
                    <option value="Ward 35">Ward 35</option>
                    <option value="Ward 36">Ward 36</option>
                  </select>
                </div>
              </div>

              <div>
                <label style={labelStyle}>Subject *</label>
                <input type="text" style={inputStyle} placeholder="Brief subject line" value={subject} onChange={(e) => setSubject(e.target.value)} />
              </div>

              <div>
                <label style={labelStyle}>Description *</label>
                <textarea style={{ ...inputStyle, minHeight: "90px", resize: "vertical" }} placeholder="Describe the issue in detail..." value={description} onChange={(e) => setDescription(e.target.value)} />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                <div>
                  <label style={labelStyle}>GPS Location</label>
                  <button type="button" onClick={handleGps} style={{ width: "100%", ...inputStyle, display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", justifyContent: "center" }}>
                    <MapPin size={14} color="#0284c7" />
                    {isLocating ? "Locating..." : gps ? "GPS Set ✓" : "Use Location"}
                  </button>
                </div>
                <div>
                  <label style={labelStyle}>Attachment</label>
                  <button type="button" onClick={() => setHasAttachment(true)} style={{ width: "100%", ...inputStyle, display: "flex", alignItems: "center", gap: "6px", cursor: "pointer", justifyContent: "center", borderColor: hasAttachment ? "#059669" : undefined, color: hasAttachment ? "#059669" : undefined }}>
                    <Paperclip size={14} />
                    {hasAttachment ? "Photo Attached ✓" : "Add Photo"}
                  </button>
                </div>
              </div>

              <button onClick={handleSubmit} className="glass-button" style={{ width: "100%", marginTop: "0.5rem" }}>
                Submit Complaint
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/* ─── Complaint Card ──────────────────────────────────────── */
function ComplaintCard({ c }: { c: any }) {
  const [expanded, setExpanded] = useState(false);
  const { bg, col, border } = statusColor(c.state);

  return (
    <div
      style={{
        background: "#ffffff", border: "1px solid #e2e8f0",
        borderRadius: "14px", overflow: "hidden", transition: "all 0.2s ease",
        boxShadow: "0 2px 6px rgba(15,23,42,0.03)",
      }}
    >
      <div
        style={{
          padding: "1.1rem 1.35rem", display: "flex", gap: "1rem", alignItems: "center",
          cursor: "pointer",
        }}
        onClick={() => setExpanded((p) => !p)}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", marginBottom: "4px" }}>
            <span style={{ fontWeight: 700, fontSize: "0.92rem", color: "#0f172a" }}>{c.case_id}</span>
            <span style={{ fontSize: "0.72rem", textTransform: "uppercase", padding: "3px 10px", borderRadius: "20px", background: bg, color: col, border: `1px solid ${border}`, fontWeight: 600 }}>{c.state}</span>
          </div>
          <p style={{ fontSize: "0.88rem", color: "#475569", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
            {c.report.text}
          </p>
        </div>
        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <p style={{ fontSize: "0.78rem", color: "#64748b" }}>{new Date(c.created_at).toLocaleDateString()}</p>
          <p style={{ fontSize: "0.75rem", color: c.sla?.breached ? "#dc2626" : "#059669", marginTop: "2px", fontWeight: 600 }}>
            {c.sla ? etaLabel(c.sla) : ""}
          </p>
        </div>
        {expanded ? <ChevronUp size={18} color="#64748b" /> : <ChevronDown size={18} color="#64748b" />}
      </div>

      {expanded && (
        <div style={{ borderTop: "1px solid #f1f5f9", padding: "1.25rem 1.35rem", display: "flex", flexDirection: "column", gap: "1rem", background: "#f8fafc" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(130px,1fr))", gap: "0.75rem" }}>
            {[
              { label: "Category", value: c.category || "—" },
              { label: "Ward", value: c.location?.ward || "—" },
              { label: "Channel", value: c.channel || "—" },
              { label: "Routing Hops", value: c.hop_count ?? 0 },
            ].map((item) => (
              <div key={item.label} style={{ background: "#ffffff", borderRadius: "10px", padding: "10px 14px", border: "1px solid #e2e8f0" }}>
                <p style={{ fontSize: "0.72rem", color: "#64748b", marginBottom: "2px", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600 }}>{item.label}</p>
                <p style={{ fontWeight: 700, fontSize: "0.9rem", color: "#0f172a", textTransform: "capitalize" }}>{item.value}</p>
              </div>
            ))}
          </div>

          {/* Timeline */}
          <div style={{ paddingLeft: "4px" }}>
            <p style={{ fontSize: "0.75rem", color: "#64748b", marginBottom: "10px", fontWeight: 700, letterSpacing: "0.05em" }}>PROGRESS TIMELINE</p>
            {[
              { label: "Submitted", done: true, time: c.created_at },
              { label: "Routed by Socio Engine", done: ["ROUTED","DISPUTE","ASSIGNED","ESCALATED","NEEDS_INFO","VERIFIED"].includes(c.state), time: null },
              { label: "Department Assigned", done: c.state === "ASSIGNED" || c.state === "VERIFIED", time: null },
              { label: "Resolved / Verified", done: c.state === "VERIFIED", time: null },
            ].map((step, i) => (
              <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: "10px", marginBottom: "8px" }}>
                <div style={{ width: "16px", height: "16px", borderRadius: "50%", background: step.done ? "#dcfce7" : "#f1f5f9", border: `2px solid ${step.done ? "#059669" : "#cbd5e1"}`, color: "#059669", flexShrink: 0, marginTop: "2px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "10px" }}>
                  {step.done && "✓"}
                </div>
                <div>
                  <p style={{ fontSize: "0.85rem", fontWeight: step.done ? 600 : 400, color: step.done ? "#0f172a" : "#64748b" }}>{step.label}</p>
                  {step.time && <p style={{ fontSize: "0.72rem", color: "#64748b" }}>{new Date(step.time).toLocaleString()}</p>}
                </div>
              </div>
            ))}
          </div>

          {c.owners?.length > 0 && (
            <div>
              <p style={{ fontSize: "0.75rem", color: "#64748b", marginBottom: "6px", fontWeight: 700, letterSpacing: "0.05em" }}>ASSIGNED TO</p>
              {c.owners.map((o: any, i: number) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", background: "#e0f2fe", border: "1px solid #bae6fd", borderRadius: "8px", padding: "8px 12px" }}>
                  <span style={{ textTransform: "capitalize", color: "#0369a1", fontWeight: 700, fontSize: "0.85rem" }}>{o.department}</span>
                  <span style={{ color: "#0369a1", fontSize: "0.82rem" }}>{o.task}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─── Main Page ──────────────────────────────────────────── */
export default function CitizenDashboard() {
  const { role, ready } = useRole("citizen");
  const { cases, addCase, isLoaded } = useCases();
  const [showModal, setShowModal] = useState(false);
  const [successId, setSuccessId] = useState<string | null>(null);

  if (!ready || !isLoaded) return null;
  if (!role) return null;

  const handleSubmit = (newCase: any) => {
    addCase(newCase);
    setShowModal(false);
    setSuccessId(newCase.case_id);
    setTimeout(() => setSuccessId(null), 4000);
  };

  const stats = [
    { label: "Total Reported", value: cases.length, icon: <BarChart2 size={18} />, color: "#0284c7", bg: "#f0f9ff", border: "#bae6fd" },
    { label: "In Progress", value: cases.filter((c) => ["NEW","ROUTED","DISPUTE","NEEDS_INFO"].includes(c.state)).length, icon: <Activity size={18} />, color: "#6d28d9", bg: "#f5f3ff", border: "#ddd6fe" },
    { label: "Resolved", value: cases.filter((c) => c.state === "VERIFIED" || c.state === "ASSIGNED").length, icon: <CheckCircle2 size={18} />, color: "#059669", bg: "#f0fdf4", border: "#bbf7d0" },
    { label: "SLA Breached", value: cases.filter((c) => c.sla?.breached).length, icon: <AlertTriangle size={18} />, color: "#dc2626", bg: "#fef2f2", border: "#fca5a5" },
  ];

  return (
    <>
      {showModal && <ComplaintModal onClose={() => setShowModal(false)} onSubmit={handleSubmit} />}

      <main style={{ maxWidth: "900px", margin: "0 auto", padding: "2.5rem 1.5rem" }}>

        {/* Success toast */}
        {successId && (
          <div style={{
            position: "fixed", top: "80px", right: "24px", zIndex: 999,
            background: "#dcfce7", border: "1px solid #86efac",
            borderRadius: "12px", padding: "12px 20px", display: "flex", gap: "10px",
            alignItems: "center", boxShadow: "0 10px 25px rgba(0,0,0,0.1)", color: "#15803d", fontWeight: 600,
            animation: "fadeIn 0.3s ease",
          }}>
            <CheckCircle2 size={18} /> Complaint <strong>{successId}</strong> submitted successfully!
          </div>
        )}

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h1 style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: "6px", color: "#0f172a" }}>My Complaints</h1>
            <p style={{ color: "#64748b", fontSize: "0.95rem" }}>Track all your reported civic issues in real-time.</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="glass-button"
            style={{ gap: "8px" }}
          >
            <Plus size={18} /> Raise New Complaint
          </button>
        </div>

        {/* Stats */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
          {stats.map((s) => (
            <div key={s.label} style={{ background: s.bg, border: `1px solid ${s.border}`, borderRadius: "14px", padding: "1.1rem", textAlign: "center" }}>
              <div style={{ display: "flex", justifyContent: "center", marginBottom: "6px", color: s.color }}>{s.icon}</div>
              <div style={{ fontSize: "1.8rem", fontWeight: 800, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: "0.75rem", color: "#475569", marginTop: "2px", fontWeight: 600 }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* List */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          {cases.length === 0 ? (
            <div style={{ textAlign: "center", padding: "4rem 2rem", background: "#ffffff", borderRadius: "16px", border: "1px solid #e2e8f0", color: "#64748b" }}>
              <div style={{ fontSize: "3rem", marginBottom: "1rem" }}>📋</div>
              <p style={{ fontSize: "1.05rem", fontWeight: 700, color: "#0f172a", marginBottom: "0.5rem" }}>No complaints reported yet</p>
              <p style={{ fontSize: "0.88rem" }}>Click <strong>Raise New Complaint</strong> to file your first issue.</p>
            </div>
          ) : (
            cases.map((c: any) => <ComplaintCard key={c.case_id} c={c} />)
          )}
        </div>
      </main>
    </>
  );
}
