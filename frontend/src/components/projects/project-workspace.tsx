"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useRef, useState, type ChangeEvent } from "react";

import { useAuth } from "@/components/auth/auth-provider";
import { SpecStatusBadge } from "@/components/projects/spec-status-badge";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ApiError,
  getProject,
  listOperations,
  listSpecs,
  uploadSpec,
  type OperationSummary,
  type Spec,
  type SpecSummary,
} from "@/lib/api";
import { SPEC_FILE_TYPES, specFileError } from "@/lib/spec-file";

const UNTAGGED = "Other";

/** A 422 means the ID in the URL isn't a valid UUID, so no such project can exist. */
function isMissingProject(error: unknown) {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

/** Groups by first tag only, so an operation with several tags is still listed once. */
function groupByTag(operations: OperationSummary[]) {
  const groups = new Map<string, OperationSummary[]>();
  for (const operation of operations) {
    const tag = operation.tags[0] ?? UNTAGGED;
    groups.set(tag, [...(groups.get(tag) ?? []), operation]);
  }
  return [...groups.entries()];
}

function SpecUpload({ projectId, hasSpec }: { projectId: string; hasSpec: boolean }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const upload = useMutation({
    mutationFn: (file: File) => uploadSpec(projectId, file),
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", projectId] }),
        queryClient.invalidateQueries({ queryKey: ["projects", user?.id] }),
      ]);
    },
  });

  function onFileChosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Let the user choose the same file again after fixing it.
    event.target.value = "";
    if (!file) return;
    upload.reset();
    const problem = specFileError(file);
    setFileError(problem);
    if (!problem) upload.mutate(file);
  }

  const error = fileError ?? upload.error?.message;

  return (
    <div className="flex flex-col items-start gap-2">
      <input
        ref={input}
        type="file"
        accept={SPEC_FILE_TYPES}
        aria-label="OpenAPI file"
        className="sr-only"
        tabIndex={-1}
        onChange={onFileChosen}
      />
      <Button
        variant={hasSpec ? "outline" : "default"}
        disabled={upload.isPending}
        onClick={() => input.current?.click()}
      >
        {upload.isPending ? "Importing…" : hasSpec ? "Upload new version" : "Upload OpenAPI file"}
      </Button>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

function ImportFailure({ spec, fallback }: { spec: SpecSummary; fallback: Spec | undefined }) {
  return (
    <Card className="border-destructive/50">
      <CardHeader>
        <CardTitle>Couldn&apos;t import {spec.source_filename}</CardTitle>
        <CardDescription>
          {fallback
            ? `Still showing version ${fallback.version_number}. Fix the problems below and upload the file again.`
            : "Fix the problems below and upload the file again."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul role="alert" className="flex flex-col gap-2 text-sm">
          {spec.validation_errors?.map((issue, index) => (
            <li key={index} className="break-words">
              {issue.message}
              {issue.pointer && (
                <code className="mt-0.5 block text-xs break-all text-muted-foreground">
                  {issue.pointer}
                </code>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function SpecOverview({ spec }: { spec: Spec }) {
  const metadata = spec.metadata_json;
  const schemes = Object.entries(metadata?.security_schemes ?? {});
  const facts: [string, string][] = [
    ["API", [spec.api_title, metadata?.version].filter(Boolean).join(" · ")],
    ["OpenAPI", spec.openapi_version ?? "Unknown"],
    ["Endpoints", String(spec.operation_count)],
    ["Schemas", String(spec.schema_count)],
    ["Source", `${spec.source_filename} (version ${spec.version_number})`],
    ["Servers", metadata?.servers.map((server) => server.url).join(", ") || "None listed"],
    [
      "Authentication",
      schemes.map(([name, scheme]) => `${name} (${scheme.scheme ?? scheme.type})`).join(", ") ||
        "None listed",
    ],
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Specification</CardTitle>
        {metadata?.description && <CardDescription>{metadata.description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[auto_1fr]">
          {facts.map(([term, value]) => (
            <div key={term} className="contents">
              <dt className="text-muted-foreground">{term}</dt>
              <dd className="min-w-0 break-words">{value}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

function OperationList({ projectId, specId }: { projectId: string; specId: string }) {
  const { data, error, isPending, refetch } = useQuery({
    // Keyed by version, so a new upload refetches the list.
    queryKey: ["operations", projectId, specId],
    queryFn: () => listOperations(projectId),
  });

  if (isPending) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading endpoints…
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
    return <p className="text-sm text-muted-foreground">This specification has no endpoints.</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      {groupByTag(data).map(([tag, operations]) => (
        <section key={tag} aria-label={tag}>
          <h3 className="mb-2 text-sm font-medium">{tag}</h3>
          <ul className="divide-y rounded-lg border">
            {operations.map((operation) => (
              <li
                key={operation.id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-2 text-sm"
              >
                <Badge variant="outline" className="font-mono">
                  {operation.method}
                </Badge>
                <code className="break-all">{operation.path}</code>
                {operation.summary && (
                  <span className="text-muted-foreground">{operation.summary}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function BackToDashboard() {
  return (
    <Link href="/dashboard" className={buttonVariants({ variant: "outline" })}>
      Back to dashboard
    </Link>
  );
}

export function ProjectWorkspace() {
  const { projectId } = useParams<{ projectId: string }>();

  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    retry: (count, error) => !isMissingProject(error) && count < 3,
  });
  const latest = project.data?.latest_spec ?? null;

  const specs = useQuery({
    // Keyed by the latest version, so a new upload refetches the list.
    queryKey: ["specs", projectId, latest?.id],
    queryFn: () => listSpecs(projectId),
    enabled: latest !== null,
  });

  if (project.isPending) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading project…
      </p>
    );
  }
  if (project.error) {
    return (
      <div role="alert" className="flex flex-col items-start gap-3">
        <p className="text-sm text-destructive">
          {isMissingProject(project.error) ? "This project doesn't exist." : project.error.message}
        </p>
        <BackToDashboard />
      </div>
    );
  }

  const browsable = specs.data?.find((spec) => spec.status === "ready");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight break-words">
              {project.data.name}
            </h1>
            <SpecStatusBadge spec={latest} />
          </div>
          {project.data.description && (
            <p className="mt-1 break-words whitespace-pre-wrap text-muted-foreground">
              {project.data.description}
            </p>
          )}
        </div>
        <SpecUpload projectId={projectId} hasSpec={latest !== null} />
      </div>

      {latest?.status === "failed" && <ImportFailure spec={latest} fallback={browsable} />}
      {specs.error && (
        <p role="alert" className="text-sm text-destructive">
          {specs.error.message}
        </p>
      )}
      {latest === null && (
        <p className="text-sm text-muted-foreground">
          Upload an OpenAPI 3.0, 3.1 or 3.2 file in JSON or YAML, up to 5 MB, to see this API&apos;s
          endpoints.
        </p>
      )}
      {browsable && (
        <>
          <SpecOverview spec={browsable} />
          <div>
            <h2 className="mb-4 text-lg font-semibold tracking-tight">Endpoints</h2>
            <OperationList projectId={projectId} specId={browsable.id} />
          </div>
        </>
      )}
    </div>
  );
}
