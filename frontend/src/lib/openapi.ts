/**
 * Turns the OpenAPI data of an uploaded specification into what the explorer displays. Only reads
 * what the file says: nothing is inferred or generated. The file is untrusted and schemas can be
 * recursive, so every shape is checked and every reference is tracked.
 */

import type { SecurityScheme } from "@/lib/api";

export type JsonObject = Record<string, unknown>;
export type SchemaMap = ReadonlyMap<string, unknown>;

export const isObject = (value: unknown): value is JsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const asText = (value: unknown) => (typeof value === "string" && value ? value : null);

const SCHEMA_REF_PREFIX = "#/components/schemas/";

function decodePointerPart(part: string) {
  let decoded = part;
  try {
    decoded = decodeURIComponent(part);
  } catch {
    // Not percent-encoded after all, so use it as written.
  }
  return decoded.replaceAll("~1", "/").replaceAll("~0", "~");
}

/** Only schema records are available here. Returns undefined for a target anywhere else. */
function lookupSchemaRef(ref: string, schemas: SchemaMap): { value: unknown } | undefined {
  if (!ref.startsWith(SCHEMA_REF_PREFIX)) return undefined;
  const [name, ...rest] = ref.slice(SCHEMA_REF_PREFIX.length).split("/").map(decodePointerPart);
  if (!schemas.has(name)) return undefined;
  let node = schemas.get(name);
  for (const part of rest) {
    if (isObject(node) && Object.hasOwn(node, part)) node = node[part];
    else if (Array.isArray(node) && /^\d+$/.test(part) && Number(part) < node.length) {
      node = node[Number(part)];
    } else return undefined;
  }
  return { value: node };
}

function refName(ref: string) {
  return decodePointerPart(ref.slice(ref.lastIndexOf("/") + 1));
}

type Followed = {
  schema: unknown;
  name: string | null;
  /** The references passed through to get here, used to detect recursion. */
  trail: readonly string[];
  circular: boolean;
  unresolved: string | null;
};

function followRefs(schema: unknown, schemas: SchemaMap, trail: readonly string[]): Followed {
  let node = schema;
  let name: string | null = null;
  const visited = [...trail];
  while (isObject(node) && typeof node.$ref === "string") {
    const ref = node.$ref;
    name ??= refName(ref);
    if (visited.includes(ref)) {
      return { schema: node, name, trail: visited, circular: true, unresolved: null };
    }
    const target = lookupSchemaRef(ref, schemas);
    if (!target) return { schema: node, name, trail: visited, circular: false, unresolved: ref };
    visited.push(ref);
    // In 3.1 a reference can override parts of its target, such as the description.
    const siblings = { ...node };
    delete siblings.$ref;
    node = isObject(target.value) ? { ...target.value, ...siblings } : target.value;
  }
  return { schema: node, name, trail: visited, circular: false, unresolved: null };
}

/** The definition a schema points to, for showing as JSON. References inside it stay as written. */
export function resolveSchemaRoot(schema: unknown, schemas: SchemaMap) {
  return followRefs(schema, schemas, []).schema;
}

export type SchemaField = {
  name: string;
  schema: unknown;
  required: boolean;
  trail: readonly string[];
};

export type SchemaVariants = {
  kind: "One of" | "Any of";
  options: unknown[];
  trail: readonly string[];
};

export type SchemaView = {
  label: string;
  description: string | null;
  facts: string[];
  fields: SchemaField[];
  variants: SchemaVariants[];
};

const emptyView = { description: null, facts: [], fields: [], variants: [] };

function shortJson(value: unknown) {
  const text = JSON.stringify(value) ?? "";
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}

const MAX_ENUM_VALUES = 20;

const CONSTRAINTS: [key: string, label: string][] = [
  ["default", "Default"],
  ["const", "Must be"],
  ["minimum", "Minimum"],
  ["exclusiveMinimum", "Greater than"],
  ["maximum", "Maximum"],
  ["exclusiveMaximum", "Less than"],
  ["multipleOf", "Multiple of"],
  ["minLength", "Min length"],
  ["maxLength", "Max length"],
  ["pattern", "Pattern"],
  ["minItems", "Min items"],
  ["maxItems", "Max items"],
];

