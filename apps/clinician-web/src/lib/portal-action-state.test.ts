import assert from "node:assert/strict";
import test from "node:test";

import { assignmentFeedbackIsCurrent } from "./portal-action-state.ts";

test("assignment feedback only describes the currently submitted form values", () => {
  const successfulSubmission = {
    status: "success" as const,
    message: "Assignment v2 is active.",
    formRevision: "4",
    assignedLearnerId: "learner-a",
  };

  assert.equal(assignmentFeedbackIsCurrent(successfulSubmission, 4, false), true);
  assert.equal(assignmentFeedbackIsCurrent(successfulSubmission, 4, true), false);
  assert.equal(assignmentFeedbackIsCurrent(successfulSubmission, 5, false), false);
  assert.equal(assignmentFeedbackIsCurrent({ ...successfulSubmission, formRevision: undefined }, 4, false), false);

  const failedSubmission = {
    status: "error" as const,
    message: "Consent has changed.",
    formRevision: "4",
  };
  assert.equal(assignmentFeedbackIsCurrent(failedSubmission, 4, false), true);
  assert.equal(assignmentFeedbackIsCurrent(failedSubmission, 5, false), false);
});
