import type { SafetyItemData } from "@/lib/demo-data";
import "./safety-privacy-workspace.css";

interface SafetyQueueProps {
  items: readonly SafetyItemData[];
}

export function SafetyQueue({ items }: SafetyQueueProps) {
  return (
    <ul className="safety-list">
      {items.map((item) => (
        <li key={item.id}>
          <span className="safety-count">
            <span aria-hidden="true">
              {item.count.toString().padStart(2, "0")}
            </span>
            <span className="sr-only">{item.countLabel}</span>
          </span>
          <div>
            <span className="safety-category">{item.category}</span>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
          <span className="review-label">Human review</span>
        </li>
      ))}
    </ul>
  );
}
