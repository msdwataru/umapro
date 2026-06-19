import { createClient } from "@/lib/supabase/server";
import { notFound } from "next/navigation";
import Link from "next/link";

export default async function HorseDetailPage({
  params,
}: {
  params: Promise<{ raceId: string; horseId: string }>;
}) {
  const { raceId, horseId } = await params;
  const raceIdNum = parseInt(raceId);
  const horseIdNum = parseInt(horseId);
  const supabase = await createClient();

  const { data: horse } = await supabase
    .from("horses")
    .select("id, name, sex, birth_date, sire_name, dam_name, owner_name")
    .eq("id", horseIdNum)
    .single();

  if (!horse) notFound();

  const { data: entry } = await supabase
    .from("race_entries")
    .select(`
      id, bracket_number, horse_number, sex_age,
      declared_weight_kg, declared_weight_diff_kg,
      latest_win_odds, morning_line_popularity, scratch_flag,
      jockeys ( id, name ),
      trainers ( id, name ),
      model_predictions (
        id, prediction_rank, edge_value, implied_probability, prediction_target,
        prediction_reasons ( id, reason_type, display_order, title, body, score )
      )
    `)
    .eq("race_id", raceIdNum)
    .eq("horse_id", horseIdNum)
    .single();

  const { data: race } = await supabase
    .from("races")
    .select("id, race_date, race_number, race_name, track_type, distance_m, class_name, racecourses ( name, short_name )")
    .eq("id", raceIdNum)
    .single();

  // 近走成績（直近10走）— race_entriesを過去レース分取得しentry_resultsをjoin
  const { data: history } = await supabase
    .from("race_entries")
    .select(`
      id, horse_number, latest_win_odds, morning_line_popularity, sex_age,
      races ( id, race_date, race_number, race_name, track_type, distance_m, class_name, racecourses ( short_name ) ),
      entry_results ( finish_position, finish_time, prize_money, popularity_final )
    `)
    .eq("horse_id", horseIdNum)
    .neq("race_id", raceIdNum)
    .order("id", { ascending: false })
    .limit(10);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rc = (race?.racecourses as any);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const jockey = entry?.jockeys as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const trainer = entry?.trainers as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const winPred = entry?.model_predictions?.find((p: any) => p.prediction_target === "win");
  const reasons = winPred?.prediction_reasons
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ? [...winPred.prediction_reasons].sort((a: any, b: any) => a.display_order - b.display_order)
    : [];

  // 年齢計算（birth_dateから）
  const age = horse.birth_date
    ? Math.floor((Date.now() - new Date(horse.birth_date).getTime()) / (365.25 * 24 * 60 * 60 * 1000))
    : null;

  return (
    <div className="space-y-6">
      {/* パンくず */}
      <nav className="text-sm text-gray-400 flex gap-2">
        <Link href="/races" className="hover:text-gray-600">レース一覧</Link>
        <span>/</span>
        <Link href={`/races/${raceId}`} className="hover:text-gray-600">
          {race?.race_name ?? `${race?.race_number}R`}
        </Link>
        <span>/</span>
        <span className="text-gray-700">{horse.name}</span>
      </nav>

      {/* 馬情報ヘッダー */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 p-5">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{horse.name}</h1>
            <p className="text-sm text-gray-400 mt-1">
              {entry?.sex_age ?? `${horse.sex ?? ""}`}
              {age != null && !entry?.sex_age && `${age}歳`}
            </p>
            {horse.sire_name && (
              <p className="text-xs text-gray-400 mt-0.5">父: {horse.sire_name} / 母: {horse.dam_name}</p>
            )}
            {horse.owner_name && (
              <p className="text-xs text-gray-400 mt-0.5">馬主: {horse.owner_name}</p>
            )}
          </div>
          {entry && (
            <div className="text-right">
              <p className="text-xs text-gray-400">馬番</p>
              <p className="text-3xl font-bold text-gray-900">{entry.horse_number}</p>
            </div>
          )}
        </div>

        {entry && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="騎手" value={jockey?.name ?? "-"} />
            <Stat label="調教師" value={trainer?.name ?? "-"} />
            <Stat
              label="馬体重"
              value={entry.declared_weight_kg != null
                ? `${entry.declared_weight_kg}kg ${entry.declared_weight_diff_kg != null ? (entry.declared_weight_diff_kg > 0 ? `(+${entry.declared_weight_diff_kg})` : `(${entry.declared_weight_diff_kg})`) : ""}`
                : "-"}
            />
            <Stat
              label="単勝オッズ"
              value={entry.latest_win_odds != null
                ? `${Number(entry.latest_win_odds).toFixed(1)}倍 (${entry.morning_line_popularity ?? "-"}人気)`
                : "-"}
            />
          </div>
        )}
      </div>

      {/* AI予測 */}
      {winPred && (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 p-5">
          <p className="text-sm font-semibold text-gray-700 mb-4">AI予測（勝利確率）</p>
          <div className="flex flex-wrap gap-6">
            <div className="text-center">
              <p className="text-xs text-gray-400 mb-1">予測順位</p>
              <p className="text-3xl font-bold text-indigo-600">{winPred.prediction_rank}位</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-gray-400 mb-1">期待値 (EV)</p>
              <p className={`text-3xl font-bold ${(winPred.edge_value ?? 0) > 0 ? "text-green-600" : "text-gray-400"}`}>
                {winPred.edge_value != null
                  ? (Number(winPred.edge_value) > 0 ? "+" : "") + Number(winPred.edge_value).toFixed(2)
                  : "-"}
              </p>
            </div>
            {winPred.implied_probability != null && (
              <div className="text-center">
                <p className="text-xs text-gray-400 mb-1">予測確率</p>
                <p className="text-3xl font-bold text-gray-700">{(Number(winPred.implied_probability) * 100).toFixed(1)}%</p>
              </div>
            )}
          </div>

          {/* 予測根拠 */}
          {reasons.length > 0 && (
            <div className="mt-5">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">予測の根拠</p>
              <div className="space-y-2">
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {reasons.slice(0, 5).map((r: any) => (
                  <div key={r.id} className="flex items-start gap-3">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${
                      r.reason_type === "strength" ? "bg-green-50 text-green-700" :
                      r.reason_type === "risk" ? "bg-red-50 text-red-700" :
                      "bg-gray-50 text-gray-500"
                    }`}>
                      {r.reason_type === "strength" ? "強み" : r.reason_type === "risk" ? "リスク" : "特徴"}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-gray-800">{r.title}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{r.body}</p>
                    </div>
                    {r.score != null && (
                      <div className="ml-auto shrink-0">
                        <div className="flex-1 bg-gray-100 rounded-full h-1.5 w-20 overflow-hidden">
                          <div
                            className="h-full bg-indigo-500 rounded-full"
                            style={{ width: `${Math.min(100, Math.abs(Number(r.score)) * 100)}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* 近走成績 */}
      {history && history.length > 0 && (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
            <p className="text-sm font-semibold text-gray-700">近走成績</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-3 py-2 text-left text-xs text-gray-400">日付</th>
                  <th className="px-3 py-2 text-left text-xs text-gray-400">場・R</th>
                  <th className="px-3 py-2 text-left text-xs text-gray-400">レース名</th>
                  <th className="px-3 py-2 text-left text-xs text-gray-400">コース</th>
                  <th className="px-3 py-2 text-right text-xs text-gray-400">着順</th>
                  <th className="px-3 py-2 text-right text-xs text-gray-400">人気</th>
                  <th className="px-3 py-2 text-right text-xs text-gray-400">単勝</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                {history.map((h: any) => {
                  const r = h.races as { id: number; race_date: string; race_number: number; race_name: string; track_type: string; distance_m: number; racecourses: { short_name: string } } | null;
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  const result = h.entry_results as any;
                  const pos = result?.finish_position;
                  const posColor = pos === 1 ? "text-yellow-600 font-bold" : pos === 2 ? "text-gray-500 font-semibold" : pos === 3 ? "text-amber-700 font-semibold" : "text-gray-400";
                  return (
                    <tr key={h.id} className="hover:bg-gray-50">
                      <td className="px-3 py-2.5 text-gray-500">{r?.race_date ?? "-"}</td>
                      <td className="px-3 py-2.5 text-gray-500">{(r?.racecourses as { short_name: string } | null)?.short_name}{r?.race_number}R</td>
                      <td className="px-3 py-2.5">
                        <Link href={`/races/${r?.id}`} className="text-gray-900 hover:text-indigo-600">
                          {r?.race_name ?? "-"}
                        </Link>
                      </td>
                      <td className="px-3 py-2.5 text-gray-500">
                        <span className={r?.track_type === "芝" ? "text-green-600" : "text-amber-600"}>
                          {r?.track_type}
                        </span>
                        {r?.distance_m}m
                      </td>
                      <td className={`px-3 py-2.5 text-right ${posColor}`}>
                        {pos != null ? `${pos}着` : "-"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-400">
                        {result?.popularity_final != null ? `${result.popularity_final}人気` : "-"}
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-500">
                        {h.latest_win_odds != null ? `${Number(h.latest_win_odds).toFixed(1)}倍` : "-"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(!history || history.length === 0) && (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 p-8 text-center">
          <p className="text-gray-400 text-sm">近走成績データがありません</p>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-gray-50 px-3 py-2">
      <p className="text-xs text-gray-400">{label}</p>
      <p className="text-sm font-medium text-gray-800 mt-0.5">{value}</p>
    </div>
  );
}
