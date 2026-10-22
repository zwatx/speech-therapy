import Link from "next/link";
import "./access-workspace.css";

export const metadata = { title: "Clinic access" };

const copy: Record<string, { title: string; detail: string }> = {
  "authentication-required": {
    title: "Sign in through your clinic.",
    detail:
      "This workspace requires an authenticated clinician account before any learner record can be opened.",
  },
  "organization-required": {
    title: "Choose a clinic organization.",
    detail:
      "Cadence binds every learner read and write to the active clinic organization. Select one in your identity provider, then return.",
  },
  "membership-required": {
    title: "Your clinic membership is not active.",
    detail:
      "Ask a clinic owner to provision or reactivate your membership. Cadence does not infer access from an email domain.",
  },
  "platform-not-configured": {
    title: "Clinical data services are not configured.",
    detail:
      "Connect Clerk identity mapping and the reviewed Postgres application role before this workspace can handle learner records.",
  },
};

export default async function AccessPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}) {
  const { reason = "authentication-required" } = await searchParams;
  const message = Object.hasOwn(copy, reason)
    ? copy[reason]!
    : copy["authentication-required"]!;
  return (
    <div className="access-page">
      <section className="access-panel" aria-labelledby="access-heading">
        <p className="section-kicker">Protected clinical workspace</p>
        <h1 id="access-heading">{message.title}</h1>
        <p>{message.detail}</p>
        <Link className="primary-action" href="/">
          Try workspace again
        </Link>
      </section>
    </div>
  );
}
