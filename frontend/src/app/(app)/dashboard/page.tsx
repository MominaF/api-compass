import type { Metadata } from "next";
import Link from "next/link";

import { ProjectList } from "@/components/projects/project-list";
import { SystemStatus } from "@/components/system-status";
import { buttonVariants } from "@/components/ui/button";

export const metadata: Metadata = { title: "Dashboard · API COMPASS" };

export default function DashboardPage() {
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">Your API projects.</p>
        </div>
        <Link href="/projects/new" className={buttonVariants({ size: "lg" })}>
          New project
        </Link>
      </div>
      <div className="mt-8">
        <ProjectList />
      </div>
      <div className="mt-10 grid gap-6 md:grid-cols-2">
        <SystemStatus />
      </div>
    </>
  );
}
