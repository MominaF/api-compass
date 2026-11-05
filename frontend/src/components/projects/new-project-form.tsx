"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAuth } from "@/components/auth/auth-provider";
import { FormField } from "@/components/form-field";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { createProject } from "@/lib/api";

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
    mutationFn: createProject,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects", user?.id] });
      // Next.js keeps visited pages mounted, so clear the form for the next project.
      reset();
      router.push("/dashboard");
    },
  });

  return (
    <form
      onSubmit={handleSubmit((values) => create.mutate(values))}
      noValidate
      className="flex flex-col gap-4"
    >
      <FormField id="name" label="Project name" error={errors.name?.message}>
        <Input
          id="name"
          placeholder="Bookstore API"
          aria-invalid={!!errors.name}
          {...register("name")}
        />
      </FormField>
      <FormField id="description" label="Description (optional)" error={errors.description?.message}>
        <Textarea
          id="description"
          rows={4}
          aria-invalid={!!errors.description}
          {...register("description")}
        />
      </FormField>
      {create.error && (
        <p role="alert" className="text-sm text-destructive">
          {create.error.message}
        </p>
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
