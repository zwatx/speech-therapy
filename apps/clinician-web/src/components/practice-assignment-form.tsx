"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import type { LearnerSummary } from "@speech-therapy/platform-data";

import { createPracticeAssignmentAction } from "@/app/assignments/actions";
import { assignmentFeedbackIsCurrent, initialAssignmentActionState } from "@/lib/portal-action-state";
import { AssignmentExercise } from "./assignment-exercise";
import "./assignment-workspace.css";

function AssignButton({ disabled }: { disabled: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button className="primary-action" disabled={disabled || pending} type="submit">
      {pending ? "Assigning…" : "Assign practice"}
    </button>
  );
}

export function PracticeAssignmentForm({
  learners,
  selectedLearnerId,
}: {
  learners: readonly LearnerSummary[];
  selectedLearnerId?: string | undefined;
}) {
  const [state, action, isPending] = useActionState(
    createPracticeAssignmentAction,
    initialAssignmentActionState,
  );
  const eligibleLearners = learners.filter(
    (learner) =>
      learner.latestConsent?.audioProcessing === true &&
      ["affirmed", "not-applicable"].includes(
        learner.latestConsent.assentStatus,
      ),
  );
  const requestedLearner = learners.find((learner) => learner.id === selectedLearnerId);
  const requestedIsEligible = eligibleLearners.some((learner) => learner.id === selectedLearnerId);
  const [learnerId, setLearnerId] = useState(
    selectedLearnerId
      ? requestedIsEligible ? selectedLearnerId : ""
      : "",
  );
  const [formRevision, setFormRevision] = useState(0);
  const [attemptTarget, setAttemptTarget] = useState("5");
  const [retryLimit, setRetryLimit] = useState("1");
  const [planFitConfirmed, setPlanFitConfirmed] = useState(false);
  function changed() {
    setFormRevision((revision) => revision + 1);
  }
  const selectedLearner = learners.find((learner) => learner.id === learnerId);
  const assignedLearner = learners.find((learner) => learner.id === state.assignedLearnerId);
  const showIneligible = Boolean(requestedLearner && !requestedIsEligible && !learnerId);
  const showFeedback = assignmentFeedbackIsCurrent(state, formRevision, isPending);
  const errorId = showFeedback && state.status === "error" ? "assignment-form-error" : undefined;

  return (
    <form action={action} className="consent-form assignment-form assignment-workflow">
      <div className="form-heading">
        <div>
          <p className="section-kicker">Audio practice</p>
          <h2>{selectedLearner ? `Prepare a practice dose for ${selectedLearner.displayLabel}` : "Prepare a practice dose"}</h2>
        </div>
        <span className="demo-notice">No pronunciation feedback</span>
      </div>

      <div className="assignment-step">
        <span className="assignment-step-number" aria-hidden="true">01</span>
        <div className="assignment-step-body">
          <label className="field-stack" htmlFor="assignment-learner">
            <span>Learner</span>
            <select
              aria-describedby={[errorId, showIneligible ? "assignment-learner-ineligible" : undefined].filter(Boolean).join(" ") || undefined}
              aria-invalid={showFeedback && state.status === "error" || undefined}
              disabled={eligibleLearners.length === 0}
              id="assignment-learner"
              name="learnerId"
              required
              value={learnerId}
              onChange={(event) => { setLearnerId(event.target.value); setPlanFitConfirmed(false); changed(); }}
            >
              {eligibleLearners.length === 0 ? (
                <option value="">No eligible learners yet</option>
              ) : (
                <>
                  {!learnerId ? <option value="">Choose an eligible learner</option> : null}
                  {eligibleLearners.map((learner) => (
                    <option key={learner.id} value={learner.id}>
                      {learner.displayLabel}
                    </option>
                  ))}
                </>
              )}
            </select>
          </label>
          {showIneligible ? (
            <p className="consent-warning" id="assignment-learner-ineligible">
              {requestedLearner?.displayLabel} cannot receive a new assignment until current audio consent and assent are recorded. Choose another eligible learner or update this learner&apos;s consent.
            </p>
          ) : null}
          {eligibleLearners.length === 0 ? (
            <p className="form-intro">
              Record current audio consent and learner assent before assigning practice.
            </p>
          ) : null}
        </div>
      </div>

      <input
        name="exerciseId"
        type="hidden"
        value="foundation-ball-initial-b-v1"
      />
      <input name="formRevision" type="hidden" value={formRevision} />
      <div className="assignment-step">
        <span className="assignment-step-number" aria-hidden="true">02</span>
        <div className="assignment-step-body">
          <p className="assignment-step-label">Available exercise</p>
          <AssignmentExercise />
          <div className="assignment-plan-fit">
            <p><span>Current plan target</span><strong>Check the learner&apos;s practice plan</strong></p>
            <p><span>Proposed exercise</span><strong>Beginning /b/ · ball</strong></p>
          </div>
          <label className="assignment-plan-confirm"><input type="checkbox" name="planFitConfirmed" value="true" checked={planFitConfirmed} disabled={!selectedLearner} onChange={(event) => { setPlanFitConfirmed(event.target.checked); changed(); }} /><span>I checked the learner&apos;s current practice plan and confirmed this exercise fits.</span></label>
          <p className="assignment-plan-hint">Confirm plan fit to enable assignment. The learner&apos;s plan target is not stored on this page.</p>
        </div>
      </div>

      <div className="assignment-step">
        <span className="assignment-step-number" aria-hidden="true">03</span>
        <div className="assignment-step-body">
          <p className="assignment-step-label">Practice dose</p>
          <div className="form-grid-two">
            <label className="field-stack" htmlFor="assignment-dose">
              <span>Accepted repetitions</span>
              <select
                aria-describedby={errorId}
                aria-invalid={showFeedback && state.status === "error" || undefined}
                value={attemptTarget}
                id="assignment-dose"
                name="attemptTarget"
                onChange={(event) => { setAttemptTarget(event.target.value); changed(); }}
              >
                {[3, 5, 8, 10].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-stack" htmlFor="assignment-retries">
              <span>Capture retries</span>
              <select
                aria-describedby={errorId}
                aria-invalid={showFeedback && state.status === "error" || undefined}
                value={retryLimit}
                id="assignment-retries"
                name="retryLimit"
                onChange={(event) => { setRetryLimit(event.target.value); changed(); }}
              >
                <option value="0">No retries</option>
                <option value="1">1 retry</option>
                <option value="2">2 retries</option>
              </select>
            </label>
          </div>
          <p className="consent-warning assignment-dose-warning">
            This replaces the learner&apos;s current practice dose and keeps its
            history. If consent changes, create a new assignment and link the device
            again. Retries address recording quality, not pronunciation.
          </p>
        </div>
      </div>
      {showFeedback ? (
        <p
          className={state.status === "error" ? "form-error" : "form-success"}
          id={state.status === "error" ? "assignment-form-error" : undefined}
          role={state.status === "error" ? "alert" : "status"}
        >
          {state.status === "success" && assignedLearner
            ? `${assignedLearner.displayLabel}: ${state.message}`
            : state.message}
        </p>
      ) : null}
      <AssignButton disabled={!learnerId || !planFitConfirmed} />
    </form>
  );
}
