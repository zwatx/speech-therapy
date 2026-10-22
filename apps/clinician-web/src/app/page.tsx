import { OverviewWorkspace } from "@/components/overview-workspace";
import { loadOverviewData } from "@/lib/overview-data";
import { requirePortalActor } from "@/lib/portal-page-access";
import { getPlatformDataService } from "@/lib/platform-runtime";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const actor = await requirePortalActor();
  const data = await loadOverviewData(actor, getPlatformDataService());
  return <OverviewWorkspace data={data} />;
}
