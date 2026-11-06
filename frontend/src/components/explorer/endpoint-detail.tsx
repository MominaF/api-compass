"use client";

import { useQuery } from "@tanstack/react-query";
import { cn } from "cn";
import Link from "next/link";
import { useEffect, useMemo, useRef, type ReactNode } from "react";

import { MethodBadge } from "@/components/explorer/method-badge";
import {
  Disclosure,
  FieldRow,
  JsonBlock,
  RequiredBadge,
  SchemaDescription,
  SchemaViewer,
} from "@/components/explorer/schema-viewer";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, getOperation, listSchemas, type Operation, type Spec } from "@/lib/api";
import {
  asText,
  collectExamples,
  describeSecurityScheme,
  isObject,
  resolveSchemaRoot,
  type JsonObject,
  type SchemaMap,
} from "@/lib/openapi";

/** Below this width the sidebar is hidden while an endpoint is open. Matches Tailwind's lg. */
const SIDEBAR_VISIBLE_QUERY = "(min-width: 64rem)";

const PARAMETER_GROUPS: [location: string, title: string][] = [
  ["path", "Path parameters"],
  ["query", "Query parameters"],
  ["header", "Headers"],
  ["cookie", "Cookies"],
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h3>{title}</h3>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">{children}</CardContent>
    </Card>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}

function Examples({ holder, schemas }: { holder: JsonObject; schemas: SchemaMap }) {
  const examples = collectExamples(holder, schemas);
  if (!examples.length) return <Muted>The specification doesn&apos;t include an example.</Muted>;
  return (
    <div className="flex flex-col gap-3">
      {examples.map((example, index) => {
        const title = example.summary ?? example.name;
        return (
          <div key={index} className="flex flex-col gap-1">
            <p className="text-sm font-medium">{title ? `Example: ${title}` : "Example"}</p>
            <JsonBlock value={example.value} label={title ? `Example: ${title}` : "Example"} />
          </div>
        );
      })}
    </div>
  );
}

function MediaTypes({ content, schemas }: { content: unknown; schemas: SchemaMap }) {
  if (!isObject(content)) return null;
  return Object.entries(content).map(([mediaType, media]) => {
    if (!isObject(media)) return null;
    return (
      <div key={mediaType} className="flex flex-col gap-3 border-t pt-3 first:border-t-0 first:pt-0">
        <p className="text-sm">
          <span className="text-muted-foreground">Content type: </span>
          <code className="break-all">{mediaType}</code>
        </p>
        {"schema" in media ? (
          <>
            <SchemaViewer schema={media.schema} schemas={schemas} />
            <Disclosure summary="View JSON schema">
              {() => (
                <JsonBlock
                  value={resolveSchemaRoot(media.schema, schemas)}
                  label={`JSON schema for ${mediaType}`}
                />
              )}
            </Disclosure>
          </>
        ) : (
          <Muted>The specification doesn&apos;t define a schema for this content type.</Muted>
        )}
        <Examples holder={media} schemas={schemas} />
      </div>
    );
  });
}

function parameterFacts(parameter: JsonObject) {
  const facts: string[] = [];
  if (parameter.deprecated === true) facts.push("Deprecated");
  if ("example" in parameter) facts.push(`Example: ${JSON.stringify(parameter.example)}`);
  if (isObject(parameter.examples)) {
    for (const [name, entry] of Object.entries(parameter.examples)) {
      if (isObject(entry) && "value" in entry) {
        facts.push(`Example ${name}: ${JSON.stringify(entry.value)}`);
      }
    }
  }
  return facts;
}

/** A parameter has either a schema or, less often, a content map holding one. */
function parameterSchema(parameter: JsonObject) {
  if ("schema" in parameter) return parameter.schema;
  const media = isObject(parameter.content) ? Object.values(parameter.content)[0] : undefined;
  return isObject(media) ? media.schema : undefined;
}

