import { createClient } from "@/lib/supabase/server";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";

interface SearchParams {
  date?: string;
  venue?: string;
  track?: string;
}

export default async function RacesPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const supabase = await createClient();

  // フィルタ用に競馬場一覧取得
  const { data: racecourses } = await supabase
    .from("racecourses")
    .select("id, name, short_name")
    .eq("is_active", true)
    .order("id");

  // レース一覧クエリ
  let query = supabase
    .from("races")
    .select(`
      id, race_date, race_number, race_name, track_type, distance_m,
      class_name, going, field_size, scheduled_start_at, status,
      racecourses ( id, name, short_name )
    `)
    .order("race_date", { ascending: false })
    .order("scheduled_start_at", { ascending: true })
    .limit(100);

  if (params.date) query = query.eq("race_date", params.date);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if (params.venue) query = (query as any).eq("racecourse_id", parseInt(params.venue));
  if (params.track) query = query.eq("track_type", params.track);

  const { data: races } = await query;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">レース一覧</h1>

      {/* フィルタパネル */}
      <form method="get" className="rounded-xl bg-white ring-1 ring-gray-200 p-4 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1 min-w-[140px]">
          <label className="text-xs font-medium text-gray-600">日付</label>
          <input
            name="date"
            type="date"
            defaultValue={params.date}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          />
        </div>
        <div className="flex flex-col gap-1 min-w-[120px]">
          <label className="text-xs font-medium text-gray-600">開催場</label>
          <select
            name="venue"
            defaultValue={params.venue}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          >
            <option value="">すべて</option>
            {racecourses?.map((rc) => (
              <option key={rc.id} value={rc.id}>{rc.name}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-[100px]">
          <label className="text-xs font-medium text-gray-600">コース</label>
          <select
            name="track"
            defaultValue={params.track}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
          >
            <option value="">すべて</option>
            <option value="芝">芝</option>
            <option value="ダート">ダート</option>
          </select>
        </div>
        <button
          type="submit"
          className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
        >
          絞り込む
        </button>
        <Link href="/races" className="text-sm text-gray-400 hover:text-gray-600 py-1.5">
          リセット
        </Link>
      </form>

      {/* レース一覧 */}
      {(!races || races.length === 0) ? (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 p-10 text-center">
          <p className="text-gray-500">該当するレースがありません</p>
        </div>
      ) : (
        <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">日付</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">場</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">R</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">レース名</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">コース</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">頭数</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">状態</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {races.map((race) => {
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  const rc = race.racecourses as any;
                  const statusMap: Record<string, { label: string; variant: "blue" | "green" | "gray" | "yellow" }> = {
                    scheduled: { label: "発走前", variant: "blue" },
                    open: { label: "発走前", variant: "blue" },
                    closed: { label: "締切", variant: "yellow" },
                    result_fixed: { label: "確定", variant: "green" },
                  };
                  const s = statusMap[race.status] ?? { label: race.status, variant: "gray" as const };
                  return (
                    <tr key={race.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 text-gray-600">{race.race_date}</td>
                      <td className="px-4 py-3 font-medium text-gray-900">{rc?.short_name ?? "-"}</td>
                      <td className="px-4 py-3 text-gray-600">{race.race_number}</td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/races/${race.id}`}
                          className="font-medium text-gray-900 hover:text-indigo-600 transition-colors"
                        >
                          {race.race_name ?? `${race.race_number}R`}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`font-medium ${race.track_type === "芝" ? "text-green-600" : "text-amber-600"}`}>
                          {race.track_type}
                        </span>
                        <span className="text-gray-400 ml-1">{race.distance_m}m</span>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{race.field_size ?? "-"}頭</td>
                      <td className="px-4 py-3"><Badge variant={s.variant}>{s.label}</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-3 bg-gray-50 border-t border-gray-100 text-xs text-gray-400">
            {races.length}件表示
          </div>
        </div>
      )}
    </div>
  );
}
