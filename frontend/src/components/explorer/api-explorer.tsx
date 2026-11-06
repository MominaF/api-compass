"use client";

import { cn } from "cn";
import { useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { EndpointDetail } from "@/components/explorer/endpoint-detail";
import { EndpointSidebar } from "@/components/explorer/endpoint-sidebar";
import type { Spec } from "@/lib/api";

export function ApiExplorer({
  projectId,
  spec,
  overview,
}: {
  projectId: string;
  spec: Spec;
  overview: ReactNode;
}) {
  // Kept in the URL so an endpoint can be linked to, and Back returns to the previous one.
  const selectedId = useSearchParams().get("endpoint");

  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_minmax(0,1fr)] lg:items-start">
      <aside
        className={cn(
          "lg:sticky lg:top-4 lg:flex lg:max-h-[calc(100vh-2rem)] lg:flex-col",
          // On small screens the list and the open endpoint take turns.
          selectedId && "hidden",
        )}
      >
        <EndpointSidebar
          projectId={projectId}
          specId={spec.id}
          total={spec.operation_count}
          selectedId={selectedId}
        />
      </aside>
      <div className="min-w-0">
        {selectedId ? (
          <EndpointDetail
            key={selectedId}
            projectId={projectId}
            operationId={selectedId}
            spec={spec}
          />
        ) : (
          <div className="flex flex-col gap-4">
            {overview}
            <p className="text-sm text-muted-foreground">
              Select an endpoint to see its parameters, schemas, responses and authentication.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
