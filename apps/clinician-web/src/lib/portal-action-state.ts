export interface PortalActionState {
  readonly status: "idle" | "error" | "success";
  readonly message?: string;
}

export const initialPortalActionState: PortalActionState = { status: "idle" };

export interface AssignmentActionState extends PortalActionState {
  readonly formRevision?: string | undefined;
  readonly assignedLearnerId?: string;
}

export const initialAssignmentActionState: AssignmentActionState = {
  status: "idle",
};

export function assignmentFeedbackIsCurrent(
  state: AssignmentActionState,
  formRevision: number,
  isPending: boolean,
): boolean {
  return Boolean(state.message && state.status !== "idle" && !isPending &&
    state.formRevision === String(formRevision));
}

export interface DeviceSessionActionState extends PortalActionState {
  readonly token?: string;
  readonly expiresAt?: string;
}

export const initialDeviceSessionActionState: DeviceSessionActionState = {
  status: "idle",
};
