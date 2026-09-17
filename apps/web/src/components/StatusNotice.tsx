import { AlertCircle, CheckCircle2, Info, Undo2 } from "lucide-react";
import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  variant?: "info" | "success" | "error";
  actionLabel?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
};

export function StatusNotice({ children, variant = "info", actionLabel, onAction, actionDisabled = false }: Props) {
  const Icon = variant === "error" ? AlertCircle : variant === "success" ? CheckCircle2 : Info;
  return (
    <div className={`notice notice-${variant}`} role={variant === "error" ? "alert" : "status"}>
      <Icon aria-hidden="true" size={18} />
      <span>{children}</span>
      {actionLabel && onAction ? (
        <button type="button" className="notice-action" disabled={actionDisabled} onClick={onAction}>
          {actionLabel === "Undo" ? <Undo2 aria-hidden="true" size={16} /> : null}
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
