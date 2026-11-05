import type { Metadata } from "next";

import { ProjectWorkspace } from "@/components/projects/project-workspace";

export const metadata: Metadata = { title: "Project · API COMPASS" };

export default function ProjectPage() {
  return <ProjectWorkspace />;
}
