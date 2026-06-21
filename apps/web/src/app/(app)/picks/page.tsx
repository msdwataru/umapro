import { createClient } from "@/lib/supabase/server";
import Link from "next/link";

const STATUS_LABEL: Record<string, string> = {
  scheduled: "発走前",
  open: "発走前",
  closed: "締切",
  result_fixed: "確定",
};

const STATUS_COLOR: Record<string, string> = {
  scheduled: "text-blue-600 bg-blue-50",
  open: "text-blue-600 bg-blue-50",
  closed: "text-yellow-600 bg-yellow-50",
  result_fixed: "text-green-600 bg-green-50",
};

export default async function PicksPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string; model?: string }>;
}) {
  const sp = await searchParams;
  const today = new Date().toISOString().split("T")[0];

  const supabase = await createClient();

  // 今日のデータがない場合は最新のレース日付を使う
  let targetDate = sp.date || today;
  if (!sp.date) {
    const { data: latestRace } = await supabase
      .from("races")
      .select("race_date")
      .order("race_date", { ascending: false })
      .limit(1)
      .single();
    if (latestRace && latestRace.race_date > today) {
      targetDate = today; // 未来データがあれば今日
    } else if (latestRace && latestRace.race_date < today) {
      // 今日のデータがなければ最新日
      const { count } = await supabase
        .from("races")
        .select("id", { count: "exact", head: true })
        .eq("race_date", today);
      if (!count || count === 0) {
        targetDate = latestRace.race_date;
      }
    }
  }

  // モデル一覧を取得
  const { data: modelVersions } = await supabase
    .from("model_versions")
    .select("id, model_name, version")
    .eq("is_production", true)
    .order("model_name");

  const selectedModelId = sp.model
    ? parseInt(sp.model)
    : (modelVersions?.find((m) => m.model_name === "course_form")?.id ??
       modelVersions?.[0]?.id ??
       null);

  const selectedModel = modelVersions?.find((m) => m.id === selectedModelId);

  // 対象日のレースを取得（予測データ込み）
  const { data: races } = await supabase
    .from("races")
    .select(`
      id, race_number, race_name, track_type, distance_m,
      field_size, scheduled_start_at, status,
      racecourses ( name, short_name ),
      race_entries (
        id, horse_number, latest_win_odds,
        horses ( name ),
        model_predictions (
          prediction_rank, predicted_value, edge_value, implied_probability,
          model_version_id
        ),
        entry_results ( finish_position )
      )
    `)
    .eq("race_date", targetDate)
    .order("scheduled_start_at", { ascending: true });

  // レースごとにモデル予測でトップピックを抽出
  type RaceEntry = {
    id: number;
    horse_number: number;
    latest_win_odds: number | null;
    horses: { name: string } | null;
    model_predictions: {
      prediction_rank: number;
      predicted_value: number;
      edge_value: number;
      implied_probability: number;
      model_version_id: number;
    }[];
    entry_results: { finish_position: number | null } | null;
  };

  type RacePick = {
    entry: RaceEntry;
    prediction: RaceEntry["model_predictions"][0];
  };

  const racesWithPicks = (races ?? []).map((race) => {
    const entries = (race.race_entries ?? []) as RaceEntry[];
    const preds = entries
      .flatMap((e) =>
        (e.model_predictions ?? [])
          .filter((p) => p.model_version_id === selectedModelId)
          .map((p) => ({ entry: e, prediction: p }))
      )
      .sort((a, b) => a.prediction.prediction_rank - b.prediction.prediction_rank);

    const top3: RacePick[] = preds.slice(0, 3);
    const hasPrediction = preds.length > 0;
    const topPick = top3[0] ?? null;
    const isBuy = topPick !== null && topPick.prediction.edge_value > 0;

    return { ...race, top3, hasPrediction, topPick, isBuy };
  });

  const racesWithData = racesWithPicks.filter((r) => r.hasPrediction);
  const racesNoData = racesWithPicks.filter((r) => !r.hasPrediction);
  const buyCount = racesWithData.filter((r) => r.isBuy).length;

  return (
    <div className="space-y-6">
      {/* ヘッダー */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">今日の買い目</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            モデルの予測をもとに、レースごとに買い推薦を表示します
          </p>
        </div>
        {racesWithData.length > 0 && (
          <div className="text-sm text-gray-500">
            <span className="font-semibold text-green-600">{buyCount}レース</span>
            　買い推薦 / 全{racesWithData.length}レース予測あり
          </div>
        )}
      </div>

      {/* フィルター */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4">
        <form method="GET" className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">日付</label>
            <input
              type="date"
              name="date"
              defaultValue={targetDate}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">予測モデル</label>
            <select
              name="model"
              defaultValue={selectedModelId ?? ""}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            >
              {(modelVersions ?? []).map((mv) => (
                <option key={mv.id} value={mv.id}>
                  {mv.model_name} ({mv.version})
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            表示
          </button>
        </form>

        {selectedModel && (
          <div className="mt-3 text-xs text-gray-400">
            使用モデル:
            <span className="ml-1 font-medium text-purple-700">{selectedModel.model_name} ({selectedModel.version})</span>
            {selectedModel.model_name === "course_form" && (
              <span className="ml-2 text-green-600">
                ※ 過去バックテスト: 1位予測 ROI +10.6%, 的中率 39.0%
              </span>
            )}
            {selectedModel.model_name === "rule_based_market" && (
              <span className="ml-2 text-gray-500">
                ※ 過去バックテスト: 1位予測 ROI -20.6%, 的中率 32.8%
              </span>
            )}
          </div>
        )}
      </div>

      {/* 予測なしのレースがある場合の説明 */}
      {racesNoData.length > 0 && (
        <div className="rounded-xl bg-amber-50 ring-1 ring-amber-100 p-4 text-sm">
          <p className="font-medium text-amber-800 mb-1">
            {racesNoData.length}レースの予測データがありません
          </p>
          <p className="text-amber-700">
            バッチを実行して本日分の予測を生成してください:
          </p>
          <code className="mt-1 block text-xs bg-amber-100 rounded px-2 py-1 text-amber-900 font-mono">
            {`python -m uma.predictions.backfill_job --from-date ${targetDate.replace(/-/g, "")} --to-date ${targetDate.replace(/-/g, "")} --model course_form`}
          </code>
        </div>
      )}

      {/* レース一覧 */}
      {racesWithPicks.length === 0 ? (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 p-12 text-center">
          <p className="text-gray-400">{targetDate} のレースデータがありません</p>
          <Link href="/races" className="mt-2 inline-block text-sm text-indigo-600 hover:underline">
            レース一覧を確認 →
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {racesWithPicks.map((race) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const rc = race.racecourses as any;
            const statusLabel = STATUS_LABEL[race.status] ?? race.status;
            const statusColor = STATUS_COLOR[race.status] ?? "text-gray-500 bg-gray-50";
            const startTime = race.scheduled_start_at
              ? new Date(race.scheduled_start_at).toLocaleTimeString("ja-JP", {
                  hour: "2-digit",
                  minute: "2-digit",
                })
              : "";

            return (
              <div
                key={race.id}
                className={`rounded-xl bg-white ring-1 ${
                  race.isBuy ? "ring-green-200" : race.hasPrediction ? "ring-gray-200" : "ring-gray-100"
                } p-4`}
              >
                {/* レースヘッダー */}
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-semibold text-gray-700 shrink-0">
                      {rc?.short_name} {race.race_number}R
                    </span>
                    <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${statusColor}`}>
                      {statusLabel}
                    </span>
                    <span className={`text-xs font-medium ${race.track_type === "芝" ? "text-green-600" : "text-amber-600"}`}>
                      {race.track_type}{race.distance_m}m
                    </span>
                    {startTime && (
                      <span className="text-xs text-gray-400">{startTime}発走</span>
                    )}
                    <span className="text-xs text-gray-400">{race.field_size}頭</span>
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    {race.hasPrediction && (
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                        race.isBuy
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}>
                        {race.isBuy ? "★ 買い推薦" : "見送り"}
                      </span>
                    )}
                    <Link
                      href={`/races/${race.id}`}
                      className="text-xs text-indigo-500 hover:text-indigo-700 hover:underline"
                    >
                      詳細 →
                    </Link>
                  </div>
                </div>

                {race.race_name && (
                  <p className="text-xs text-gray-400 mt-0.5 ml-0.5">{race.race_name}</p>
                )}

                {/* 予測ピック */}
                {race.hasPrediction ? (
                  <div className="mt-3 space-y-1.5">
                    {race.top3.map((pick, idx) => {
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const horse = pick.entry.horses as any;
                      const odds = pick.entry.latest_win_odds;
                      const ev = pick.prediction.edge_value;
                      const evPct = (ev * 100).toFixed(1);
                      const expectedReturn = odds ? Math.round(odds * 100 - 100) : null;
                      // eslint-disable-next-line @typescript-eslint/no-explicit-any
                      const finishPos = (pick.entry.entry_results as any)?.finish_position;

                      return (
                        <div
                          key={pick.entry.id}
                          className={`flex items-center gap-3 rounded-lg px-3 py-2 ${
                            idx === 0
                              ? pick.prediction.edge_value > 0
                                ? "bg-green-50 ring-1 ring-green-200"
                                : "bg-gray-50 ring-1 ring-gray-200"
                              : "bg-gray-50/50"
                          }`}
                        >
                          {/* ランク */}
                          <span className={`shrink-0 text-xs font-bold w-5 text-center ${
                            idx === 0 ? "text-indigo-600" : "text-gray-400"
                          }`}>
                            {idx === 0 ? "①" : idx === 1 ? "②" : "③"}
                          </span>

                          {/* 馬番 */}
                          <span className="shrink-0 text-xs font-semibold bg-gray-800 text-white rounded px-1.5 py-0.5 min-w-[24px] text-center">
                            {pick.entry.horse_number}番
                          </span>

                          {/* 馬名 */}
                          <span className="font-medium text-sm text-gray-900 flex-1 min-w-0 truncate">
                            {horse?.name ?? "不明"}
                          </span>

                          {/* オッズ */}
                          {odds != null && (
                            <span className="shrink-0 text-sm font-semibold text-gray-700">
                              {odds.toFixed(1)}倍
                            </span>
                          )}

                          {/* EV */}
                          <span className={`shrink-0 text-xs font-medium ${
                            ev > 0 ? "text-green-600" : "text-gray-400"
                          }`}>
                            EV {ev > 0 ? "+" : ""}{evPct}%
                          </span>

                          {/* 予想払戻（100円賭け時）*/}
                          {idx === 0 && odds != null && (
                            <span className={`shrink-0 text-xs ${
                              ev > 0 ? "text-green-700 font-semibold" : "text-gray-400"
                            }`}>
                              100円→{odds.toFixed(0)}倍
                              {expectedReturn != null && (
                                <span className="ml-1">
                                  ({expectedReturn >= 0 ? "+" : ""}{expectedReturn}円)
                                </span>
                              )}
                            </span>
                          )}

                          {/* 着順（結果確定後） */}
                          {finishPos != null && (
                            <span className={`shrink-0 text-xs font-bold ${
                              finishPos === 1 ? "text-amber-500" : "text-gray-300"
                            }`}>
                              {finishPos}着
                            </span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-gray-400 italic">このレースの予測データがありません</p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 使い方説明 */}
      <div className="rounded-xl bg-gray-50 ring-1 ring-gray-200 p-4 text-xs text-gray-500 space-y-1">
        <p className="font-semibold text-gray-600">この画面の見方</p>
        <p>• <span className="text-green-600 font-medium">★ 買い推薦</span> = モデルの1位予測かつEV+（期待値プラス）のレース</p>
        <p>• <span className="font-medium">EV（期待値）</span> = モデルが推定する確率 − 市場オッズ逆数。正なら統計的に市場より有利。</p>
        <p>• ① が最推薦、② ③ は参考候補。100円賭け時の払戻額を表示。</p>
        <p>• <span className="text-purple-600 font-medium">course_form</span> モデルは過去バックテストでROI +10.6%（1位予測のみ）。</p>
      </div>
    </div>
  );
}
