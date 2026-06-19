import { createClient } from "@/lib/supabase/server";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";

export default async function RaceDetailPage({
  params,
}: {
  params: Promise<{ raceId: string }>;
}) {
  const { raceId } = await params;
  const supabase = await createClient();

  const { data: race } = await supabase
    .from("races")
    .select(`
      id, race_date, race_number, race_name, track_type, distance_m,
      class_name, going, field_size, scheduled_start_at, status,
      racecourses ( name, short_name ),
      race_results ( winning_time, weather_final, going_final, lap_text ),
      race_entries (
        id, bracket_number, horse_number, sex_age,
        declared_weight_kg, declared_weight_diff_kg,
        latest_win_odds, latest_place_odds_min, morning_line_popularity,
        horses ( id, name, sex, birth_date ),
        jockeys ( id, name ),
        model_predictions ( prediction_rank, edge_value, implied_probability, prediction_target ),
        entry_results ( finish_position, finish_time, margin_text, passing_order_text, last3f, abnormal_result_code )
      )
    `)
    .eq("id", parseInt(raceId))
    .single();

  if (!race) notFound();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rc = race.racecourses as any;
  const statusMap: Record<string, { label: string; variant: "blue" | "green" | "gray" | "yellow" }> = {
    scheduled: { label: "発走前", variant: "blue" },
    open: { label: "発走前", variant: "blue" },
    closed: { label: "締切", variant: "yellow" },
    result_fixed: { label: "確定", variant: "green" },
  };
  const status = statusMap[race.status] ?? { label: race.status, variant: "gray" as const };

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const entries = [...(race.race_entries ?? [])].sort((a: any, b: any) => a.horse_number - b.horse_number);

  // 着順ソート済み（result_fixed の場合に使用）
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raceResult = race.race_results as any;
  const resultEntries = race.status === "result_fixed"
    ? [...(race.race_entries ?? [])].sort((a: any, b: any) => {
        const pa = a.entry_results?.finish_position ?? 999;
        const pb = b.entry_results?.finish_position ?? 999;
        return pa - pb;
      })
    : [];

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const topPicks = entries.filter((e: any) =>
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    e.model_predictions?.some((p: any) => p.prediction_target === "win" && p.prediction_rank <= 3)
  );

  return (
    <div className="space-y-6">
      {/* パンくず */}
      <nav className="text-sm text-gray-400 flex gap-2">
        <Link href="/today" className="hover:text-gray-600">今日</Link>
        <span>/</span>
        <Link href="/races" className="hover:text-gray-600">レース一覧</Link>
        <span>/</span>
        <span className="text-gray-700">{race.race_name ?? `${race.race_number}R`}</span>
      </nav>

      {/* レースヘッダー */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 p-5">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <p className="text-sm text-gray-400">
              {race.race_date} &middot; {rc?.name} {race.race_number}R
            </p>
            <h1 className="text-xl font-bold text-gray-900 mt-1">
              {race.race_name ?? `${rc?.short_name}${race.race_number}R`}
            </h1>
          </div>
          <Badge variant={status.variant}>{status.label}</Badge>
        </div>
        <div className="flex flex-wrap gap-4 mt-4 text-sm text-gray-600">
          <span>
            <span className={`font-semibold ${race.track_type === "芝" ? "text-green-600" : "text-amber-600"}`}>
              {race.track_type}
            </span>
            {" "}{race.distance_m}m
          </span>
          {race.class_name && <span className="text-gray-500">{race.class_name}</span>}
          {race.going && <span>馬場: {race.going}</span>}
          <span>{race.field_size}頭立て</span>
          {race.scheduled_start_at && (
            <span>
              {new Date(race.scheduled_start_at).toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" })}発走
            </span>
          )}
        </div>
      </div>

      {/* 推奨コーナー */}
      {topPicks.length > 0 && (
        <div className="rounded-xl bg-indigo-50 ring-1 ring-indigo-200 p-4">
          <p className="text-xs font-semibold text-indigo-700 uppercase tracking-wide mb-3">AI推奨馬</p>
          <div className="flex flex-wrap gap-3">
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            {topPicks.map((e: any) => {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const pred = e.model_predictions?.find((p: any) => p.prediction_target === "win");
              const horse = e.horses as { id: number; name: string } | null;
              return (
                <div key={e.id} className="bg-white rounded-lg px-4 py-3 ring-1 ring-indigo-200 flex items-center gap-3">
                  <span className="text-lg font-bold text-gray-400">{e.horse_number}</span>
                  <div>
                    <Link
                      href={`/races/${raceId}/horses/${horse?.id}`}
                      className="font-semibold text-gray-900 hover:text-indigo-700"
                    >
                      {horse?.name ?? "-"}
                    </Link>
                    <p className="text-xs text-gray-400">{e.sex_age}</p>
                  </div>
                  {pred && (
                    <div className="text-right ml-2">
                      <p className={`text-sm font-semibold ${(pred.edge_value ?? 0) > 0 ? "text-green-600" : "text-gray-400"}`}>
                        EV {pred.edge_value != null ? (pred.edge_value > 0 ? "+" : "") + Number(pred.edge_value).toFixed(2) : "-"}
                      </p>
                      {pred.implied_probability != null && (
                        <p className="text-xs text-gray-400">確率 {(Number(pred.implied_probability) * 100).toFixed(1)}%</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* レース結果 */}
      {race.status === "result_fixed" && resultEntries.length > 0 && (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex items-center justify-between">
            <p className="text-sm font-semibold text-gray-700">レース結果</p>
            {raceResult?.winning_time && (
              <span className="text-xs text-gray-500">勝ち時計: {raceResult.winning_time}</span>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-3 py-2 text-center text-xs text-gray-400 w-12">着順</th>
                  <th className="px-3 py-2 text-center text-xs text-gray-400 w-10">枠</th>
                  <th className="px-3 py-2 text-center text-xs text-gray-400 w-10">馬番</th>
                  <th className="px-3 py-2 text-left text-xs text-gray-400">馬名</th>
                  <th className="px-3 py-2 text-left text-xs text-gray-400">性齢</th>
                  <th className="px-3 py-2 text-left text-xs text-gray-400">騎手</th>
                  <th className="px-3 py-2 text-right text-xs text-gray-400">タイム</th>
                  <th className="px-3 py-2 text-right text-xs text-gray-400">着差</th>
                  <th className="px-3 py-2 text-right text-xs text-gray-400">上り</th>
                  <th className="px-3 py-2 text-right text-xs text-gray-400">馬体重</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {resultEntries.map((e: any) => {
                  const horse = e.horses as { id: number; name: string } | null;
                  const jockey = e.jockeys as { id: number; name: string } | null;
                  const er = e.entry_results;
                  const pos = er?.finish_position;
                  const isTop3 = pos != null && pos <= 3;
                  const posColor = pos === 1 ? "text-yellow-600 font-bold" : pos === 2 ? "text-gray-500 font-bold" : pos === 3 ? "text-amber-700 font-bold" : "text-gray-700";
                  return (
                    <tr key={e.id} className={`hover:bg-gray-50 transition-colors ${isTop3 ? "bg-yellow-50/40" : ""}`}>
                      <td className={`px-3 py-2.5 text-center text-base ${posColor}`}>
                        {er?.abnormal_result_code ?? (pos != null ? `${pos}着` : "-")}
                      </td>
                      <td className="px-3 py-2.5 text-center text-gray-400">{e.bracket_number ?? "-"}</td>
                      <td className="px-3 py-2.5 text-center font-bold text-gray-800">{e.horse_number}</td>
                      <td className="px-3 py-2.5">
                        <Link href={`/races/${raceId}/horses/${horse?.id}`} className="font-medium text-gray-900 hover:text-indigo-600">
                          {horse?.name ?? "-"}
                        </Link>
                      </td>
                      <td className="px-3 py-2.5 text-gray-500">{e.sex_age ?? "-"}</td>
                      <td className="px-3 py-2.5 text-gray-600">{jockey?.name ?? "-"}</td>
                      <td className="px-3 py-2.5 text-right text-gray-700 font-mono">{er?.finish_time ?? "-"}</td>
                      <td className="px-3 py-2.5 text-right text-gray-500">{er?.margin_text || "-"}</td>
                      <td className="px-3 py-2.5 text-right text-gray-600">{er?.last3f != null ? Number(er.last3f).toFixed(1) : "-"}</td>
                      <td className="px-3 py-2.5 text-right text-gray-500 text-xs">
                        {e.declared_weight_kg != null
                          ? `${e.declared_weight_kg}${e.declared_weight_diff_kg != null ? `(${e.declared_weight_diff_kg > 0 ? "+" : ""}${e.declared_weight_diff_kg})` : ""}`
                          : "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 出馬表 */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
          <p className="text-sm font-semibold text-gray-700">出馬表</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="px-3 py-2 text-left text-xs text-gray-400">枠</th>
                <th className="px-3 py-2 text-left text-xs text-gray-400">馬番</th>
                <th className="px-3 py-2 text-left text-xs text-gray-400">馬名</th>
                <th className="px-3 py-2 text-left text-xs text-gray-400">性齢</th>
                <th className="px-3 py-2 text-left text-xs text-gray-400">騎手</th>
                <th className="px-3 py-2 text-right text-xs text-gray-400">単勝</th>
                <th className="px-3 py-2 text-right text-xs text-gray-400">人気</th>
                <th className="px-3 py-2 text-right text-xs text-gray-400">EV(勝)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {entries.map((e: any) => {
                const horse = e.horses as { id: number; name: string } | null;
                const jockey = e.jockeys as { id: number; name: string } | null;
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const winPred = e.model_predictions?.find((p: any) => p.prediction_target === "win");
                const isTop = winPred && winPred.prediction_rank <= 3;
                return (
                  <tr key={e.id} className={`hover:bg-gray-50 transition-colors ${isTop ? "bg-indigo-50/50" : ""}`}>
                    <td className="px-3 py-2.5 text-gray-400">{e.bracket_number ?? "-"}</td>
                    <td className="px-3 py-2.5 font-bold text-gray-800">{e.horse_number}</td>
                    <td className="px-3 py-2.5">
                      <Link
                        href={`/races/${raceId}/horses/${horse?.id}`}
                        className="font-medium text-gray-900 hover:text-indigo-600"
                      >
                        {horse?.name ?? "-"}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-gray-500">{e.sex_age ?? "-"}</td>
                    <td className="px-3 py-2.5 text-gray-600">{jockey?.name ?? "-"}</td>
                    <td className="px-3 py-2.5 text-right text-gray-700">
                      {e.latest_win_odds != null ? Number(e.latest_win_odds).toFixed(1) : "-"}
                    </td>
                    <td className="px-3 py-2.5 text-right text-gray-500">
                      {e.morning_line_popularity != null ? `${e.morning_line_popularity}人気` : "-"}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {winPred ? (
                        <span className={`font-semibold ${(winPred.edge_value ?? 0) > 0 ? "text-green-600" : "text-gray-400"}`}>
                          {winPred.edge_value != null
                            ? (Number(winPred.edge_value) > 0 ? "+" : "") + Number(winPred.edge_value).toFixed(2)
                            : "-"}
                        </span>
                      ) : <span className="text-gray-300">-</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
