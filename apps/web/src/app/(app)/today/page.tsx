import { createClient } from "@/lib/supabase/server";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";

function trackLabel(type: string) {
  return type === "芝" ? "芝" : "ダ";
}

function statusBadge(status: string) {
  const map: Record<string, { label: string; variant: "blue" | "green" | "gray" | "yellow" }> = {
    scheduled: { label: "発走前", variant: "blue" },
    open: { label: "発走前", variant: "blue" },
    closed: { label: "締切", variant: "yellow" },
    result_fixed: { label: "確定", variant: "green" },
  };
  return map[status] ?? { label: status, variant: "gray" };
}

export default async function TodayPage() {
  const supabase = await createClient();
  const today = new Date().toISOString().split("T")[0];

  const { data: races } = await supabase
    .from("races")
    .select(`
      id, race_date, race_number, race_name, track_type, distance_m,
      class_name, going, field_size, scheduled_start_at, status,
      racecourses ( name, short_name ),
      race_entries ( id, model_predictions ( prediction_rank, edge_value, prediction_target ) )
    `)
    .eq("race_date", today)
    .order("scheduled_start_at", { ascending: true });

  // 期待値スコアが存在するレースを「注目レース」とする
  const highlighted = races?.filter((r) =>
    r.race_entries?.some((e) =>
      e.model_predictions?.some(
        (p) => p.prediction_target === "win" && p.prediction_rank === 1 && (p.edge_value ?? 0) > 0
      )
    )
  ) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-bold text-gray-900">
          今日の推奨レース
          <span className="ml-2 text-sm font-normal text-gray-400">{today}</span>
        </h1>
        {races && races.length > 0 && (
          <span className="text-sm text-gray-500">{races.length} レース</span>
        )}
      </div>

      {(!races || races.length === 0) ? (
        <EmptyState date={today} />
      ) : (
        <div className="space-y-8">
          {highlighted.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-indigo-700 uppercase tracking-wide mb-3">
                注目レース（期待値プラス）
              </h2>
              <RaceGrid races={highlighted} />
            </section>
          )}
          <section>
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
              全レース
            </h2>
            <RaceGrid races={races} />
          </section>
        </div>
      )}
    </div>
  );
}

type Race = Awaited<ReturnType<typeof import("@/lib/supabase/server").createClient>>["from"] extends
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  any ? any : never;

function RaceGrid({ races }: { races: Race[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {races.map((race: Race) => {
        const { label, variant } = statusBadge(race.status);
        const hasPrediction = race.race_entries?.some((e: Race) =>
          e.model_predictions?.length > 0
        );
        return (
          <Link
            key={race.id}
            href={`/races/${race.id}`}
            className="group rounded-xl bg-white p-4 ring-1 ring-gray-200 hover:ring-indigo-300 hover:shadow-sm transition-all"
          >
            <div className="flex items-start justify-between mb-2">
              <div>
                <span className="text-xs text-gray-400">
                  {(race.racecourses as Race)?.short_name} {race.race_number}R
                </span>
                <p className="font-semibold text-gray-900 text-sm leading-tight mt-0.5 group-hover:text-indigo-700 transition-colors">
                  {race.race_name ?? `${race.race_number}R`}
                </p>
              </div>
              <Badge variant={variant}>{label}</Badge>
            </div>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <span className={`font-medium ${race.track_type === "芝" ? "text-green-600" : "text-amber-600"}`}>
                {trackLabel(race.track_type)}
              </span>
              <span>{race.distance_m}m</span>
              {race.going && <span>({race.going})</span>}
              <span className="ml-auto">{race.field_size}頭</span>
            </div>
            {race.scheduled_start_at && (
              <p className="mt-1 text-xs text-gray-400">
                {new Date(race.scheduled_start_at).toLocaleTimeString("ja-JP", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                発走
              </p>
            )}
            {hasPrediction && (
              <div className="mt-2 pt-2 border-t border-gray-100">
                <span className="text-xs text-indigo-600 font-medium">予測データあり</span>
              </div>
            )}
          </Link>
        );
      })}
    </div>
  );
}

function EmptyState({ date }: { date: string }) {
  return (
    <div className="rounded-xl bg-white ring-1 ring-gray-200 p-12 text-center">
      <p className="text-4xl mb-4">🏁</p>
      <p className="font-semibold text-gray-700">本日（{date}）の開催はありません</p>
      <p className="text-sm text-gray-400 mt-1">
        レース情報は開催日の朝以降に表示されます
      </p>
      <Link
        href="/races"
        className="mt-4 inline-block text-sm text-indigo-600 hover:underline"
      >
        過去レース一覧を見る →
      </Link>
    </div>
  );
}
