"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import { deleteLearnerAction } from "@/app/learners/[learnerId]/actions";
import { initialPortalActionState } from "@/lib/portal-action-state";

function DeleteButton({ disabled }: { disabled: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button className="danger-action" disabled={disabled || pending} type="submit">
      {pending ? "Deleting…" : "Delete learner data"}
    </button>
  );
}

export function LearnerDataControls({
  learnerId,
  canExport,
  canDelete,
}: {
  learnerId: string;
  canExport: boolean;
  canDelete: boolean;
}) {
  const [exportMessage, setExportMessage] = useState<string>();
  const [exporting, setExporting] = useState(false);
  const boundDelete = deleteLearnerAction.bind(null, learnerId);
  const [deleteState, deleteAction] = useActionState(
    boundDelete,
    initialPortalActionState,
  );

  async function exportData() {
    setExporting(true);
    setExportMessage(undefined);
    try {
      const response = await fetch(`/api/v1/learners/${learnerId}/export`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: "{}",
      });
      if (!response.ok) throw new Error("export rejected");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `cadence-learner-${learnerId}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setExportMessage("Export prepared. Store the file only in an approved location.");
    } catch {
      setExportMessage("The export could not be prepared safely.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="data-controls">
      <button
        className="secondary-action"
        disabled={!canExport || exporting}
        onClick={exportData}
        type="button"
      >
        {exporting ? "Preparing export…" : "Export learner data"}
      </button>
      {!canExport ? (
        <p className="form-error">Reviewer roles cannot create data exports.</p>
      ) : null}
      {exportMessage ? <p role="status">{exportMessage}</p> : null}

      <form action={deleteAction} className="deletion-form">
        <label className="field-stack" htmlFor="deletion-confirmation">
          <span>Owner-only deletion confirmation</span>
          <input
            autoComplete="off"
            aria-describedby={deleteState.status === "error"
              ? "deletion-confirmation-help deletion-confirmation-error"
              : "deletion-confirmation-help"}
            aria-invalid={deleteState.status === "error"}
            disabled={!canDelete}
            id="deletion-confirmation"
            name="confirmation"
            placeholder="DELETE LEARNER DATA"
          />
        </label>
        <p id="deletion-confirmation-help">
          Type <code>DELETE LEARNER DATA</code> exactly. This action
          pseudonymizes the learner and removes device sessions and derived
          attempts. Consent snapshots, practice assignments, audit events,
          research artifact-lineage records, and quarantine evidence remain.
          Linked research artifacts are blocked from further use; external
          deletion or remediation actions are tracked separately and may still
          be pending.
        </p>
        {!canDelete ? (
          <p className="form-error">Only a tenant owner can delete this record.</p>
        ) : null}
        {deleteState.message ? (
          <p className="form-error" id="deletion-confirmation-error" role="alert">
            {deleteState.message}
          </p>
        ) : null}
        <DeleteButton disabled={!canDelete} />
      </form>
    </div>
  );
}
