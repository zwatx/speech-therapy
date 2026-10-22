import Link from "next/link";

export default function NotFound() {
  return (
    <section className="route-error" aria-labelledby="not-found-heading">
      <p className="section-kicker">Not found</p>
      <h1 id="not-found-heading">Page not found.</h1>
      <p>Check the link, or return to your practice workspace.</p>
      <Link className="primary-action" href="/">
        Return to overview
      </Link>
    </section>
  );
}
