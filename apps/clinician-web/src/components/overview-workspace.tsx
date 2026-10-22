"use client";

import { useState } from "react";

import type { OverviewData, OverviewLearner } from "@/lib/overview-data";
import { PortalIcon } from "./portal-icon";
import { PortalLink } from "./portal-link";
import "./overview-workspace.css";

export function OverviewWorkspace({ data }: { data: OverviewData }) {
  const preview = data.mode === "preview";
  const [query, setQuery] = useState("");
  const [reviewOnly, setReviewOnly] = useState(false);
  const learners = data.learners.filter((learner) =>
    (!reviewOnly || learner.reviewAvailable)
    && (learner.displayName + " " + learner.target).toLowerCase().includes(query.trim().toLowerCase()),
  );

  function recordHref(learner: OverviewLearner) {
    return preview
      ? "/learners?learner=" + encodeURIComponent(learner.id)
      : "/learners/" + encodeURIComponent(learner.id);
  }

  function assignmentHref(learner: OverviewLearner) {
    return "/assignments?learner=" + encodeURIComponent(learner.id) + "#assignment-form";
  }

  return (
    <div className="notebook-workspace">
      <header className="notebook-header">
        <h1>Practice overview</h1>
      </header>
      <p className="notebook-disclosure">
        <span className="notebook-disclosure-inner">
          <strong>{preview ? "Demo workspace" : "Clinic workspace"}</strong>
          {preview ? "Fictional records · no patient data" : "Recorded activity · no clinical progress assessment"}
        </span>
      </p>
      <section className="notebook-caseload" aria-labelledby="notebook-caseload-heading">
        <div className="notebook-toolbar">
          <div className="notebook-section-heading">
            <h2 id="notebook-caseload-heading">Learners</h2>
            <span>{data.learners.length} records</span>
          </div>
          <div className="notebook-controls">
            <label className="notebook-search">
              <span className="sr-only">{preview ? "Search demo learners" : "Search learners"}</span>
              <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a learner or target" />
              <span aria-hidden="true"><PortalIcon name="search" /></span>
            </label>
            <div className="notebook-filters" role="group" aria-label="Filter learners">
              <button type="button" aria-pressed={!reviewOnly} onClick={() => setReviewOnly(false)}>All learners</button>
              <button type="button" aria-pressed={reviewOnly} onClick={() => setReviewOnly(true)}>Review available</button>
            </div>
          </div>
        </div>
        <p className="sr-only" role="status">{learners.length} learners shown</p>
        <div className="notebook-column-headings" aria-hidden="true">
          <span>Learner</span><span>{preview ? "Example target" : "Assigned target"}</span><span>Last practice</span>
          <span>Attempts</span><span>Review</span><span>Open</span>
        </div>
        {learners.length ? (
          <ol className="notebook-learner-list" aria-label="Learner practice records">
            {learners.map((learner, index) => (
              <li className="notebook-learner-row" key={learner.id}>
                <div className="notebook-learner-name">
                  <span className="notebook-row-index" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                  <PortalLink href={recordHref(learner)}>{learner.displayName}</PortalLink>
                </div>
                <div className="notebook-learner-target"><span className="sr-only">{preview ? "Example target: " : "Assigned target: "}</span>{learner.target}</div>
                <div className="notebook-learner-activity">
                  <div className="notebook-learner-date"><span className="notebook-mobile-label" aria-hidden="true">Last practice </span><span className="sr-only">Last practice: </span>{learner.lastPractice}</div>
                  <div className="notebook-learner-attempts"><span className="notebook-mobile-label" aria-hidden="true">Attempts </span><span className="sr-only">Recorded attempts: </span>{learner.attempts}</div>
                  <div className={learner.reviewAvailable ? "notebook-learner-review is-available" : "notebook-learner-review"}><span className="notebook-mobile-label" aria-hidden="true">Review </span><span className="sr-only">Review: </span>{learner.reviewAvailable ? "Available" : "None listed"}</div>
                </div>
                <div className="notebook-learner-actions">
                  {learner.reviewAvailable ? <PortalLink href={"/review?learner=" + encodeURIComponent(learner.id)}>Review attempts<span aria-hidden="true">→</span></PortalLink> : null}
                  {!learner.reviewAvailable && data.canManageAssignments ? (
                    <PortalLink href={assignmentHref(learner)}>{preview ? "Preview assignment" : learner.target === "No current assignment" ? "Assign target" : "Manage assignment"}<span aria-hidden="true">→</span></PortalLink>
                  ) : !learner.reviewAvailable ? <PortalLink href={recordHref(learner)}>Open record<span aria-hidden="true">→</span></PortalLink> : null}
                </div>
              </li>
            ))}
          </ol>
        ) : <p className="notebook-empty">{data.learners.length === 0 ? "No learners are recorded for this clinic. Open learner records to get started." : "No learners match this view."}</p>}
        <p className="notebook-footnote">Attempts count recorded activity, not dose completion or pronunciation accuracy. Review availability reflects recent authorized records; recordings are not retained.</p>
      </section>
    </div>
  );
}
