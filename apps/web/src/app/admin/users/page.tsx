import { createClient } from "@/lib/supabase/server";
import { revalidatePath } from "next/cache";
import { Badge } from "@/components/ui/badge";

async function approveUser(formData: FormData) {
  "use server";
  const supabase = await createClient();
  const userId = formData.get("userId") as string;
  await supabase.from("user_profiles").update({ status: "approved" }).eq("id", userId);
  revalidatePath("/admin/users");
}

async function rejectUser(formData: FormData) {
  "use server";
  const supabase = await createClient();
  const userId = formData.get("userId") as string;
  await supabase.from("user_profiles").update({ status: "rejected" }).eq("id", userId);
  revalidatePath("/admin/users");
}

export default async function UsersPage() {
  const supabase = await createClient();

  const { data: users } = await supabase
    .from("user_profiles")
    .select("id, display_name, role, status, created_at, last_login_at")
    .order("created_at", { ascending: false });

  const statusBadge = (status: string) => {
    const map: Record<string, { label: string; variant: "green" | "blue" | "red" | "gray" | "yellow" }> = {
      pending: { label: "承認待ち", variant: "yellow" },
      approved: { label: "承認済み", variant: "green" },
      rejected: { label: "拒否", variant: "red" },
    };
    return map[status] ?? { label: status, variant: "gray" };
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">会員管理</h1>
        <span className="text-sm text-gray-400">{users?.length ?? 0}件</span>
      </div>

      <div className="rounded-xl bg-white ring-1 ring-gray-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">表示名</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">ロール</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">ステータス</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">登録日</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">最終ログイン</th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {users?.map((user) => {
                const { label, variant } = statusBadge(user.status);
                return (
                  <tr key={user.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">{user.display_name ?? "-"}</td>
                    <td className="px-4 py-3 text-gray-500">{user.role}</td>
                    <td className="px-4 py-3"><Badge variant={variant}>{label}</Badge></td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {user.created_at ? new Date(user.created_at).toLocaleDateString("ja-JP") : "-"}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">
                      {user.last_login_at ? new Date(user.last_login_at).toLocaleDateString("ja-JP") : "-"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        {user.status === "pending" && (
                          <>
                            <form action={approveUser}>
                              <input type="hidden" name="userId" value={user.id} />
                              <button
                                type="submit"
                                className="text-xs px-2.5 py-1 rounded-md bg-green-600 text-white hover:bg-green-700"
                              >
                                承認
                              </button>
                            </form>
                            <form action={rejectUser}>
                              <input type="hidden" name="userId" value={user.id} />
                              <button
                                type="submit"
                                className="text-xs px-2.5 py-1 rounded-md bg-red-100 text-red-700 hover:bg-red-200"
                              >
                                拒否
                              </button>
                            </form>
                          </>
                        )}
                        {user.status === "approved" && (
                          <form action={rejectUser}>
                            <input type="hidden" name="userId" value={user.id} />
                            <button
                              type="submit"
                              className="text-xs px-2.5 py-1 rounded-md bg-gray-100 text-gray-600 hover:bg-gray-200"
                            >
                              停止
                            </button>
                          </form>
                        )}
                        {user.status === "rejected" && (
                          <form action={approveUser}>
                            <input type="hidden" name="userId" value={user.id} />
                            <button
                              type="submit"
                              className="text-xs px-2.5 py-1 rounded-md bg-indigo-100 text-indigo-700 hover:bg-indigo-200"
                            >
                              再承認
                            </button>
                          </form>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {(!users || users.length === 0) && (
          <p className="text-sm text-gray-400 text-center py-8">ユーザーなし</p>
        )}
      </div>
    </div>
  );
}
