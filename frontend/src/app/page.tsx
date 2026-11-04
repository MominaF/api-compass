import { Compass } from "lucide-react";

import { SystemStatus } from "@/components/system-status";

export default function DashboardPage() {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4">
          <Compass className="size-5 text-primary" aria-hidden />
          <span className="font-semibold tracking-tight">API COMPASS</span>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-10">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-muted-foreground">
          Explore, understand, and test unfamiliar REST APIs from their OpenAPI specifications.
        </p>
        <div className="mt-8 grid gap-6 md:grid-cols-2">
          <SystemStatus />
        </div>
      </main>
    </div>
  );
}