function Parameters({ parameters, schemas }: { parameters: unknown[]; schemas: SchemaMap }) {
  const valid = parameters.filter(isObject);
  if (!valid.length) return <Muted>This endpoint has no parameters.</Muted>;
  return PARAMETER_GROUPS.map(([location, title]) => {
    const group = valid.filter((parameter) => parameter.in === location);
    if (!group.length) return null;
    return (
      <div key={location} className="flex flex-col gap-2">
        <h4 className="text-sm font-medium">{title}</h4>
        <ul className="divide-y rounded-lg border">
          {group.map((parameter) => (
            <li key={String(parameter.name)} className="px-3 py-2">
              <FieldRow
                name={String(parameter.name)}
                required={parameter.required === true}
                schema={parameterSchema(parameter)}
                schemas={schemas}
                description={asText(parameter.description)}
                facts={parameterFacts(parameter)}
              />
            </li>
          ))}
        </ul>
      </div>
    );
  });
}

function RequestBody({ body, schemas }: { body: JsonObject | null; schemas: SchemaMap }) {
  if (!body) return <Muted>This endpoint has no request body.</Muted>;
  const description = asText(body.description);
  return (
    <>
      <div>
        <RequiredBadge required={body.required === true} />
      </div>
      {description && <SchemaDescription text={description} />}
      <MediaTypes content={body.content} schemas={schemas} />
    </>
  );
}

function statusColor(code: string) {
  if (code.startsWith("2")) return "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200";
  if (code.startsWith("3")) return "bg-blue-100 text-blue-900 dark:bg-blue-950 dark:text-blue-200";
  if (code.startsWith("4")) return "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200";
  if (code.startsWith("5")) return "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200";
  return "bg-muted text-foreground";
}

function Responses({ responses, schemas }: { responses: JsonObject; schemas: SchemaMap }) {
  const entries = Object.entries(responses);
  if (!entries.length) return <Muted>The specification doesn&apos;t list any responses.</Muted>;
  const firstSuccess = entries.find(([code]) => code.startsWith("2"))?.[0] ?? entries[0][0];
  return (
    <ul className="flex flex-col gap-3">
      {entries.map(([code, response]) => {
        const fields = isObject(response) ? response : {};
        return (
          <li key={code} className="rounded-lg border px-3 py-2">
            <Disclosure
              defaultOpen={code === firstSuccess}
              summary={
                <span className="flex flex-wrap items-center gap-2">
                  <Badge variant="ghost" className={cn("rounded-md font-mono", statusColor(code))}>
                    {code}
                  </Badge>
                  <span className="break-words">{asText(fields.description)}</span>
                </span>
              }
            >
              {() =>
                isObject(fields.content) && Object.keys(fields.content).length > 0 ? (
                  <div className="flex flex-col gap-3">
                    <MediaTypes content={fields.content} schemas={schemas} />
                  </div>
                ) : (
                  <Muted>This response has no body.</Muted>
                )
              }
            </Disclosure>
          </li>
        );
      })}
    </ul>
  );
}

function Authentication({ security, spec }: { security: unknown[]; spec: Spec }) {
  const requirements = security.filter(isObject);
  if (!requirements.length) {
    return <Muted>The specification doesn&apos;t require authentication for this endpoint.</Muted>;
  }
  const optional = requirements.some((requirement) => Object.keys(requirement).length === 0);
  const alternatives = requirements.filter((requirement) => Object.keys(requirement).length > 0);
  const schemes = spec.metadata_json?.security_schemes ?? {};
  return (
    <>
      {optional && <Muted>Authentication is optional for this endpoint.</Muted>}
      {alternatives.length > 1 && <Muted>Use any one of these options:</Muted>}
      <ul className="flex flex-col gap-3">
        {alternatives.map((requirement, index) => (
          <li key={index} className="flex flex-col gap-3 rounded-lg border px-3 py-2">
            {Object.keys(requirement).length > 1 && <Muted>Send all of these together:</Muted>}
            {Object.entries(requirement).map(([name, scopes]) => {
              const scheme = Object.hasOwn(schemes, name) ? schemes[name] : undefined;
              if (!scheme) {
                return (
                  <p key={name} className="text-sm">
                    <code>{name}</code>: not defined in this specification.
                  </p>
                );
              }
              const { kind, format } = describeSecurityScheme(scheme);
              const scopeList = Array.isArray(scopes) ? scopes.map(String) : [];
              const description = asText(scheme.description);
              return (
                <div key={name} className="flex flex-col gap-1 text-sm">
                  <p>
                    <span className="font-medium">{kind}</span>{" "}
                    <code className="text-xs text-muted-foreground">{name}</code>
                  </p>
                  <code className="rounded-md bg-muted px-2 py-1 text-xs break-all">{format}</code>
                  {description && <SchemaDescription text={description} />}
                  {scopeList.length > 0 && <Muted>Scopes: {scopeList.join(", ")}</Muted>}
                </div>
              );
            })}
          </li>
        ))}
      </ul>
    </>
  );
}

