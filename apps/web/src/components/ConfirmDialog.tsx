import { AlertTriangle, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

type Props = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busy?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  busy = false,
  error,
  onCancel,
  onConfirm,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      onCancel={(event) => {
        if (busy) {
          event.preventDefault();
          return;
        }
        onCancel();
      }}
      onClose={() => {
        if (open && !busy) onCancel();
      }}
    >
      <button
        type="button"
        className="icon-button dialog-close"
        aria-label="Close dialog"
        disabled={busy}
        onClick={onCancel}
      >
        <X aria-hidden="true" size={20} />
      </button>
      <div className="dialog-icon" aria-hidden="true">
        <AlertTriangle size={22} />
      </div>
      <h2 id={titleId}>{title}</h2>
      <p id={descriptionId} className="muted">
        {description}
      </p>
      {error ? (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="button button-danger" disabled={busy} onClick={onConfirm}>
          {busy ? "Deleting…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
