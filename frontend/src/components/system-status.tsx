"use client";

import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { API_BASE_URL, getHealth } from "@/lib/api";

type Tone = "ok" | "warn" | "down" | "pending";

const toneStyles: Record<Tone, string> = {
  ok: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  warn: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  down: "bg-destructive/10 text-destructive",
  pending: "bg-muted text-muted-foreground",
};

function StatusRow({ label, tone, value }: { label: string; tone: Tone; value: string }) {
  return (
    <div className="flex items-center justify-between py-2">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd>
        <Badge className={toneStyles[tone]}>
          <span aria-hidden className="size-1.5 rounded-full bg-current" />
          {value}
        </Badge>
      </dd>
    </div>
  );
}

export function SystemStatus() {
  const { data, error, isPending, isFetching, refetch } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 30_000,
  });

  const apiTone: Tone = isPending ? "pending" : error ? "down" : "ok";
  const dbTone: Tone = isPending || error ? "pending" : data.database === "ok" ? "ok" : "warn";

  return (
    <Card>
      <CardHeader>
        <CardTitle>System status</CardTitle>
        <CardDescription className="font-mono text-xs break-all">{API_BASE_URL}</CardDescription>
        <CardAction>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => void refetch()}
            disabled={isFetching}
            aria-label="Recheck system status"
          >
            <RefreshCw className={isFetching ? "animate-spin" : undefined} />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent>
        <dl className="divide-y" aria-live="polite">
          <StatusRow
            label="Backend API"
            tone={apiTone}
            value={isPending ? "Checking…" : error ? "Unreachable" : `Online · v${data.version}`}
          />
          <StatusRow
            label="Database"
            tone={dbTone}
            value={
              isPending ? "Checking…" : error ? "Unknown" : data.database === "ok" ? "Connected" : "Unavailable"
            }
          />
        </dl>
        {error && <p className="mt-3 text-sm text-destructive">{error.message}</p>}
        {data?.database === "unavailable" && (
          <p className="mt-3 text-sm text-muted-foreground">
            The API is running but can&apos;t reach Postgres. Check <code>DATABASE_URL</code> in{" "}
            <code>backend/.env</code>.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
