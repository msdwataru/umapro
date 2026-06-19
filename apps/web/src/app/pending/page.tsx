import { signOut } from "@/app/actions/auth";
import { Button } from "@/components/ui/button";

export default function PendingPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md text-center space-y-6">
        <div className="text-5xl">🏇</div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">承認をお待ちください</h1>
          <p className="mt-3 text-gray-500 leading-relaxed">
            ご登録ありがとうございます。
            <br />
            管理者が承認するとご利用いただけます。
            <br />
            承認後にあらためてログインしてください。
          </p>
        </div>

        <div className="rounded-xl bg-white p-6 ring-1 ring-gray-200 text-left space-y-2">
          <p className="text-sm font-medium text-gray-700">承認までの流れ</p>
          <ol className="text-sm text-gray-500 space-y-1 list-decimal list-inside">
            <li>管理者がアカウントを確認</li>
            <li>承認後、登録メールアドレスへ通知</li>
            <li>ログインして全機能をご利用開始</li>
          </ol>
        </div>

        <form action={signOut}>
          <Button type="submit" variant="ghost" size="sm">
            ログアウト
          </Button>
        </form>
      </div>
    </div>
  );
}
