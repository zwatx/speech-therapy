"use client";

import { useState, type FormEvent } from "react";
import { learnerRows } from "@/lib/demo-data";
import { AssignmentExercise } from "./assignment-exercise";
import "./assignment-workspace.css";

export function PreviewAssignmentForm({ selectedLearnerId }: { selectedLearnerId?: string | undefined }) {
  const [summary, setSummary] = useState("");
  const [learnerId, setLearnerId] = useState(selectedLearnerId ?? "");
  const [planFitConfirmed, setPlanFitConfirmed] = useState(false);
  const selectedLearner = learnerRows.find((learner) => learner.id === learnerId);

  function previewAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const learner = learnerRows.find(({ id }) => id === values.get("learnerId"));
    if (!learner || !planFitConfirmed) return;
    const retries = values.get("retryLimit");
    setSummary(`${learner.displayName} · ball · ${values.get("attemptTarget")} repetitions · ${retries} ${retries === "1" ? "retry" : "retries"}. Nothing was saved or sent.`);
  }

  return (
    <form className="preview-assignment-form assignment-workflow" onSubmit={previewAssignment} onChange={() => setSummary("")}>
      <div className="form-heading"><div><p className="section-kicker">Audio practice</p><h2>{selectedLearner ? `Prepare a practice dose for ${selectedLearner.displayName}` : "Prepare a practice dose"}</h2></div><span className="demo-notice">Preview only</span></div>
      <p className="form-intro assignment-intro">Live assignment requires current audio consent and learner assent.</p>
      <div className="assignment-step">
        <span className="assignment-step-number" aria-hidden="true">01</span>
        <div className="assignment-step-body">
          <label className="field-stack" htmlFor="preview-learner">
            <span>Learner</span>
            <select id="preview-learner" name="learnerId" required value={learnerId} onChange={(event) => { setLearnerId(event.target.value); setPlanFitConfirmed(false); }}>
              {!learnerId ? <option value="">Choose a learner</option> : null}
              {learnerRows.map((learner) => <option key={learner.id} value={learner.id}>{learner.displayName}</option>)}
            </select>
          </label>
        </div>
      </div>
      <div className="assignment-step">
        <span className="assignment-step-number" aria-hidden="true">02</span>
        <div className="assignment-step-body">
          <p className="assignment-step-label">Available exercise</p>
          <AssignmentExercise />
          <div className="assignment-plan-fit">
            <p><span>Example learner target</span><strong>{selectedLearner?.target ?? "Select a learner"}</strong></p>
            <p><span>Proposed exercise</span><strong>Beginning /b/ · ball</strong></p>
          </div>
          <label className="assignment-plan-confirm"><input type="checkbox" checked={planFitConfirmed} disabled={!selectedLearner} onChange={(event) => setPlanFitConfirmed(event.target.checked)} /><span>I checked the learner&apos;s current practice plan and confirmed this exercise fits.</span></label>
          <p className="assignment-plan-hint">The example target is illustrative; check the current plan before previewing.</p>
        </div>
      </div>
      <div className="assignment-step">
        <span className="assignment-step-number" aria-hidden="true">03</span>
        <div className="assignment-step-body">
          <p className="assignment-step-label">Practice dose</p>
          <div className="form-grid-two">
            <label className="field-stack" htmlFor="preview-repetitions"><span>Accepted repetitions</span><select id="preview-repetitions" name="attemptTarget" defaultValue="5">{[3, 5, 8, 10].map((count) => <option key={count} value={count}>{count}</option>)}</select></label>
            <label className="field-stack" htmlFor="preview-retries"><span>Capture retries</span><select id="preview-retries" name="retryLimit" defaultValue="1"><option value="0">No retries</option><option value="1">1 retry</option><option value="2">2 retries</option></select></label>
          </div>
          <p className="form-intro">Retries address recording quality. Changing consent ends device access; create a new assignment and link the device again before practice resumes.</p>
        </div>
      </div>
      <button className="primary-action" type="submit" disabled={!learnerId || !planFitConfirmed}>Preview assignment</button>
      <div className="preview-result" role="status">{summary}</div>
    </form>
  );
}
