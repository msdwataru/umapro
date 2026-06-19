import { createClient } from "@/lib/supabase/server";

export default async function AnalysisPage() {
  const supabase = await createClient();

  // 直近90日の予測データからコース別・距離別の期待値集計
  const { data: predictions } = await supabase
    .from("model_predictions")
    .select(`
      edge_value, prediction_target, prediction_rank,
      race_entries (
        race_id,
        races ( track_type, distance_m, class_name, going )
      )
    `)
    .eq("prediction_target", "win")
    .not("edge_value", "is", null)
    .order("edge_value", { ascending: false })
    .limit(500);

  // コース×距離別のEV集計
  const buckets: Record<string, { count: number; evSum: number; evPlus: number }> = {};
  for (const p of predictions ?? []) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const entry = p.race_entries as any;
    const race = entry?.races as { track_type: string; distance_m: number; class_name: string } | null;
    if (!race) continue;
    const key = `${race.track_type}_${Math.round(race.distance_m / 200) * 200}m`;
    if (!buckets[key]) buckets[key] = { count: 0, evSum: 0, evPlus: 0 };
    const ev = Number(p.edge_value ?? 0);
    buckets[key].count++;
    buckets[key].evSum += ev;
    if (ev > 0) buckets[key].evPlus++;
  }

  const bucketList = Object.entries(buckets)
    .map(([key, v]) => ({
      label: key,
      count: v.count,
      avgEV: v.evSum / v.count,
      plusRate: v.evPlus / v.count,
    }))
    .sort((a, b) => b.avgEV - a.avgEV);

  // 上位EV馬
  const topEdge = (predictions ?? [])
    .filter((p) => Number(p.edge_value ?? 0) > 0)
    .slice(0, 20);

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-bold text-gray-900">条件分析</h1>
        <p className="text-xs text-gray-400">直近500予測データをもとに集計</p>
      </div>

      {/* コース別期待値 */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
          <p className="text-sm font-semibold text-gray-700">コース×距離別 平均EV</p>
        </div>
        {bucketList.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-10">分析データが不足しています</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">コース</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">サンプル数</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">平均EV</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">EV+率</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">EVバー</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {bucketList.map((b) => {
                  const [trackType, dist] = b.label.split("_");
                  const barWidth = Math.min(100, Math.abs(b.avgEV) * 200);
                  return (
                    <tr key={b.label} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5">
                        <span className={`font-medium ${trackType === "芝" ? "text-green-600" : "text-amber-600"}`}>
                          {trackType}
                        </span>
                        <span className="text-gray-500 ml-1">{dist}</span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-500">{b.count}</td>
                      <td className={`px-4 py-2.5 text-right font-semibold ${b.avgEV > 0 ? "text-green-600" : "text-gray-400"}`}>
                        {b.avgEV > 0 ? "+" : ""}{b.avgEV.toFixed(3)}
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-500">
                        {(b.plusRate * 100).toFixed(0)}%
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-end">
                          <div className="w-24 bg-gray-100 rounded-full h-1.5 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${b.avgEV > 0 ? "bg-green-500" : "bg-red-400"}`}
                              style={{ width: `${barWidth}%` }}
                            />
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 上位EV予測 */}
      {topEdge.length > 0 && (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
            <p className="text-sm font-semibold text-gray-700">EV上位予測（直近）</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">コース</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">クラス</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">予測順位</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">EV</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">予測確率</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {topEdge.map((p) => {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  const entry = p.race_entries as any;
                  const race = entry?.races as { track_type: string; distance_m: number; class_name: string; going: string } | null;
                  return (
                    <tr key={`${p.prediction_rank}-${p.edge_value}`} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5">
                        <span className={`font-medium ${race?.track_type === "芝" ? "text-green-600" : "text-amber-600"}`}>
                          {race?.track_type ?? "-"}
                        </span>
                        <span className="text-gray-500 ml-1">{race?.distance_m}m</span>
                        {race?.going && <span className="text-gray-400 ml-1">({race.going})</span>}
                      </td>
                      <td className="px-4 py-2.5 text-gray-500">{race?.class_name ?? "-"}</td>
                      <td className="px-4 py-2.5 text-right text-gray-500">{p.prediction_rank}位</td>
                      <td className="px-4 py-2.5 text-right font-semibold text-green-600">
                        +{Number(p.edge_value).toFixed(3)}
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-400">-</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
