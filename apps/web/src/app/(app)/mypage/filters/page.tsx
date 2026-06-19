import { createClient } from "@/lib/supabase/server";
import { revalidatePath } from "next/cache";

async function deleteFilter(formData: FormData) {
  "use server";
  const supabase = await createClient();
  const filterId = parseInt(formData.get("filterId") as string);
  await supabase.from("saved_filters").delete().eq("id", filterId);
  revalidatePath("/mypage/filters");
}

export default async function FiltersPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const { data: filters } = await supabase
    .from("saved_filters")
    .select("id, filter_name, filter_type, filter_json, is_default, created_at")
    .eq("user_id", user!.id)
    .order("created_at", { ascending: false });

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-bold text-gray-900">保存済みフィルタ</h1>

      {(!filters || filters.length === 0) ? (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 p-10 text-center">
          <p className="text-gray-500">保存されたフィルタはありません</p>
          <p className="text-xs text-gray-400 mt-1">レース一覧ページの絞り込みを保存できます</p>
        </div>
      ) : (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 divide-y divide-gray-50">
          {filters.map((f) => {
            const params = f.filter_json as Record<string, string> | null;
            return (
              <div key={f.id} className="px-5 py-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-gray-900">{f.filter_name}</p>
                    {f.is_default && (
                      <span className="text-xs bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded">デフォルト</span>
                    )}
                    <span className="text-xs text-gray-400">{f.filter_type}</span>
                  </div>
                  {params && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {Object.entries(params).filter(([, v]) => v).map(([k, v]) => (
                        <span key={k} className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                          {k}: {v}
                        </span>
                      ))}
                    </div>
                  )}
                  <p className="text-xs text-gray-400 mt-1">
                    {new Date(f.created_at).toLocaleDateString("ja-JP")}
                  </p>
                </div>
                <form action={deleteFilter}>
                  <input type="hidden" name="filterId" value={f.id} />
                  <button
                    type="submit"
                    className="text-xs text-red-400 hover:text-red-600 shrink-0"
                  >
                    削除
                  </button>
                </form>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
