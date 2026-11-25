/**
 * Context-aware Shortcut Manager for Desktop UI.
 *
 * Implements Step 7.3:
 * Keys 1-5 and Delete fire strictly in POOL context, never inside INPUT, MODAL, or STUDIO.
 */

export type ShortcutContext = "POOL" | "STUDIO" | "MODAL" | "INPUT";

interface ShortcutHandlers {
  onSlotAssign?: (slotIndex: number) => void;
  onDelete?: () => void;
  onEscape?: () => void;
  onSave?: () => void;
}

export class ShortcutManager {
  private currentContext: ShortcutContext = "POOL";
  private handlers: ShortcutHandlers = {};
  private target: EventTarget | null = null;
  private boundListener: (e: KeyboardEvent) => void;

  constructor(handlers: ShortcutHandlers = {}, target?: EventTarget | null) {
    this.handlers = handlers;
    this.target = target !== undefined ? target : (typeof window !== "undefined" ? window : null);
    this.boundListener = this.handleKeyDown.bind(this);
  }

  public setContext(context: ShortcutContext): void {
    this.currentContext = context;
  }

  public getContext(): ShortcutContext {
    return this.currentContext;
  }

  public setHandlers(handlers: ShortcutHandlers): void {
    this.handlers = handlers;
  }

  public attach(): () => void {
    if (this.target) {
      this.target.addEventListener("keydown", this.boundListener as EventListener);
    }
    return () => this.detach();
  }

  public detach(): void {
    if (this.target) {
      this.target.removeEventListener("keydown", this.boundListener as EventListener);
    }
  }

  private handleKeyDown(e: KeyboardEvent): void {
    // 1. Detect if target is editable form element
    const target = e.target as HTMLElement | null;
    const isInput =
      target &&
      (target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" ||
        target.isContentEditable);

    if (isInput) {
      if (e.key === "Escape") {
        this.handlers.onEscape?.();
      }
      return; // Do not intercept typing inside form inputs!
    }

    // 2. Global Save shortcut (Ctrl+S / Cmd+S)
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      this.handlers.onSave?.();
      return;
    }

    // 3. Modal / Studio Esc handling
    if (e.key === "Escape") {
      this.handlers.onEscape?.();
      return;
    }

    // 4. Strict POOL Context shortcuts (1-5 for slot assignments, Delete for removal)
    if (this.currentContext === "POOL") {
      if (["1", "2", "3", "4", "5"].includes(e.key)) {
        e.preventDefault();
        const slotIdx = parseInt(e.key, 10);
        this.handlers.onSlotAssign?.(slotIdx);
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        this.handlers.onDelete?.();
      }
    }
  }
}
