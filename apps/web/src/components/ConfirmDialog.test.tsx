import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

const originalShowModal = HTMLDialogElement.prototype.showModal;
const originalClose = HTMLDialogElement.prototype.close;
const showModal = vi.fn(function show(this: HTMLDialogElement) {
  this.setAttribute("open", "");
});
const close = vi.fn(function closeDialog(this: HTMLDialogElement) {
  this.removeAttribute("open");
});

beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: showModal,
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: close,
  });
});

afterEach(() => {
  cleanup();
  showModal.mockClear();
  close.mockClear();
});

afterAll(() => {
  if (originalShowModal) {
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
      configurable: true,
      value: originalShowModal,
    });
  } else {
    Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  }
  if (originalClose) {
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
      configurable: true,
      value: originalClose,
    });
  } else {
    Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
  }
});

function renderDialog(
  overrides: Partial<ComponentProps<typeof ConfirmDialog>> = {},
) {
  const props: ComponentProps<typeof ConfirmDialog> = {
    open: true,
    title: "Delete Mountain loop?",
    description: "This permanently removes the trip and its route.",
    confirmLabel: "Delete trip",
    onCancel: vi.fn(),
    onConfirm: vi.fn(),
    ...overrides,
  };
  return { props, ...render(<ConfirmDialog {...props} />) };
}

describe("ConfirmDialog", () => {
  it("opens as a named modal with a useful accessible description", () => {
    renderDialog();

    expect(showModal).toHaveBeenCalledTimes(1);
    const dialog = screen.getByRole("dialog", { name: "Delete Mountain loop?" });
    expect(dialog).toHaveAccessibleDescription("This permanently removes the trip and its route.");
    expect(screen.getByRole("button", { name: "Close dialog" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Delete trip" })).toBeEnabled();
  });

  it("routes explicit cancel and confirm controls to separate callbacks", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    renderDialog({ onCancel, onConfirm });

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Delete trip" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("honors the native cancel event unless a destructive action is pending", () => {
    const onCancel = vi.fn();
    const { rerender } = renderDialog({ onCancel });
    const dialog = screen.getByRole("dialog", { name: "Delete Mountain loop?" });

    const cancel = new Event("cancel", { bubbles: false, cancelable: true });
    fireEvent(dialog, cancel);
    expect(cancel.defaultPrevented).toBe(false);
    expect(onCancel).toHaveBeenCalledTimes(1);

    rerender(
      <ConfirmDialog
        open
        busy
        title="Delete Mountain loop?"
        description="This permanently removes the trip and its route."
        confirmLabel="Delete trip"
        onCancel={onCancel}
        onConfirm={vi.fn()}
      />,
    );
    const pendingCancel = new Event("cancel", { bubbles: false, cancelable: true });
    fireEvent(dialog, pendingCancel);
    expect(pendingCancel.defaultPrevented).toBe(true);
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("locks every exit while busy and announces a destructive failure", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();
    renderDialog({ busy: true, error: "The trip could not be deleted.", onCancel, onConfirm });

    expect(screen.getByRole("alert")).toHaveTextContent("The trip could not be deleted.");
    expect(screen.getByRole("button", { name: "Close dialog" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deleting…" })).toBeDisabled();
    expect(onCancel).not.toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("closes the native dialog when controlled state becomes false", () => {
    const { props, rerender } = renderDialog();
    rerender(<ConfirmDialog {...props} open={false} />);

    expect(close).toHaveBeenCalledTimes(1);
  });
});
