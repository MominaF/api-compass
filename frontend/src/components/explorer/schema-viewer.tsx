"use client";

import { ChevronRight } from "lucide-react";
import { cn } from "cn";
import { useId, useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { inspectSchema, type SchemaMap, type SchemaView } from "@/lib/openapi";

/** Renders its content only once opened, since recursive schemas could otherwise never finish. */
export function Disclosure({
  summary,
  defaultOpen = false,
  children,
}: {
  summary: ReactNode;
  defaultOpen?: boolean;
  children: () => ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? contentId : undefined}
        onClick={() => setOpen(!open)}
        className="flex w-full items-start gap-1 rounded-sm text-left text-sm outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
      >
        <ChevronRight
          aria-hidden
          className={cn("mt-0.5 size-4 shrink-0 transition-transform", open && "rotate-90")}
        />
        <span className="min-w-0 flex-1">{summary}</span>
      </button>
      {open && (
        <div id={contentId} className="mt-2 ml-5">
          {children()}
        </div>
      )}
    </div>
  );
}

export function RequiredBadge({ required }: { required: boolean }) {
  return required ? (
    <Badge variant="destructive">Required</Badge>
  ) : (
    <span className="text-xs text-muted-foreground">Optional</span>
  );
}

export function SchemaFacts({ facts }: { facts: string[] }) {
  if (!facts.length) return null;
  return (
    <ul className="flex flex-col gap-0.5 text-xs text-muted-foreground">
      {facts.map((fact) => (
        <li key={fact} className="break-words">
          {fact}
        </li>
      ))}
    </ul>
  );
}

function hasChildren(view: SchemaView) {
  return view.fields.length > 0 || view.variants.length > 0;
}

function SchemaChildren({ view, schemas }: { view: SchemaView; schemas: SchemaMap }) {
  return (
    <div className="flex flex-col gap-3">
      {view.fields.length > 0 && (
        <ul className="divide-y rounded-lg border">
          {view.fields.map((field) => (
            <li key={field.name} className="px-3 py-2">
              <FieldRow
                name={field.name}
                required={field.required}
                schema={field.schema}
                schemas={schemas}
                trail={field.trail}
              />
            </li>
          ))}
        </ul>
      )}
      {view.variants.map((group, groupIndex) => (
        <div key={groupIndex} className="flex flex-col gap-2">
          <p className="text-sm font-medium">{group.kind}</p>
          <ul className="flex flex-col gap-2 rounded-lg border px-3 py-2">
            {group.options.map((option, index) => {
              const optionView = inspectSchema(option, schemas, group.trail);
              return (
                <li key={index} className="flex flex-col gap-1">
                  {hasChildren(optionView) ? (
                    <Disclosure summary={<code className="break-all">{optionView.label}</code>}>
                      {() => <SchemaChildren view={optionView} schemas={schemas} />}
                    </Disclosure>
                  ) : (
                    <code className="text-sm break-all">{optionView.label}</code>
                  )}
                  {optionView.description && <SchemaDescription text={optionView.description} />}
                  <SchemaFacts facts={optionView.facts} />
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Descriptions can hold CommonMark, which is shown as written rather than rendered. */
export function SchemaDescription({ text }: { text: string }) {
  return <p className="text-sm break-words whitespace-pre-wrap text-muted-foreground">{text}</p>;
}

/** One named value: an object's field or an endpoint's parameter. */
export function FieldRow({
  name,
  required,
  schema,
  schemas,
  trail,
  description,
  facts = [],
}: {
  name: string;
  required: boolean;
  schema: unknown;
  schemas: SchemaMap;
  trail?: readonly string[];
  description?: string | null;
  facts?: string[];
}) {
  const view = inspectSchema(schema, schemas, trail);
  const heading = (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
      <code className={cn("font-medium break-all", required && "font-semibold")}>{name}</code>
      <RequiredBadge required={required} />
      <code className="text-xs break-all text-muted-foreground">{view.label}</code>
    </span>
  );
  const text = description ?? view.description;

  return (
    <div className="flex flex-col gap-1 text-sm">
      {hasChildren(view) ? (
        <Disclosure summary={heading}>
          {() => <SchemaChildren view={view} schemas={schemas} />}
        </Disclosure>
      ) : (
        heading
      )}
      {text && <SchemaDescription text={text} />}
      <SchemaFacts facts={[...view.facts, ...facts]} />
    </div>
  );
}

/** A whole request or response schema: its type, with its first level of fields already open. */
export function SchemaViewer({ schema, schemas }: { schema: unknown; schemas: SchemaMap }) {
  const view = inspectSchema(schema, schemas);
  return (
    <div className="flex flex-col gap-2">
      <code className="text-sm break-all">{view.label}</code>
      {view.description && <SchemaDescription text={view.description} />}
      <SchemaFacts facts={view.facts} />
      {hasChildren(view) && <SchemaChildren view={view} schemas={schemas} />}
    </div>
  );
}

export function JsonBlock({ value, label }: { value: unknown; label: string }) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return (
    <pre
      aria-label={label}
      // Focusable so the block can be scrolled from the keyboard.
      tabIndex={0}
      className="max-h-96 overflow-auto rounded-lg bg-muted p-3 font-mono text-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    >
      {text}
    </pre>
  );
}
