"use client";

import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import type { LearnerDeviceSessionSummary } from "@speech-therapy/platform-data";
import {
  maximumActorTokenGenerationsPerHour,
  maximumLearnerTokenGenerationsPerHour,
} from "@speech-therapy/platform-data/device-session-policy";

import {
  revokeDeviceSessionAction,
  rotateDeviceSessionAction,
} from "@/app/learners/[learnerId]/actions";
import {
  initialDeviceSessionActionState,
  initialPortalActionState,
} from "@/lib/portal-action-state";

const statusCopy = {
  active: "Active",
  expired: "Expired",
  revoked: "Revoked",
  inactive: "Inactive",
  "consent-invalidated": "Consent changed",
} as const;

function date(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(new Date(value));
}

function RevokeButton({ disabled, label }: { disabled: boolean; label: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      aria-label={label}
      className="danger-action"
      disabled={disabled || pending}
      type="submit"
    >
      {pending ? "Revoking…" : "Revoke access"}
    </button>
  );
}

function RotateButton({ disabled, label }: { disabled: boolean; label: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      aria-label={label}
      className="secondary-action"
      disabled={disabled || pending}
      type="submit"
    >
      {pending ? "Replacing…" : "Replace link code"}
    </button>
  );
}

function DeviceSessionRow({
  canManage,
  learnerId,
  session,
}: {
  canManage: boolean;
  learnerId: string;
  session: LearnerDeviceSessionSummary;
}) {
  const boundAction = revokeDeviceSessionAction.bind(
    null,
    learnerId,
    session.id,
  );
  const [revokeState, revokeAction] = useActionState(
    boundAction,
    initialPortalActionState,
  );
  const boundRotateAction = rotateDeviceSessionAction.bind(
    null,
    learnerId,
    session.id,
  );
  const [rotateState, rotateAction] = useActionState(
    boundRotateAction,
    initialDeviceSessionActionState,
  );
  const [revokeConfirmed, setRevokeConfirmed] = useState(false);
  const [rotateConfirmed, setRotateConfirmed] = useState(false);
  const rotated = rotateState.status === "success" && Boolean(rotateState.token);
  const active = session.status === "active";
  const actionable = active && !rotated;
  const revokeConfirmationId = `revoke-${session.id}`;
  const rotateConfirmationId = `rotate-${session.id}`;
  const rotationLifetimeId = `rotate-lifetime-${session.id}`;

  return (
    <li>
      <div className="device-session-heading">
        <strong>Issued {date(session.createdAt)} UTC</strong>
        <span
          className={`status-label ${actionable ? "status-on-track" : "status-not-started"}`}
        >
          {rotated ? "Replaced" : statusCopy[session.status]}
        </span>
      </div>
      <p>
        Consent v{session.consentVersion} · expires {date(session.expiresAt)} UTC
      </p>
      <code>Access record …{session.id.slice(-8)}</code>
      {session.revokedAt ? (
        <small>Revoked {date(session.revokedAt)} UTC</small>
      ) : null}
      {canManage && actionable ? (
        <details className="device-session-rotation">
          <summary>Replace this link code</summary>
          <form action={rotateAction} className="device-session-rotation-form">
            <p>
              The old code stops working as soon as the replacement is created.
              If this request is interrupted, do not assume either code works:
              refresh, find the newest active record, then replace or revoke it again.
              Creating or replacing codes is limited to {maximumLearnerTokenGenerationsPerHour}
              per learner and {maximumActorTokenGenerationsPerHour} per clinician each UTC hour.
              You can still revoke access when either limit is reached.
            </p>
            <label className="field-stack" htmlFor={rotationLifetimeId}>
              <span>Replacement access window</span>
              <select
                defaultValue="24"
                id={rotationLifetimeId}
                name="lifetimeHours"
              >
                <option value="1">1 hour</option>
                <option value="8">8 hours</option>
                <option value="24">24 hours</option>
                <option value="72">72 hours</option>
              </select>
            </label>
            <label
              className="device-session-confirmation"
              htmlFor={rotateConfirmationId}
            >
              <input
                checked={rotateConfirmed}
                id={rotateConfirmationId}
                name="confirmation"
                onChange={(event) => setRotateConfirmed(event.target.checked)}
                type="checkbox"
              />
              <span>I understand the old link code stops working immediately.</span>
            </label>
            <RotateButton
              disabled={!rotateConfirmed}
              label={`Replace device link code for consent version ${session.consentVersion}, record ending ${session.id.slice(-8)}`}
            />
          </form>
        </details>
      ) : null}
      {rotateState.message ? (
        <p
          className={rotateState.status === "error" ? "form-error" : "form-success"}
          role={rotateState.status === "error" ? "alert" : "status"}
        >
          {rotateState.message}
        </p>
      ) : null}
      {rotateState.token && rotateState.expiresAt ? (
        <div className="token-receipt" aria-live="polite">
          <span>Replacement shown once</span>
          <code>{rotateState.token}</code>
          <p>
            Expires {date(rotateState.expiresAt)} UTC. Enter it directly on the
            learner device before refreshing this page.
          </p>
        </div>
      ) : null}
      {canManage && actionable ? (
        <form action={revokeAction} className="device-session-revoke-form">
          <label
            className="device-session-confirmation"
            htmlFor={revokeConfirmationId}
          >
            <input
              checked={revokeConfirmed}
              id={revokeConfirmationId}
              name="confirmation"
              onChange={(event) => setRevokeConfirmed(event.target.checked)}
              type="checkbox"
            />
            <span>This device must be linked again after access is revoked.</span>
          </label>
          <RevokeButton
            disabled={!revokeConfirmed}
            label={`Revoke device access for consent version ${session.consentVersion}, record ending ${session.id.slice(-8)}`}
          />
        </form>
      ) : null}
      {revokeState.message ? (
        <p
          className={revokeState.status === "error" ? "form-error" : "form-success"}
          role={revokeState.status === "error" ? "alert" : "status"}
        >
          {revokeState.message}
        </p>
      ) : null}
    </li>
  );
}

export function DeviceSessionList({
  canManage,
  learnerId,
  sessions,
}: {
  canManage: boolean;
  learnerId: string;
  sessions: readonly LearnerDeviceSessionSummary[];
}) {
  return (
    <div className="device-session-history">
      <h3>Device links</h3>
      <p className="device-session-scope">
        Every active access record and up to 25 recent inactive records are shown.
      </p>
      {sessions.length === 0 ? (
        <p className="read-only-note">No device access has been issued.</p>
      ) : (
        <ul className="device-session-list">
          {sessions.map((session) => (
            <DeviceSessionRow
              canManage={canManage}
              key={session.id}
              learnerId={learnerId}
              session={session}
            />
          ))}
        </ul>
      )}
      {!canManage && sessions.some((session) => session.status === "active") ? (
        <p className="read-only-note">
          Reviewer roles cannot replace or revoke device access.
        </p>
      ) : null}
    </div>
  );
}
