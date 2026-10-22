"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import {
  maximumActiveLearnerDeviceSessions,
  maximumActorTokenGenerationsPerHour,
  maximumLearnerTokenGenerationsPerHour,
} from "@speech-therapy/platform-data/device-session-policy";

import { issueDeviceSessionAction } from "@/app/learners/[learnerId]/actions";
import { initialDeviceSessionActionState } from "@/lib/portal-action-state";

function IssueButton({ disabled }: { disabled: boolean }) {
  const { pending } = useFormStatus();
  return (
    <button className="primary-action" disabled={disabled || pending} type="submit">
      {pending ? "Creating code…" : "Create device link code"}
    </button>
  );
}

export function DeviceSessionForm({
  learnerId,
  eligible,
  activeCount,
}: {
  learnerId: string;
  eligible: boolean;
  activeCount: number;
}) {
  const boundAction = issueDeviceSessionAction.bind(null, learnerId);
  const [state, action] = useActionState(
    boundAction,
    initialDeviceSessionActionState,
  );
  const atLimit = activeCount >= maximumActiveLearnerDeviceSessions;
  return (
    <form action={action} className="compact-form">
      <p className="form-intro">
        A link code connects the learner&apos;s device using their current consent.
        Changing consent ends that access. Each learner can have up to {maximumActiveLearnerDeviceSessions}
        active device links. Creating or replacing codes is limited to {maximumLearnerTokenGenerationsPerHour}
        per learner and {maximumActorTokenGenerationsPerHour} per clinician each UTC hour.
      </p>
      <label className="field-stack" htmlFor="lifetime-hours">
        <span>Access window</span>
        <select defaultValue="24" id="lifetime-hours" name="lifetimeHours">
          <option value="1">1 hour</option>
          <option value="8">8 hours</option>
          <option value="24">24 hours</option>
          <option value="72">72 hours</option>
        </select>
      </label>
      {!eligible ? (
        <p className="form-error" role="status">
          Enable audio consent and record assent as affirmed or not applicable first.
        </p>
      ) : null}
      {eligible && atLimit ? (
        <p className="form-error" role="status">
          Revoke an existing device link or replace its code before creating another.
        </p>
      ) : null}
      {state.message ? (
        <p
          className={state.status === "error" ? "form-error" : "form-success"}
          role={state.status === "error" ? "alert" : "status"}
        >
          {state.message}
        </p>
      ) : null}
      {state.token && state.expiresAt ? (
        <div className="token-receipt" aria-live="polite">
          <span>Shown once</span>
          <code>{state.token}</code>
          <p>
            Expires {new Date(state.expiresAt).toLocaleString("en-US", {
              dateStyle: "medium",
              timeStyle: "short",
              timeZone: "UTC",
            })} UTC. Enter
            it directly on the learner device; do not place it in email or notes.
          </p>
        </div>
      ) : null}
      <IssueButton disabled={!eligible || atLimit} />
    </form>
  );
}