function schemaFacts(node: JsonObject) {
  const facts: string[] = [];
  if (Array.isArray(node.enum)) {
    const shown = node.enum.slice(0, MAX_ENUM_VALUES).map(shortJson).join(", ");
    const hidden = node.enum.length - MAX_ENUM_VALUES;
    facts.push(`Allowed: ${shown}${hidden > 0 ? ` and ${hidden} more` : ""}`);
  }
  for (const [key, label] of CONSTRAINTS) {
    // In 3.0 exclusiveMinimum and exclusiveMaximum are booleans that only modify the bound.
    if (key in node && typeof node[key] !== "boolean") {
      facts.push(`${label}: ${shortJson(node[key])}`);
    }
  }
  if (node.exclusiveMinimum === true) facts.push("Minimum is exclusive");
  if (node.exclusiveMaximum === true) facts.push("Maximum is exclusive");
  if (node.readOnly === true) facts.push("Read-only");
  if (node.writeOnly === true) facts.push("Write-only");
  if (node.deprecated === true) facts.push("Deprecated");
  return facts;
}

function typeNames(node: JsonObject) {
  const declared = Array.isArray(node.type) ? node.type : [node.type];
  const names = declared.filter((name): name is string => typeof name === "string");
  if (node.nullable === true && !names.includes("null")) names.push("null");
  return names;
}

/** Combines an object's own fields with those of its allOf parts, which all apply together. */
function collectObjectParts(root: JsonObject, schemas: SchemaMap, trail: readonly string[]) {
  const fields = new Map<string, SchemaField>();
  const required = new Set<string>();
  const variants: SchemaVariants[] = [];
  let description: string | null = null;
  // One allOf can reach another schema repeatedly. Visiting each once keeps this linear.
  const merged = new Set<string>();

  const visit = (node: JsonObject, nodeTrail: readonly string[]) => {
    description ??= asText(node.description);
    if (isObject(node.properties)) {
      for (const [name, schema] of Object.entries(node.properties)) {
        fields.set(name, { name, schema, required: false, trail: nodeTrail });
      }
    }
    if (Array.isArray(node.required)) {
      for (const name of node.required) if (typeof name === "string") required.add(name);
    }
    if (isObject(node.additionalProperties) || node.additionalProperties === true) {
      const name = "(any other property)";
      fields.set(name, {
        name,
        schema: node.additionalProperties,
        required: false,
        trail: nodeTrail,
      });
    }
    for (const [key, kind] of [
      ["oneOf", "One of"],
      ["anyOf", "Any of"],
    ] as const) {
      const options = node[key];
      if (Array.isArray(options)) variants.push({ kind, options, trail: nodeTrail });
    }
    if (Array.isArray(node.allOf)) {
      for (const part of node.allOf) {
        const followed = followRefs(part, schemas, nodeTrail);
        const key = isObject(part) && typeof part.$ref === "string" ? part.$ref : null;
        if (followed.circular || !isObject(followed.schema) || (key && merged.has(key))) continue;
        if (key) merged.add(key);
        visit(followed.schema, followed.trail);
      }
    }
  };
  visit(root, trail);

  for (const name of required) {
    // A field can be required without being described, and it still has to be sent.
    if (!fields.has(name)) fields.set(name, { name, schema: true, required: true, trail });
  }
  const list = [...fields.values()].map((field) => ({
    ...field,
    required: required.has(field.name),
  }));
  return { fields: list, variants, description };
}

