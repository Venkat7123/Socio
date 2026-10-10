"use client";

import { useState } from "react";
import { useRole } from "@/lib/useRole";
import { useCases } from "@/lib/useCases";
import { MapPin, Camera, Upload, CheckCircle2, Activity, HardHat } from "lucide-react";

export default function FieldCrewView() {
  const { role, ready } = useRole("field");
  const { cases, updateCase, isLoaded } = useCases();
  const [activeTask, setActiveTask] = useState<string | null>(null);
  const [photoUploaded, setPhotoUploaded] = useState(false);

  if (!ready || !isLoaded || !role) return null;

  // Show tasks in ASSIGNED, ROUTED or legacy NEW state
  const myTasks = cases.filter(
    (c: any) => c.state === "ASSIGNED" || c.state === "ROUTED" || c.state === "NEW"
  );

  const handleResolve = (caseId: string) => {
    updateCase(caseId, { state: "VERIFIED" });
    setActiveTask(null);
    setPhotoUploaded(false);
  };

  return (
    <main
      className="container flex-column"
      style={{ maxWidth: "680px", marginTop: "1rem", gap: "1.75rem" }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <h1 style={{ fontSize: "1.8rem", fontWeight: 800, letterSpacing: "-0.025em", color: "#0f172a" }}>
            Field Crew Portal
          </h1>
          <p className="subtext">Assigned to: Corporation Operations (Ward W-34, 35, 36)</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", background: "#f0fdf4", border: "1px solid #bbf7d0", padding: "6px 14px", borderRadius: "20px", color: "#15803d", fontWeight: 700, fontSize: "0.82rem" }}>
          <HardHat size={15} /> Active Shift
        </div>
      </header>

      {/* Summary */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "1rem",
        }}
      >
        {[
          { label: "Pending Tasks", value: myTasks.length, color: "#0284c7", bg: "#f0f9ff", border: "#bae6fd" },
          {
            label: "Completed Today",
            value: cases.filter((c: any) => c.state === "VERIFIED").length,
            color: "#059669",
            bg: "#f0fdf4",
            border: "#bbf7d0",
          },
          {
            label: "Total Queue",
            value: cases.filter((c: any) =>
              ["ASSIGNED", "ROUTED", "NEW"].includes(c.state)
            ).length,
            color: "#6d28d9",
            bg: "#f5f3ff",
            border: "#ddd6fe",
          },
        ].map((s) => (
          <div
            key={s.label}
            style={{
              background: s.bg,
              border: `1px solid ${s.border}`,
              borderRadius: "14px",
              padding: "1rem",
              textAlign: "center",
            }}
          >
            <Activity size={16} color={s.color} style={{ marginBottom: "6px" }} />
            <div
              style={{
                fontSize: "1.7rem",
                fontWeight: 800,
                color: s.color,
                lineHeight: 1,
              }}
            >
              {s.value}
            </div>
            <div
              style={{
                fontSize: "0.75rem",
                color: "#475569",
                marginTop: "4px",
                fontWeight: 600,
              }}
            >
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {myTasks.length === 0 && (
        <div
          style={{
            textAlign: "center",
            padding: "3.5rem 2rem",
            background: "#f0fdf4",
            border: "1px solid #bbf7d0",
            borderRadius: "16px",
          }}
        >
          <CheckCircle2 size={44} color="#059669" style={{ marginBottom: "1rem" }} />
          <p style={{ fontWeight: 800, color: "#059669", fontSize: "1.1rem" }}>All tasks completed!</p>
          <p className="subtext" style={{ fontSize: "0.88rem", marginTop: "4px" }}>
            No pending field cases assigned to your queue at this moment.
          </p>
        </div>
      )}

      {myTasks.map((task: any) => (
        <div
          key={task.case_id}
          className="glass-panel flex-column"
          style={{ gap: "1.1rem", padding: "1.5rem" }}
        >
          <div className="flex-between">
            <span style={{ fontWeight: 800, fontSize: "1rem", color: "#0f172a" }}>
              {task.case_id}
            </span>
            <span className="status-badge status-assigned">Assigned</span>
          </div>

          <div>
            <span
              style={{
                fontSize: "0.75rem",
                textTransform: "uppercase",
                color: "#0284c7",
                fontWeight: 700,
                letterSpacing: "0.05em",
              }}
            >
              {task.grievance_type || "Issue"} • {task.category}
            </span>
            <h3
              style={{
                fontSize: "1.15rem",
                marginBottom: "6px",
                marginTop: "4px",
                color: "#0f172a",
              }}
            >
              {task.report.subject || "No Subject"}
            </h3>
            <p
              className="subtext"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                fontSize: "0.88rem",
                color: "#475569",
              }}
            >
              <MapPin size={15} color="#0284c7" /> {task.location.street || "Unknown Street"} (
              {task.location.ward})
            </p>
            {task.location.address_hint && (
              <p
                className="subtext"
                style={{ fontSize: "0.8rem", marginTop: "4px", color: "#64748b" }}
              >
                Hint: {task.location.address_hint}
              </p>
            )}
          </div>

          <div
            style={{
              background: "#f0f9ff",
              padding: "12px 16px",
              borderRadius: "10px",
              borderLeft: "4px solid #0284c7",
              borderTop: "1px solid #bae6fd",
              borderRight: "1px solid #bae6fd",
              borderBottom: "1px solid #bae6fd",
            }}
          >
            <p style={{ fontSize: "0.92rem", color: "#0369a1", lineHeight: 1.5 }}>&ldquo;{task.report.text}&rdquo;</p>
          </div>
          {task.report.voice_note && (
            <div
              style={{
                fontSize: "0.85rem",
                color: "#059669",
                fontWeight: 700,
                background: "#f0fdf4",
                padding: "6px 12px",
                borderRadius: "8px",
                border: "1px solid #bbf7d0",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                width: "fit-content",
              }}
            >
              🎙️ Voice note attached by citizen
            </div>
          )}

          <hr style={{ border: "0", borderTop: "1px solid #e2e8f0" }} />

          {activeTask !== task.case_id ? (
            <button
              className="glass-button"
              onClick={() => setActiveTask(task.case_id)}
            >
              Start Resolution Work
            </button>
          ) : (
            <div className="flex-column" style={{ gap: "1rem" }}>
              <div
                style={{
                  background: "#f8fafc",
                  padding: "1.5rem",
                  borderRadius: "14px",
                  border: "2px dashed #0284c7",
                  textAlign: "center",
                }}
              >
                {!photoUploaded ? (
                  <>
                    <Camera
                      size={38}
                      color="#0284c7"
                      style={{ marginBottom: "8px" }}
                    />
                    <p style={{ fontWeight: 700, fontSize: "0.95rem", color: "#0f172a" }}>
                      Capture Proof of Completion
                    </p>
                    <p
                      className="subtext"
                      style={{ fontSize: "0.82rem", marginBottom: "1.25rem" }}
                    >
                      GPS location &amp; timestamp will be embedded automatically.
                    </p>
                    <button
                      className="glass-button secondary"
                      onClick={() => setPhotoUploaded(true)}
                      style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}
                    >
                      <Upload size={16} /> Simulate Camera Upload
                    </button>
                  </>
                ) : (
                  <>
                    <CheckCircle2
                      size={38}
                      color="#059669"
                      style={{ marginBottom: "8px" }}
                    />
                    <p
                      style={{
                        fontWeight: 800,
                        fontSize: "0.95rem",
                        color: "#059669",
                      }}
                    >
                      Proof Uploaded &amp; GPS Stamped ✓
                    </p>
                    <p
                      className="subtext"
                      style={{ fontSize: "0.82rem", marginTop: "4px" }}
                    >
                      Ready to transmit verification to Socio Engine.
                    </p>
                  </>
                )}
              </div>

              {photoUploaded && (
                <button
                  className="glass-button"
                  onClick={() => handleResolve(task.case_id)}
                  style={{
                    background:
                      "linear-gradient(135deg, #059669, #047857)",
                  }}
                >
                  Submit &amp; Resolve Task
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </main>
  );
}
