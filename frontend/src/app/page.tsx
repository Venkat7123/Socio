"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    const role = localStorage.getItem("socio_role");
    if (role) router.replace(`/${role}`);
    else router.replace("/login");
  }, []);
  return null;
}
