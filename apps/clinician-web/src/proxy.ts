import { clerkMiddleware } from "@clerk/nextjs/server";
import { type NextFetchEvent, type NextRequest, NextResponse } from "next/server";
import { isPreviewView } from "./lib/preview-navigation";
import { previewLearnerRecords } from "./lib/preview-learner-records";

// Proxy attaches verified Clerk request context only. Every page, Route Handler,
// and Server Action that touches clinical data independently resolves the active
// organization to an internal tenant membership; path matching is never an
// authorization boundary.
const withClerk = clerkMiddleware();

export default function proxy(request: NextRequest, event: NextFetchEvent) {
  if (request.nextUrl.pathname === "/accessibility-preview"
    || request.nextUrl.pathname.startsWith("/accessibility-preview/")) {
    const auditEnabled = process.env.NODE_ENV !== "production"
      && process.env.CADENCE_ACCESSIBILITY_AUDIT_MODE === "1";
    const knownView = request.nextUrl.pathname === "/accessibility-preview"
      || isPreviewView(request.nextUrl.pathname.slice("/accessibility-preview/".length));
    const rootViews = request.nextUrl.searchParams.getAll("view");
    const knownRootView = request.nextUrl.pathname !== "/accessibility-preview"
      || rootViews.length === 0 || (rootViews.length === 1 && rootViews[0] === "overview");
    const learnerIds = request.nextUrl.searchParams.getAll("learner");
    const knownLearner = learnerIds.length === 0 || (
      (request.nextUrl.pathname === "/accessibility-preview/learners"
        || request.nextUrl.pathname === "/accessibility-preview/review"
        || request.nextUrl.pathname === "/accessibility-preview/assignments")
      && learnerIds.length === 1
      && previewLearnerRecords.some((record) => record.id === learnerIds[0])
    );
    return auditEnabled && knownView && knownRootView && knownLearner
      ? NextResponse.next()
      : new NextResponse("Not found", { status: 404 });
  }
  return withClerk(request, event);
}

export const config = {
  matcher: [
    "/((?!access(?:/|$)|_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico)).*)",
    "/(api)(.*)",
  ],
};
