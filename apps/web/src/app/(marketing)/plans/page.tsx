import Link from "next/link";

export default function PlansPage() {
  return (
    <main className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-100">
        <div className="mx-auto max-w-6xl px-4 h-14 flex items-center justify-between">
          <Link href="/" className="font-bold text-gray-900">UMA</Link>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-gray-600 hover:text-gray-900">ログイン</Link>
            <Link
              href="/register"
              className="text-sm bg-indigo-600 text-white px-4 py-1.5 rounded-full hover:bg-indigo-700"
            >
              登録申請
            </Link>
          </div>
        </div>
      </header>

      <section className="py-20 px-4 text-center">
        <h1 className="text-3xl font-bold text-gray-900">ご利用案内</h1>
        <p className="mt-3 text-gray-500">UMA は現在クローズドベータとして運営しています</p>

        <div className="mt-12 mx-auto max-w-sm">
          <div className="rounded-2xl bg-white ring-1 ring-indigo-200 p-8 text-left shadow-sm">
            <div className="text-center mb-6">
              <p className="text-xs font-semibold text-indigo-600 uppercase tracking-widest">招待制</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">無料</p>
              <p className="text-sm text-gray-400 mt-1">管理者承認後に全機能が利用可能</p>
            </div>
            <ul className="space-y-3 text-sm text-gray-700">
              {[
                "今日の推奨レース",
                "レース一覧・詳細",
                "馬詳細・AI予測根拠",
                "コース×距離 条件分析",
                "バックテスト（期間・条件自由設定）",
                "お気に入り・保存フィルタ",
              ].map((f) => (
                <li key={f} className="flex items-center gap-2">
                  <span className="text-green-500">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <div className="mt-8 text-center">
              <Link
                href="/register"
                className="block rounded-full bg-indigo-600 text-white px-6 py-2.5 font-semibold hover:bg-indigo-700 transition-colors"
              >
                利用申請する
              </Link>
            </div>
          </div>
        </div>

        <p className="mt-8 text-xs text-gray-400">
          申請後は管理者が内容を確認します。承認まで数日かかる場合があります。
        </p>
      </section>
    </main>
  );
}
