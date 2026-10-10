"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useRole, type Role } from "@/lib/useRole";
import { User, Briefcase, HardHat, ArrowRight, Shield, Zap, Globe } from "lucide-react";

const ROLES: {
  id: Role;
  label: string;
  subtitle: string;
  description: string;
  icon: React.ReactNode;
  gradient: string;
  glowColor: string;
  glowBorder: string;
  features: string[];
}[] = [
  {
    id: "citizen",
    label: "Citizen",
    subtitle: "Report & Track",
    description:
      "Submit civic complaints via voice or text, track resolution status in real-time, and receive updates on your reported issues.",
    icon: <User size={28} />,
    gradient: "linear-gradient(135deg, #0284c7, #2563eb)",
    glowColor: "rgba(2, 132, 199, 0.12)",
    glowBorder: "#7dd3fc",
    features: ["Submit complaints (voice or text)", "Track complaint status", "View resolution timeline"],
  },
  {
    id: "officer",
    label: "Officer",
    subtitle: "Monitor & Manage",
    description:
      "Access the full Socio Engine monitoring dashboard — track all cases, route complaints, and manage departments.",
    icon: <Briefcase size={28} />,
    gradient: "linear-gradient(135deg, #6d28d9, #4f46e5)",
    glowColor: "rgba(109, 40, 217, 0.12)",
    glowBorder: "#c4b5fd",
    features: ["Full case monitoring", "Analytics & hotspot view", "Agent routing transcripts"],
  },
  {
    id: "field",
    label: "Field Crew",
    subtitle: "Execute & Resolve",
    description:
      "View your assigned tasks, capture proof of completion with GPS, and update case status directly in the field.",
    icon: <HardHat size={28} />,
    gradient: "linear-gradient(135deg, #059669, #0d9488)",
    glowColor: "rgba(5, 150, 105, 0.12)",
    glowBorder: "#6ee7b7",
    features: ["Assigned task queue", "Photo + GPS capture", "Real-time status updates"],
  },
];

export default function LoginPage() {
  const { setRole, role } = useRole();
  const router = useRouter();

  useEffect(() => {
    if (role) router.replace(`/${role}`);
  }, [role]);

  const handleSelect = (r: NonNullable<Role>) => {
    setRole(r);
    router.push(`/${r}`);
  };

  return (
    <main
      style={{
        minHeight: "calc(100vh - 65px)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "3rem 1.5rem",
        background: "var(--bg-color)",
      }}
    >
      {/* Hero Header */}
      <div style={{ textAlign: "center", marginBottom: "3.5rem" }}>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "6px 16px",
            borderRadius: "20px",
            background: "#e0f2fe",
            border: "1px solid #bae6fd",
            marginBottom: "1.25rem",
          }}
        >
          <Zap size={14} color="#0284c7" />
          <span
            style={{
              fontSize: "0.78rem",
              color: "#0369a1",
              fontWeight: 700,
              letterSpacing: "0.08em",
            }}
          >
            MULTI-AGENT CIVIC PLATFORM
          </span>
        </div>
        <h1
          style={{
            fontSize: "clamp(2.2rem, 5vw, 3.6rem)",
            fontWeight: 800,
            letterSpacing: "-0.03em",
            lineHeight: 1.1,
            marginBottom: "1rem",
            color: "#0f172a",
          }}
        >
          Welcome to <span className="text-gradient">Socio</span>
        </h1>
        <p
          style={{
            color: "#475569",
            fontSize: "1.1rem",
            maxWidth: "500px",
            margin: "0 auto",
            lineHeight: 1.6,
          }}
        >
          Select your portal role to enter your personalized dashboard. Instant access, no sign-up required.
        </p>
      </div>

      {/* Role Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))",
          gap: "1.75rem",
          width: "100%",
          maxWidth: "1020px",
        }}
      >
        {ROLES.map((roleItem) => (
          <button
            key={roleItem.id}
            onClick={() => handleSelect(roleItem.id as NonNullable<Role>)}
            style={{
              all: "unset",
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
              background: "#ffffff",
              border: "1px solid #e2e8f0",
              borderRadius: "20px",
              padding: "2rem",
              gap: "1.25rem",
              transition: "transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease",
              boxSizing: "border-box",
              textAlign: "left",
              boxShadow: "0 4px 20px -2px rgba(15, 23, 42, 0.05)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.transform = "translateY(-6px)";
              (e.currentTarget as HTMLElement).style.boxShadow = `0 20px 40px -10px ${roleItem.glowColor}, 0 10px 20px -5px rgba(0,0,0,0.04)`;
              (e.currentTarget as HTMLElement).style.borderColor = roleItem.glowBorder;
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
              (e.currentTarget as HTMLElement).style.boxShadow = "0 4px 20px -2px rgba(15, 23, 42, 0.05)";
              (e.currentTarget as HTMLElement).style.borderColor = "#e2e8f0";
            }}
          >
            {/* Icon */}
            <div
              style={{
                width: "60px",
                height: "60px",
                borderRadius: "16px",
                background: roleItem.gradient,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#fff",
                boxShadow: `0 8px 20px -4px ${roleItem.glowColor}`,
                flexShrink: 0,
              }}
            >
              {roleItem.icon}
            </div>

            {/* Text */}
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "6px" }}>
                <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "#0f172a" }}>{roleItem.label}</h2>
                <span
                  style={{
                    fontSize: "0.75rem",
                    padding: "3px 10px",
                    borderRadius: "20px",
                    background: "#f1f5f9",
                    color: "#475569",
                    fontWeight: 600,
                  }}
                >
                  {roleItem.subtitle}
                </span>
              </div>
              <p
                style={{
                  color: "#64748b",
                  fontSize: "0.88rem",
                  lineHeight: 1.55,
                }}
              >
                {roleItem.description}
              </p>
            </div>

            {/* Features */}
            <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: "8px" }}>
              {roleItem.features.map((f, i) => (
                <li
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    fontSize: "0.84rem",
                    color: "#475569",
                  }}
                >
                  <div
                    style={{
                      width: "6px",
                      height: "6px",
                      borderRadius: "50%",
                      background: roleItem.gradient,
                      flexShrink: 0,
                    }}
                  />
                  {f}
                </li>
              ))}
            </ul>

            {/* CTA */}
            <div
              style={{
                marginTop: "auto",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                background: roleItem.gradient,
                borderRadius: "10px",
                padding: "11px 16px",
                color: "#fff",
                fontWeight: 600,
                fontSize: "0.9rem",
                justifyContent: "center",
                boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
              }}
            >
              Enter as {roleItem.label} <ArrowRight size={16} />
            </div>
          </button>
        ))}
      </div>

      {/* Footer */}
      <div
        style={{
          marginTop: "3.5rem",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          color: "#64748b",
          fontSize: "0.82rem",
          background: "#ffffff",
          padding: "8px 20px",
          borderRadius: "30px",
          border: "1px solid #e2e8f0",
          boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
        }}
      >
        <Shield size={15} color="#0284c7" />
        <span>No sign-up required — instant interactive access</span>
        <span style={{ margin: "0 4px", color: "#cbd5e1" }}>•</span>
        <Globe size={15} color="#6d28d9" />
        <span>Civic Engine real-time routing</span>
      </div>
    </main>
  );
}
