"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Compass } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAuth } from "@/components/auth/auth-provider";
import { FormField } from "@/components/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { requireSupabase } from "@/lib/supabase";

const email = z.email("Enter a valid email address.");
const schemas = {
  "sign-in": z.object({ email, password: z.string().min(1, "Enter your password.") }),
  "sign-up": z.object({ email, password: z.string().min(8, "Use at least 8 characters.") }),
};
type Values = z.infer<(typeof schemas)["sign-in"]>;

const copy = {
  "sign-in": {
    title: "Sign in",
    description: "Welcome back to API COMPASS.",
    submit: "Sign in",
    pending: "Signing in…",
    switchText: "New here?",
    switchLabel: "Create an account",
    switchHref: "/signup",
  },
  "sign-up": {
    title: "Create your account",
    description: "Start exploring your APIs.",
    submit: "Create account",
    pending: "Creating account…",
    switchText: "Already have an account?",
    switchLabel: "Sign in",
    switchHref: "/login",
  },
};

export function AuthForm({ mode }: { mode: "sign-in" | "sign-up" }) {
  const router = useRouter();
  const { status } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const [checkEmail, setCheckEmail] = useState(false);
  const text = copy[mode];

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schemas[mode]),
    defaultValues: { email: "", password: "" },
  });

  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard");
  }, [status, router]);

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setFormError(null);
    try {
      const auth = requireSupabase().auth;
      const { data, error } =
        mode === "sign-in"
          ? await auth.signInWithPassword({ email, password })
          : await auth.signUp({ email, password });
      if (error) {
        setFormError(error.message);
        return;
      }
      // Next.js keeps visited pages mounted, so don't leave the password in the hidden form.
      reset();
      // With email confirmation on, sign-up succeeds without starting a session.
      if (!data.session) setCheckEmail(true);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Something went wrong. Try again.");
    }
  });

  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-10">
      <Link href="/" className="flex items-center gap-2">
        <Compass className="size-5 text-primary" aria-hidden />
        <span className="font-semibold tracking-tight">API COMPASS</span>
      </Link>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{checkEmail ? "Check your email" : text.title}</CardTitle>
          <CardDescription>
            {checkEmail
              ? "Follow the link we sent you to confirm your account, then sign in."
              : text.description}
          </CardDescription>
        </CardHeader>
        {!checkEmail && (
          <CardContent>
            <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
              <FormField id="email" label="Email" error={errors.email?.message}>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  aria-invalid={!!errors.email}
                  {...register("email")}
                />
              </FormField>
              <FormField id="password" label="Password" error={errors.password?.message}>
                <Input
                  id="password"
                  type="password"
                  autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
                  aria-invalid={!!errors.password}
                  {...register("password")}
                />
              </FormField>
              {formError && (
                <p role="alert" className="text-sm text-destructive">
                  {formError}
                </p>
              )}
              <Button type="submit" size="lg" disabled={isSubmitting}>
                {isSubmitting ? text.pending : text.submit}
              </Button>
              <p className="text-center text-sm text-muted-foreground">
                {text.switchText}{" "}
                <Link href={text.switchHref} className="text-primary underline-offset-4 hover:underline">
                  {text.switchLabel}
                </Link>
              </p>
            </form>
          </CardContent>
        )}
      </Card>
    </main>
  );
}
