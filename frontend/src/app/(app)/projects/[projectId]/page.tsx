import type { Metadata } from "next";
import { Suspense } from "react";

import { ProjectWorkspace } from "@/components/projects/project-workspace";

export const metadata: Metadata = { title: "Project · API COMPASS" };

export default function ProjectPage() {
  return (
    <Suspense
      fallback={
        <p role="status" className="text-sm text-muted-foreground">
          Loading project…
        </p>
      }
    >
      <ProjectWorkspace />
    </Suspense>
  );
}
