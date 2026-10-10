"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, User } from "lucide-react";
import { type Role } from "@/lib/useRole";

const NAV_LINKS: Record<NonNullable<Role>, { href: string; label: string }[]> =
  {
    citizen: [{ href: "/citizen", label: "My Complaints" }],
    officer: [
      { href: "/officer", label: "Monitoring" },
      { href: "/officer/cases", label: "All Cases" },
      { href: "/officer/analytics", label: "Analytics" },
    ],
    field: [
      { href: "/field", label: "My Tasks" },
      { href: "/officer", label: "Monitor" },
    ],
  };

const ROLE_LABELS: Record<NonNullable<Role>, string> = {
  citizen: "Citizen",
  officer: "Officer",
  field: "Field Crew",
};

export default function NavBar() {
  const [role, setRole] = useState<Role>(null);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    setRole((localStorage.getItem("socio_role") as Role) || null);
  }, [pathname]);

  const logout = () => {
    localStorage.removeItem("socio_role");
    router.replace("/login");
  };

  const isLoginPage = pathname === "/login" || pathname === "/";

  return (
    <nav className="nav-bar">
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div
          style={{
            width: "32px",
            height: "32px",
            borderRadius: "8px",
            background:
              "linear-gradient(135deg, var(--accent-cyan), var(--accent-purple))",
            flexShrink: 0,
          }}
        />
        <h2 className="text-gradient">Socio</h2>
      </div>

      {!isLoginPage && role && (
        <div className="nav-links">
          {NAV_LINKS[role]?.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={pathname.startsWith(link.href) ? "active" : ""}
            >
              {link.label}
            </Link>
          ))}
        </div>
      )}

      {!isLoginPage && role && (
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 14px",
              borderRadius: "20px",
              background: "#e0f2fe",
              border: "1px solid #bae6fd",
              fontSize: "0.82rem",
              color: "#0369a1",
              fontWeight: 600,
            }}
          >
            <User size={13} />
            {ROLE_LABELS[role]}
          </div>
          <button
            onClick={logout}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              background: "#ffffff",
              border: "1px solid #cbd5e1",
              borderRadius: "8px",
              color: "#475569",
              padding: "6px 14px",
              cursor: "pointer",
              fontSize: "0.82rem",
              fontWeight: 500,
              transition: "all 0.2s",
              boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.background = "#f1f5f9";
              (e.currentTarget as HTMLElement).style.color = "#0f172a";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.background = "#ffffff";
              (e.currentTarget as HTMLElement).style.color = "#475569";
            }}
          >
            <LogOut size={13} /> Logout
          </button>
        </div>
      )}
    </nav>
  );
}
