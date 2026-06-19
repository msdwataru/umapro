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
    .order("id", { ascending: false })
    .limit(50);

  const statusColor: Record<string, string> = {
    queued: "text-yellow-600",
    running: "text-blue-600",
    completed: "text-green-600",
    failed: "text-red-600",
  };

  const params2 = run.parameters_json as Record<string, unknown> | null;

  // 全体サマリー（bet_type横断）
  const totalStake = results?.reduce((s, r) => s + Number(r.stake_amount), 0) ?? 0;
  const totalPayout = results?.reduce((s, r) => s + Number(r.payout_amount), 0) ?? 0;
  const overallROI = totalStake > 0 ? ((totalPayout - totalStake) / totalStake) * 100 : null;

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
            <h1 className="text-xl font-bold text-gray-900">{run.run_name ?? `Run #${run.id}`}</h1>
            {params2 && (
              <p className="text-sm text-gray-400 mt-1">
                {[
                  params2.track_type && String(params2.track_type),
                  params2.distance_min && `${params2.distance_min}〜${params2.distance_max}m`,
                  params2.ev_threshold != null && `EV≥${params2.ev_threshold}`,
                  params2.date_from && `${params2.date_from} 〜 ${params2.date_to}`,
                ].filter(Boolean).join(" / ")}
              </p>
            )}
          </div>
          <span className={`text-sm font-semibold ${statusColor[run.status] ?? "text-gray-400"}`}>
            {run.status}
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

      {/* 結果サマリー */}
      {run.status === "completed" && results && results.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4 text-center">
              <p className="text-xs text-gray-400 uppercase tracking-wide">総ROI</p>
              <p className={`text-2xl font-bold mt-1 ${overallROI != null && overallROI > 0 ? "text-green-600" : "text-gray-500"}`}>
                {overallROI != null ? (overallROI > 0 ? "+" : "") + overallROI.toFixed(1) + "%" : "-"}
              </p>
            </div>
            <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4 text-center">
              <p className="text-xs text-gray-400 uppercase tracking-wide">総賭け金</p>
              <p className="text-2xl font-bold mt-1 text-gray-700">
                {totalStake.toLocaleString()}円
              </p>
            </div>
            <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4 text-center">
              <p className="text-xs text-gray-400 uppercase tracking-wide">総払戻</p>
              <p className={`text-2xl font-bold mt-1 ${totalPayout >= totalStake ? "text-green-600" : "text-gray-500"}`}>
                {totalPayout.toLocaleString()}円
              </p>
            </div>
            <div className="rounded-xl bg-white ring-1 ring-gray-200 p-4 text-center">
              <p className="text-xs text-gray-400 uppercase tracking-wide">総賭け数</p>
              <p className="text-2xl font-bold mt-1 text-gray-700">
                {results.reduce((s, r) => s + r.bet_count, 0)}回
              </p>
            </div>
          </div>

          {/* 式別内訳 */}
          <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
              <p className="text-sm font-semibold text-gray-700">式別内訳</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">式別</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">レース数</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">賭け数</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">的中率</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">平均オッズ</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">ROI</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">MDD</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {results.map((r) => {
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    const bt = r.bet_types as any;
                    const roi = Number(r.roi) * 100;
                    return (
                      <tr key={r.id} className="hover:bg-gray-50">
                        <td className="px-4 py-2.5 font-medium text-gray-900">{bt?.name ?? "-"}</td>
                        <td className="px-4 py-2.5 text-right text-gray-500">{r.race_count}</td>
                        <td className="px-4 py-2.5 text-right text-gray-500">{r.bet_count}</td>
                        <td className="px-4 py-2.5 text-right text-gray-500">
                          {(Number(r.hit_rate) * 100).toFixed(1)}%
                        </td>
                        <td className="px-4 py-2.5 text-right text-gray-500">
                          {r.avg_odds != null ? Number(r.avg_odds).toFixed(1) : "-"}倍
                        </td>
                        <td className={`px-4 py-2.5 text-right font-semibold ${roi > 0 ? "text-green-600" : "text-gray-400"}`}>
                          {roi > 0 ? "+" : ""}{roi.toFixed(1)}%
                        </td>
                        <td className="px-4 py-2.5 text-right text-red-400">
                          {r.max_drawdown != null ? `-${(Number(r.max_drawdown) * 100).toFixed(1)}%` : "-"}
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

      {/* 賭けログ（直近50件） */}
      {bets && bets.length > 0 && (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
            <p className="text-sm font-semibold text-gray-700">賭けログ</p>
            <span className="text-xs text-gray-400">全{totalBets}件中50件表示</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">レース</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">EV</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">賭け</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">払戻</th>
                  <th className="px-4 py-2 text-center text-xs font-semibold text-gray-500">的中</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {bets.map((b) => {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  const race = b.races as any;
                  const profit = Number(b.payout_amount) - Number(b.stake_amount);
                  return (
                    <tr key={b.id} className={`hover:bg-gray-50 ${b.is_hit ? "bg-green-50/30" : ""}`}>
                      <td className="px-4 py-2.5 text-gray-700">
                        <span className={`text-xs font-medium ${race?.track_type === "芝" ? "text-green-600" : "text-amber-600"}`}>
                          {race?.track_type}
                        </span>
                        <span className="text-gray-400 ml-1">{race?.distance_m}m</span>
                        <span className="text-gray-500 ml-2">{race?.racecourses?.short_name}{race?.race_number}R</span>
                        {race?.race_date && <span className="text-gray-400 ml-1">({race.race_date})</span>}
                      </td>
                      <td className={`px-4 py-2.5 text-right text-xs ${(b.edge_value ?? 0) > 0 ? "text-green-600" : "text-gray-400"}`}>
                        {b.edge_value != null ? (Number(b.edge_value) > 0 ? "+" : "") + Number(b.edge_value).toFixed(2) : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-500">{Number(b.stake_amount).toLocaleString()}円</td>
                      <td className={`px-4 py-2.5 text-right font-medium ${profit >= 0 ? "text-green-600" : "text-gray-400"}`}>
                        {profit >= 0 ? "+" : ""}{profit.toLocaleString()}円
                      </td>
                      <td className="px-4 py-2.5 text-center">
                        {b.is_hit ? <span className="text-green-600 font-bold">✓</span> : <span className="text-gray-300">✗</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
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
    </div>
  );
}
