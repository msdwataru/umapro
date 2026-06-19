import { createClient } from "@/lib/supabase/server";
import Link from "next/link";
import { redirect } from "next/navigation";

async function createBacktestRun(formData: FormData) {
  "use server";
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) return;

  const params = {
    track_type: formData.get("track_type") as string,
    distance_min: Number(formData.get("distance_min")),
    distance_max: Number(formData.get("distance_max")),
    ev_threshold: Number(formData.get("ev_threshold")),
    date_from: formData.get("date_from") as string,
    date_to: formData.get("date_to") as string,
  };

  const { data } = await supabase
    .from("backtest_runs")
    .insert({
      user_id: user.id,
      run_name: formData.get("run_name") as string || `バックテスト ${new Date().toLocaleDateString("ja-JP")}`,
      status: "queued",
      parameters_json: params,
    })
    .select("id")
    .single();

  if (data) redirect(`/backtest/${data.id}`);
}

export default async function BacktestPage() {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  const { data: runs } = await supabase
    .from("backtest_runs")
    .select("id, run_name, status, created_at, started_at, finished_at, parameters_json")
    .eq("user_id", user!.id)
    .order("created_at", { ascending: false })
    .limit(20);

  const statusColor: Record<string, string> = {
    queued: "text-yellow-600 bg-yellow-50",
    running: "text-blue-600 bg-blue-50",
    completed: "text-green-600 bg-green-50",
    failed: "text-red-600 bg-red-50",
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">バックテスト</h1>

      {/* 新規作成フォーム */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 p-5">
        <p className="text-sm font-semibold text-gray-700 mb-4">新規バックテスト</p>
        <form action={createBacktestRun} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">名前</label>
              <input
                name="run_name"
                type="text"
                placeholder="例: 芝1600m EV>0.1"
                className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">コース</label>
              <select
                name="track_type"
                className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              >
                <option value="">すべて</option>
                <option value="芝">芝</option>
                <option value="ダート">ダート</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">距離（下限m）</label>
              <input
                name="distance_min"
                type="number"
                defaultValue={1000}
                step={100}
                className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">距離（上限m）</label>
              <input
                name="distance_max"
                type="number"
                defaultValue={3600}
                step={100}
                className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">EV閾値（以上を買い）</label>
              <input
                name="ev_threshold"
                type="number"
                defaultValue={0.0}
                step={0.05}
                className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div className="sm:col-span-1" />
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">開始日</label>
              <input
                name="date_from"
                type="date"
                className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">終了日</label>
              <input
                name="date_to"
                type="date"
                className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
              />
            </div>
          </div>
          <div className="pt-2">
            <button
              type="submit"
              className="rounded-md bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              バックテスト実行
            </button>
            <p className="text-xs text-gray-400 mt-2">
              バッチ処理でバックグラウンド実行されます。結果は数分後に確認できます。
            </p>
          </div>
        </form>
      </div>

      {/* 実行履歴 */}
      <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50">
          <p className="text-sm font-semibold text-gray-700">実行履歴</p>
        </div>
        {(!runs || runs.length === 0) ? (
          <p className="text-sm text-gray-400 text-center py-10">実行履歴がありません</p>
        ) : (
          <div className="divide-y divide-gray-50">
            {runs.map((run) => {
              const params = run.parameters_json as Record<string, unknown> | null;
              const cls = statusColor[run.status] ?? "text-gray-400 bg-gray-50";
              return (
                <div key={run.id} className="px-4 py-3 flex items-center gap-3 hover:bg-gray-50">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/backtest/${run.id}`}
                        className="font-medium text-gray-900 hover:text-indigo-600 text-sm"
                      >
                        {run.run_name ?? `Run #${run.id}`}
                      </Link>
                      <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${cls}`}>
                        {run.status}
                      </span>
                    </div>
                    {params && (
                      <p className="text-xs text-gray-400 mt-0.5">
                        {[
                          params.track_type && String(params.track_type),
                          params.distance_min && `${params.distance_min}〜${params.distance_max}m`,
                          params.ev_threshold != null && `EV≥${params.ev_threshold}`,
                          params.date_from && `${params.date_from}〜${params.date_to}`,
                        ].filter(Boolean).join(" / ")}
                      </p>
                    )}
                  </div>
                  <span className="text-xs text-gray-400 shrink-0">
                    {new Date(run.created_at).toLocaleDateString("ja-JP")}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
