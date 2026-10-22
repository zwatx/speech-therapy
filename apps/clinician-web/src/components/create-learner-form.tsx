"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { createLearnerAction } from "@/app/learners/actions";
import { initialPortalActionState } from "@/lib/portal-action-state";

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button className="primary-action" disabled={pending} type="submit">
      {pending ? "Creating…" : "Create learner record"}
    </button>
  );
}

export function CreateLearnerForm() {
  const [state, action] = useActionState(
    createLearnerAction,
    initialPortalActionState,
  );
  return (
    <form action={action} className="workspace-form">
      <div>
        <p className="section-kicker">New learner</p>
        <h2>Add a learner</h2>
        <p className="form-intro">
          Use the clinic-approved display label. Do not enter a birth date,
          diagnosis, or full legal name here.
        </p>
      </div>
      <label htmlFor="display-label">Display label</label>
      <input
        autoComplete="off"
        aria-describedby={state.status === "error"
          ? "display-label-help create-learner-error"
          : "display-label-help"}
        aria-invalid={state.status === "error"}
        id="display-label"
        maxLength={120}
        name="displayLabel"
        placeholder="Example: Avery M."
        required
      />
      <p className="field-help" id="display-label-help">
        Consent is recorded separately after creation.
      </p>
      {state.status === "error" ? (
        <p className="form-error" id="create-learner-error" role="alert">
          {state.message}
        </p>
      ) : null}
      <SubmitButton />
    </form>
  );
}
