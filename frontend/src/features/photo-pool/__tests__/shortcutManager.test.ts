import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ShortcutManager } from "../ShortcutManager";

describe("ShortcutManager", () => {
  let manager: ShortcutManager;
  let target: EventTarget;
  let slotAssignMock: (slot: number) => void;
  let deleteMock: () => void;
  let escapeMock: () => void;
  let saveMock: () => void;
  let cleanup: () => void;

  function dispatchKey(key: string, options: Partial<KeyboardEventInit & { target: unknown }> = {}) {
    const event = new CustomEvent("keydown", {
      bubbles: true,
      cancelable: true,
    }) as unknown as KeyboardEvent;

    Object.defineProperty(event, "key", { value: key, enumerable: true });
    Object.defineProperty(event, "ctrlKey", {
      value: Boolean(options.ctrlKey),
      enumerable: true,
    });
    Object.defineProperty(event, "metaKey", {
      value: Boolean(options.metaKey),
      enumerable: true,
    });
    if (options.target) {
      Object.defineProperty(event, "target", {
        value: options.target,
        enumerable: true,
      });
    }

    target.dispatchEvent(event as unknown as Event);
  }

  beforeEach(() => {
    target = new EventTarget();
    slotAssignMock = vi.fn();
    deleteMock = vi.fn();
    escapeMock = vi.fn();
    saveMock = vi.fn();

    manager = new ShortcutManager(
      {
        onSlotAssign: slotAssignMock,
        onDelete: deleteMock,
        onEscape: escapeMock,
        onSave: saveMock,
      },
      target
    );
    cleanup = manager.attach();
  });

  afterEach(() => {
    cleanup();
  });

  it("handles slot assignment 1-5 in POOL context", () => {
    manager.setContext("POOL");

    dispatchKey("1");
    expect(slotAssignMock).toHaveBeenCalledWith(1);

    dispatchKey("3");
    expect(slotAssignMock).toHaveBeenCalledWith(3);

    dispatchKey("5");
    expect(slotAssignMock).toHaveBeenCalledWith(5);
  });

  it("handles Delete and Backspace in POOL context", () => {
    manager.setContext("POOL");

    dispatchKey("Delete");
    expect(deleteMock).toHaveBeenCalledTimes(1);

    dispatchKey("Backspace");
    expect(deleteMock).toHaveBeenCalledTimes(2);
  });

  it("does NOT trigger slot assignment or delete in STUDIO context", () => {
    manager.setContext("STUDIO");

    dispatchKey("1");
    expect(slotAssignMock).not.toHaveBeenCalled();

    dispatchKey("Delete");
    expect(deleteMock).not.toHaveBeenCalled();
  });

  it("does NOT intercept keys when typing inside an INPUT or TEXTAREA", () => {
    manager.setContext("POOL");

    const fakeInput = { tagName: "INPUT" } as unknown as HTMLElement;
    dispatchKey("1", { target: fakeInput });

    expect(slotAssignMock).not.toHaveBeenCalled();
  });

  it("handles global Ctrl+S / Cmd+S save shortcut", () => {
    dispatchKey("s", { ctrlKey: true });
    expect(saveMock).toHaveBeenCalledTimes(1);

    dispatchKey("s", { metaKey: true });
    expect(saveMock).toHaveBeenCalledTimes(2);
  });

  it("handles Escape in any context", () => {
    manager.setContext("STUDIO");
    dispatchKey("Escape");
    expect(escapeMock).toHaveBeenCalledTimes(1);
  });
});
