"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut } from "@/app/actions/auth";

const links = [
  { href: "/picks", label: "買い目" },
  { href: "/today", label: "レース" },
  { href: "/races", label: "一覧" },
  { href: "/analysis", label: "条件分析" },
  { href: "/backtest", label: "バックテスト" },
  { href: "/mypage", label: "マイページ" },
];

export function Nav({ isAdmin }: { isAdmin?: boolean }) {
  const pathname = usePathname();

  return (
    <header className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
        <Link href="/today" className="text-lg font-bold text-indigo-600 tracking-tight">
          umapro
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                pathname.startsWith(l.href)
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`}
            >
              {l.label}
            </Link>
          ))}
          {isAdmin && (
            <Link
              href="/admin"
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                pathname.startsWith("/admin")
                  ? "bg-amber-50 text-amber-700"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
            >
              管理
            </Link>
          )}
        </nav>

        <form action={signOut}>
          <button
            type="submit"
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            ログアウト
          </button>
        </form>
      </div>

      {/* Mobile nav */}
      <nav className="flex md:hidden overflow-x-auto border-t border-gray-100 px-2 pb-1">
        {links.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              pathname.startsWith(l.href)
                ? "text-indigo-700 bg-indigo-50"
                : "text-gray-600"
            }`}
          >
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
