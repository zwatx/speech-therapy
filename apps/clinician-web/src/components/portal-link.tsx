"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ComponentProps } from "react";
import { portalHref } from "@/lib/preview-navigation";

export function PortalLink({ href, ...props }: Omit<ComponentProps<typeof Link>, "href"> & { href: string }) {
  return <Link {...props} href={portalHref(href, usePathname())} />;
}
