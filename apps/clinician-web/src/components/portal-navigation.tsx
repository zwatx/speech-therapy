"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { canonicalPortalPath } from "@/lib/preview-navigation";
import { PortalIcon } from "./portal-icon";
import { PortalLink } from "./portal-link";

const navigation = [
  { href: "/", label: "Practice", icon: "overview" },
  { href: "/learners", label: "Learners", icon: "learners" },
  { href: "/assignments", label: "Assignments", icon: "assignments" },
  { href: "/review", label: "Attempt review", icon: "review" },
  { href: "/safety", label: "Safety desk", icon: "safety" },
] as const;

function current(pathname: string, href: string): boolean {
  return href === "/" ? pathname === href : pathname.startsWith(`${href}/`) || pathname === href;
}

export function PortalNavigation({ mobile = false }: { mobile?: boolean }) {
  const pathname = canonicalPortalPath(usePathname());
  return (
    <nav
      aria-label={mobile ? "Mobile primary navigation" : "Primary"}
      className={mobile ? undefined : "primary-nav"}
      onClick={mobile ? (event) => {
        if (event.target instanceof Element && event.target.closest("a")) {
          event.currentTarget.closest("details")?.removeAttribute("open");
        }
      } : undefined}
    >
      {navigation.map((item) => (
        <PortalLink
          aria-current={current(pathname, item.href) ? "page" : undefined}
          href={item.href}
          key={item.href}
        >
          {!mobile ? <PortalIcon name={item.icon} /> : null}
          {item.label}
        </PortalLink>
      ))}
      {mobile ? (
        <>
          <PortalLink
            aria-current={current(pathname, "/settings/privacy") ? "page" : undefined}
            href="/settings/privacy"
          >
            Privacy controls
          </PortalLink>
        </>
      ) : null}
    </nav>
  );
}

export function PortalPrivacyLink({ children }: { children: ReactNode }) {
  const pathname = canonicalPortalPath(usePathname());
  return (
    <PortalLink
      aria-current={current(pathname, "/settings/privacy") ? "page" : undefined}
      href="/settings/privacy"
    >
      {children}
    </PortalLink>
  );
}
