import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/admin", label: "ダッシュボード" },
  { href: "/admin/users", label: "会員管理" },
  { href: "/admin/sync", label: "データ同期" },
  { href: "/admin/models", label: "モデル管理" },
  { href: "/admin/audit", label: "推奨監査" },
  { href: "/admin/logs", label: "ログ" },
];

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const { data: profile } = await supabase
    .from("user_profiles")
    .select("*")
    .eq("id", user.id)
    .single();

  if (!profile || profile.role !== "admin") redirect("/today");

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="mx-auto max-w-7xl px-4">
          <div className="flex items-center gap-6 h-14">
            <Link href="/today" className="text-sm font-bold text-indigo-600">UMA</Link>
            <span className="text-gray-300">/</span>
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Admin</span>
            <nav className="flex gap-1 ml-4">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="px-3 py-1.5 rounded-md text-sm text-gray-600 hover:bg-gray-100 hover:text-gray-900 transition-colors"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
