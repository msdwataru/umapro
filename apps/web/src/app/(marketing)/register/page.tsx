"use client";

import { useActionState } from "react";
import Link from "next/link";
import { signUp } from "@/app/actions/auth";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function RegisterPage() {
  const [state, action, pending] = useActionState(signUp, null);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900">UMA</h1>
          <p className="mt-1 text-sm text-gray-500">期待値ベースの競馬分析</p>
        </div>

        <div className="rounded-xl bg-white p-8 shadow-sm ring-1 ring-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 mb-6">新規登録</h2>

          <form action={action} className="space-y-4">
            <Input
              id="display_name"
              name="display_name"
              type="text"
              label="表示名"
              placeholder="ニックネーム"
              required
            />
            <Input
              id="email"
              name="email"
              type="email"
              label="メールアドレス"
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
            <Input
              id="password"
              name="password"
              type="password"
              label="パスワード（8文字以上）"
              placeholder="••••••••"
              autoComplete="new-password"
              minLength={8}
              required
            />

            {state?.error && (
              <p className="text-sm text-red-600 bg-red-50 rounded-md px-3 py-2">
                {state.error}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={pending}>
              {pending ? "登録中..." : "アカウントを作成"}
            </Button>
          </form>
        </div>

        <p className="text-center text-sm text-gray-500">
          すでにアカウントをお持ちの方は{" "}
          <Link href="/login" className="text-indigo-600 hover:underline font-medium">
            ログイン
          </Link>
        </p>
      </div>
    </div>
  );
}
