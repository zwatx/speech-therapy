"use client";

import { useEffect, useRef } from "react";

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    console.error("Clinical workspace route failed", error);
    heading.current?.focus();
  }, [error]);

  return (
    <section className="route-error" aria-labelledby="route-error-heading">
      <p className="section-kicker">Workspace unavailable</p>
      <h1 id="route-error-heading" ref={heading} tabIndex={-1}>
        We couldn’t load this page.
      </h1>
      <p>
        Try again. If you just saved a change, check its status after the page
        reloads before submitting it again.
      </p>
      <button type="button" onClick={reset}>
        Try again
      </button>
    </section>
  );
}
