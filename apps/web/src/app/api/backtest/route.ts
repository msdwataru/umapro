import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();

  const { data, error } = await supabase
    .from("backtest_runs")
    .insert({
      user_id: user.id,
      run_name: body.run_name ?? null,
      status: "queued",
      parameters_json: body.parameters,
    })
    .select("id")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // TODO: バッチサーバーへ実行リクエストを送信

  return NextResponse.json({ run_id: data.id }, { status: 202 });
}
