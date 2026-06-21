import { createClient } from "@/lib/supabase/server";
import { notFound } from "next/navigation";
import Link from "next/link";

export default async function BacktestResultPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  const runIdNum = parseInt(runId);
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const { data: run } = await supabase
    .from("backtest_runs")
    .select("id, run_name, status, parameters_json, started_at, finished_at, error_message, created_at")
    .eq("id", runIdNum)
    .eq("user_id", user!.id)
    .single();

  // モデル名を parameters_json.model_version_id から引く
  const runParams = run?.parameters_json as Record<string, unknown> | null;
  const modelVersionId = runParams?.model_version_id as number | null | undefined;
  let modelLabel: string | null = null;
  if (modelVersionId) {
    const { data: mv } = await supabase
      .from("model_versions")
      .select("model_name, version")
      .eq("id", modelVersionId)
      .single();
    if (mv) modelLabel = `${mv.model_name} (${mv.version})`;
  }

  if (!run) notFound();

  const { data: results } = await supabase
    .from("backtest_results")
    .select(`
      id, race_count, bet_count, hit_count, stake_amount, payout_amount,
      roi, hit_rate, max_drawdown, avg_odds,
      bet_types ( code, name )
    `)
    .eq("backtest_run_id", runIdNum);

  const { data: bets, count: totalBets } = await supabase
    .from("backtest_bets")
    .select(`
      id, stake_amount, payout_amount, is_hit, edge_value,
      races ( race_date, race_number, track_type, distance_m, racecourses ( short_name ) )
    `, { count: "exact" })
    .eq("backtest_run_id", runIdNum)
    .order("id", { ascending: true })
    .limit(50);

  const statusColor: Record<string, string> = {
    queued: "text-yellow-600",
    running: "text-blue-600",
    completed: "text-green-600",
    failed: "text-red-600",
  };
  const statusLabel: Record<string, string> = {
    queued: "待機中",
    running: "処理中",
    completed: "完了",
    failed: "失敗",
  };

  const params2 = runParams;

  const totalStake = results?.reduce((s, r) => s + Number(r.stake_amount), 0) ?? 0;
  const totalPayout = results?.reduce((s, r) => s + Number(r.payout_amount), 0) ?? 0;
  const totalProfit = totalPayout - totalStake;
  const overallROI = totalStake > 0 ? ((totalPayout - totalStake) / totalStake) * 100 : null;
  const totalBetCount = results?.reduce((s, r) => s + r.bet_count, 0) ?? 0;
  const totalHitCount = results?.reduce((s, r) => s + r.hit_count, 0) ?? 0;
  const overallHitRate = totalBetCount > 0 ? (totalHitCount / totalBetCount) * 100 : null;

  // 累積収支を計算（賭けログ用）
  let cumulative = 0;
  const betsWithCumulative = (bets ?? []).map((b) => {
    const profit = Number(b.payout_amount) - Number(b.stake_amount);
    cumulative += profit;
    return { ...b, profit, cumulative };
  });

  const isCompleted = run.status === "completed" && results && results.length > 0;

  return (
    <div className="space-y-6">
      <nav className="text-sm text-gray-400 flex gap-2">
        <Link href="/backtest" className="hover:text-gray-600">バックテスト</Link>
        <span>/</span>
        <span className="text-gray-700">{run.run_name ?? `Run #${run.id}`}</span>
      </nav>

      {/* ヘッダー */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-bold text-gray-900">{run.run_name ?? `Run #${run.id}`}</h1>
              {modelLabel && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 font-medium">
                  {modelLabel}
                </span>
              )}
            </div>
            {params2 && (
              <p className="text-sm text-gray-400 mt-1">
                {[
                  params2.track_type ? String(params2.track_type) : "全コース",
                  params2.distance_min && `${params2.distance_min}〜${params2.distance_max}m`,
                  params2.ev_threshold != null && `EV≥${params2.ev_threshold}`,
                  params2.date_from && `${params2.date_from} 〜 ${params2.date_to}`,
                ].filter(Boolean).join(" / ")}
              </p>
            )}
          </div>
          <span className={`text-sm font-semibold px-2 py-1 rounded-full ${
            run.status === "completed" ? "bg-green-50 text-green-700" :
            run.status === "running" ? "bg-blue-50 text-blue-700" :
            run.status === "failed" ? "bg-red-50 text-red-700" :
            "bg-yellow-50 text-yellow-700"
          }`}>
            {statusLabel[run.status] ?? run.status}
          </span>
        </div>
        {run.status === "running" && (
          <div className="mt-3 text-sm text-blue-600 animate-pulse">処理中です。しばらくお待ちください...</div>
        )}
        {run.status === "queued" && (
          <div className="mt-3 text-sm text-yellow-600">キューに入っています。バッチ処理が開始されるまでお待ちください。</div>
        )}
        {run.error_message && (
          <div className="mt-3 text-sm text-red-600 bg-red-50 rounded-md p-3">{run.error_message}</div>
        )}
      </div>

      {isCompleted && (
        <>
          {/* サマリーカード */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4 text-center">
              <p className="text-xs text-gray-400 mb-1">ROI（投資収益率）</p>
              <p className={`text-2xl font-bold ${overallROI != null && overallROI > 0 ? "text-green-600" : "text-red-500"}`}>
                {overallROI != null ? (overallROI > 0 ? "+" : "") + overallROI.toFixed(1) + "%" : "-"}
              </p>
              <p className="text-xs text-gray-400 mt-1">+なら黒字、−なら赤字</p>
            </div>
            <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4 text-center">
              <p className="text-xs text-gray-400 mb-1">収支（損益）</p>
              <p className={`text-2xl font-bold ${totalProfit >= 0 ? "text-green-600" : "text-red-500"}`}>
                {totalProfit >= 0 ? "+" : ""}{totalProfit.toLocaleString()}円
              </p>
              <p className="text-xs text-gray-400 mt-1">払戻 − 賭け金の合計</p>
            </div>
            <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4 text-center">
              <p className="text-xs text-gray-400 mb-1">的中率</p>
              <p className="text-2xl font-bold text-gray-700">
                {overallHitRate != null ? overallHitRate.toFixed(1) + "%" : "-"}
              </p>
              <p className="text-xs text-gray-400 mt-1">
                {totalBetCount}回中{totalHitCount}回的中
              </p>
            </div>
            <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4 text-center">
              <p className="text-xs text-gray-400 mb-1">賭け回数</p>
              <p className="text-2xl font-bold text-gray-700">{totalBetCount.toLocaleString()}回</p>
              <p className="text-xs text-gray-400 mt-1">{totalStake.toLocaleString()}円 投資</p>
            </div>
          </div>

          {/* 結果の読み方 */}
          <div className="rounded-xl bg-indigo-50 ring-1 ring-indigo-100 p-5">
            <p className="text-sm font-semibold text-indigo-800 mb-3">この結果の読み方</p>
            <div className="space-y-2 text-sm text-indigo-900">
              <div className="flex gap-2">
                <span className="shrink-0">📊</span>
                <span>
                  <strong>{totalBetCount}回</strong>の単勝を買い、<strong>{totalHitCount}回</strong>的中（約
                  {overallHitRate != null ? Math.round(100 / overallHitRate) : "？"}回に1回）。
                  合計 <strong>{totalStake.toLocaleString()}円</strong> を投資して
                  <strong>{totalPayout.toLocaleString()}円</strong> を回収。
                </span>
              </div>
              <div className="flex gap-2">
                <span className="shrink-0">💰</span>
                <span>
                  収支は <strong className={totalProfit >= 0 ? "text-green-700" : "text-red-700"}>
                    {totalProfit >= 0 ? "+" : ""}{totalProfit.toLocaleString()}円（ROI {overallROI?.toFixed(1)}%）
                  </strong>。
                  JRA 単勝の市場平均回収率は約 <strong>77〜80%</strong> なので、ROI が
                  {overallROI != null && overallROI > -20
                    ? <strong className="text-green-700"> −20% より高ければ平均より良い</strong>
                    : <strong className="text-red-700"> −20% を下回っており市場平均以下</strong>
                  } 結果です。
                </span>
              </div>
              {results?.map((r) => {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                const bt = r.bet_types as any;
                const mdd = Number(r.max_drawdown) * 100;
                return (
                  <div key={r.id} className="flex gap-2">
                    <span className="shrink-0">📉</span>
                    <span>
                      最大ドローダウン（MDD）は <strong>{mdd.toFixed(1)}%</strong>。
                      これは連敗が続いたときに一時的に資金が最大で何%目減りしたかを示します。
                      {mdd > 50
                        ? " 資金の半分以上が一時的に失われており、リスクは高めです。"
                        : mdd > 20
                        ? " ある程度の損失局面がありますが、許容範囲内です。"
                        : " 比較的安定したドローダウンです。"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 式別内訳 */}
          <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
              <p className="text-sm font-semibold text-gray-700">式別内訳</p>
              <p className="text-xs text-gray-400 mt-0.5">賭け式（単勝・複勝など）ごとの成績</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">式別</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">
                      <span>レース数</span>
                    </th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">
                      <span>賭け数</span>
                    </th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">
                      <span title="何回に1回当たるか">的中率</span>
                    </th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">
                      <span title="的中したときの平均払戻倍率">平均払戻</span>
                    </th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">
                      <span title="100円賭けたときの平均回収額。100%以上が黒字">ROI</span>
                    </th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">
                      <span title="最悪の連敗時に資金がどれだけ減ったか（小さいほど安定）">MDD</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {results.map((r) => {
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    const bt = r.bet_types as any;
                    const roi = Number(r.roi) * 100;
                    const hitRate = Number(r.hit_rate) * 100;
                    const mdd = Number(r.max_drawdown) * 100;
                    const timesPerHit = hitRate > 0 ? Math.round(100 / hitRate) : null;
                    return (
                      <tr key={r.id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-medium text-gray-900">{bt?.name ?? "-"}</td>
                        <td className="px-4 py-3 text-right text-gray-500">{r.race_count}R</td>
                        <td className="px-4 py-3 text-right text-gray-500">{r.bet_count}回</td>
                        <td className="px-4 py-3 text-right">
                          <span className="text-gray-700 font-medium">{hitRate.toFixed(1)}%</span>
                          {timesPerHit && (
                            <span className="text-xs text-gray-400 ml-1">（約{timesPerHit}回に1回）</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-500">
                          {r.avg_odds != null ? Number(r.avg_odds).toFixed(1) + "倍" : "-"}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className={`font-semibold ${roi > 0 ? "text-green-600" : roi > -20 ? "text-yellow-600" : "text-red-500"}`}>
                            {roi > 0 ? "+" : ""}{roi.toFixed(1)}%
                          </span>
                          <span className="text-xs text-gray-400 ml-1">
                            （{roi > 0 ? "黒字" : roi > -20 ? "平均前後" : "赤字"}）
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className={`${mdd > 50 ? "text-red-500" : mdd > 20 ? "text-yellow-600" : "text-gray-500"}`}>
                            -{mdd.toFixed(1)}%
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {run.status === "completed" && (!results || results.length === 0) && (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 p-10 text-center">
          <p className="text-gray-500">条件に合う賭け対象がありませんでした</p>
          <p className="text-xs text-gray-400 mt-1">EVの閾値を下げるか、対象期間・コースを広げてください</p>
          <Link href="/backtest" className="mt-3 inline-block text-sm text-indigo-600 hover:underline">
            条件を変えて再実行 →
          </Link>
        </div>
      )}

      {/* 賭けログ */}
      {betsWithCumulative.length > 0 && (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
            <div>
              <p className="text-sm font-semibold text-gray-700">賭けログ</p>
              <p className="text-xs text-gray-400 mt-0.5">各レースでの賭け結果。累積収支で損益の推移を確認できます。</p>
            </div>
            <span className="text-xs text-gray-400 shrink-0">全{totalBets}件中50件表示</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">レース</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">
                    <span title="このレースでの損益（的中: 払戻−賭け金、外れ: −賭け金）">損益</span>
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">
                    <span title="このレースまでの累積損益">累積収支</span>
                  </th>
                  <th className="px-4 py-2 text-center text-xs font-semibold text-gray-500">結果</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {betsWithCumulative.map((b) => {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  const race = b.races as any;
                  return (
                    <tr key={b.id} className={`hover:bg-gray-50 ${b.is_hit ? "bg-green-50/40" : ""}`}>
                      <td className="px-4 py-2.5 text-gray-700">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`text-xs font-medium ${race?.track_type === "芝" ? "text-green-600" : "text-amber-600"}`}>
                            {race?.track_type}
                          </span>
                          <span className="text-gray-400">{race?.distance_m}m</span>
                          <span className="text-gray-500">{race?.racecourses?.short_name}{race?.race_number}R</span>
                          {race?.race_date && (
                            <span className="text-gray-400 text-xs">{race.race_date}</span>
                          )}
                        </div>
                      </td>
                      <td className={`px-4 py-2.5 text-right font-medium ${b.profit >= 0 ? "text-green-600" : "text-gray-400"}`}>
                        {b.profit >= 0 ? "+" : ""}{b.profit.toLocaleString()}円
                      </td>
                      <td className={`px-4 py-2.5 text-right font-semibold ${b.cumulative >= 0 ? "text-green-600" : "text-red-500"}`}>
                        {b.cumulative >= 0 ? "+" : ""}{b.cumulative.toLocaleString()}円
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {b.is_hit
                          ? <span className="inline-flex items-center gap-1 text-green-700 font-semibold text-xs bg-green-100 px-2 py-0.5 rounded-full">✓ 的中</span>
                          : <span className="text-xs text-gray-300">✗ 外れ</span>
                        }
                      </td>
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
