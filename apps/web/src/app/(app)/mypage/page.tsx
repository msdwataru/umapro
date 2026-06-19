import { createClient } from "@/lib/supabase/server";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";

export default async function MyPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const { data: profile } = await supabase
    .from("user_profiles")
    .select("id, display_name, role, status, created_at, last_login_at")
    .eq("id", user!.id)
    .single();

  const { count: favCount } = await supabase
    .from("favorites")
    .select("*", { count: "exact", head: true })
    .eq("user_id", user!.id);

  const { count: filterCount } = await supabase
    .from("saved_filters")
    .select("*", { count: "exact", head: true })
    .eq("user_id", user!.id);

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-bold text-gray-900">マイページ</h1>

      {/* プロフィールカード */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-lg font-semibold text-gray-900">{profile?.display_name ?? "-"}</p>
            <p className="text-sm text-gray-400 mt-0.5">{user?.email}</p>
          </div>
          <Badge variant={profile?.role === "admin" ? "blue" : "green"}>
            {profile?.role === "admin" ? "管理者" : "一般"}
          </Badge>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-gray-400">登録日</p>
            <p className="text-gray-700 mt-0.5">
              {profile?.created_at ? new Date(profile.created_at).toLocaleDateString("ja-JP") : "-"}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400">最終ログイン</p>
            <p className="text-gray-700 mt-0.5">
              {profile?.last_login_at ? new Date(profile.last_login_at).toLocaleDateString("ja-JP") : "-"}
            </p>
          </div>
        </div>
      </div>

      {/* クイックリンク */}
      <div className="grid grid-cols-2 gap-4">
        <Link
          href="/mypage/favorites"
          className="rounded-xl bg-white ring-1 ring-gray-200 p-5 hover:ring-indigo-300 hover:shadow-sm transition-all group"
        >
          <p className="text-2xl font-bold text-gray-900 group-hover:text-indigo-700">{favCount ?? 0}</p>
          <p className="text-sm text-gray-500 mt-1">お気に入り馬</p>
          <p className="text-xs text-indigo-600 mt-2 group-hover:underline">一覧を見る →</p>
        </Link>
        <Link
          href="/mypage/filters"
          className="rounded-xl bg-white ring-1 ring-gray-200 p-5 hover:ring-indigo-300 hover:shadow-sm transition-all group"
        >
          <p className="text-2xl font-bold text-gray-900 group-hover:text-indigo-700">{filterCount ?? 0}</p>
          <p className="text-sm text-gray-500 mt-1">保存済みフィルタ</p>
          <p className="text-xs text-indigo-600 mt-2 group-hover:underline">管理する →</p>
        </Link>
      </div>
    </div>
  );
}
