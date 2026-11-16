"use client";

import { MissingId } from "@/components/routing/missing-id";
import { useRouteId } from "@/lib/use-route-id";
import { AdminUserDetail } from "@/components/admin/user-detail";

export function AdminUserRoute({ id }: { id: string }) {
  const real = useRouteId(id);
  if (!real) return <MissingId back="/admin/users" />;
  return <AdminUserDetail key={real} id={real} />;
}
