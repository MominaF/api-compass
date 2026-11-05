import { Compass, FileSearch, FlaskConical, MessageSquare } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";

const features = [
  {
    icon: FileSearch,
    title: "Explore any API",
    text: "Turn an OpenAPI specification into a searchable map of endpoints and schemas.",
  },
  {
    icon: MessageSquare,
    title: "Ask questions",
    text: "Get answers about authentication, parameters and workflows, cited from the spec.",
  },
  {
    icon: FlaskConical,
    title: "Build and test",
    text: "Describe a request in plain language, then run it against a safe mock.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-4">
          <div className="flex items-center gap-2">
            <Compass className="size-5 text-primary" aria-hidden />
            <span className="font-semibold tracking-tight">API COMPASS</span>
          </div>
          <Link href="/login" className={buttonVariants({ variant: "ghost" })}>
            Sign in
          </Link>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-16">
        <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance">
          Understand an unfamiliar API in minutes
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted-foreground">
          Explore, understand and test REST APIs from their OpenAPI specifications.
        </p>
        <Link href="/signup" className={`${buttonVariants({ size: "lg" })} mt-8`}>
          Get started
        </Link>
        <ul className="mt-16 grid gap-8 md:grid-cols-3">
          {features.map(({ icon: Icon, title, text }) => (
            <li key={title}>
              <Icon className="size-5 text-primary" aria-hidden />
              <h2 className="mt-3 font-medium">{title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{text}</p>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
