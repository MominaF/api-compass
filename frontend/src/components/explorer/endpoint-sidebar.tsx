"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { cn } from "cn";
import Link from "next/link";
import { useEffect, useState } from "react";

import { MethodBadge, methodColor } from "@/components/explorer/method-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { listOperations, type OperationSummary } from "@/lib/api";

const FILTER_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const UNTAGGED = "Other";
const SEARCH_DELAY_MS = 200;
const MAX_QUERY_LENGTH = 200;

/** Groups by first tag only, so an operation with several tags is still listed once. */
function groupByTag(operations: OperationSummary[]) {
  const groups = new Map<string, OperationSummary[]>();
  for (const operation of operations) {
    const tag = operation.tags[0] ?? UNTAGGED;
    groups.set(tag, [...(groups.get(tag) ?? []), operation]);
  }
  return [...groups.entries()];
}

function EndpointLink({
  projectId,
  operation,
  selected,
}: {
  projectId: string;
  operation: OperationSummary;
  selected: boolean;
}) {
  const description = operation.summary ?? operation.description;
  return (
    <Link
      href={`/projects/${projectId}?endpoint=${operation.id}`}
      prefetch={false}
      aria-current={selected ? "true" : undefined}
      className={cn(
        "flex flex-col gap-1 px-3 py-2 text-sm outline-none hover:bg-muted focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:ring-inset",
        selected && "bg-muted",
      )}
    >
      <span className="flex items-baseline gap-2">
        <MethodBadge method={operation.method} />
        <code className="min-w-0 font-medium break-all">{operation.path}</code>
      </span>
      {description && <span className="line-clamp-2 text-muted-foreground">{description}</span>}
      {operation.operation_id && (
        <code className="text-xs break-all text-muted-foreground">{operation.operation_id}</code>
      )}
    </Link>
  );
}

export function EndpointSidebar({
  projectId,
  specId,
  total,
  selectedId,
}: {
  projectId: string;
  specId: string;
  total: number;
  selectedId: string | null;
}) {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [methods, setMethods] = useState<string[]>([]);

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, error, isPending, isPlaceholderData, refetch } = useQuery({
    queryKey: ["operations", projectId, specId, query, methods],
    queryFn: () => listOperations(projectId, { specId, query, methods }),
    // Keep the current results on screen while the next ones load, so the list doesn't flash.
    placeholderData: keepPreviousData,
  });

  const filtered = search.trim() !== "" || methods.length > 0;

  function clearFilters() {
    setSearch("");
    setQuery("");
    setMethods([]);
  }

  return (
    <div className="flex flex-col gap-4 lg:min-h-0">
      <h2 className="text-lg font-semibold tracking-tight">Endpoints</h2>
      <div role="search" className="flex flex-col gap-2">
        <Input
          type="search"
          aria-label="Search endpoints"
          placeholder="Search endpoints"
          maxLength={MAX_QUERY_LENGTH}
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <div role="group" aria-label="Filter by HTTP method" className="flex flex-wrap gap-1">
          {FILTER_METHODS.map((method) => {
            const active = methods.includes(method);
            return (
              <Button
                key={method}
                variant="outline"
                size="xs"
                aria-pressed={active}
                className={cn("font-mono", active && methodColor(method))}
                onClick={() =>
                  setMethods((current) =>
                    active ? current.filter((name) => name !== method) : [...current, method],
                  )
                }
              >
                {method}
              </Button>
            );
          })}
        </div>
        <div className="flex min-h-6 items-center justify-between gap-2 text-sm text-muted-foreground">
          <p role="status">{data && `Showing ${data.length} of ${total}`}</p>
          {filtered && (
            <Button variant="ghost" size="xs" onClick={clearFilters}>
              Clear
            </Button>
          )}
        </div>
      </div>

      {error ? (
        <div role="alert" className="flex flex-col items-start gap-3">
          <p className="text-sm text-destructive">{error.message}</p>
          <Button variant="outline" onClick={() => void refetch()}>
            Try again
          </Button>
        </div>
      ) : isPending ? (
        <p role="status" className="text-sm text-muted-foreground">
          Loading endpoints…
        </p>
      ) : data.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {filtered ? "No endpoints match." : "This specification has no endpoints."}
        </p>
      ) : (
        <nav
          aria-label="Endpoints"
          aria-busy={isPlaceholderData}
          className="flex flex-col gap-4 lg:min-h-0 lg:overflow-y-auto"
        >
          {groupByTag(data).map(([tag, operations]) => (
            <section key={tag} aria-label={tag}>
              <h3 className="mb-2 text-sm font-medium">{tag}</h3>
              <ul className="divide-y overflow-hidden rounded-lg border">
                {operations.map((operation) => (
                  <li key={operation.id}>
                    <EndpointLink
                      projectId={projectId}
                      operation={operation}
                      selected={operation.id === selectedId}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </nav>
      )}
    </div>
  );
}
