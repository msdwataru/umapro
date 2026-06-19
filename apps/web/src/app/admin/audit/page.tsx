import { createClient } from "@/lib/supabase/server";

export default async function AuditPage() {
  const supabase = await createClient();

  const { data: audits } = await supabase
    .from("recommendation_audits")
    .select(`
      id, prediction_generated_at, published_at, payload_json,
      race_id, race_entry_id, model_version_id,
      races ( id, race_date, race_number, race_name, racecourses ( short_name ) )
    `)
    .order("prediction_generated_at", { ascending: false })
    .limit(100);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">推奨結果監査</h1>

      <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
          <p className="text-sm font-semibold text-gray-700">推奨ログ（直近100件）</p>
          <span className="text-xs text-gray-400">{audits?.length ?? 0}件</span>
        </div>
        {(!audits || audits.length === 0) ? (
          <p className="text-sm text-gray-400 text-center py-10">監査データがありません</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">予測生成日時</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">レース</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">モデルID</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">公開日時</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {audits.map((a: any) => {
                  const race = a.races as { id: number; race_date: string; race_number: number; race_name: string; racecourses: { short_name: string } } | null;
                  return (
                    <tr key={a.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 text-xs text-gray-500">
                        {a.prediction_generated_at ? new Date(a.prediction_generated_at).toLocaleString("ja-JP") : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-gray-700">
                        <span className="text-xs">{race?.racecourses?.short_name}</span>
                        {" "}{race?.race_number}R {race?.race_name}
                        {race?.race_date && <span className="text-gray-400 ml-1">({race.race_date})</span>}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-400">{a.model_version_id}</td>
                      <td className="px-4 py-2.5 text-xs text-gray-400">
                        {a.published_at ? new Date(a.published_at).toLocaleString("ja-JP") : "未公開"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
