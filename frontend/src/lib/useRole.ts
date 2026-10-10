"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export type Role = "citizen" | "officer" | "field" | null;

export function useRole(required?: Role | Role[]) {
  const [role, setRoleState] = useState<Role>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const stored = (localStorage.getItem("socio_role") as Role) || null;
    setRoleState(stored);
    setReady(true);

    if (required && !stored) {
      router.replace("/login");
    } else if (required && stored) {
      const allowed = Array.isArray(required) ? required : [required];
      if (!allowed.includes(stored)) {
        router.replace(`/${stored}`);
      }
    }
  }, []);

  const setRole = (r: Role) => {
    if (r) localStorage.setItem("socio_role", r);
    else localStorage.removeItem("socio_role");
    setRoleState(r);
  };

  const logout = () => {
    localStorage.removeItem("socio_role");
    setRoleState(null);
    router.replace("/login");
  };

  return { role, setRole, logout, ready };
}
