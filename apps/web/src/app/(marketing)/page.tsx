import Link from "next/link";

export default function TopPage() {
  return (
    <main className="min-h-screen bg-gray-50">
      {/* ヘッダー */}
      <header className="bg-white border-b border-gray-100">
        <div className="mx-auto max-w-6xl px-4 h-14 flex items-center justify-between">
          <span className="font-bold text-gray-900 tracking-tight">umapro</span>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-gray-600 hover:text-gray-900">ログイン</Link>
            <Link
              href="/register"
              className="text-sm bg-indigo-600 text-white px-4 py-1.5 rounded-full hover:bg-indigo-700 transition-colors"
            >
              登録申請
            </Link>
          </div>
        </div>
      </header>

      {/* ヒーロー */}
      <section className="py-20 px-4 text-center">
        <p className="text-xs font-semibold text-indigo-600 uppercase tracking-widest mb-4">
          期待値ベースの競馬分析
        </p>
        <h1 className="text-4xl sm:text-5xl font-bold text-gray-900 leading-tight">
          データが示す<br />
          <span className="text-indigo-600">本当の狙い目</span>を掴む
        </h1>
        <p className="mt-6 text-lg text-gray-500 max-w-xl mx-auto">
          AIモデルによるオッズ比較・期待値算出で、
          感覚ではなく数字にもとづいた馬券購入の判断をサポートします。
        </p>
        <div className="mt-8 flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/register"
            className="rounded-full bg-indigo-600 text-white px-8 py-3 font-semibold hover:bg-indigo-700 transition-colors"
          >
            利用申請する
          </Link>
          <Link
            href="/login"
            className="rounded-full bg-white text-gray-700 px-8 py-3 font-semibold ring-1 ring-gray-200 hover:bg-gray-50 transition-colors"
          >
            ログイン
          </Link>
        </div>
        <p className="mt-4 text-xs text-gray-400">管理者承認後にご利用いただけます</p>
      </section>

      {/* 特徴 */}
      <section className="py-16 px-4 bg-white border-t border-gray-100">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-2xl font-bold text-gray-900 mb-12">主な機能</h2>
          <div className="grid sm:grid-cols-3 gap-8">
            {[
              {
                icon: "📊",
                title: "期待値（EV）算出",
                desc: "モデルの予測確率とオッズを比較し、EV（期待値）をリアルタイムで表示。プラスEVの馬だけを素早く絞り込めます。",
              },
              {
                icon: "🔍",
                title: "条件分析",
                desc: "コース・距離・クラス・馬場状態ごとにEVの傾向を集計。得意条件・不得意条件を一目で把握できます。",
              },
              {
                icon: "🧪",
                title: "バックテスト",
                desc: "過去データで自分の戦略をシミュレーション。ROI・最大ドローダウンなど詳細なパフォーマンス指標を確認できます。",
              },
            ].map((f) => (
              <div key={f.title} className="text-center">
                <div className="text-4xl mb-3">{f.icon}</div>
                <h3 className="font-semibold text-gray-900 mb-2">{f.title}</h3>
                <p className="text-sm text-gray-500 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* フロー */}
      <section className="py-16 px-4">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-10">ご利用の流れ</h2>
          <div className="space-y-6 text-left">
            {[
              { step: "01", title: "利用申請", desc: "メールアドレスと表示名でアカウントを作成します。" },
              { step: "02", title: "管理者承認", desc: "申請内容を確認後、管理者がアカウントを承認します。" },
              { step: "03", title: "ご利用開始", desc: "承認後すぐにすべての機能をご利用いただけます。" },
            ].map((s) => (
              <div key={s.step} className="flex gap-5 items-start">
                <span className="text-2xl font-bold text-indigo-200 shrink-0 w-10">{s.step}</span>
                <div>
                  <p className="font-semibold text-gray-900">{s.title}</p>
                  <p className="text-sm text-gray-500 mt-0.5">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-10">
            <Link
              href="/register"
              className="rounded-full bg-indigo-600 text-white px-8 py-3 font-semibold hover:bg-indigo-700 transition-colors"
            >
              利用申請する
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-gray-100 py-6 text-center text-xs text-gray-400">
        umapro &copy; 2026 &nbsp;|&nbsp; 馬券の購入はご自身の判断と責任のもとで行ってください
      </footer>
    </main>
  );
}
