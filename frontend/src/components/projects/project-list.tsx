"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderPlus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { deleteProject, listProjects, type Project } from "@/lib/api";

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

function ProjectCard({ project, onDelete }: { project: Project; onDelete: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="break-words">{project.name}</CardTitle>
        <CardDescription>Created {dateFormat.format(new Date(project.created_at))}</CardDescription>
        <CardAction>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onDelete}
            aria-label={`Delete ${project.name}`}
          >
            <Trash2 />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col items-start gap-3">
        {project.description && (
          <p className="text-sm break-words whitespace-pre-wrap text-muted-foreground">
            {project.description}
          </p>
        )}
        <Badge variant="secondary">No spec uploaded</Badge>
      </CardContent>
    </Card>
  );
}

export function ProjectList() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const queryKey = ["projects", user?.id];
  const [pendingDelete, setPendingDelete] = useState<Project | null>(null);

  const { data, error, isPending, refetch } = useQuery({ queryKey, queryFn: listProjects });

  const remove = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: async () => {
      setPendingDelete(null);
      await queryClient.invalidateQueries({ queryKey });
    },
  });

  if (isPending) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading projects…
      </p>
    );
  }

  if (error) {
    return (
      <div role="alert" className="flex flex-col items-start gap-3">
        <p className="text-sm text-destructive">{error.message}</p>
        <Button variant="outline" onClick={() => void refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-8 text-center">
          <FolderPlus className="size-8 text-muted-foreground" aria-hidden />
          <div>
            <p className="font-medium">No projects yet</p>
            <p className="text-sm text-muted-foreground">Create a project for each API you work with.</p>
          </div>
          <Link href="/projects/new" className={buttonVariants()}>
            New project
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <ul className="grid gap-4 md:grid-cols-2">
        {data.map((project) => (
          <li key={project.id}>
            <ProjectCard
              project={project}
              onDelete={() => {
                remove.reset();
                setPendingDelete(project);
              }}
            />
          </li>
        ))}
      </ul>

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open && !remove.isPending) setPendingDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {pendingDelete?.name}?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the project and can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {remove.error && (
            <p role="alert" className="text-sm text-destructive">
              {remove.error.message}
            </p>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => pendingDelete && remove.mutate(pendingDelete.id)}
            >
              {remove.isPending ? "Deleting…" : "Delete project"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
