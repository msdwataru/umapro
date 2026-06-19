import { createClient } from "@/lib/supabase/server";

export default async function ModelsPage() {
  const supabase = await createClient();

  const { data: models } = await supabase
    .from("model_versions")
    .select("id, model_name, version, model_type, training_period_start, training_period_end, metrics_json, is_production, deployed_at, created_at")
    .order("created_at", { ascending: false });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">モデル管理</h1>

      <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
          <p className="text-sm font-semibold text-gray-700">モデルバージョン一覧</p>
          <span className="text-xs text-gray-400">{models?.length ?? 0}件</span>
        </div>
        {(!models || models.length === 0) ? (
          <p className="text-sm text-gray-400 text-center py-10">モデルが登録されていません</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">モデル名</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">バージョン</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">タイプ</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">訓練期間</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">メトリクス</th>
                  <th className="px-4 py-2 text-center text-xs font-semibold text-gray-500">本番</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">デプロイ日時</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {models.map((m) => {
                  const metrics = m.metrics_json as Record<string, number> | null;
                  return (
                    <tr key={m.id} className={`hover:bg-gray-50 ${m.is_production ? "bg-indigo-50/30" : ""}`}>
                      <td className="px-4 py-2.5 font-medium text-gray-900">{m.model_name}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{m.version}</td>
                      <td className="px-4 py-2.5 text-gray-500">{m.model_type}</td>
                      <td className="px-4 py-2.5 text-xs text-gray-400">
                        {m.training_period_start && m.training_period_end
                          ? `${m.training_period_start} 〜 ${m.training_period_end}`
                          : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-400">
                        {metrics
                          ? Object.entries(metrics).slice(0, 3).map(([k, v]) => `${k}: ${typeof v === "number" ? v.toFixed(3) : v}`).join(" / ")
                          : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {m.is_production ? (
                          <span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500" title="本番稼働中" />
                        ) : (
                          <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-300" />
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-400">
                        {m.deployed_at ? new Date(m.deployed_at).toLocaleString("ja-JP") : "-"}
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
