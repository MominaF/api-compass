"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAuth } from "@/components/auth/auth-provider";
import { FormField } from "@/components/form-field";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createProject, uploadSpec, type Project } from "@/lib/api";
import { SPEC_FILE_TYPES, specFileError } from "@/lib/spec-file";

// Matches the limits the API enforces.
const schema = z.object({
  name: z.string().trim().min(1, "Enter a project name.").max(120, "Use 120 characters or fewer."),
  description: z.string().trim().max(2000, "Use 2,000 characters or fewer."),
});
type Values = z.infer<typeof schema>;

export function NewProjectForm() {
  const router = useRouter();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  // Set once the project exists, so retrying a failed upload doesn't create a second project.
  const [created, setCreated] = useState<Project | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", description: "" },
  });

  const create = useMutation({
    mutationFn: async (values: Values) => {
      const project = created ?? (await createProject(values));
      setCreated(project);
      if (file) await uploadSpec(project.id, file);
      return project;
    },
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: ["projects", user?.id] });
      // Next.js keeps visited pages mounted, so clear the form for the next project.
      reset();
      setFile(null);
      setCreated(null);
      router.push(`/projects/${project.id}`);
    },
  });

  return (
    <form
      onSubmit={handleSubmit((values) => {
        if (!fileError) create.mutate(values);
      })}
      noValidate
      className="flex flex-col gap-4"
    >
      <FormField id="name" label="Project name" error={errors.name?.message}>
        <Input
          id="name"
          placeholder="Bookstore API"
          aria-invalid={!!errors.name}
          disabled={created !== null}
          {...register("name")}
        />
      </FormField>
      <FormField id="description" label="Description (optional)" error={errors.description?.message}>
        <Textarea
          id="description"
          rows={4}
          aria-invalid={!!errors.description}
          disabled={created !== null}
          {...register("description")}
        />
      </FormField>
      <FormField id="spec" label="OpenAPI file (optional)" error={fileError ?? undefined}>
        <Input
          id="spec"
          type="file"
          accept={SPEC_FILE_TYPES}
          aria-invalid={!!fileError}
          onChange={(event) => {
            const chosen = event.target.files?.[0] ?? null;
            setFile(chosen);
            setFileError(chosen && specFileError(chosen));
          }}
        />
        <p className="text-sm text-muted-foreground">
          OpenAPI 3.0, 3.1 or 3.2 in JSON or YAML, up to 5 MB. You can also add this later.
        </p>
      </FormField>
      {create.error && (
        <div role="alert" className="flex flex-col gap-1 text-sm text-destructive">
          <p>{create.error.message}</p>
          {created && (
            <p>
              The project was created, but the file wasn&apos;t imported. Try again, or{" "}
              <Link href={`/projects/${created.id}`} className="underline underline-offset-4">
                open the project
              </Link>
              .
            </p>
          )}
        </div>
      )}
      <div className="flex gap-2">
        <Button type="submit" size="lg" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create project"}
        </Button>
        <Link href="/dashboard" className={buttonVariants({ variant: "outline", size: "lg" })}>
          Cancel
        </Link>
      </div>
    </form>
  );
}
