import { AppHeader } from "@/components/app-header";
import { RequireAuth } from "@/components/auth/require-auth";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <div className="flex min-h-full flex-1 flex-col">
        <AppHeader />
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">{children}</main>
      </div>
    </RequireAuth>
  );
}
