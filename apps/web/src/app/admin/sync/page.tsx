import { createClient } from "@/lib/supabase/server";

export default async function SyncPage() {
  const supabase = await createClient();

  const { data: jobs } = await supabase
    .from("job_runs")
    .select("id, job_name, status, started_at, finished_at, records_processed, error_summary")
    .order("started_at", { ascending: false })
    .limit(50);

  const statusColor: Record<string, string> = {
    success: "text-green-600 bg-green-50",
    running: "text-blue-600 bg-blue-50",
    failed: "text-red-600 bg-red-50",
    pending: "text-yellow-600 bg-yellow-50",
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">データ同期管理</h1>

      <div className="rounded-xl bg-yellow-50 ring-1 ring-yellow-200 px-4 py-3 text-sm text-yellow-800">
        バッチジョブは Python バッチ（<code className="font-mono">apps/batch/</code>）から実行されます。このページはジョブ実行履歴の確認専用です。
      </div>

      <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
          <p className="text-sm font-semibold text-gray-700">ジョブ実行履歴</p>
          <span className="text-xs text-gray-400">{jobs?.length ?? 0}件</span>
        </div>
        {(!jobs || jobs.length === 0) ? (
          <p className="text-sm text-gray-400 text-center py-10">実行履歴がありません</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">ジョブ名</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">ステータス</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">開始時刻</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">終了時刻</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-gray-500">処理件数</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-gray-500">エラー</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {jobs.map((job) => {
                  const cls = statusColor[job.status] ?? "text-gray-400 bg-gray-50";
                  const duration = job.started_at && job.finished_at
                    ? Math.round((new Date(job.finished_at).getTime() - new Date(job.started_at).getTime()) / 1000)
                    : null;
                  return (
                    <tr key={job.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-700">{job.job_name}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
                          {job.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-500">
                        {job.started_at ? new Date(job.started_at).toLocaleString("ja-JP") : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-500">
                        {job.finished_at
                          ? `${new Date(job.finished_at).toLocaleString("ja-JP")}${duration != null ? ` (${duration}s)` : ""}`
                          : "-"}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-gray-500 text-right">
                        {job.records_processed ?? "-"}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-red-500 max-w-[200px] truncate">
                        {job.error_summary ?? "-"}
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
