export default function Loading() {
  return (
    <div className="loading-state" aria-live="polite" aria-busy="true">
      <span aria-hidden="true" />
      <div>
        <strong>Loading your workspace</strong>
        <p>Getting the latest records.</p>
      </div>
    </div>
  );
}
