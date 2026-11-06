import { cn } from "cn";

import { Badge } from "@/components/ui/badge";

/** The method's name is always shown too, so color is never the only signal. */
const METHOD_COLORS: Record<string, string> = {
  GET: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200",
  POST: "bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-200",
  PUT: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
  PATCH: "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200",
  DELETE: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200",
};
const OTHER_METHOD_COLOR = "bg-muted text-foreground";

export const methodColor = (method: string) => METHOD_COLORS[method] ?? OTHER_METHOD_COLOR;

export function MethodBadge({ method }: { method: string }) {
  return (
    <Badge variant="ghost" className={cn("rounded-md font-mono font-semibold", methodColor(method))}>
      {method}
    </Badge>
  );
}
