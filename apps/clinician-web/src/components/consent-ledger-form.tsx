"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import type { LearnerConsentSummary } from "@speech-therapy/platform-data";

import { saveConsentAction } from "@/app/learners/[learnerId]/actions";
import { initialPortalActionState } from "@/lib/portal-action-state";

function SaveButton() {
  const { pending } = useFormStatus();
  return (
    <button className="primary-action" disabled={pending} type="submit">
      {pending ? "Saving consent…" : "Save consent choices"}
    </button>
  );
}

export function ConsentLedgerForm({
  learnerId,
  current,
}: {
  learnerId: string;
  current: LearnerConsentSummary | undefined;
}) {
  const boundAction = saveConsentAction.bind(null, learnerId);
  const [state, action] = useActionState(
    boundAction,
    initialPortalActionState,
  );
  const [assent, setAssent] = useState(
    current?.assentStatus ?? "affirmed",
  );
  const [audio, setAudio] = useState(current?.audioProcessing ?? false);
  const [review, setReview] = useState(current?.clinicianReview ?? false);
  const [research, setResearch] = useState(current?.researchUse ?? false);
  const processingPermitted = assent === "affirmed" || assent === "not-applicable";

  function changeAssent(value: LearnerConsentSummary["assentStatus"]) {
    setAssent(value);
    if (value === "declined" || value === "withdrawn") {
      setAudio(false);
      setReview(false);
      setResearch(false);
    }
  }

  return (
    <form action={action} className="consent-form">
      <div className="form-heading">
        <div>
          <p className="section-kicker">Consent update</p>
          <h3>Practice permissions</h3>
        </div>
        <span className="demo-notice">Practice notice v1</span>
      </div>

      <label className="field-stack" htmlFor="assent-status">
        <span>Learner assent status</span>
        <select
          id="assent-status"
          name="assentStatus"
          onChange={(event) => {
            const value = event.target.value;
            if (
              value === "affirmed" ||
              value === "not-applicable" ||
              value === "declined" ||
              value === "withdrawn"
            ) {
              changeAssent(value);
            }
          }}
          value={assent}
        >
          <option value="affirmed">Affirmed</option>
          <option value="not-applicable">Not applicable</option>
          <option value="declined">Declined</option>
          <option value="withdrawn">Withdrawn</option>
        </select>
      </label>

      <fieldset className="choice-list">
        <legend>Separate processing choices</legend>
        <label className={!processingPermitted ? "choice-disabled" : undefined}>
          <input
            checked={audio}
            disabled={!processingPermitted}
            name="audioProcessing"
            onChange={(event) => setAudio(event.target.checked)}
            type="checkbox"
          />
          <span>
            <strong>Practice audio processing</strong>
            <small>Required before a learner device can practice.</small>
          </span>
        </label>
        <label aria-disabled="true" className="choice-disabled">
          <input checked={false} disabled type="checkbox" />
          <span>
            <strong>Visual cue processing</strong>
            <small>Unavailable until a target and visual protocol are validated.</small>
          </span>
        </label>
        <label className={!processingPermitted ? "choice-disabled" : undefined}>
          <input
            checked={review}
            disabled={!processingPermitted}
            name="clinicianReview"
            onChange={(event) => setReview(event.target.checked)}
            type="checkbox"
          />
          <span>
            <strong>Clinician review</strong>
            <small>Review derived capture details. Recordings are not retained.</small>
          </span>
        </label>
        <label className={!processingPermitted ? "choice-disabled" : undefined}>
          <input
            checked={research}
            disabled={!processingPermitted}
            name="researchUse"
            onChange={(event) => setResearch(event.target.checked)}
            type="checkbox"
          />
          <span>
            <strong>Research contribution</strong>
            <small>Off unless explicitly chosen; never inferred from practice.</small>
          </span>
        </label>
      </fieldset>

      <p className="consent-warning">
        Declined or withdrawn assent turns every processing choice off. Saving
        these choices ends existing device access and keeps the consent history.
        Create a new assignment and device link before practice resumes.
      </p>
      {state.message ? (
        <p
          className={state.status === "error" ? "form-error" : "form-success"}
          role={state.status === "error" ? "alert" : "status"}
        >
          {state.message}
        </p>
      ) : null}
      <SaveButton />
    </form>
  );
}
