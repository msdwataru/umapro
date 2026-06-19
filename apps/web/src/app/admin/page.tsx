import { createClient } from "@/lib/supabase/server";

async function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-xl bg-white ring-1 ring-gray-200 p-5">
      <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-bold text-gray-900 mt-1">{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

export default async function AdminDashboardPage() {
  const supabase = await createClient();

  const [
    { count: pendingUsers },
    { count: totalRaces },
    { count: totalPredictions },
    { data: recentJobs },
    { data: recentLogs },
  ] = await Promise.all([
    supabase.from("user_profiles").select("*", { count: "exact", head: true }).eq("status", "pending"),
    supabase.from("races").select("*", { count: "exact", head: true }),
    supabase.from("model_predictions").select("*", { count: "exact", head: true }),
    supabase.from("job_runs").select("id, job_name, status, started_at, finished_at, error_summary").order("started_at", { ascending: false }).limit(5),
    supabase.from("system_logs").select("id, level, message, created_at").order("created_at", { ascending: false }).limit(5),
  ]);

  const statusColor: Record<string, string> = {
    success: "text-green-600",
    running: "text-blue-600",
    failed: "text-red-600",
    pending: "text-yellow-600",
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">管理ダッシュボード</h1>

      {/* KPI */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="承認待ちユーザー" value={pendingUsers ?? 0} sub="要対応" />
        <StatCard label="総レース数" value={totalRaces ?? 0} />
        <StatCard label="総予測数" value={totalPredictions ?? 0} />
        <StatCard label="本日" value={new Date().toLocaleDateString("ja-JP")} />
      </div>

      <div className="grid sm:grid-cols-2 gap-6">
        {/* 直近ジョブ */}
        <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
            <p className="text-sm font-semibold text-gray-700">直近ジョブ実行</p>
            <a href="/admin/sync" className="text-xs text-indigo-600 hover:underline">詳細 →</a>
          </div>
          {!recentJobs || recentJobs.length === 0 ? (
            <p className="text-sm text-gray-400 p-4">実行履歴なし</p>
          ) : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-gray-50">
                {recentJobs.map((job) => (
                  <tr key={job.id}>
                    <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{job.job_name}</td>
                    <td className={`px-4 py-2.5 text-xs font-medium ${statusColor[job.status] ?? "text-gray-400"}`}>{job.status}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-400 text-right">
                      {job.started_at ? new Date(job.started_at).toLocaleString("ja-JP") : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* 直近ログ */}
        <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
            <p className="text-sm font-semibold text-gray-700">システムログ</p>
            <a href="/admin/logs" className="text-xs text-indigo-600 hover:underline">詳細 →</a>
          </div>
          {!recentLogs || recentLogs.length === 0 ? (
            <p className="text-sm text-gray-400 p-4">ログなし</p>
          ) : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-gray-50">
                {recentLogs.map((log) => (
                  <tr key={log.id}>
                    <td className={`px-4 py-2.5 text-xs font-medium ${log.level === "error" ? "text-red-600" : log.level === "warn" ? "text-yellow-600" : "text-gray-400"}`}>
                      {log.level}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-700 truncate max-w-[200px]">{log.message}</td>
                    <td className="px-4 py-2.5 text-xs text-gray-400 text-right">
                      {new Date(log.created_at).toLocaleString("ja-JP")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
