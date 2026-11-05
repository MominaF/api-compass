import { Badge } from "@/components/ui/badge";
import type { SpecSummary } from "@/lib/api";

const labels = {
  processing: { text: "Processing", variant: "secondary" },
  ready: { text: "Ready", variant: "default" },
  failed: { text: "Import failed", variant: "destructive" },
} as const;

export function SpecStatusBadge({ spec }: { spec: SpecSummary | null }) {
  if (!spec) return <Badge variant="secondary">No spec uploaded</Badge>;
  const { text, variant } = labels[spec.status];
  return <Badge variant={variant}>{text}</Badge>;
}
