import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

export default async function FavoritesPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const { data: favorites } = await supabase
    .from("favorites")
    .select(`
      id, favorite_type, created_at,
      horses ( id, name, sex )
    `)
    .eq("user_id", user!.id)
    .eq("favorite_type", "horse")
    .order("created_at", { ascending: false });

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-bold text-gray-900">お気に入り馬</h1>

      {(!favorites || favorites.length === 0) ? (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 p-10 text-center">
          <p className="text-gray-500">お気に入りに登録した馬はいません</p>
          <Link href="/races" className="mt-3 inline-block text-sm text-indigo-600 hover:underline">
            レース一覧から馬を探す →
          </Link>
        </div>
      ) : (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 divide-y divide-gray-50">
          {favorites.map((fav) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const horse = fav.horses as any;
            return (
              <div key={fav.id} className="px-5 py-4 flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-gray-900">{horse?.name ?? "-"}</p>
                  <p className="text-xs text-gray-400">{horse?.sex ?? "-"}</p>
                </div>
                <span className="text-xs text-gray-400">
                  {new Date(fav.created_at).toLocaleDateString("ja-JP")}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
