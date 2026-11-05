import type { Metadata } from "next";

import { NewProjectForm } from "@/components/projects/new-project-form";

export const metadata: Metadata = { title: "New project · API COMPASS" };

export default function NewProjectPage() {
  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-2xl font-semibold tracking-tight">New project</h1>
      <p className="mt-1 mb-6 text-muted-foreground">A project represents one API.</p>
      <NewProjectForm />
    </div>
  );
}
