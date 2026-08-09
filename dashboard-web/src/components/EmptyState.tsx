export const requiredFields = ["reason"] as const;

export function EmptyState({ title = "数据不足", reason }: { title?: string; reason: string }) {
  return (
    <section className="empty-state" role="status">
      <strong>{title}</strong>
      <p>{reason}</p>
    </section>
  );
}