/** Describes one schema, following references but stopping at anything recursive. */
export function inspectSchema(
  schema: unknown,
  schemas: SchemaMap,
  trail: readonly string[] = [],
): SchemaView {
  const followed = followRefs(schema, schemas, trail);
  const { name } = followed;
  const named = (label: string) => (name ? `${name} (${label})` : label);

  if (followed.circular) return { ...emptyView, label: `${name} (recursive, shown above)` };
  if (followed.unresolved) return { ...emptyView, label: `Reference: ${followed.unresolved}` };

  const node = followed.schema;
  if (!isObject(node)) {
    return { ...emptyView, label: named(node === false ? "no value allowed" : "any value") };
  }

  const types = typeNames(node);
  const parts = collectObjectParts(node, schemas, followed.trail);
  const facts = schemaFacts(node);

  if (types.includes("array") || (!types.length && "items" in node)) {
    const items = "items" in node ? inspectSchema(node.items, schemas, followed.trail) : null;
    const others = types.filter((type) => type !== "array");
    const arrayLabel = items ? `array of ${items.label}` : "array";
    return {
      label: named([arrayLabel, ...others].join(" or ")),
      description: parts.description,
      facts,
      fields: items?.fields ?? [],
      variants: items?.variants ?? [],
    };
  }

  const format = asText(node.format);
  let label = types.join(" or ");
  if (!label) {
    if (parts.fields.length) label = "object";
    else if (Array.isArray(node.enum)) label = "enum";
    else if (parts.variants.length) label = parts.variants[0].kind.toLowerCase();
    else label = "any value";
  }
  return {
    label: named(format ? `${label}, ${format}` : label),
    description: parts.description,
    facts,
    fields: parts.fields,
    variants: parts.variants,
  };
}

export type NamedExample = { name: string | null; summary: string | null; value: unknown };

/**
 * The examples a media type or parameter declares, falling back to those on its schema. External
 * examples are never fetched, so those list their URL for the reader to follow.
 */
export function collectExamples(holder: JsonObject, schemas: SchemaMap): NamedExample[] {
  if ("example" in holder) return [{ name: null, summary: null, value: holder.example }];
  if (isObject(holder.examples)) {
    return Object.entries(holder.examples).flatMap(([name, entry]) => {
      if (!isObject(entry)) return [];
      const summary = asText(entry.summary);
      if ("value" in entry) return [{ name, summary, value: entry.value }];
      if ("dataValue" in entry) return [{ name, summary, value: entry.dataValue }];
      if ("serializedValue" in entry) return [{ name, summary, value: entry.serializedValue }];
      const external = asText(entry.externalValue);
      return external ? [{ name, summary, value: `Hosted elsewhere: ${external}` }] : [];
    });
  }
  const schema = followRefs(holder.schema, schemas, []).schema;
  if (isObject(schema)) {
    if ("example" in schema) return [{ name: null, summary: null, value: schema.example }];
    if (Array.isArray(schema.examples)) {
      return schema.examples.map((value) => ({ name: null, summary: null, value }));
    }
  }
  return [];
}

/** How a request has to present a credential for this scheme, as the specification defines it. */
export function describeSecurityScheme(scheme: SecurityScheme): { kind: string; format: string } {
  switch (scheme.type?.toLowerCase()) {
    case "http": {
      const httpScheme = scheme.scheme?.toLowerCase();
      if (httpScheme === "bearer") {
        const token = scheme.bearerFormat ? `<${scheme.bearerFormat} token>` : "<token>";
        return { kind: "HTTP bearer token", format: `Authorization: Bearer ${token}` };
      }
      if (httpScheme === "basic") {
        return {
          kind: "HTTP basic authentication",
          format: "Authorization: Basic <base64 of username:password>",
        };
      }
      return {
        kind: `HTTP ${scheme.scheme ?? "authentication"}`,
        format: `Authorization: ${scheme.scheme ?? "<scheme>"} <credentials>`,
      };
    }
    case "apikey": {
      const location = scheme.in ?? "request";
      const key = scheme.name ?? "key";
      if (location === "header") return { kind: "API key", format: `${key}: <API key>` };
      if (location === "query") return { kind: "API key", format: `?${key}=<API key>` };
      if (location === "cookie") return { kind: "API key", format: `Cookie: ${key}=<API key>` };
      return { kind: "API key", format: `${key} in the ${location}` };
    }
    case "oauth2": {
      const flows = Object.keys(scheme.flows ?? {}).join(", ");
      return {
        kind: flows ? `OAuth 2.0 (${flows})` : "OAuth 2.0",
        format: "Authorization: Bearer <access token>",
      };
    }
    case "openidconnect":
      return {
        kind: "OpenID Connect",
        format: scheme.openIdConnectUrl
          ? `Authorization: Bearer <access token>, from ${scheme.openIdConnectUrl}`
          : "Authorization: Bearer <access token>",
      };
    case "mutualtls":
      return { kind: "Mutual TLS", format: "Connect with a trusted client certificate." };
    default:
      return { kind: scheme.type ?? "Unknown", format: "Not described by the specification." };
  }
}
