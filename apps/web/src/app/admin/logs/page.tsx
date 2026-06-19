import { createClient } from "@/lib/supabase/server";

export default async function LogsPage() {
  const supabase = await createClient();

  const { data: logs } = await supabase
    .from("system_logs")
    .select("id, level, event_type, message, context_json, occurred_at, job_run_id")
    .order("occurred_at", { ascending: false })
    .limit(200);

  const levelStyle: Record<string, string> = {
    error: "text-red-700 bg-red-50 ring-red-200",
    warn: "text-yellow-700 bg-yellow-50 ring-yellow-200",
    info: "text-blue-700 bg-blue-50 ring-blue-200",
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">システムログ</h1>

      <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
          <p className="text-sm font-semibold text-gray-700">直近200件</p>
          <span className="text-xs text-gray-400">{logs?.length ?? 0}件</span>
        </div>
        {(!logs || logs.length === 0) ? (
          <p className="text-sm text-gray-400 text-center py-10">ログがありません</p>
        ) : (
          <div className="divide-y divide-gray-50">
            {logs.map((log) => {
              const style = levelStyle[log.level] ?? levelStyle.info;
              return (
                <div key={log.id} className="px-4 py-3 flex gap-3 items-start hover:bg-gray-50">
                  <span className={`mt-0.5 shrink-0 text-xs font-semibold px-1.5 py-0.5 rounded ring-1 ${style}`}>
                    {log.level}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      {log.event_type && (
                        <span className="text-xs font-mono text-gray-400">{log.event_type}</span>
                      )}
                      {log.job_run_id && (
                        <span className="text-xs text-gray-300">job:{log.job_run_id}</span>
                      )}
                      <p className="text-sm text-gray-800">{log.message}</p>
                    </div>
                    {log.context_json && (
                      <pre className="mt-1 text-xs text-gray-400 font-mono whitespace-pre-wrap break-all">
                        {typeof log.context_json === "string"
                          ? log.context_json
                          : JSON.stringify(log.context_json, null, 2)}
                      </pre>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-gray-400">
                    {new Date(log.occurred_at).toLocaleString("ja-JP")}
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