function OperationView({
  operation,
  spec,
  schemas,
}: {
  operation: Operation;
  spec: Spec;
  schemas: SchemaMap;
}) {
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    // On small screens the link just used disappears, so move focus to what replaced it.
    if (!window.matchMedia(SIDEBAR_VISIBLE_QUERY).matches) heading.current?.focus();
  }, []);

  return (
    <article className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <MethodBadge method={operation.method} />
          <code className="min-w-0 text-sm font-medium break-all">{operation.path}</code>
        </div>
        <h2 ref={heading} tabIndex={-1} className="text-xl font-semibold tracking-tight outline-none">
          {operation.summary ?? operation.operation_id ?? `${operation.method} ${operation.path}`}
        </h2>
        {operation.description && <SchemaDescription text={operation.description} />}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">Operation ID</dt>
          <dd className="min-w-0 break-all">
            {operation.operation_id ? <code>{operation.operation_id}</code> : "None"}
          </dd>
          <dt className="text-muted-foreground">Tags</dt>
          <dd className="flex min-w-0 flex-wrap gap-1">
            {operation.tags.length
              ? operation.tags.map((tag) => (
                  <Badge key={tag} variant="secondary">
                    {tag}
                  </Badge>
                ))
              : "None"}
          </dd>
        </dl>
      </div>

      <Section title="Authentication">
        <Authentication security={operation.security_json} spec={spec} />
      </Section>
      <Section title="Parameters">
        <Parameters parameters={operation.parameters_json} schemas={schemas} />
      </Section>
      <Section title="Request body">
        <RequestBody body={operation.request_body_json} schemas={schemas} />
      </Section>
      <Section title="Responses">
        <Responses responses={operation.responses_json} schemas={schemas} />
      </Section>
    </article>
  );
}

function isMissing(error: unknown) {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

export function EndpointDetail({
  projectId,
  operationId,
  spec,
}: {
  projectId: string;
  operationId: string;
  spec: Spec;
}) {
  const operation = useQuery({
    queryKey: ["operation", projectId, operationId],
    queryFn: () => getOperation(projectId, operationId),
    retry: (count, error) => !isMissing(error) && count < 3,
  });
  const schemaList = useQuery({
    queryKey: ["schemas", projectId, spec.id],
    queryFn: () => listSchemas(projectId, spec.id),
  });
  const schemas = useMemo<SchemaMap>(
    () => new Map(schemaList.data?.map((schema) => [schema.schema_name, schema.definition])),
    [schemaList.data],
  );

  const overviewLink = (
    <Link
      href={`/projects/${projectId}`}
      className={cn(buttonVariants({ variant: "outline", size: "sm" }), "self-start")}
    >
      Back to overview
    </Link>
  );

  // A link saved before a new upload can name an endpoint from a replaced version.
  if (
    isMissing(operation.error) ||
    (operation.data && operation.data.spec_version_id !== spec.id)
  ) {
    return (
      <div role="alert" className="flex flex-col gap-3">
        <p className="text-sm">This endpoint isn&apos;t in the version of the API shown here.</p>
        {overviewLink}
      </div>
    );
  }

  const error = operation.error ?? schemaList.error;
  if (error) {
    return (
      <div role="alert" className="flex flex-col items-start gap-3">
        <p className="text-sm text-destructive">{error.message}</p>
        <Button
          variant="outline"
          onClick={() => {
            if (operation.error) void operation.refetch();
            if (schemaList.error) void schemaList.refetch();
          }}
        >
          Try again
        </Button>
      </div>
    );
  }
  if (!operation.data || !schemaList.data) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading endpoint…
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {overviewLink}
      <OperationView operation={operation.data} spec={spec} schemas={schemas} />
    </div>
  );
}
